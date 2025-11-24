FROM python:3.11-slim

WORKDIR /app

# 필수 라이브러리 설치
# mcp: 통신 프로토콜
# requests, beautifulsoup4: 크롤링
RUN pip install "mcp[cli]" requests beautifulsoup4

COPY server.py .

ENTRYPOINT ["python", "server.py"]