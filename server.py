from mcp.server.fastmcp import FastMCP
from curl_cffi import requests # 🔥 강력한 requests
from bs4 import BeautifulSoup
import json
import re
import sys
from urllib.parse import urljoin
from datetime import datetime

ALGUMON_URL = "https://algumon.com"
mcp = FastMCP("OmniAnalyst")

def log(msg):
    sys.stderr.write(f"[DEBUG] {msg}\n")
    sys.stderr.flush()

@mcp.tool()
def fetch_board_items(env_name: str) -> str:
    """알구몬 리스트 수집 (순정 크롬 위장)"""
    log(f"--- 스캔 시작: {datetime.now().strftime('%H:%M:%S')} ---")
    
    try:
        # 🔥 헤더를 최소화하고 라이브러리 자동 설정에 맡깁니다.
        # User-Agent를 수동으로 넣으면 TLS지문과 불일치하여 차단당합니다.
        resp = requests.get(
            ALGUMON_URL, 
            impersonate="chrome120",  # 최신 크롬(v120)으로 완벽 빙의
            timeout=20
        )
        
        log(f"웹사이트 접속 상태코드: {resp.status_code}") 

        if resp.status_code != 200:
            log(f"⚠️ 여전히 차단됨! (Code: {resp.status_code})")
            # 403이면 내용을 살짝 봅니다 (혹시 캡차인지 확인)
            if resp.status_code == 403:
                log(f"차단 페이지 내용 일부: {resp.text[:100]}")
            return json.dumps({"error": f"차단됨 (HTTP {resp.status_code})"}, ensure_ascii=False)

        soup = BeautifulSoup(resp.text, 'html.parser')
        products = soup.select(".product-body")
        log(f"확보한 게시글 수: {len(products)}개")

        if len(products) == 0:
            # 혹시 선택자가 바뀌었는지 확인하기 위해 전체 링크 수 체크
            links = soup.select("a")
            log(f"게시글 0개. (페이지 내 링크 총 {len(links)}개 발견)")
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

                title_tag = post.select_one(".deal-title .item-name a")
                if title_tag:
                    item["title"] = title_tag.get_text(strip=True)
                    item["link"] = urljoin(ALGUMON_URL, title_tag.get('href'))
                else: continue

                comment_icon = post.select_one(".icon-commenting-o")
                if comment_icon:
                    cmt_text = comment_icon.parent.get_text(strip=True)
                    nums = re.findall(r'\d+', cmt_text)
                    if nums: item["comments"] = int(nums[0])

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

        return json.dumps(all_items, ensure_ascii=False)

    except Exception as e:
        log(f"에러 발생: {e}")
        return json.dumps({"error": f"접속 실패: {e}"}, ensure_ascii=False)


@mcp.tool()
def fetch_post_detail(url: str, content_selector: str) -> str:
    """상세 내용 수집 (순정 크롬 위장)"""
    try:
        session = requests.Session()
        # 여기도 User-Agent 수동 설정 제거
        resp = session.get(url, impersonate="chrome120", timeout=20)
        
        if "이동중" in resp.text or "redirect" in resp.url or "refresh" in resp.text.lower():
            log("   ↪️ 대기 페이지 감지...")
            soup = BeautifulSoup(resp.text, 'html.parser')
            meta = soup.find("meta", attrs={"http-equiv": "refresh"})
            new_url = None
            if meta:
                content = meta.get("content", "")
                match = re.search(r"url=([^;'\"]+)", content, re.IGNORECASE)
                if match: new_url = match.group(1)
            if not new_url:
                match = re.search(r"location\.href\s*=\s*['\"]([^'\"]+)['\"]", resp.text)
                if match: new_url = match.group(1)
            if new_url:
                resp = session.get(new_url, impersonate="chrome120", timeout=20)

        final_url = resp.url
        if "ppomppu.co.kr" in final_url: resp.encoding = 'cp949'
        else: resp.encoding = resp.apparent_encoding 
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        extracted_text = []
        selectors = [
            ".han-comment", ".comment_wrapper", "#quote", ".list_comment", 
            ".comment-content", ".comment_view", ".xe_content", 
            ".reply", ".review", ".comment", ".list-group-item"
        ]
        for sel in selectors:
            found = soup.select(sel)
            if found:
                for el in found:
                    t = el.get_text(strip=True)
                    if t: extracted_text.append(f"- {t}")
        
        if not extracted_text:
            for s in soup(["script", "style", "iframe", "header", "footer", "nav"]):
                s.extract()
            full_text = soup.get_text(separator="\n", strip=True)
            full_text = re.sub(r'\n+', '\n', full_text)
            return f"[전체 텍스트 분석]\n{full_text[:3500]}"

        return f"[댓글 수집 성공]\n" + "\n".join(extracted_text[:50])

    except Exception as e:
        return f"접속 실패: {e}"

if __name__ == "__main__":
    mcp.run()
