import asyncio
import os
import time
import json
import requests
import traceback
from datetime import datetime
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import google.generativeai as genai
from google.generativeai.types import Tool, FunctionDeclaration

# --- 🔐 환경 변수 ---
API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# --- 💾 영구 기억 저장소 설정 ---
# 도커 볼륨(/data)에 저장하여 재부팅 후에도 기억 유지
DATA_DIR = "/data"
SEEN_FILE = os.path.join(DATA_DIR, "seen_links.json")

if not API_KEY:
    print("❌ 경고: GEMINI_API_KEY가 없습니다.")

genai.configure(api_key=API_KEY)
MODEL_NAME = 'models/gemini-2.5-flash' 

# --- 🛠️ 헬퍼 함수들 ---
def send_telegram(message):
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": message}
        requests.post(url, data=data, timeout=5)
    except Exception as e:
        print(f"⚠️ 텔레그램 전송 실패: {e}")

def load_seen_links():
    """파일에서 이미 본 링크 목록을 불러옵니다."""
    if not os.path.exists(SEEN_FILE):
        return set()
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data) # 리스트를 집합(set)으로 변환
    except Exception as e:
        print(f"⚠️ 기억 불러오기 실패: {e}")
        return set()

def save_seen_link(link):
    """새로운 링크를 파일에 추가합니다."""
    try:
        # 1. 기존 데이터 로드
        current_links = load_seen_links()
        current_links.add(link)
        
        # 2. 너무 많이 쌓이면 오래된 것 삭제 (최근 2000개만 유지)
        # (알구몬 글 리젠 속도 고려 시 2000개면 며칠 분량)
        links_list = list(current_links)
        if len(links_list) > 2000:
            links_list = links_list[-2000:]
            
        # 3. 저장
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(links_list, f, ensure_ascii=False)
            
    except Exception as e:
        print(f"⚠️ 기억 저장 실패: {e}")

# --- 🚀 메인 로직 ---
async def main():
    server_params = StdioServerParameters(
        command="docker",
        args=["run", "-i", "--rm", "-v", f"{os.getcwd()}/data:/data", "mcp-hotdeal"],
        env=None
    )

    print(f"🔌 Omni-Analyst 연결 중... (기억 파일: {SEEN_FILE})")

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
            
            # 시작할 때 기억 불러오기
            seen_links = load_seen_links()
            print(f"🧠 기억 복원 완료: {len(seen_links)}개의 과거 핫딜을 알고 있습니다.")

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
                        
                        # 감시 시작 전 한 번 더 최신 상태 로드
                        seen_links = load_seen_links()

                        while True:
                            print(f"\n⏰ 스캔 중... ({time.strftime('%H:%M:%S')})")
                            res = await session.call_tool("fetch_board_items", arguments={"env_name": "algumon"})
                            
                            try:
                                items = json.loads(res.content[0].text)
                            except:
                                print("⚠️ 파싱 대기")
                                time.sleep(interval); continue

                            if isinstance(items, dict) and "error" in items:
                                print(f"❌ {items['error']}"); break

                            today_str = datetime.now().strftime("%m/%d")

                            for item in items:
                                title = item.get("title", "")
                                raw_link = item.get("link", "")
                                
                                # 링크 꼬리 자르기 (?v=... 제거)
                                clean_link = raw_link.split('?')[0]
                                
                                comments = item.get("comments", 0)
                                date_text = item.get("date_text", "")
                                
                                # 🔥 이미 파일에 저장된 링크면 절대 통과 금지
                                if clean_link in seen_links: continue

                                # 날짜 필터
                                is_today = False
                                if any(x in date_text for x in ["방금", "분", "시간", "초"]): is_today = True
                                elif ":" in date_text or today_str in date_text: is_today = True
                                elif not date_text: is_today = True

                                if not is_today: continue 

                                # 조건 필터
                                is_hit = False
                                if keyword == "all" or keyword in title:
                                    if comments >= min_comments: is_hit = True

                                if is_hit:
                                    print(f"  🔍 분석 중: {title} (💬{comments})")
                                    
                                    detail = await session.call_tool("fetch_post_detail", arguments={"url": raw_link, "content_selector": "AUTO"})
                                    body_text = detail.content[0].text

                                    prompt = f"""
                                    너는 핫딜 판독기야. 아래 내용을 보고 '핫딜'인지 판단해.
                                    
                                    [분석 대상]
                                    {body_text[:4000]}
                                    
                                    [기준]
                                    1. 긍정 반응('싸다', '탑승', '감사', '좋음') or 가격 장점 = POSITIVE.
                                    2. 부정 반응('비싸다', '품절', '바이럴') = NEGATIVE.
                                    3. 반응 없어도 구성 좋으면 POSITIVE.
                                    
                                    답변(JSON): {{"judgment": "POSITIVE/NEGATIVE/UNKNOWN", "reason": "한줄요약"}}
                                    """
                                    
                                    try:
                                        ai_res = chat.send_message(prompt)
                                        raw_json = ai_res.text.replace("```json","").replace("```","").strip()
                                        ai_json = json.loads(raw_json)
                                        
                                        if ai_json["judgment"] == "POSITIVE":
                                            msg = f"🔥 [핫딜/💬{comments}개]\n제목: {title}\n이유: {ai_json['reason']}\n링크: {clean_link}"
                                            send_telegram(msg)
                                            print("  ✅ 알림 전송!")
                                        elif ai_json["judgment"] == "UNKNOWN":
                                            print(f"  ❓ 보류: {ai_json['reason']}")
                                        else:
                                            print(f"  ⛔ 탈락: {ai_json['reason']}")
                                            
                                    except Exception as e:
                                        send_telegram(f"⚠️ [분석에러/💬{comments}] {title}\n{clean_link}")
                                        print(f"  ⚠️ AI 에러: {e}")

                                    # 🔥 [중요] 분석 시도한 링크는 파일에 즉시 기록 (성공이든 실패든 다시 안 봄)
                                    seen_links.add(clean_link)
                                    save_seen_link(clean_link)
                            
                            time.sleep(interval)

                    except KeyboardInterrupt:
                        print("\n🛑 감시 중단")
                        continue
                    except Exception as e:
                        print(f"⚠️ 에러: {e}")
                        time.sleep(10)
                        continue

                try:
                    resp = chat.send_message(user_input)
                    print(f"🤖: {resp.text}")
                except: pass

if __name__ == "__main__":
    start_msg = f"🟢 [봇 시작] 시스템 가동 (재시작됨)\n시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    send_telegram(start_msg)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        send_telegram("🛑 [봇 종료] 사용자 종료")
    except Exception as e:
        error_trace = traceback.format_exc()
        error_msg = f"🚨 [비상] 봇 사망\n이유: {e}\n{error_trace[-500:]}"
        send_telegram(error_msg)
