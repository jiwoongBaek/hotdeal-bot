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
MODEL_NAME = 'models/gemini-2.5-flash' # 가성비 모델

# --- 🤖 텔레그램 함수 ---
def send_telegram(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("⚠️ 텔레그램 설정이 없습니다. (콘솔 출력만 함)")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, data=data, timeout=5)
    except Exception as e:
        print(f"텔레그램 전송 실패: {e}")

# --- 🚀 메인 로직 ---
async def main():
    server_params = StdioServerParameters(
        command="docker",
        args=[
            "run", "-i", "--rm", 
            "-v", f"{os.getcwd()}/data:/data", 
            "mcp-hotdeal"
        ],
        env=None
    )

    print(f"🔌 Omni-Analyst 연결 중... (모델: {MODEL_NAME})")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # 도구 정의 (Gemini용)
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

            print("\n✅ 시스템 준비 완료! (monitor 명령어 사용 가능)")
            print("예) monitor 핫딜 햇반 10 60")

            while True:
                user_input = input("🗣️ 나: ")
                if user_input.lower() in ['q', 'exit']: break
                if not user_input.strip(): continue

                # 🚨 [스마트 감시 모드]
                if user_input.startswith("monitor"):
                    try:
                        parts = user_input.split()
                        env_name = parts[1]
                        keyword = parts[2]
                        min_comments = int(parts[3])
                        interval = int(parts[4])
                        
                        print(f"🕵️‍♂️ [AI 감시] '{keyword}' OR 댓글 {min_comments}개+ (오늘 게시글만)")
                        seen_links = set()

                        while True:
                            print(f"\n⏰ 스캔 중... ({time.strftime('%H:%M:%S')})")
                            res = await session.call_tool("fetch_board_items", arguments={"env_name": env_name})
                            try:
                                items = json.loads(res.content[0].text)
                            except:
                                time.sleep(interval); continue

                            if isinstance(items, dict) and "error" in items:
                                print(f"❌ {items['error']}"); break

                            # 오늘 날짜 문자열 (예: 11/26)
                            today_str = datetime.now().strftime("%m/%d")

                            for item in items:
                                title = item.get("title", "")
                                link = item.get("link", "")
                                comments = item.get("comments", 0)
                                site = item.get("site", "")
                                date_text = item.get("date_text", "")
                                content_sel = item.get("content_selector", "")
                                
                                if link in seen_links: continue

                                # 1. 📅 날짜 필터 (오늘 글인가?)
                                is_today = False
                                # 시간이 적혀있으면(:) 오늘 글임. 혹은 오늘 날짜가 포함되어 있으면 통과.
                                if ":" in date_text or today_str in date_text:
                                    is_today = True
                                if not date_text: is_today = True # 날짜 없으면 안전하게 통과

                                if not is_today: continue 

                                # 2. 조건 필터
                                is_hit = False
                                if keyword != "all" and keyword in title: is_hit = True
                                if comments >= min_comments: is_hit = True

                                if is_hit:
                                    print(f"  🔍 분석 중: {title} (💬{comments}/📅{date_text})")
                                    
                                    # 3. AI 댓글 여론 분석
                                    detail = await session.call_tool("fetch_post_detail", arguments={"url": link, "content_selector": content_sel})
                                    comments_body = detail.content[0].text

                                    prompt = f"""
                                    너는 핫딜 판독기야. 아래 댓글들을 보고 살 만한 딜인지 판단해.
                                    [댓글들]
                                    {comments_body}
                                    
                                    [판단기준]
                                    - POSITIVE: 가격 저렴, 구매 완료, 칭찬 등
                                    - NEGATIVE: 비쌈, 품절, 별로임, 바이럴 등
                                    
                                    답변(JSON): {{"judgment": "POSITIVE/NEGATIVE", "reason": "한줄요약"}}
                                    """
                                    
                                    try:
                                        ai_res = chat.send_message(prompt)
                                        ai_json = json.loads(ai_res.text.replace("```json","").replace("```","").strip())
                                        
                                        if ai_json["judgment"] == "POSITIVE":
                                            msg = f"🔥 [핫딜/💬{comments}개]\n사이트: {site}\n제목: {title}\n반응: {ai_json['reason']}\n링크: {link}"
                                            send_telegram(msg)
                                            print("  ✅ 알림 전송!")
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

                # 일반 대화 처리
                try:
                    resp = chat.send_message(user_input)
                    part = resp.candidates[0].content.parts[0]
                    if part.function_call:
                        fc = part.function_call
                        res = await session.call_tool(fc.name, arguments=dict(fc.args))
                        from google.ai.generativelanguage_v1beta.types import content
                        f_resp = content.Part(function_response=content.FunctionResponse(name=fc.name, response={"result": res.content[0].text}))
                        final = chat.send_message([f_resp])
                        print(f"🤖: {final.text}")
                    else:
                        print(f"🤖: {part.text}")
                except Exception as e:
                    print(f"❌ 대화 에러: {e}")

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("\n👋 종료합니다.")