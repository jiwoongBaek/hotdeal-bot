import asyncio
import os
import time
import json
import requests # 텔레그램용
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import google.generativeai as genai
from google.generativeai.types import Tool, FunctionDeclaration
from datetime import datetime

# --- 🔐 1. 보안 설정 (환경 변수에서 로드) ---
API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not API_KEY:
    print("❌ 경고: GEMINI_API_KEY가 설정되지 않았습니다.")

# Gemini 설정 (가성비 Flash 모델 사용)
genai.configure(api_key=API_KEY)
MODEL_NAME = 'models/gemini-2.5-flash' # 비용 절약을 위해 Flash 추천

# --- 🤖 텔레그램 전송 함수 ---
def send_telegram(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("⚠️ 텔레그램 설정이 없어 알림을 보낼 수 없습니다 (콘솔 출력만 함).")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, data=data, timeout=5)
    except Exception as e:
        print(f"텔레그램 전송 실패: {e}")

# --- 🚀 메인 로직 ---
async def main():
    # 2. 도커 실행 설정 (데이터 볼륨 마운트 필수!)
    server_params = StdioServerParameters(
        command="docker",
        args=[
            "run", 
            "-i", 
            "--rm", 
            "-v", f"{os.getcwd()}/data:/data", # 설정 DB 영구 저장
            "mcp-hotdeal" # 이미지 이름
        ],
        env=None
    )

    print(f"🔌 Docker(Omni-Analyst)에 연결 중... (모델: {MODEL_NAME})")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            
            # 3. 도구 초기화
            await session.initialize()
            tools_list = await session.list_tools()
            
            # Gemini에게 알려줄 도구 목록 변환
            gemini_tools = []
            for tool in tools_list.tools:
                props = {}
                required = []
                for prop_name in tool.inputSchema.get("properties", {}):
                    props[prop_name] = {"type": "STRING"}
                    required.append(prop_name)

                gemini_tools.append(
                    Tool(function_declarations=[
                        FunctionDeclaration(
                            name=tool.name,
                            description=tool.description,
                            parameters={"type": "OBJECT", "properties": props, "required": required}
                        )
                    ])
                )

            model = genai.GenerativeModel(model_name=MODEL_NAME, tools=gemini_tools)
            chat = model.start_chat(enable_automatic_function_calling=False)

            print("\n✅ 시스템 준비 완료!")
            print("💡 사용법:")
            print("  1. 설정: '핫딜 환경 만들어줘', '뽐뿌 사이트 추가해줘'")
            print("  2. 감시: monitor [환경] [키워드] [최소댓글] [초]")
            print("     예) monitor 핫딜 햇반 10 60")
            print("     예) monitor 핫딜 all 15 30 (키워드 없이 댓글 15개 이상만)")
            print("🚪 종료: q\n")

            # 4. 무한 대화 루프
            while True:
                user_input = input("🗣️ 나: ")
                if user_input.lower() in ['q', 'exit']:
                    print("시스템 종료 👋")
                    break
                
                if not user_input.strip(): continue

                # 🚨 [스마트 감시 모드]
                # ... (monitor 명령어 처리 부분) ...
                if user_input.startswith("monitor"):
                    try:
                        parts = user_input.split()
                        if len(parts) < 5:
                            print("⚠️ 사용법: monitor [환경] [키워드] [최소댓글] [초]")
                            continue
                        env_name = parts[1]
                        keyword = parts[2]
                        min_comments = int(parts[3])
                        interval = int(parts[4])
                    except (IndexError, ValueError):
                        print("⚠️ 입력 오류: monitor [환경] [키워드] [최소댓글] [초]")
                        continue

                    try:
                        print(f"🕵️‍♂️ [AI 감시] 오늘 올라온 글 중 '{keyword}' OR 댓글 {min_comments}개 이상 (댓글 여론 분석)")
                        seen_links = set()

                        while True:
                            print(f"\n⏰ 스캔 중... ({time.strftime('%H:%M:%S')})")
                            result = await session.call_tool("fetch_board_items", arguments={"env_name": env_name})
                            try:
                                items = json.loads(result.content[0].text)
                            except:
                                time.sleep(interval)
                                continue

                            if isinstance(items, dict) and "error" in items:
                                print(f"❌ {items['error']}")
                                break
                            
                            # 오늘 날짜 구하기 (MM/DD 또는 MM-DD 형식 매칭용)
                            today_str = datetime.now().strftime("%m/%d") # 예: 11/26
                            today_str_2 = datetime.now().strftime("%m-%d")

                            for item in items:
                                title = item.get("title", "")
                                link = item.get("link", "")
                                comments = item.get("comments", 0)
                                site = item.get("site", "")
                                date_text = item.get("date_text", "") # 가져온 날짜
                                content_sel = item.get("content_selector", "") # 댓글 선택자
                                
                                if link in seen_links: continue

                                # 1. 📅 [날짜 필터] 오늘 올라온 글인가?
                                # 보통 오늘 글은 시간(14:30)으로 표시되거나, 오늘 날짜(11/26)가 적혀있음
                                is_today = False
                                if ":" in date_text: # 시간이 있으면 오늘임
                                    is_today = True
                                elif today_str in date_text or today_str_2 in date_text:
                                    is_today = True
                                
                                # 날짜 정보가 없으면(못 찾았으면) 일단 통과시킴 (놓치는 것보단 나으니)
                                if not date_text: is_today = True 

                                if not is_today:
                                    continue # 오늘 글 아니면 패스

                                # 2. [조건 필터] 키워드 or 댓글 수
                                is_candidate = False
                                if keyword != "all" and keyword in title: is_candidate = True
                                if comments >= min_comments: is_candidate = True

                                if is_candidate:
                                    print(f"  🔍 [1차 통과] {title} ({comments}플/날짜:{date_text}) -> 댓글 여론 분석 중...")
                                    
                                    # 3. [AI 분석] 댓글 긁어와서 분석
                                    detail_res = await session.call_tool("fetch_post_detail", arguments={"url": link, "content_selector": content_sel})
                                    comments_body = detail_res.content[0].text

                                    prompt = f"""
                                    너는 핫딜 판독기야. 아래는 게시글에 달린 '댓글들'이다.
                                    댓글 반응을 보고 진짜 살 만한 핫딜인지 판단해줘.
                                    
                                    [판단 기준]
                                    - POSITIVE: "가격 좋다", "샀다", "고맙다", "역대가" 등 긍정적 반응 다수.
                                    - NEGATIVE: "비싸다", "별로다", "품절", "바이럴", "망했다" 등 부정적 반응 다수.
                                    
                                    [댓글 내용]
                                    {comments_body}
                                    
                                    답변은 오직 JSON으로: {{"judgment": "POSITIVE/NEGATIVE", "reason": "한 줄 요약"}}
                                    """
                                    
                                    try:
                                        ai_resp = chat.send_message(prompt)
                                        ai_text = ai_resp.text.replace("```json", "").replace("```", "").strip()
                                        analysis = json.loads(ai_text)
                                        
                                        # 텔레그램 메시지에 댓글 수(comments) 포함
                                        if analysis["judgment"] == "POSITIVE":
                                            msg = f"🔥 [핫딜/💬{comments}개]\n사이트: {site}\n제목: {title}\n반응: {analysis['reason']}\n링크: {link}"
                                            print(f"  ✅ [알림 전송] {title}")
                                            send_telegram(msg)
                                        else:
                                            print(f"  ⛔ [탈락] {analysis['reason']}")

                                    except Exception as e:
                                        print(f"  ⚠️ 분석 에러(일단 전송): {e}")
                                        send_telegram(f"⚠️ [분석실패/💬{comments}개] {title}\n{link}")

                                    seen_links.add(link)

                            time.sleep(interval)

                    except KeyboardInterrupt:
                        print("\n🛑 감시 모드 종료. 대화 모드로 복귀합니다.")
                        continue
                    except Exception as e:
                        print(f"⚠️ 에러 발생: {e}")
                        continue

                # 💬 [일반 대화 모드 (Gemini)]
                try:
                    response = chat.send_message(user_input)
                    part = response.candidates[0].content.parts[0]

                    # 도구 사용 요청 처리
                    if part.function_call:
                        fc = part.function_call
                        print(f"  ⚙️ 도구 실행: {fc.name}...")
                        
                        result = await session.call_tool(fc.name, arguments=dict(fc.args))
                        
                        # 결과 반환
                        from google.ai.generativelanguage_v1beta.types import content
                        func_resp = content.Part(
                            function_response=content.FunctionResponse(
                                name=fc.name, response={"result": result.content[0].text}
                            )
                        )
                        final_res = chat.send_message([func_resp])
                        print(f"🤖 분석가: {final_res.text}\n")
                    else:
                        print(f"🤖 분석가: {part.text}\n")
                        
                except Exception as e:
                    print(f"❌ 대화 에러: {e}")

if __name__ == "__main__":
    asyncio.run(main())