#!/bin/bash
# ==============================================================================
# 🚀 Manual Run Helper for Raspberry Pi 5
# ==============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$APP_DIR/automation-pipeline"

if [ -d "venv" ]; then
    source venv/bin/activate
fi

echo "=================================================="
echo "🤖 Auto Blog 수동 실행 메뉴"
echo "=================================================="
echo " [1] 대화형 주제 선택 및 발행 (Interactive)"
echo " [2] 무인 자동 즉시 글 생성 & 배포 (Auto Publish)"
echo " [3] 주간 트래픽 & 애드센스 수익 보고서 확인 (Report)"
echo " [4] 블로그 로컬 프리뷰 서버 실행 (Local Preview)"
echo " [0] 종료"
echo "=================================================="
read -p "👉 실행할 메뉴 번호를 입력하세요: " CHOICE

case "$CHOICE" in
    1)
        python3 main_pipeline.py --mode interactive
        ;;
    2)
        python3 main_pipeline.py --mode auto --approve
        ;;
    3)
        python3 main_pipeline.py --mode report
        ;;
    4)
        cd "$APP_DIR/blog-frontend"
        npm run dev -- --host 0.0.0.0
        ;;
    *)
        echo "종료합니다."
        ;;
esac
