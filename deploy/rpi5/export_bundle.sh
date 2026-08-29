#!/bin/bash
# ==============================================================================
# 📦 Raspberry Pi 5 Migration Bundle Exporter
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
BUNDLE_NAME="auto_blog_rpi5_bundle.tar.gz"
OUTPUT_PATH="$APP_DIR/$BUNDLE_NAME"

echo "================================================================="
echo "📦 [이관 번들 제작] 라즈베리파이 5 이관용 경량 압축 패키지 생성 시작"
echo "📂 원본 경로: $APP_DIR"
echo "================================================================="

cd "$APP_DIR"

# 불필요한 대용량/임시 파일(node_modules, venv, pycache, dist) 제외하고 압축
tar --exclude='blog-frontend/node_modules' \
    --exclude='blog-frontend/dist' \
    --exclude='automation-pipeline/venv' \
    --exclude='automation-pipeline/__pycache__' \
    --exclude='automation-pipeline/*/__pycache__' \
    --exclude='.DS_Store' \
    --exclude='*.tar.gz' \
    -czf "$OUTPUT_PATH" .

FILE_SIZE=$(du -h "$OUTPUT_PATH" | cut -f1)

echo "================================================================="
echo "🎉 [번들 생성 완료!]"
echo "📁 생성 파일: $OUTPUT_PATH"
echo "⚖️ 압축 용량: $FILE_SIZE (대용량 캐시가 제외되어 매우 가볍습니다)"
echo ""
echo "🚀 [라즈베리파이 5로 전송하는 1줄 명령어 예시 (SCP)]:"
echo "   scp $BUNDLE_NAME pi@<라즈베리파이_IP>:~/"
echo ""
echo "📥 [라즈베리파이 5에서 압축 해제 및 1클릭 설치]:"
echo "   mkdir -p ~/auto_blog_system && tar -xzf ~/$BUNDLE_NAME -C ~/auto_blog_system"
echo "   cd ~/auto_blog_system && bash deploy/rpi5/scripts/install_rpi5.sh"
echo "================================================================="
