#!/bin/bash
# ==============================================================================
# 🍓 Direct SSH Automation Helper for Raspberry Pi 5
# ==============================================================================
set -e

KEY_PATH="/Users/absolujin/.gemini/antigravity/scratch/auto_blog_system/deploy/rpi5/keys/rpi5_key"
BUNDLE_PATH="/Users/absolujin/.gemini/antigravity/scratch/auto_blog_system/auto_blog_rpi5_bundle.tar.gz"

RPI_USER="${1:-pi}"
RPI_HOST="${2:-raspberrypi.local}"
RPI_PORT="${3:-22}"

if [ -z "$2" ]; then
    echo "사용법: bash rpi5_ssh.sh <USER> <HOST_IP> [PORT]"
    echo "예시:   bash rpi5_ssh.sh pi 192.168.0.50 22"
    exit 1
fi

echo "================================================="
echo "🚀 [라즈베리파이 5] SSH 원격 자동 배포 시작..."
echo "🎯 대상: $RPI_USER@$RPI_HOST:$RPI_PORT"
echo "================================================="

# 1. SSH 연결 테스트
echo -e "\n1️⃣ SSH 연결 확인 중..."
ssh -i "$KEY_PATH" -p "$RPI_PORT" -o StrictHostKeyChecking=no -o ConnectTimeout=5 "$RPI_USER@$RPI_HOST" "echo '✅ SSH 연결 성공: \$(hostname)'"

# 2. 번들 파일 전송
echo -e "\n2️⃣ 설치 번들 파일 전송 중 ($BUNDLE_PATH)..."
scp -i "$KEY_PATH" -P "$RPI_PORT" -o StrictHostKeyChecking=no "$BUNDLE_PATH" "$RPI_USER@$RPI_HOST:~/"

# 3. 원격 압축 해제 및 1클릭 설치 실행
echo -e "\n3️⃣ 원격 라즈베리파이 5 설치 스크립트 실행 중..."
ssh -i "$KEY_PATH" -p "$RPI_PORT" -o StrictHostKeyChecking=no "$RPI_USER@$RPI_HOST" << 'REMOTE_SCRIPT'
    mkdir -p ~/auto_blog_system
    tar -xzf ~/auto_blog_rpi5_bundle.tar.gz -C ~/auto_blog_system
    cd ~/auto_blog_system
    bash deploy/rpi5/scripts/install_rpi5.sh
REMOTE_SCRIPT

echo -e "\n🎉 라즈베리파이 5 원격 구축이 완료되었습니다!"
