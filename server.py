from mcp.server.fastmcp import FastMCP
import sqlite3
import requests
from bs4 import BeautifulSoup
import json
import os
import re
from urllib.parse import urljoin

# 도커 볼륨에 저장될 DB 경로
DB_PATH = "/data/config.db"
mcp = FastMCP("OmniAnalyst")

def init_db():
    os.makedirs("/data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    # 환경 테이블
    conn.execute('''
        CREATE TABLE IF NOT EXISTS environments (
            name TEXT PRIMARY KEY, 
            description TEXT
        )
    ''')
    # 사이트 설정 테이블
    conn.execute('''
        CREATE TABLE IF NOT EXISTS sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            env_name TEXT,
            site_name TEXT,
            board_url TEXT,
            title_selector TEXT,
            comment_selector TEXT,
            link_selector TEXT,
            FOREIGN KEY(env_name) REFERENCES environments(name)
        )
    ''')
    conn.commit()
    conn.close()

# 서버 시작 시 DB 초기화
init_db()

# --- ⚙️ 설정 관리 도구 ---

@mcp.tool()
def create_environment(name: str, description: str = "") -> str:
    """새로운 감시 환경을 만듭니다. (예: 핫딜, 뉴스)"""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT INTO environments VALUES (?, ?)", (name, description))
        conn.commit()
        return f"✅ 환경 생성 완료: {name}"
    except sqlite3.IntegrityError:
        return "⚠️ 이미 존재하는 환경입니다."
    finally:
        conn.close()

@mcp.tool()
def add_board_to_env(env_name: str, site_name: str, board_url: str, title_selector: str, comment_selector: str, link_selector: str = "") -> str:
    """환경에 게시판 사이트를 추가합니다. link_selector는 비워두면 자동 추론합니다."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "INSERT INTO sites (env_name, site_name, board_url, title_selector, comment_selector, link_selector) VALUES (?, ?, ?, ?, ?, ?)",
            (env_name, site_name, board_url, title_selector, comment_selector, link_selector)
        )
        conn.commit()
        return f"✅ 사이트 추가 완료: {site_name}"
    except Exception as e:
        return f"❌ 추가 실패: {e}"
    finally:
        conn.close()

# --- 🔍 데이터 수집 도구 ---

@mcp.tool()
def fetch_board_items(env_name: str) -> str:
    """해당 환경의 모든 게시판 1페이지를 긁어와 [제목, 댓글수, 링크] 리스트를 JSON으로 반환합니다."""
    conn = sqlite3.connect(DB_PATH)
    sites = conn.execute("SELECT site_name, board_url, title_selector, comment_selector, link_selector FROM sites WHERE env_name = ?", (env_name,)).fetchall()
    conn.close()

    if not sites:
        return json.dumps({"error": f"'{env_name}' 환경에 등록된 사이트가 없습니다."})

    all_items = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

    for site_name, url, t_sel, c_sel, l_sel in sites:
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # 제목 요소들 찾기
            titles = soup.select(t_sel)
            
            # 상위 15개만 처리
            for t_el in titles[:15]:
                item = {
                    "site": site_name, 
                    "title": t_el.get_text(strip=True), 
                    "comments": 0, 
                    "link": ""
                }
                
                # 1. 링크 추출
                a_tag = None
                if l_sel:
                    a_tag = t_el if t_el.name == 'a' else t_el.select_one(l_sel)
                
                # 링크 선택자가 없거나 실패하면 부모/자식 탐색
                if not a_tag:
                    a_tag = t_el if t_el.name == 'a' else t_el.find_parent('a')
                
                if a_tag and a_tag.has_attr('href'):
                    item["link"] = urljoin(url, a_tag['href'])

                # 2. 댓글 수 추출
                if c_sel:
                    c_text = ""
                    # A. 제목 태그 내부에서 찾기
                    c_tag = t_el.select_one(c_sel)
                    if c_tag:
                        c_text = c_tag.get_text()
                    # B. 없으면 부모의 자식(형제) 중에서 찾기
                    elif t_el.parent:
                        c_tag_parent = t_el.parent.select_one(c_sel)
                        if c_tag_parent:
                            c_text = c_tag_parent.get_text()
                    
                    # 숫자만 추출 (예: "[15]" -> 15)
                    nums = re.findall(r'\d+', c_text)
                    if nums:
                        item["comments"] = int(nums[0])

                all_items.append(item)

        except Exception as e:
            print(f"Error fetching {site_name}: {e}")
            continue

    return json.dumps(all_items, ensure_ascii=False)

if __name__ == "__main__":
    mcp.run()