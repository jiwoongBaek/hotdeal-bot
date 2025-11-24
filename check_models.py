import google.generativeai as genai
import os

# API 키 설정 (환경 변수에서 가져옴)
API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=API_KEY)

print("📋 사용 가능한 모델 목록:")
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"- {m.name}")
except Exception as e:
    print(f"에러 발생: {e}")
