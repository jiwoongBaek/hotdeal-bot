# server.py (날짜 필터링 + 댓글 분석 버전)
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
    # 🌟 date_selector 컬럼 추가 (날짜 필터링용)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            env_name TEXT,
            site_name TEXT,
            board_url TEXT,
            title_selector TEXT,
            comment_selector TEXT,
            link_selector TEXT,
            content_selector TEXT, -- 이제부터 이건 '댓글 영역'을 긁는 용도로 씁니다
            date_selector TEXT,    -- [신규] 리스트에서 날짜/시간 위치
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

@mcp.tool()
def add_board_to_env(env_name: str, site_name: str, board_url: str, title_selector: str, comment_selector: str, content_selector: str, date_selector: str, link_selector: str = "") -> str:
    """사이트 추가 (날짜 선택자 포함)"""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "INSERT INTO sites (env_name, site_name, board_url, title_selector, comment_selector, link_selector, content_selector, date_selector) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (env_name, site_name, board_url, title_selector, comment_selector, link_selector, content_selector, date_selector)
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
    """리스트 수집 (날짜 정보 포함)"""
    conn = sqlite3.connect(DB_PATH)
    sites = conn.execute("SELECT site_name, board_url, title_selector, comment_selector, link_selector, content_selector, date_selector FROM sites WHERE env_name = ?", (env_name,)).fetchall()
    conn.close()

    if not sites: return json.dumps({"error": "등록된 사이트 없음"})

    all_items = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8'
    }

    for site_name, url, t_sel, c_sel, l_sel, cont_sel, d_sel in sites:
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.encoding = resp.apparent_encoding
            soup = BeautifulSoup(resp.text, 'html.parser')
            titles = soup.select(t_sel)
            
            for t_el in titles[:20]:
                item = {
                    "site": site_name, 
                    "title": t_el.get_text(strip=True), 
                    "comments": 0, 
                    "link": "",
                    "date_text": "", # [신규] 날짜 텍스트
                    "content_selector": cont_sel
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

                # [신규] 날짜 찾기
                if d_sel:
                    d_tag = t_el.select_one(d_sel) or (t_el.parent.select_one(d_sel) if t_el.parent else None)
                    if d_tag:
                        item["date_text"] = d_tag.get_text(strip=True)

                all_items.append(item)
        except Exception as e:
            all_items.append({"error": f"{site_name} 에러: {e}"})

    return json.dumps(all_items, ensure_ascii=False)

@mcp.tool()
def fetch_post_detail(url: str, content_selector: str) -> str:
    """게시글 링크로 들어가서 내용(이제는 댓글들)을 가져옵니다."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 댓글 내용 추출
        content = ""
        if content_selector:
            # 댓글들은 여러 개가 있으니 모두 긁어서 합침
            elements = soup.select(content_selector)
            content = "\n".join([f"- {el.get_text(strip=True)}" for el in elements])
        
        if not content: return "댓글을 찾을 수 없습니다."
            
        return content[:3000] # 댓글은 길어질 수 있으니 3000자 제한
    except Exception as e:
        return f"수집 실패: {e}"

if __name__ == "__main__":
    mcp.run()