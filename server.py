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
    # DB 관련 코드는 에러 방지용으로 남겨둡니다.
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
    """알구몬 전용 파서 (날짜 자동 변환 기능 포함)"""
    print(f"🔍 [알구몬] 데이터 수집 시작...")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        resp = requests.get(ALGUMON_URL, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        all_items = []
        today_str = datetime.now().strftime("%m/%d") # 예: "12/17"
        
        # .product-body 클래스를 가진 모든 요소를 찾음 (가장 확실한 방법)
        products = soup.select(".product-body")
        
        for post in products[:25]:
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

                # 3. 날짜 (여기가 핵심!)
                # "22분 전" 같은 텍스트 찾기
                date_tag = post.select_one(".created-at")
                raw_date = ""
                if date_tag:
                    raw_date = date_tag.get_text(strip=True)
                else:
                    # created-at이 없으면 메타 정보에서 찾기
                    meta_tag = post.select_one(".deal-price-meta-info")
                    if meta_tag:
                        raw_date = meta_tag.get_text(strip=True)

                # 🔥 [날짜 변환 마법]
                # '전'이나 '방금'이 있으면 오늘 날짜를 강제로 붙여줌
                if any(x in raw_date for x in ["방금", "분 전", "시간 전", "초 전"]):
                    item["date_text"] = f"{today_str} ({raw_date})"
                else:
                    item["date_text"] = raw_date

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
        
        # 댓글 영역 긁기
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
