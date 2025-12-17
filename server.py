from mcp.server.fastmcp import FastMCP
import requests
from bs4 import BeautifulSoup
import json
import re
from urllib.parse import urljoin
from datetime import datetime

# 알구몬 주소
ALGUMON_URL = "https://algumon.com"
mcp = FastMCP("OmniAnalyst")

@mcp.tool()
def fetch_board_items(env_name: str) -> str:
    print(f"🔍 [알구몬] 1페이지 스캔 시작...")
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

        print(f"✅ 리스트 확보: {len(all_items)}개")
        return json.dumps(all_items, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"알구몬 접속 실패: {e}"}, ensure_ascii=False)


@mcp.tool()
def fetch_post_detail(url: str, content_selector: str) -> str:
    """사이트 내용 수집 (강력한 폴백 적용)"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://algumon.com/'
        }
        
        resp = requests.get(url, headers=headers, timeout=10)
        final_url = resp.url
        print(f"   👉 접속: {final_url[:40]}...")

        # 인코딩 보정
        if "ppomppu.co.kr" in final_url:
            resp.encoding = 'cp949'
        else:
            resp.encoding = resp.apparent_encoding 
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 1. 댓글 전용 구역 시도
        selectors = [
            ".han-comment", ".comment_wrapper", "#quote", ".list_comment", # 뽐뿌
            ".comment-content", ".comment_view", ".xe_content", # 퀘이사/루리웹
            ".reply", ".review", ".comment", ".list-group-item" 
        ]
        
        extracted_text = []
        for sel in selectors:
            found = soup.select(sel)
            if found:
                for el in found:
                    t = el.get_text(strip=True)
                    extracted_text.append(f"- {t}")
        
        # 2. 댓글이 없으면? -> 페이지 전체 텍스트 긁어서 반환 (절대 실패 없음)
        if not extracted_text:
            print("   ⚠️ 댓글 선택 실패 -> 페이지 전체 텍스트 수집")
            
            # 스크립트 제거
            for s in soup(["script", "style", "iframe", "header", "footer", "nav"]):
                s.extract()
                
            full_text = soup.get_text(separator="\n", strip=True)
            # 텍스트 정리
            full_text = re.sub(r'\n+', '\n', full_text)
            
            return f"[전체 페이지 내용]\n{full_text[:4000]}" # 4000자 제한

        return f"[댓글 수집 성공]\n" + "\n".join(extracted_text[:50])

    except Exception as e:
        return f"접속 실패: {e}"

if __name__ == "__main__":
    mcp.run()
