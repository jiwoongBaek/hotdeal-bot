# 파일경로: /home/baek828/hotdeal-bot/server.py
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
    """알구몬 핫딜 리스트 수집"""
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
    """사이트별 댓글/본문 수집"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://algumon.com/'
        }
        
        resp = requests.get(url, headers=headers, timeout=10)
        
        # 인코딩 보정
        if "ppomppu.co.kr" in url:
            resp.encoding = 'cp949'
        else:
            resp.encoding = resp.apparent_encoding 
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        final_url = resp.url
        print(f"   👉 [외부 접속] {final_url[:30]}...")

        comments = []
        
        if "ppomppu.co.kr" in final_url:
            comments = soup.select(".han-comment, .comment_wrapper, #quote, .list_comment")
            if not comments: comments = soup.select(".board-contents")
        elif "quasarzone.com" in final_url:
            comments = soup.select(".comment-content")
        elif "ruliweb.com" in final_url:
            comments = soup.select(".comment_view, .board_main_view")
        elif "fmkorea.com" in final_url:
            comments = soup.select(".comment-content, .xe_content")
        elif "arca.live" in final_url:
            comments = soup.select(".comment-content, .article-content")
        else:
            comments = soup.select(".comment, .review, .reply, .list-group-item")

        extracted_text = []
        for el in comments:
            text = el.get_text(strip=True)
            if text: extracted_text.append(f"- {text}")
            
        result = "\n".join(extracted_text)
        
        if not result:
            body_text = soup.get_text(strip=True)[:1000]
            return f"[댓글 찾기 실패, 본문 요약]\n{body_text}"
            
        return f"[수집 성공]\n{result[:3000]}"

    except Exception as e:
        return f"접속 실패: {e}"

if __name__ == "__main__":
    mcp.run()
