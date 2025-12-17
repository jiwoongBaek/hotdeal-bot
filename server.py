from mcp.server.fastmcp import FastMCP
import sqlite3
import requests
from bs4 import BeautifulSoup
import json
import os
import re
from urllib.parse import urljoin
from datetime import datetime

# 알구몬 주소
ALGUMON_URL = "https://algumon.com"
DB_PATH = "/data/config.db"
mcp = FastMCP("OmniAnalyst")

def init_db():
    os.makedirs("/data", exist_ok=True)
    # DB 관련 코드는 호환성을 위해 유지
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS environments (name TEXT PRIMARY KEY, description TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS sites (id INTEGER PRIMARY KEY, env_name TEXT, site_name TEXT)')
    conn.close()

init_db()

@mcp.tool()
def create_environment(name: str, description: str = "") -> str:
    return "✅ 알구몬 전용 모드입니다."

@mcp.tool()
def add_board_to_env(env_name: str, site_name: str, board_url: str, title_selector: str, comment_selector: str, content_selector: str, date_selector: str, link_selector: str = "") -> str:
    return "✅ 알구몬 전용 모드라 설정이 필요 없습니다."

@mcp.tool()
def fetch_board_items(env_name: str) -> str:
    """알구몬 전용 파서 (날짜 정제 기능 강화)"""
    print(f"🔍 [알구몬] 데이터 수집 시작...")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        resp = requests.get(ALGUMON_URL, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        all_items = []
        today_str = datetime.now().strftime("%m/%d") # 예: "12/17"
        
        # .product-body 클래스를 가진 모든 요소 스캔
        products = soup.select(".product-body")
        
        for post in products[:25]: # 상위 25개만
            try:
                item = {
                    "site": "알구몬",
                    "title": "",
                    "comments": 0,
                    "link": "",
                    "date_text": "",
                    "content_selector": ".post-content"
                }

                # 1. 제목 & 링크
                title_tag = post.select_one(".deal-title .item-name a")
                if title_tag:
                    item["title"] = title_tag.get_text(strip=True)
                    item["link"] = urljoin(ALGUMON_URL, title_tag.get('href'))
                else:
                    continue

                # 2. 댓글 수 (아이콘 옆 숫자 찾기)
                comment_icon = post.select_one(".icon-commenting-o")
                if comment_icon:
                    cmt_text = comment_icon.parent.get_text(strip=True)
                    nums = re.findall(r'\d+', cmt_text)
                    if nums:
                        item["comments"] = int(nums[0])

                # 3. 날짜 (여기가 핵심 개선 포인트!)
                raw_text = ""
                
                # (A) .created-at 태그가 있으면 최우선
                date_tag = post.select_one(".created-at")
                if date_tag:
                    raw_text = date_tag.get_text(strip=True)
                else:
                    # (B) 없으면 메타 정보 전체에서 찾기
                    meta_tag = post.select_one(".deal-price-meta-info")
                    if meta_tag:
                        raw_text = meta_tag.get_text(strip=True) # 여기에 배송비 등 잡동사니가 섞여 있음

                # 🔥 [날짜 정제 마법] 정규식으로 시간 패턴만 추출
                # 예: "35분 전", "1시간 전", "방금", "12-17" 등을 찾음
                clean_date = ""
                time_match = re.search(r'(\d+분\s*전|\d+시간\s*전|방금|\d+초\s*전|\d{2}-\d{2}|\d{2}/\d{2})', raw_text)
                
                if time_match:
                    clean_date = time_match.group(1)
                else:
                    # 정규식 실패 시, 텍스트의 맨 마지막 단어를 가져옴 (보통 날짜가 끝에 있음)
                    parts = raw_text.split()
                    if parts: clean_date = parts[-1]

                # 최종 날짜 포맷팅
                if any(x in clean_date for x in ["방금", "분", "시간", "초"]):
                    item["date_text"] = f"{today_str} ({clean_date})"
                else:
                    item["date_text"] = clean_date

                all_items.append(item)

            except Exception as e:
                continue

        print(f"✅ 수집 완료: {len(all_items)}개 (알구몬)")
        return json.dumps(all_items, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": f"알구몬 접속 실패: {e}"}, ensure_ascii=False)

@mcp.tool()
def fetch_post_detail(url: str, content_selector: str) -> str:
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        elements = soup.select(".post-content")
        if not elements:
            elements = soup.select(".comment-list")
            
        content = "\n".join([f"- {el.get_text(strip=True)[:200]}" for el in elements])
        if not content: return "내용 없음"
        return content[:3000]
    except Exception as e:
        return f"실패: {e}"

if __name__ == "__main__":
    mcp.run()
