from mcp.server.fastmcp import FastMCP
import sqlite3
import requests
from bs4 import BeautifulSoup
import json
import os
import re
from urllib.parse import urljoin
from datetime import datetime

ALGUMON_URL = "https://algumon.com"
DB_PATH = "/data/config.db"
mcp = FastMCP("OmniAnalyst")

def init_db():
    os.makedirs("/data", exist_ok=True)ㅁfrom mcp.server.fastmcp import FastMCP
import requests
from bs4 import BeautifulSoup
import json
import re
from urllib.parse import urljoin
from datetime import datetime

# 알구몬 주소
ALGUMON_URL = "https://algumon.com"
mcp = FastMCP("OmniAnalyst")

# --- 도구들 ---
@mcp.tool()
def fetch_board_items(env_name: str) -> str:
    print(f"🔍 [알구몬] 리스트 스캔 중...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        resp = requests.get(ALGUMON_URL, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        all_items = []
        today_str = datetime.now().strftime("%m/%d")
        
        products = soup.select(".product-body")
        
        for post in products[:25]:
            try:
                item = {
                    "site": "알구몬",
                    "title": "",
                    "comments": 0,
                    "link": "",
                    "date_text": "",
                    "content_selector": "AUTO"
                }

                # 제목 & 링크
                title_tag = post.select_one(".deal-title .item-name a")
                if title_tag:
                    item["title"] = title_tag.get_text(strip=True)
                    item["link"] = urljoin(ALGUMON_URL, title_tag.get('href'))
                else: continue

                # 댓글 수
                comment_icon = post.select_one(".icon-commenting-o")
                if comment_icon:
                    cmt_text = comment_icon.parent.get_text(strip=True)
                    nums = re.findall(r'\d+', cmt_text)
                    if nums: item["comments"] = int(nums[0])

                # 날짜 정제
                raw_text = ""
                date_tag = post.select_one(".created-at")
                if date_tag: raw_text = date_tag.get_text(strip=True)
                else:
                    meta_tag = post.select_one(".deal-price-meta-info")
                    if meta_tag: raw_text = meta_tag.get_text(strip=True)

                clean_date = ""
                time_match = re.search(r'(\d+분\s*전|\d+시간\s*전|방금|\d+초\s*전|\d{2}-\d{2}|\d{2}/\d{2})', raw_text)
                if time_match: clean_date = time_match.group(1)
                else:
                    parts = raw_text.split()
                    if parts: clean_date = parts[-1]

                if any(x in clean_date for x in ["방금", "분", "시간", "초"]):
                    item["date_text"] = f"{today_str} ({clean_date})"
                else:
                    item["date_text"] = clean_date

                all_items.append(item)
            except: continue

        print(f"✅ 리스트 확보: {len(all_items)}개")
        return json.dumps(all_items, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"알구몬 접속 실패: {e}"}, ensure_ascii=False)


