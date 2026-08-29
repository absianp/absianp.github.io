#!/bin/bash
# ==============================================================================
# 🍓 Raspberry Pi 5 - Auto Blog System 1-Click Installer
# ==============================================================================
set -e

CURRENT_USER=$(whoami)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "================================================================="
echo "🚀 [라즈베리파이 5] Auto Blog System 자동 설치 및 서비스 등록을 시작합니다."
echo "👤 실행 계정: $CURRENT_USER"
echo "📂 설치 경로: $APP_DIR"
echo "================================================================="

# 1. 필수 시스템 패키지 설치
echo -e "\n📦 [1/5] 라즈베리파이 필수 패키지 점검 및 설치 중 (apt-get)..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip git curl nodejs npm

# 2. Node.js & Astro 블로그 의존성 설치
echo -e "\n🌐 [2/5] Astro 블로그 프론트엔드 의존성 설치 중..."
cd "$APP_DIR/blog-frontend"
npm install --production=false

# 3. Python 가상환경(venv) 생성 및 패키지 설치
echo -e "\n🐍 [3/5] Python 가상환경(venv) 구성 및 에이전트 패키지 설치 중..."
cd "$APP_DIR/automation-pipeline"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

# 4. 환경 변수 파일(.env) 확인
echo -e "\n⚙️ [4/5] 설정 파일 점검..."
if [ ! -f "$APP_DIR/automation-pipeline/config/.env" ]; then
    if [ -f "$APP_DIR/automation-pipeline/config/.env.example" ]; then
        cp "$APP_DIR/automation-pipeline/config/.env.example" "$APP_DIR/automation-pipeline/config/.env"
        echo "⚠️ config/.env 파일이 없어 .env.example로부터 생성했습니다. API 키를 입력해주세요."
    fi
fi

# 5. Systemd 서비스 및 타이머 등록
echo -e "\n⏰ [5/5] 백그라운드 24/7 스케줄러(Systemd Timer) 등록 중..."
SYSTEMD_SRC="$APP_DIR/deploy/rpi5/systemd"

# 현재 사용자 계정에 맞춰 서비스 파일 내 경로 및 유저명 동적 치환
sudo cp "$SYSTEMD_SRC/auto-blog.service" /etc/systemd/system/
sudo cp "$SYSTEMD_SRC/auto-blog.timer" /etc/systemd/system/
sudo cp "$SYSTEMD_SRC/auto-blog-report.service" /etc/systemd/system/
sudo cp "$SYSTEMD_SRC/auto-blog-report.timer" /etc/systemd/system/

sudo sed -i "s|User=pi|User=$CURRENT_USER|g" /etc/systemd/system/auto-blog.service
sudo sed -i "s|/home/pi/auto_blog_system|$APP_DIR|g" /etc/systemd/system/auto-blog.service
sudo sed -i "s|User=pi|User=$CURRENT_USER|g" /etc/systemd/system/auto-blog-report.service
sudo sed -i "s|/home/pi/auto_blog_system|$APP_DIR|g" /etc/systemd/system/auto-blog-report.service

sudo systemctl daemon-reload
sudo systemctl enable --now auto-blog.timer
sudo systemctl enable --now auto-blog-report.timer

echo "================================================================="
echo "🎉 [설치 완료!] 라즈베리파이 5에서 자동화 시스템이 성공적으로 가동되었습니다."
echo ""
echo "📌 활성화된 타이머 확인:"
echo "   systemctl list-timers | grep auto-blog"
echo ""
echo "🔍 로그 실시간 확인:"
echo "   journalctl -u auto-blog.service -f"
echo ""
echo "⚡ 지금 즉시 테스트 실행:"
echo "   bash $APP_DIR/deploy/rpi5/scripts/run_manual.sh"
echo "================================================================="
