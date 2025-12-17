from mcp.server.fastmcp import FastMCP
import sqlite3
import requests
from bs4 import BeautifulSoup
import json
import os
import re
from urllib.parse import urljoin

# 알구몬 주소 (고정)
ALGUMON_URL = "https://algumon.com"

DB_PATH = "/data/config.db"
mcp = FastMCP("OmniAnalyst")

# --- 🛠️ 초기화 (DB는 에러 방지용으로 살려둠) ---
def init_db():
    os.makedirs("/data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS environments (name TEXT PRIMARY KEY, description TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS sites (id INTEGER PRIMARY KEY, env_name TEXT, site_name TEXT)')
    conn.commit()
    conn.close()

init_db()

@mcp.tool()
def create_environment(name: str, description: str = "") -> str:
    return f"✅ 환경 '{name}' 설정됨 (알구몬 전용 모드)"

@mcp.tool()
def add_board_to_env(env_name: str, site_name: str, board_url: str, title_selector: str, comment_selector: str, content_selector: str, date_selector: str, link_selector: str = "") -> str:
    return "✅ (알구몬 전용 모드라 설정이 필요 없습니다. 바로 monitor 명령어를 쓰세요!)"

# --- 🔍 알구몬 전용 수집기 (핵심) ---
@mcp.tool()
def fetch_board_items(env_name: str) -> str:
    """알구몬 핫딜 리스트를 전용 파서로 수집합니다."""
    print(f"🔍 [알구몬] 데이터 수집 시작...")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        resp = requests.get(ALGUMON_URL, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        all_items = []
        
        # 1. 게시글 리스트 전체 가져오기 (li.post-item)
        post_items = soup.select("li.post-item")
        
        for post in post_items[:25]: # 상위 25개만
            try:
                item = {
                    "site": "알구몬",
                    "title": "",
                    "comments": 0,
                    "link": "",
                    "date_text": "",
                    "content_selector": ".post-content" # 본문(댓글) 긁어올 때 쓸 영역
                }

                # (1) 제목 & 링크 추출
                # .deal-title 안에 있는 링크(a)가 진짜 제목임
                title_tag = post.select_one(".deal-title .item-name a")
                if title_tag:
                    item["title"] = title_tag.get_text(strip=True)
                    item["link"] = urljoin(ALGUMON_URL, title_tag.get('href'))
                
                # 제목 없으면 스킵 (광고 등)
                if not item["title"]: continue

                # (2) 댓글 수 추출
                # .icon-commenting-o 아이콘을 가진 부모 요소(span)를 찾음
                comment_icon = post.select_one(".icon-commenting-o")
                if comment_icon:
                    # 아이콘 바로 옆의 숫자 텍스트 추출
                    cmt_text = comment_icon.parent.get_text(strip=True)
                    # 숫자만 걸러내기
                    nums = re.findall(r'\d+', cmt_text)
                    if nums:
                        item["comments"] = int(nums[0])

                # (3) 날짜/시간 추출
                # "22분 전" 같은 텍스트가 있는 .created-at 또는 .deal-price-meta-info
                date_tag = post.select_one(".created-at")
                if not date_tag:
                    # 없으면 메타 정보 전체에서 시간 찾기
                    meta_tag = post.select_one(".deal-price-meta-info")
                    if meta_tag:
                        item["date_text"] = meta_tag.get_text(strip=True)
                else:
                    item["date_text"] = date_tag.get_text(strip=True)

                all_items.append(item)

            except Exception as e:
                print(f"⚠️ 파싱 에러(개별): {e}")
                continue

        print(f"✅ 수집 완료: {len(all_items)}개 발견")
        return json.dumps(all_items, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": f"알구몬 접속 실패: {e}"}, ensure_ascii=False)

@mcp.tool()
def fetch_post_detail(url: str, content_selector: str) -> str:
    """게시글 상세(댓글) 수집"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 알구몬 댓글 영역 (.post-content 또는 댓글 리스트)
        content = ""
        
        # 본문/댓글 텍스트 긁기
        elements = soup.select(".post-content") # 기본 본문
        if not elements:
            # 댓글 영역이 따로 있다면 여기 추가 (보통 알구몬은 post-content에 포함됨)
            elements = soup.select(".comment-list")
            
        content = "\n".join([f"- {el.get_text(strip=True)[:200]}" for el in elements])
        
        if not content: return "내용(댓글)을 찾을 수 없습니다."
        return content[:3000]
    except Exception as e:
        return f"수집 실패: {e}"

if __name__ == "__main__":
    mcp.run()