@mcp.tool()
def fetch_post_detail(url: str, content_selector: str) -> str:
    """사이트별 댓글/본문 수집 (강화된 버전)"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://algumon.com/'
        }
        
        resp = requests.get(url, headers=headers, timeout=10)
        
        # 뽐뿌용 인코딩 강제 보정 (EUC-KR 이슈 해결)
        if "ppomppu.co.kr" in url:
            resp.encoding = 'cp949' # euc-kr의 확장
        else:
            resp.encoding = resp.apparent_encoding 
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        final_url = resp.url
        print(f"   👉 [외부 접속] {final_url[:30]}...")

        comments = []
        
        # --- 사이트별 맞춤 선택자 ---
        if "ppomppu.co.kr" in final_url:
            # 뽐뿌: 댓글 + 본문 코멘트
            comments = soup.select(".han-comment, .comment_wrapper, #quote, .list_comment")
            if not comments: # 댓글 없으면 본문 내용이라도 긁음
                comments = soup.select(".board-contents")
                
        elif "quasarzone.com" in final_url:
            comments = soup.select(".comment-content")
            
        elif "ruliweb.com" in final_url:
            comments = soup.select(".comment_view, .board_main_view")
            
        elif "fmkorea.com" in final_url:
            comments = soup.select(".comment-content, .xe_content")
            
        elif "arca.live" in final_url:
            comments = soup.select(".comment-content, .article-content")
            
        else:
            # 그 외 사이트 (쇼핑몰 등): 일반적인 댓글 클래스 시도
            comments = soup.select(".comment, .review, .reply, .list-group-item")

        # 텍스트 추출
        extracted_text = []
        for el in comments:
            text = el.get_text(strip=True)
            if text: extracted_text.append(f"- {text}")
            
        result = "\n".join(extracted_text)
        
        # 정 못 찾았으면 페이지 전체 텍스트 일부라도 반환 (AI 판단용)
        if not result:
            body_text = soup.get_text(strip=True)[:1000]
            return f"[댓글 찾기 실패, 본문 요약]\n{body_text}"
            
        return f"[수집 성공]\n{result[:3000]}"

    except Exception as e:
        return f"접속 실패: {e}"

if __name__ == "__main__":
    mcp.run()
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS environments (name TEXT PRIMARY KEY, description TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS sites (id INTEGER PRIMARY KEY, env_name TEXT, site_name TEXT)')
    conn.close()

init_db()

@mcp.tool()
def create_environment(name: str, description: str = "") -> str:
    return "✅ 알구몬 전용 모드"

@mcp.tool()
def add_board_to_env(env_name: str, site_name: str, board_url: str, title_selector: str, comment_selector: str, content_selector: str, date_selector: str, link_selector: str = "") -> str:
    return "✅ 설정 불필요 (자동 감지 모드)"

@mcp.tool()
def fetch_board_items(env_name: str) -> str:
    """알구몬 리스트 수집 (날짜 정제 포함)"""
    print(f"🔍 [알구몬] 리스트 스캔 중...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        resp = requests.get(ALGUMON_URL, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        all_items = []
        today_str = datetime.now().strftime("%m/%d")
        
        products = soup.select(".product-body")
        
        for post in products[:25]:
            try:
                item = {
                    "site": "알구몬",
                    "title": "",
                    "comments": 0,
                    "link": "",
                    "date_text": "",
                    "content_selector": "AUTO" # 자동으로 처리하도록 표시
                }

                # 제목 & 링크
                title_tag = post.select_one(".deal-title .item-name a")
                if title_tag:
                    item["title"] = title_tag.get_text(strip=True)
                    item["link"] = urljoin(ALGUMON_URL, title_tag.get('href'))
                else: continue

                # 댓글 수
                comment_icon = post.select_one(".icon-commenting-o")
                if comment_icon:
                    cmt_text = comment_icon.parent.get_text(strip=True)
                    nums = re.findall(r'\d+', cmt_text)
                    if nums: item["comments"] = int(nums[0])

                # 날짜 정제
                raw_text = ""
                date_tag = post.select_one(".created-at")
                if date_tag: raw_text = date_tag.get_text(strip=True)
                else:
                    meta_tag = post.select_one(".deal-price-meta-info")
                    if meta_tag: raw_text = meta_tag.get_text(strip=True)

                clean_date = ""
                time_match = re.search(r'(\d+분\s*전|\d+시간\s*전|방금|\d+초\s*전|\d{2}-\d{2}|\d{2}/\d{2})', raw_text)
                if time_match: clean_date = time_match.group(1)
                else:
                    parts = raw_text.split()
                    if parts: clean_date = parts[-1]

                if any(x in clean_date for x in ["방금", "분", "시간", "초"]):
                    item["date_text"] = f"{today_str} ({clean_date})"
                else:
                    item["date_text"] = clean_date

                all_items.append(item)
            except: continue

        print(f"✅ 리스트 확보: {len(all_items)}개")
        return json.dumps(all_items, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"알구몬 접속 실패: {e}"}, ensure_ascii=False)


# 🔥 [핵심 기능] 사이트별 댓글 수집기
@mcp.tool()
def fetch_post_detail(url: str, content_selector: str) -> str:
    """링크를 타고 들어가서 사이트별로 댓글을 긁어옵니다."""
    try:
        # 1. 헤더 설정 (차단 방지용)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://algumon.com/'
        }
        
        # 2. 접속 (리다이렉트 자동 추적)
        # 알구몬 링크 -> 실제 사이트(뽐뿌 등)로 이동됨
        resp = requests.get(url, headers=headers, timeout=10)
        
        # 인코딩 자동 보정 (뽐뿌 등에서 한글 깨짐 방지)
        resp.encoding = resp.apparent_encoding 
        
        final_url = resp.url
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        print(f"   👉 [외부 접속] {final_url[:40]}... (사이트 판독 중)")

        # 3. 사이트별 댓글 선택자 매핑
        comments = []
        
        if "ppomppu.co.kr" in final_url: # 뽐뿌
            # 뽐뿌는 댓글 구조가 다양함 (일반/모바일/앱)
            # 주요 댓글 영역들 시도
            selectors = [".han-comment", ".comment_wrapper", "#quote", ".comment-content"]
            for sel in selectors:
                found = soup.select(sel)
                if found:
                    comments = found; break
                    
        elif "quasarzone.com" in final_url: # 퀘이사존
            comments = soup.select(".comment-content")
            
        elif "ruliweb.com" in final_url: # 루리웹
            comments = soup.select(".comment_view")
            
        elif "fmkorea.com" in final_url: # 펨코
            comments = soup.select(".comment-content")
            
        elif "arca.live" in final_url: # 아카라이브
            comments = soup.select(".comment-content")
            
        else: # 그 외 사이트 (네이버몰, G마켓 등 쇼핑몰 자체일 경우)
            # 일반적인 댓글 클래스명으로 찍어보기
            comments = soup.select(".comment, .review, .reply, .list-group-item")

        # 4. 텍스트 추출 및 정리
        extracted_text = []
        for el in comments:
            text = el.get_text(strip=True)
            if text: extracted_text.append(f"- {text}")
            
        result = "\n".join(extracted_text)
        
        if not result:
            return "⚠️ 댓글을 찾을 수 없습니다. (사이트 구조가 다르거나 댓글이 없음)"
            
        return f"[댓글 수집 성공]\n{result[:3000]}" # 너무 길면 자름

    except Exception as e:
        return f"상세 페이지 접속 실패: {e}"

if __name__ == "__main__":
    mcp.run()
