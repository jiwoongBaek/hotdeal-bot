import asyncio
import os
import time
import json
import requests
from datetime import datetime
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import google.generativeai as genai
from google.generativeai.types import Tool, FunctionDeclaration

# --- 🔐 환경 변수 ---
API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not API_KEY:
    print("❌ 경고: GEMINI_API_KEY가 없습니다.")

genai.configure(api_key=API_KEY)
MODEL_NAME = 'models/gemini-2.5-flash' 

def send_telegram(message):
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    try: requests.post(url, data=data, timeout=5)
    except: pass

async def main():
    server_params = StdioServerParameters(
        command="docker",
        args=["run", "-i", "--rm", "-v", f"{os.getcwd()}/data:/data", "mcp-hotdeal"],
        env=None
    )

    print(f"🔌 Omni-Analyst 연결 중... (모델: {MODEL_NAME})")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            tools_list = await session.list_tools()
            gemini_tools = []
            for tool in tools_list.tools:
                props = {k: {"type": "STRING"} for k in tool.inputSchema.get("properties", {})}
                gemini_tools.append(Tool(function_declarations=[FunctionDeclaration(
                    name=tool.name, description=tool.description, 
                    parameters={"type": "OBJECT", "properties": props}
                )]))

            model = genai.GenerativeModel(model_name=MODEL_NAME, tools=gemini_tools)
            chat = model.start_chat(enable_automatic_function_calling=False)

            print("\n✅ 준비 완료! 이제 'monitor' 뒤에 환경 이름 없이 바로 입력하세요.")
            print("예) monitor all 5 60  (키워드 'all', 댓글 5개 이상, 60초 간격)")

            while True:
                user_input = input("🗣️ 나: ")
                if user_input.lower() in ['q', 'exit']: break
                if not user_input.strip(): continue

                if user_input.startswith("monitor"):
                    try:
                        parts = user_input.split()
                        # [변경점] parts[1]이 바로 키워드가 됩니다. (환경 이름 삭제)
                        if len(parts) < 4:
                            print("⚠️ 형식: monitor [키워드] [댓글수] [초단위간격]")
                            continue
                            
                        keyword = parts[1]
                        min_comments = int(parts[2])
                        interval = int(parts[3])
                        
                        print(f"🕵️‍♂️ [AI 감시] '{keyword}' OR 댓글 {min_comments}개+ (오늘 게시글만)")
                        seen_links = set()

                        while True:
                            print(f"\n⏰ 스캔 중... ({time.strftime('%H:%M:%S')})")
                            # fetch_board_items 호출 시 env_name은 더미값('algumon') 전달
                            res = await session.call_tool("fetch_board_items", arguments={"env_name": "algumon"})
                            try:
                                items = json.loads(res.content[0].text)
                            except:
                                time.sleep(interval); continue

                            if isinstance(items, dict) and "error" in items:
                                print(f"❌ {items['error']}"); break

                            today_str = datetime.now().strftime("%m/%d")

                            for item in items:
                                title = item.get("title", "")
                                link = item.get("link", "")
                                comments = item.get("comments", 0)
                                site = item.get("site", "")
                                date_text = item.get("date_text", "")
                                content_sel = item.get("content_selector", "")
                                
                                if link in seen_links: continue

                                # 날짜 필터
                                is_today = False
                                if any(x in date_text for x in ["방금", "분", "시간", "초"]): is_today = True
                                elif ":" in date_text or today_str in date_text: is_today = True
                                elif not date_text: is_today = True

                                if not is_today: continue 

                                # 조건 필터
                                is_hit = False
                                if keyword != "all" and keyword in title: is_hit = True
                                if comments >= min_comments: is_hit = True

                                if is_hit:
                                    print(f"  🔍 분석 중: {title} (💬{comments}/📅{date_text})")
                                    
                                    # 상세 분석
                                    detail = await session.call_tool("fetch_post_detail", arguments={"url": link, "content_selector": content_sel})
                                    comments_body = detail.content[0].text

                                    prompt = f"""
                                    너는 핫딜 판독기야. 아래 내용을 보고 살 만한 딜인지 판단해.
                                    댓글이 없으면 '판단불가'라고 해.

                                    [수집된 내용]
                                    {comments_body}
                                    
                                    [판단기준]
                                    - POSITIVE: 가격 저렴, 구매 완료, 칭찬, '탑승' 등 긍정적 반응
                                    - NEGATIVE: 비쌈, 품절, 별로임, 바이럴 등 부정적 반응
                                    - UNKNOWN: 댓글이나 정보가 부족함
                                    
                                    답변(JSON): {{"judgment": "POSITIVE/NEGATIVE/UNKNOWN", "reason": "한줄요약"}}
                                    """
                                    
                                    try:
                                        ai_res = chat.send_message(prompt)
                                        # JSON 파싱 강화
                                        raw_json = ai_res.text.replace("```json","").replace("```","").strip()
                                        ai_json = json.loads(raw_json)
                                        
                                        if ai_json["judgment"] == "POSITIVE":
                                            msg = f"🔥 [핫딜/💬{comments}개]\n제목: {title}\n반응: {ai_json['reason']}\n링크: {link}"
                                            send_telegram(msg)
                                            print("  ✅ 알림 전송!")
                                        elif ai_json["judgment"] == "UNKNOWN":
                                            print(f"  ❓ 판단 보류: {ai_json['reason']}")
                                        else:
                                            print(f"  ⛔ 탈락: {ai_json['reason']}")
                                    except:
                                        send_telegram(f"⚠️ [분석실패/💬{comments}] {title}\n{link}")

                                    seen_links.add(link)
                            time.sleep(interval)

                    except KeyboardInterrupt:
                        print("\n🛑 감시 중단"); continue
                    except Exception as e:
                        print(f"⚠️ 에러: {e}"); continue

                try:
                    resp = chat.send_message(user_input)
                    print(f"🤖: {resp.text}")
                except: pass

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("\n👋 종료합니다.")
