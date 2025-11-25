import asyncio
import os
import time
import json
import requests # 텔레그램용
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import google.generativeai as genai
from google.generativeai.types import Tool, FunctionDeclaration

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
            print("  1. 설정: '핫딜 환경 만들어줘', '펨코 사이트 추가해줘'")
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
                        env_name = parts[1]
                        keyword = parts[2]
                        min_comments = int(parts[3])
                        interval = int(parts[4])
                        
                        print(f"🕵️‍♂️ [AI 감시 모드] 키워드: '{keyword}' OR 댓글: {min_comments}개+ (판독 후 알림)")
                        seen_links = set()

                        while True:
                            print(f"\n⏰ 스캔 중...")
                            result = await session.call_tool("fetch_board_items", arguments={"env_name": env_name})
                            try:
                                items = json.loads(result.content[0].text)
                            except:
                                time.sleep(interval)
                                continue

                            if isinstance(items, dict) and "error" in items:
                                print(f"❌ {items['error']}")
                                break

                            for item in items:
                                title = item.get("title", "")
                                link = item.get("link", "")
                                comments = item.get("comments", 0)
                                site = item.get("site", "")
                                content_sel = item.get("content_selector", "") # 본문 선택자
                                
                                if link in seen_links: continue

                                # 1차 필터: 키워드나 댓글 수 통과
                                is_candidate = False
                                if keyword != "all" and keyword in title: is_candidate = True
                                if comments >= min_comments: is_candidate = True

                                if is_candidate:
                                    print(f"  🔍 [1차 통과] {title} ({comments}플) -> AI 분석 시작...")
                                    
                                    # 2차 필터: AI 상세 분석 (fetch_post_detail 호출)
                                    detail_res = await session.call_tool("fetch_post_detail", arguments={"url": link, "content_selector": content_sel})
                                    post_body = detail_res.content[0].text

                                    # Gemini에게 판결 요청 (Structured Prompting)
                                    prompt = f"""
                                    너는 핫딜 판독기야. 아래 게시글 내용을 보고 '살 만한 핫딜(POSITIVE)'인지 '별로인 딜/품절/바이럴(NEGATIVE)'인지 판단해줘.
                                    
                                    [판단 기준]
                                    1. 긍정적: "가격 좋다", "탑승", "역대가", "감사합니다" 등의 반응이나 싼 가격.
                                    2. 부정적: "비싸다", "품절", "종료", "바이럴", "별로다" 등의 반응.
                                    3. 제목에 '{keyword}'가 있다면 가산점.
                                    
                                    [게시글 내용]
                                    제목: {title}
                                    본문내용: {post_body}
                                    
                                    답변은 오직 다음 JSON 형식으로만 줘:
                                    {{"judgment": "POSITIVE" 또는 "NEGATIVE", "reason": "한 줄 요약"}}
                                    """
                                    
                                    try:
                                        ai_resp = chat.send_message(prompt)
                                        ai_text = ai_resp.text.replace("```json", "").replace("```", "").strip()
                                        analysis = json.loads(ai_text)
                                        
                                        if analysis["judgment"] == "POSITIVE":
                                            msg = f"🔥 [AI 추천 핫딜]\n사이트: {site}\n제목: {title}\n이유: {analysis['reason']}\n링크: {link}"
                                            print(f"  ✅ [합격] 알림 전송!")
                                            send_telegram(msg)
                                        else:
                                            print(f"  ⛔ [탈락] {analysis['reason']}")

                                    except Exception as e:
                                        print(f"  ⚠️ AI 분석 에러: {e}")
                                        # 에러나면 안전하게 그냥 알림 보냄 (놓치는 것보단 나으니)
                                        send_telegram(f"⚠️ [분석실패/핫딜추정] {title}\n{link}")

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