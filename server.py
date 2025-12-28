from mcp.server.fastmcp import FastMCP
import requests
from bs4 import BeautifulSoup
import json
import re
import sys
from urllib.parse import urljoin
from datetime import datetime

ALGUMON_URL = "https://algumon.com"
mcp = FastMCP("OmniAnalyst")

# 📢 로그를 터미널(stderr)에 강제로 찍는 함수
def log(msg):
    sys.stderr.write(f"[DEBUG] {msg}\n")
    sys.stderr.flush()

@mcp.tool()
def fetch_board_items(env_name: str) -> str:
    """알구몬 리스트 수집 (진단 모드)"""
    log(f"--- 스캔 시작: {datetime.now().strftime('%H:%M:%S')} ---")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
    }

    try:
        resp = requests.get(ALGUMON_URL, headers=headers, timeout=15)
        log(f"웹사이트 접속 상태코드: {resp.status_code}") # 200이 아니면 차단된 것
        
        if resp.status_code != 200:
            log(f"⚠️ 접속 실패! 상태코드: {resp.status_code}")
            return json.dumps({"error": f"HTTP Error {resp.status_code}"}, ensure_ascii=False)

        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 상품 리스트 찾기 (가장 넓은 범위로 시도)
        products = soup.select(".product-body")
        log(f"찾은 게시글 개수: {len(products)}개") # 여기가 0이면 사이트 구조 변경됨

        # 만약 0개라면 HTML 일부를 찍어서 확인
        if len(products) == 0:
            log("⚠️ 게시글을 하나도 못 찾았습니다. 사이트 구조가 바뀌었거나 차단 페이지일 수 있습니다.")
            log(f"HTML 앞부분 200자: {resp.text[:200]}")
            return json.dumps([], ensure_ascii=False)

        all_items = []
        today_str = datetime.now().strftime("%m/%d")
        
        for post in products[:30]: 
            try:
                item = {
                    "site": "알구몬",
                    "title": "",
                    "comments": 0,
                    "link": "",
                    "date_text": "",
                    "content_selector": "AUTO"
                }

                # 제목
                title_tag = post.select_one(".deal-title .item-name a")
                if title_tag:
                    item["title"] = title_tag.get_text(strip=True)
                    item["link"] = urljoin(ALGUMON_URL, title_tag.get('href'))
                else: 
                    continue

                # 댓글 수
                comment_icon = post.select_one(".icon-commenting-o")
                if comment_icon:
                    cmt_text = comment_icon.parent.get_text(strip=True)
                    nums = re.findall(r'\d+', cmt_text)
                    if nums: item["comments"] = int(nums[0])

                # 날짜
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

        log(f"최종 처리된 항목: {len(all_items)}개")
        return json.dumps(all_items, ensure_ascii=False)

    except Exception as e:
        log(f"치명적 에러 발생: {e}")
        return json.dumps({"error": f"접속 실패: {e}"}, ensure_ascii=False)

# fetch_post_detail은 그대로 둡니다 (문제는 리스트 수집이니까요)
@mcp.tool()
def fetch_post_detail(url: str, content_selector: str) -> str:
    return "상세 내용 수집 함수" # (생략)

if __name__ == "__main__":
    mcp.run()
