FROM python:3.10-slim

WORKDIR /app

# 필수 패키지 설치
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 라이브러리 설치 목록 복사
COPY requirements.txt .

# 🔥 이 부분이 중요합니다! (curl_cffi 설치)
RUN pip install --no-cache-dir -r requirements.txt

# 소스코드 복사
COPY server.py .

# 실행
CMD ["python", "server.py"]
