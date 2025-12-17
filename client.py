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

API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not API_KEY: print("❌ GEMINI_API_KEY 없음")

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

    print(f"🔌 연결 중... (모델: {MODEL_NAME})")

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

            print("\n✅ 준비 완료! (예: monitor all 5 60)")

            while True:
                user_input = input("🗣️ 나: ")
                if user_input.lower() in ['q', 'exit']: break
                if not user_input.strip(): continue

                if user_input.startswith("monitor"):
                    try:
                        parts = user_input.split()
                        if len(parts) < 4:
                            print("⚠️ 형식: monitor [키워드] [댓글수] [초단위간격]")
                            continue
                            
                        keyword = parts[1]
                        min_comments = int(parts[2])
                        interval = int(parts[3])
                        
                        print(f"🕵️‍♂️ [AI 감시] '{keyword}' OR 댓글 {min_comments}개+")
                        seen_links = set()

                        while True:
                            print(f"\n⏰ 스캔 중... ({time.strftime('%H:%M:%S')})")
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
                                date_text = item.get("date_text", "")
                                
                                if link in seen_links: continue

                                is_today = False
                                if any(x in date_text for x in ["방금", "분", "시간", "초"]): is_today = True
                                elif ":" in date_text or today_str in date_text: is_today = True
                                elif not date_text: is_today = True

                                if not is_today: continue 

                                is_hit = False
                                if keyword != "all" and keyword in title: is_hit = True
                                if comments >= min_comments: is_hit = True

                                if is_hit:
                                    print(f"  🔍 분석 중: {title} (💬{comments})")
                                    
                                    detail = await session.call_tool("fetch_post_detail", arguments={"url": link, "content_selector": "AUTO"})
                                    body_text = detail.content[0].text

                                    # 🔥 [핵심 수정] 프롬프트를 더 유연하게 변경
                                    prompt = f"""
                                    너는 핫딜 판독기야. 아래 텍스트는 게시글의 내용이야 (댓글이 포함되어 있을 수도 있고, 본문만 있을 수도 있어).
                                    이 내용을 읽고 사람들이 좋아하는 '핫딜'인지 판단해.

                                    [분석 대상 텍스트]
                                    {body_text[:4000]}
                                    
                                    [판단 기준]
                                    1. 긍정적 단어('싸다', '탑승', '구매완료', '좋네요', '감사')가 보이거나 가격 메리트가 있어 보이면 POSITIVE.
                                    2. 부정적 단어('비싸다', '별로', '품절', '바이럴')가 보이면 NEGATIVE.
                                    3. 명확한 댓글이 없더라도 가격이나 구성이 좋아 보이면 POSITIVE로 판단해도 됨.
                                    4. 도저히 판단 불가일 때만 UNKNOWN.
                                    
                                    답변(JSON): {{"judgment": "POSITIVE/NEGATIVE/UNKNOWN", "reason": "한줄요약"}}
                                    """
                                    
                                    try:
                                        ai_res = chat.send_message(prompt)
                                        raw_json = ai_res.text.replace("```json","").replace("```","").strip()
                                        ai_json = json.loads(raw_json)
                                        
                                        if ai_json["judgment"] == "POSITIVE":
                                            msg = f"🔥 [핫딜/💬{comments}개]\n제목: {title}\n이유: {ai_json['reason']}\n링크: {link}"
                                            send_telegram(msg)
                                            print("  ✅ 알림 전송!")
                                        elif ai_json["judgment"] == "UNKNOWN":
                                            print(f"  ❓ 판단 보류: {ai_json['reason']}")
                                        else:
                                            print(f"  ⛔ 탈락: {ai_json['reason']}")
                                    except:
                                        # 에러 나면 일단 알림 보내보는 전략
                                        send_telegram(f"⚠️ [분석에러/💬{comments}] {title}\n{link}")

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
