# 🍓 라즈베리파이 5(Raspberry Pi 5) 24/7 무인 자동화 이관 및 운영 가이드

본 가이드는 현재 PC에서 구축된 **Auto Blog System**을 **라즈베리파이 5(또는 라즈베리파이 4)**로 손쉽게 이관하여 **24시간 365일 무중단 자동화 부업 머신**으로 가동하는 전체 과정을 단계별로 안내합니다.

---

## 💡 왜 라즈베리파이 5인가요?

1. **초절전 24/7 가동**: 소비전력 약 3~5W 수준으로, 1년 내내 켜두어도 전기요금이 1년에 수천 원 미만입니다.
2. **PC 독립성**: 개인 PC를 켜둘 필요 없이 라즈베리파이가 매일 정해진 시간(예: 아침 7시)에 자료를 수집하고 글을 발행합니다.
3. **모바일 원클릭 승인**: 침대나 출근길에 텔레그램 알림을 받고 [승인] 버튼만 누르면 라즈베리파이가 즉시 GitHub Pages로 배포합니다.
4. **리눅스 Systemd 안정성**: 네트워크 단절이나 재부팅 후에도 타이머와 서비스가 자동으로 자가 복구됩니다.

---

## 📦 이관 번들 패키지 정보

- **번들 압축 파일**: `auto_blog_rpi5_bundle.tar.gz` (용량: 약 80KB)
- **포함 내역**:
  - Astro 블로그 소스 및 테마, 애드센스 슬롯, 필수 정책 페이지
  - AI 에이전트 파이프라인 전체 (수집, 작성, 검토, 배포, 리포트)
  - 라즈베리파이 1클릭 자동 설치 스크립트 (`install_rpi5.sh`)
  - Systemd 서비스 및 타이머 파일 (`auto-blog.service`, `auto-blog.timer`)
  - 하드웨어 & 네트워크 자가 진단 스크립트 (`healthcheck.sh`)
  - 수동 실행 및 관리 메뉴 (`run_manual.sh`)
  - Docker Compose 배포 파일 (`Dockerfile`, `docker-compose.yml`)

---

## 🚀 5단계 이관 및 가동 절차

### 1단계: 번들 파일을 라즈베리파이 5로 전송
현재 PC의 터미널에서 `SCP` 명령어로 압축 파일을 라즈베리파이로 복사합니다.

```bash
# PC 터미널에서 실행 (라즈베리파이 IP 주소 입력)
cd /Users/absolujin/.gemini/antigravity/scratch/auto_blog_system
scp auto_blog_rpi5_bundle.tar.gz pi@<라즈베리파이_IP>:~/
```

---

### 2단계: 라즈베리파이에서 압축 해제 및 1클릭 설치
라즈베리파이에 SSH로 접속한 뒤 설치 스크립트를 실행합니다.

```bash
# 라즈베리파이 SSH 접속
ssh pi@<라즈베리파이_IP>

# 디렉토리 생성 및 압축 해제
mkdir -p ~/auto_blog_system
tar -xzf ~/auto_blog_rpi5_bundle.tar.gz -C ~/auto_blog_system
cd ~/auto_blog_system

# 1-Click 자동 설치 스크립트 실행 (패키지 설치, venv 생성, systemd 등록 완료)
bash deploy/rpi5/scripts/install_rpi5.sh
```

---

### 3단계: 환경 변수(API 키) 설정
Gemini API 키 및 텔레그램 봇 토큰을 설정합니다.

```bash
nano ~/auto_blog_system/automation-pipeline/config/.env
```

```env
# 구글 AI 스튜디오에서 발급받은 무료 Gemini API 키
GEMINI_API_KEY=your_actual_gemini_api_key_here

# (선택) 텔레그램 모바일 알림 및 승인 봇
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
```
*(저장: `Ctrl + O` $\rightarrow$ `Enter` $\rightarrow$ 종료: `Ctrl + X`)*

---

### 4단계: GitHub SSH Push 권한 설정 (최초 1회)
라즈베리파이가 글을 작성한 후 GitHub Pages 저장소로 Push할 수 있도록 SSH 키를 등록합니다.

```bash
# 라즈베리파이에서 SSH 키 생성 (엔터 3번 입력)
ssh-keygen -t ed25519 -C "rpi5-autoblog"

# 생성된 공개키 복사
cat ~/.ssh/id_ed25519.pub
```
1. GitHub 웹사이트 $\rightarrow$ 본인의 블로그 저장소 $\rightarrow$ **Settings** $\rightarrow$ **Deploy keys** (또는 본인 계정 **SSH Keys**) 진입.
2. **Add deploy key** 클릭 $\rightarrow$ 위에서 출력된 공개키 붙여넣기 $\rightarrow$ **`Allow write access` 체크** 후 저장.

---

### 5단계: 정상 작동 확인 (수동 테스트)
```bash
# 수동 실행 메뉴 호출
bash ~/auto_blog_system/deploy/rpi5/scripts/run_manual.sh
```
메뉴 `[1]` (대화형 실행) 또는 `[2]` (자동 즉시 발행)를 선택하여 글이 정상적으로 생성되고 배포되는지 테스트합니다.

---

## ⏰ 라즈베리파이 자동화 스케줄 안내

| 타이머 이름 | 실행 주기 | 수행 작업 |
| :--- | :--- | :--- |
| `auto-blog.timer` | **매일 아침 07:00 (KST)** | 트렌드 자료 수집 $\rightarrow$ 1,500자+ 글 작성 $\rightarrow$ SEO/정책 검사 $\rightarrow$ 자동 배포 |
| `auto-blog-report.timer` | **매주 일요일 저녁 20:00 (KST)** | 주간 구글 검색 노출수, 클릭수, 애드센스 예상 수익 집계 보고 |

---

## 🛠️ 라즈베리파이 일상 운영 및 모니터링 명령어

### 1. 스케줄러 타이머 상태 및 다음 실행 예정 시간 확인
```bash
systemctl list-timers | grep auto-blog
```

### 2. 에이전트 실행 실시간 로그 확인
```bash
journalctl -u auto-blog.service -f
```

### 3. 하드웨어 및 시스템 상태 진단 (온도, 저장공간, 네트워크)
```bash
bash ~/auto_blog_system/deploy/rpi5/scripts/healthcheck.sh
```

### 4. 로컬 네트워크에서 블로그 미리보기 (포트 3000)
```bash
cd ~/auto_blog_system/blog-frontend
npm run dev -- --host 0.0.0.0
# 동일 공유기 내 스마트폰/PC 브라우저에서 http://<라즈베리파이_IP>:3000 접속
```

---

## 🐳 (대안) Docker Compose로 실행하기

Docker 환경을 선호하시는 경우 다음과 같이 1줄로 가동하실 수 있습니다.

```bash
cd ~/auto_blog_system/deploy/rpi5
docker compose up -d
```
