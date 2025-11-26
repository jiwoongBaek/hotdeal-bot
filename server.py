# server.py (최종_진짜_최종_v2.py)
from mcp.server.fastmcp import FastMCP
import sqlite3
import requests
from bs4 import BeautifulSoup
import json
import os
import re
from urllib.parse import urljoin

DB_PATH = "/data/config.db"
mcp = FastMCP("OmniAnalyst")

def init_db():
    os.makedirs("/data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS environments (name TEXT PRIMARY KEY, description TEXT)
    ''')
    # 🌟 content_selector 컬럼 추가됨 (본문 긁어오기용)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            env_name TEXT,
            site_name TEXT,
            board_url TEXT,
            title_selector TEXT,
            comment_selector TEXT,
            link_selector TEXT,
            content_selector TEXT, 
            FOREIGN KEY(env_name) REFERENCES environments(name)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- ⚙️ 설정 도구 ---

@mcp.tool()
def create_environment(name: str, description: str = "") -> str:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT INTO environments VALUES (?, ?)", (name, description))
        conn.commit()
        return f"✅ 환경 생성: {name}"
    except:
        return "⚠️ 이미 존재함"
    finally:
        conn.close()

# 🌟 content_selector 인자 추가
@mcp.tool()
def add_board_to_env(env_name: str, site_name: str, board_url: str, title_selector: str, comment_selector: str, content_selector: str, link_selector: str = "") -> str:
    """사이트 추가 (본문 선택자 포함)"""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "INSERT INTO sites (env_name, site_name, board_url, title_selector, comment_selector, link_selector, content_selector) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (env_name, site_name, board_url, title_selector, comment_selector, link_selector, content_selector)
        )
        conn.commit()
        return f"✅ 사이트 추가 완료: {site_name}"
    except Exception as e:
        return f"❌ 실패: {e}"
    finally:
        conn.close()

# --- 🔍 수집 도구 ---

@mcp.tool()
def fetch_board_items(env_name: str) -> str:
    """게시판 리스트를 가져옵니다. (본문 선택자 정보도 함께 반환)"""
    conn = sqlite3.connect(DB_PATH)
    sites = conn.execute("SELECT site_name, board_url, title_selector, comment_selector, link_selector, content_selector FROM sites WHERE env_name = ?", (env_name,)).fetchall()
    conn.close()

    if not sites: return json.dumps({"error": "등록된 사이트 없음"})

    all_items = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://www.google.com/'
    }

    for site_name, url, t_sel, c_sel, l_sel, cont_sel in sites:
        try:
            resp = requests.get(url, headers=headers, timeout=5)
            soup = BeautifulSoup(resp.text, 'html.parser')
            titles = soup.select(t_sel)
            
            for t_el in titles[:15]:
                item = {
                    "site": site_name, "title": t_el.get_text(strip=True), 
                    "comments": 0, "link": "", 
                    "content_selector": cont_sel # 🌟 중요: 상세 페이지 긁을 때 쓸 선택자를 같이 전달
                }
                
                # 링크 찾기
                a_tag = t_el if t_el.name == 'a' else (t_el.select_one(l_sel) if l_sel else t_el.find_parent('a'))
                if a_tag and a_tag.has_attr('href'):
                    item["link"] = urljoin(url, a_tag['href'])

                # 댓글 수 찾기
                if c_sel:
                    c_tag = t_el.select_one(c_sel) or (t_el.parent.select_one(c_sel) if t_el.parent else None)
                    if c_tag:
                        nums = re.findall(r'\d+', c_tag.get_text())
                        if nums: item["comments"] = int(nums[0])

                all_items.append(item)
        except Exception as e:
            print(f"List Error {site_name}: {e}")

    return json.dumps(all_items, ensure_ascii=False)

# 🌟 [신규] 상세 페이지 내용 긁어오기 도구
@mcp.tool()
def fetch_post_detail(url: str, content_selector: str) -> str:
    """게시글 링크로 들어가서 본문 내용을 가져옵니다."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8'
        }
        resp = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 본문 추출
        content = ""
        if content_selector:
            elements = soup.select(content_selector)
            content = "\n".join([el.get_text(strip=True) for el in elements])
        
        # 선택자가 없거나 실패하면 대충 body에서 긁어오기 (길이 제한)
        if not content:
            content = soup.get_text(strip=True)[:1000]
            
        return content[:2000] # 너무 길면 Gemini가 힘들어하니 2000자 제한
    except Exception as e:
        return f"본문 수집 실패: {e}"

if __name__ == "__main__":
    mcp.run()

@mcp.tool()
def debug_site(url: str) -> str:
    """해당 URL에 접속해서 상태 코드와 HTML 앞부분 500자를 보여줍니다."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        resp = requests.get(url, headers=headers, timeout=10)
        return f"상태코드: {resp.status_code}\n내용일부:\n{resp.text[:500]}"
    except Exception as e:
        return f"접속 에러: {e}"