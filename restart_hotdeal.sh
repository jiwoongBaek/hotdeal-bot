#!/bin/bash

SESSION_NAME="hotdeal"
BOT_DIR="/home/baek828/hotdeal-bot"

echo "[$(date)] 🔄 봇 재시작 작업 시작..."

# 1. 기존 세션이 있다면 무조건 종료 (강제 리셋)
tmux has-session -t $SESSION_NAME 2>/dev/null
if [ $? == 0 ]; then
    echo "[$(date)] 기존 세션 발견. 종료 중..."
    tmux kill-session -t $SESSION_NAME
    sleep 5 # 세션이 완전히 죽을 때까지 잠시 대기
fi

echo "[$(date)] 새 세션 생성 및 봇 실행..."

# 2. 새 세션 생성 (백그라운드)
tmux new-session -d -s $SESSION_NAME

# 3. 봇 폴더로 이동
tmux send-keys -t $SESSION_NAME "cd $BOT_DIR" C-m

# 4. 가상환경 활성화
tmux send-keys -t $SESSION_NAME "source .venv/bin/activate" C-m

# 5. 환경변수 설정 (입력해주신 키 적용됨)
tmux send-keys -t $SESSION_NAME "export GEMINI_API_KEY='AIzaSyAXK_1KLGtum6NEw1LTZ2cHhjOVshUrLWo'" C-m
tmux send-keys -t $SESSION_NAME "export TELEGRAM_TOKEN='8540180652:AAFL6YdHXwxol3SMnencJGr9jvZek39_Q2M'" C-m
tmux send-keys -t $SESSION_NAME "export CHAT_ID='-5089222983'" C-m

# 6. 봇 실행
tmux send-keys -t $SESSION_NAME "python client.py" C-m

# 7. 로딩 대기 (15초) - 봇이 켜질 시간을 줍니다
sleep 15

# 8. 모니터링 명령어 입력 (알구몬 감시)
tmux send-keys -t $SESSION_NAME "monitor algumon all 5 600" C-m

echo "[$(date)] ✅ 봇 재시작 완료."
