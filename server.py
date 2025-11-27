from mcp.server.fastmcp import FastMCP
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import yfinance as yf
from youtube_transcript_api import YouTubeTranscriptApi
import json

mcp = FastMCP("WealthArchitect")

# 구글 시트 인증 설정
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
KEY_FILE = "/app/service_account.json" # 도커 내부 경로

def get_sheet_client():
    creds = ServiceAccountCredentials.from_json_keyfile_name(KEY_FILE, SCOPE)
    return gspread.authorize(creds)

# --- 📊 1. 포트폴리오 관리 도구 (배치 업데이트 적용) ---

@mcp.tool()
def sync_portfolio_prices(sheet_name: str) -> str:
    """
    구글 시트의 데이터를 한 번에 가져와서 메모리에서 계산 후 한 번에 업데이트합니다.
    (API 호출 최소화로 에러 방지)
    """
    try:
        client = get_sheet_client()
        sh = client.open(sheet_name)
        ws = sh.get_worksheet(0) # 첫 번째 시트
        
        # 1. 전체 데이터 한 번에 가져오기 (API Call 1)
        all_values = ws.get_all_values()
        
        if not all_values:
            return "❌ 시트가 비어있습니다."

        header = all_values[0]
        rows = all_values[1:]
        
        updated_rows = []
        total_balance = 0
        
        # 2. 메모리에서 계산 (통신 X)
        for row in rows:
            # 빈 행이 있거나 길이가 짧으면 패스
            if not row or len(row) < 5:
                updated_rows.append(row)
                continue

            # 데이터 파싱 (콤마 제거 등 안전장치)
            ticker = row[2].strip()
            try:
                qty_str = row[3].replace(',', '').strip()
                qty = float(qty_str) if qty_str else 0
                
                avg_str = row[4].replace(',', '').strip()
                avg_price = float(avg_str) if avg_str else 0
            except:
                qty, avg_price = 0, 0

            current_price = avg_price # 기본값 (조회 실패 시 평단가 유지)

            # 주가 조회 (API Call - yfinance는 별도 제한이 널널함)
            if ticker and ticker != '-' and ('.KS' in ticker or len(ticker) < 5):
                try:
                    stock = yf.Ticker(ticker)
                    # fast_info가 빠름. 실패하면 history로 우회
                    current_price = stock.fast_info['last_price']
                except:
                    pass 
            
            # 펀드인 경우 현재가를 평단가와 같다고 가정 (자동조회 불가 영역)
            if ticker == '-':
                current_price = avg_price

            # 수익률 및 평가금액 계산
            profit_rate = ((current_price - avg_price) / avg_price * 100) if avg_price > 0 else 0
            
            # 평가금액 계산 (펀드인지 확인)
            is_fund = 'Fund' in row[5] or '펀드' in row[5]
            if is_fund:
                valuation = (qty / 1000) * current_price # 펀드는 1000좌당 가격
            else:
                valuation = qty * current_price

            total_balance += valuation

            # 3. 행 데이터 업데이트 (E, F, G열 수정)
            # row 리스트의 값을 직접 수정
            # 만약 row 길이가 짧으면 늘려줌
            while len(row) < 8:
                row.append("")
            
            row[4] = int(current_price) # E열: 현재가 (정수)
            row[5] = f"{profit_rate:.2f}%" # F열: 수익률
            row[6] = int(valuation) # G열: 평가금액
            
            updated_rows.append(row)

        # 4. 전체 데이터 한 번에 쓰기 (API Call 2)
        # 헤더 + 수정된 행들 합치기
        final_data = [header] + updated_rows
        ws.update(range_name='A1', values=final_data)

        return f"✅ 포트폴리오 업데이트 완료! 총 평가금액: {int(total_balance):,}원"

    except Exception as e:
        return f"❌ 시트 업데이트 실패: {e}"

@mcp.tool()
def get_portfolio_summary(sheet_name: str) -> str:
    """구글 시트 데이터를 JSON으로 가져옵니다."""
    try:
        client = get_sheet_client()
        sh = client.open(sheet_name)
        ws = sh.get_worksheet(0)
        return json.dumps(ws.get_all_records(), ensure_ascii=False)
    except Exception as e:
        return f"데이터 읽기 실패: {e}"

@mcp.tool()
def get_youtube_transcript(video_url: str) -> str:
    """유튜브 자막 수집"""
    try:
        video_id = video_url.split("v=")[-1].split("&")[0]
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko'])
        text = " ".join([t['text'] for t in transcript])
        return text[:15000]
    except Exception as e:
        return f"자막 실패: {e}"

if __name__ == "__main__":
    mcp.run()