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

# 🔍 로그 전용 함수 (통신 방해 안 함)
def log(msg):
    sys.stderr.write(f"{msg}\n")
    sys.stderr.flush()

@mcp.tool()
def fetch_board_items(env_name: str) -> str:
    """알구몬 리스트 수집"""
    log(f"🔍 [알구몬] 리스트 스캔 시작...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        resp = requests.get(ALGUMON_URL, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        all_items = []
        today_str = datetime.now().strftime("%m/%d")
        
        products = soup.select(".product-body")
        
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

        log(f"✅ 리스트 확보: {len(all_items)}개")
        return json.dumps(all_items, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"알구몬 접속 실패: {e}"}, ensure_ascii=False)


@mcp.tool()
def fetch_post_detail(url: str, content_selector: str) -> str:
    """리다이렉트 추적 및 본문 수집"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://algumon.com/'
        }
        
        session = requests.Session()
        resp = session.get(url, headers=headers, timeout=10)
        
        # 리다이렉트 감지
        if "이동중" in resp.text or "redirect" in resp.url or "refresh" in resp.text.lower():
            log("   ↪️ 대기 페이지 감지! 진짜 주소 추적 중...")
            
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
                log(f"   👉 진짜 목적지 발견: {new_url[:40]}...")
                resp = session.get(new_url, headers=headers, timeout=10)

        final_url = resp.url
        log(f"   ✅ 최종 접속: {final_url[:30]}...")
        
        if "ppomppu.co.kr" in final_url:
            resp.encoding = 'cp949'
        else:
            resp.encoding = resp.apparent_encoding 
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 댓글 찾기
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
        
        # 댓글 없으면 본문
        if not extracted_text:
            log("   ⚠️ 댓글 영역 없음 -> 본문 전체 수집")
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
