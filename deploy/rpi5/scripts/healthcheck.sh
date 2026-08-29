#!/bin/bash
# ==============================================================================
# 🍓 Raspberry Pi 5 - System Health & Diagnostic Script
# ==============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

echo "================================================="
echo "🍓 [라즈베리파이 5] Auto Blog System 상태 진단"
echo "================================================="

# 1. 온도 체크
if [ -f /sys/class/thermal/thermal_zone0/temp ]; then
    TEMP_RAW=$(cat /sys/class/thermal/thermal_zone0/temp)
    TEMP_C=$(awk "BEGIN {print $TEMP_RAW/1000}")
    echo "🌡️ CPU 온도: ${TEMP_C}°C"
elif command -v vcgencmd &> /dev/null; then
    vcgencmd measure_temp
fi

# 2. 디스크 여유 공간
echo -e "\n💾 저장공간 여유율:"
df -h "$APP_DIR" | awk 'NR==1 || NR==2'

# 3. 네트워크 및 인터넷 연결
echo -e "\n🌐 인터넷 연결 테스트 (Google DNS Ping):"
if ping -c 1 8.8.8.8 &> /dev/null; then
    echo "✅ 인터넷 연결 정상"
else
    echo "❌ 인터넷 연결 실패! Wi-Fi 또는 이더넷을 확인하세요."
fi

# 4. Systemd 타이머 상태 (User Unit 및 System Unit 모두 점검)
echo -e "\n⏰ Systemd 스케줄러 타이머 상태:"
if systemctl --user is-active auto-blog.timer &> /dev/null || systemctl is-active auto-blog.timer &> /dev/null; then
    echo "✅ auto-blog.timer: 활성화 (Running - 매일 아침 07:00 실행)"
else
    echo "❌ auto-blog.timer: 비활성화"
fi

if systemctl --user is-active auto-blog-report.timer &> /dev/null || systemctl is-active auto-blog-report.timer &> /dev/null; then
    echo "✅ auto-blog-report.timer: 활성화 (Running - 매주 일요일 20:00 실행)"
else
    echo "❌ auto-blog-report.timer: 비활성화"
fi

# 5. Git 원격 동기화 상태
echo -e "\n🐙 Git 저장소 상태:"
cd "$APP_DIR"
if [ -d ".git" ]; then
    git status -s
    echo "원격 브랜치:"
    git remote -v
else
    echo "ℹ️ 로컬 Git 저장소 미연결 (GitHub 저장소 URL 연결 필요)"
fi

# 6. 환경 변수 파일 점검
echo -e "\n🔑 API 키 설정 여부:"
ENV_FILE="$APP_DIR/automation-pipeline/config/.env"
if [ -f "$ENV_FILE" ]; then
    grep -q "GEMINI_API_KEY" "$ENV_FILE" && echo "✅ GEMINI_API_KEY 등록됨" || echo "⚠️ GEMINI_API_KEY 미설정"
    grep -q "TELEGRAM_BOT_TOKEN" "$ENV_FILE" && echo "✅ TELEGRAM_BOT_TOKEN 등록됨" || echo "ℹ️ TELEGRAM_BOT_TOKEN 미설정 (선택)"
else
    echo "❌ .env 파일이 없습니다 ($ENV_FILE)"
fi

echo "================================================="
