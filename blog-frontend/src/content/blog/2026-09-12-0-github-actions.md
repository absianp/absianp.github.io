---
title: '서버 비용 0원: GitHub Actions와 파이썬으로 구축하는 매일 아침 데이터 자동 수집 및 텔레그램 알림 시스템'
description: 월 서버 비용 없이 GitHub Actions와 파이썬 크론 스케줄러로 매일 아침 데이터를 자동 수집하고 텔레그램 알림을 받는
  실전 파이프라인 구축 가이드입니다.
pubDate: '2026-09-12'
category: 개발 & 테크
tags:
- GitHub Actions
- 파이썬 자동화
- 크론 스케줄러
- 무료 서버
author: 앱시안 (absian)
readingTime: 9 min read
featured: false
draft: false
faqs:
- question: GitHub Actions의 무료 사용 시간을 초과하면 자동으로 결제되나요?
  answer: 아닙니다. 개인 무료 계정의 경우 기본적으로 추가 결제 한도(Spending Limit)가 0달러로 잠겨 있습니다. 프라이빗 저장소의
    월 2,000분 무료 할당량을 모두 소진하면 해당 월의 워크플로 실행이 일시 중단될 뿐, 사용자가 카드를 등록하고 한도를 명시적으로 올리지
    않는 한 예상치 못한 비용이 청구되지 않습니다.
- question: 크론(cron) 스케줄이 정확히 제 시간에 돌지 않고 가끔 누락되는 이유는 무엇인가요?
  answer: GitHub의 크론 엔진은 고가용성 SLA를 보장하는 전용 스케줄러가 아니며, 트래픽이 높은 시간대(특히 매시 00분)에는 공용
    러너 풀 대기로 인해 수 분에서 수십 분의 지연이 발생할 수 있습니다. 지연을 최소화하려면 정각(00분)을 피해 '17분', '43분'처럼
    독특한 분 단위로 크론 표현식을 수정하는 것을 강력히 권장합니다.
- question: 텔레그램 대신 슬랙(Slack)이나 디스코드(Discord)로 알림 채널을 바꿀 수 있나요?
  answer: 네, 얼마든지 가능합니다. 슬랙의 Incoming Webhook URL이나 디스코드 웹훅 URL을 생성한 후, 텔레그램 발송 함수
    대신 해당 웹훅 주소로 JSON 형식의 메시지를 POST 요청으로 전송하도록 `main.py`의 네트워크 발송 로직만 교체하시면 동일하게 작동합니다.
---

# 서버 비용 0원: GitHub Actions와 파이썬으로 구축하는 매일 아침 데이터 자동 수집 및 텔레그램 알림 시스템

매일 아침 특정 웹사이트의 공지사항, 환율 지표, 채용 정보, 혹은 기술 블로그의 신규 아티클을 확인하기 위해 수동으로 브라우저를 열고 계신가요? 많은 개발자와 데이터 엔지니어들이 이러한 반복 작업을 자동화하고자 파이썬(Python) 크롤링 스크립트를 작성합니다. 하지만 스크립트 작성을 마친 직후 곧바로 현실적인 장벽에 부딪히게 됩니다. 바로 **"이 스크립트를 어디서, 언제 실행할 것인가?"**라는 인프라 문제입니다.

개인 PC를 24시간 켜두자니 전기세와 소음이 부담스럽고, AWS EC2나 라이트세일(Lightsail) 같은 클라우드 VPS(가상 사설 서버)를 임대하자니 매달 최소 5~10달러(약 7,000원~14,000원)의 고정 지출이 발생합니다. 단순 10초짜리 크롤러 스크립트 하나를 위해 서버를 항시 띄워두는 것은 명백한 리소스 낭비입니다.

이번 가이드에서는 CI/CD 도구로 널리 알려진 **GitHub Actions**를 서버리스 크론 스케줄러로 전환하여, **서버 비용 0원**으로 매일 아침 데이터를 수집하고 텔레그램(Telegram)으로 요약 리포트를 받아보는 엔드투엔드(End-to-End) 자동화 파이프라인을 구축해 봅니다.

---

## 1. 왜 GitHub Actions 기반 스케줄러인가? (인프라 비교 분석)

주기적인 데이터 수집 작업을 배포할 때 고려할 수 있는 대표적인 인프라 대안들을 비교해 보겠습니다. 각각의 특성을 이해하면 왜 GitHub Actions가 개인 및 소규모 자동화 프로젝트에서 최고의 가성비를 발휘하는지 명확해집니다.

| 인프라 구분 | 월 예상 비용 | 셋업 및 유지보수 난이도 | 장점 | 단점 및 한계 |
| :--- | :--- | :--- | :--- | :--- |
| **GitHub Actions** | **0원 (무료)** | **낮음 (YAML 설정)** | 형상 관리 일원화, Secrets 기반 보안, 무료 티어 제공(월 2,000분) | 실행 시점의 미세한 지연(큐 대기), 최대 단일 작업 6시간 제한 |
| **AWS Lambda + EventBridge** | 0원 (프리티어 내) | 중간 (IAM 권한, 배포 패키징) | 높은 신뢰도, 정밀한 트리거 시간 | 패키지 용량 제한, Layer 빌드 번거로움, 과금 정책 모니터링 필요 |
| **클라우드 VPS (EC2/Lightsail)** | 월 5,000원 ~ 15,000원 | 높음 (OS 보안, crontab 관리) | 제약 없는 자유도, 고정 IP 할당 가능 | 매월 지속적인 비용 발생, OS 패치 및 서버 다운타임 자체 관리 |
| **로컬 PC 크론탭 (Cron)** | 0원 (하드웨어 제외) | 낮음 | 구현 직관적, 네트워크 차단 위험 적음 | PC가 꺼지면 미실행, 절전 모드 충돌, 전기세 부담 |

GitHub Actions는 별도의 인프라 프로비저닝 없이 `.github/workflows/` 디렉터리에 YAML 선언문 하나만 추가하면 클라우드 가상 머신(Ubuntu 최신 환경)을 즉시 할당받아 작업을 수행하고 종료합니다. 코드 저장소와 실행 환경이 하나로 결합되므로 배포 파이프라인이 획기적으로 단순해집니다.

---

## 2. 텔레그램 봇 API 설정 및 GitHub Secrets 보안 구성

자동화 스크립트가 수집한 데이터를 전송할 텔레그램 봇을 생성하고, 안전하게 토큰을 보관하는 단계입니다. API 토큰이 코드 저장소에 평문으로 커밋되면 봇 권한이 탈취될 수 있으므로 GitHub Secrets를 필수적으로 사용해야 합니다.

### 2.1. 텔레그램 Bot Token 및 Chat ID 발급
1. 텔레그램 앱 검색창에 `@BotFather`를 검색하고 대화를 시작합니다.
2. `/newbot` 명령어를 입력한 뒤 봇의 이름과 유니크한 유저네임을 순서대로 입력합니다.
3. 생성이 완료되면 `HTTP API access token` 형태의 고유 토큰(`예: 1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ`)이 발급됩니다.
4. 생성된 봇을 대화방에 초대한 후 아무 메시지(예: `test`)를 전송합니다.
5. 브라우저에서 아래 URL로 접속하여 내 계정의 `chat_id`를 확인합니다:
   ```bash
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
   ```
   반환된 JSON 데이터 중 `"chat":{"id": 123456789, ...}` 부분의 숫자 값이 여러분의 `CHAT_ID`입니다.

### 2.2. GitHub Secrets 등록
1. 본 작업을 진행할 GitHub 리포지토리로 이동합니다.
2. **Settings** → **Secrets and variables** → **Actions** 메뉴를 클릭합니다.
3. **New repository secret** 버튼을 눌러 다음 두 가지 비밀 변수를 생성합니다:
   - `TELEGRAM_BOT_TOKEN`: BotFather에게 발급받은 API 토큰 값
   - `TELEGRAM_CHAT_ID`: 앞서 확인한 본인의 텔레그램 Chat ID 숫자 값

이 과정을 거치면 워크플로 실행 시 코드에 토큰을 직접 노출하지 않고 환경 변수 형태로 주입할 수 있습니다.

---

## 3. 파이썬 데이터 크롤링 및 알림 파이프라인 구현

이제 실제로 데이터를 긁어와 텔레그램으로 쏘아 올려주는 파이썬 코드를 작성합니다. 여기서는 파이썬 표준 생태계의 대표 주자인 `requests`와 `BeautifulSoup4`를 결합합니다. 대상 웹사이트의 봇 차단을 우회하기 위한 정석적인 헤더 설정도 포함되어 있습니다.

리포지토리 루트에 `requirements.txt`와 `main.py` 파일을 생성합니다.

### requirements.txt
```text
requests>=2.31.0
beautifulsoup4>=4.12.2
```

### main.py
```python
import os
import sys
import requests
from bs4 import BeautifulSoup
from datetime import datetime

def fetch_data() -> list[dict]:
    """
    대상 웹페이지에서 데이터를 스크래핑합니다.
    실제 서비스 환경에서는 수집하려는 타깃 웹사이트의 DOM 구조에 맞게 셀렉터를 수정하세요.
    """
    target_url = "https://news.ycombinator.com/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    try:
        response = requests.get(target_url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] HTTP 요청 실패: {e}", file=sys.stderr)
        sys.exit(1)

    soup = BeautifulSoup(response.text, "html.parser")
    items = []
    
    # Hacker News 상위 5개 타이틀 및 링크 파싱 예시
    titles = soup.select(".titleline > a")[:5]
    for idx, item in enumerate(titles, 1):
        items.append({
            "rank": idx,
            "title": item.get_text(strip=True),
            "url": item.get("href", "#")
        })
    
    return items

def send_telegram_alert(token: str, chat_id: str, message: str) -> None:
    """
    텔레그램 Bot API를 활용해 HTML 포맷팅된 메시지를 발송합니다.
    """
    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }

    try:
        res = requests.post(api_url, json=payload, timeout=10)
        res.raise_for_status()
        print("[SUCCESS] 텔레그램 메시지 발송 완료")
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] 텔레그램 메시지 발송 실패: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    # 환경 변수로부터 보안 키 로드
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("[CRITICAL] 환경 변수(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)가 누락되었습니다.", file=sys.stderr)
        sys.exit(1)

    print("[INFO] 데이터 수집 시작...")
    dataset = fetch_data()
    
    today_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    text_lines = [
        f"<b>🚀 [모닝 테크 리포트] {today_str}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]

    for row in dataset:
        text_lines.append(f"{row['rank']}. <a href='{row['url']}'>{row['title']}</a>")

    text_lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    text_lines.append("<i>* GitHub Actions 서버리스 파이프라인에서 자동 발송됨</i>")

    final_message = "\n".join(text_lines)
    send_telegram_alert(bot_token, chat_id, final_message)

if __name__ == "__main__":
    main()
```

---

## 4. GitHub Actions 워크플로(.yml) 스케줄링 및 의존성 캐싱

이제 작성된 파이썬 스크립트를 주기적으로 실행할 워크플로 파일을 정의합니다. 리포지토리 내에 `.github/workflows/daily_automation.yml` 경로로 파일을 생성합니다.

> [!IMPORTANT]
> **시간대 주의 (UTC vs KST):**
> GitHub Actions의 크론(cron) 엔진은 항상 **UTC(협정 세계시)**를 기준으로 작동합니다. 한국 시간(KST)은 UTC보다 9시간 빠릅니다(`UTC+9`).
> 따라서 한국 시간 매일 아침 **08시 00분**에 스크립트를 실행하려면, 9시간을 뺀 **UTC 전날 23시 00분**으로 설정해야 합니다.

```yaml
name: Daily Data Scraping & Telegram Alert

on:
  schedule:
    # UTC 기준 23:00 -> 한국 시간(KST) 기준 익일 08:00 실행
    - cron: '0 23 * * *'
  # 필요 시 웹 인터페이스에서 'Run workflow' 버튼으로 즉시 수동 실행 가능하도록 설정
  workflow_dispatch:

jobs:
  scrape-and-notify:
    runs-on: ubuntu-latest
    timeout-minutes: 10 # 무한 루프 방지를 위한 최대 실행 시간 지정

    steps:
      - name: 체크아웃 리포지토리 코드
        uses: actions/checkout@v4

      - name: 파이썬 런타임 환경 구성 및 pip 캐시 활성화
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip' # 패키지 다운로드 시간을 획기적으로 단축

      - name: 의존성 패키지 설치
        run: |
          python -m pip install --upgrade pip
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

      - name: 데이터 수집 및 알림 스크립트 실행
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: |
          python main.py
```

### 캐싱 전략과 실행 시간(Minute) 절약
- **퍼블릭(Public) 리포지토리:** GitHub Actions 실행 시간이 **완전 무료(무제한)**로 제공됩니다. 비즈니스 로직에 비밀 코드가 없다면 퍼블릭 리포지토리를 권장합니다.
- **프라이빗(Private) 리포지토리:** 무료 티어 계정 기준 **월 2,000분의 실행 시간**이 주어집니다. 하루 1회 1분 남짓 소요되는 스크립트는 월 30분 내외만 소모하므로 프라이빗 리포지토리에서도 충분히 100% 무료 운영이 가능합니다.
- `cache: 'pip'` 옵션은 이전에 다운로드한 라이브러리 휠(Wheel) 파일을 GitHub 캐시 저장소에 보관하여, 매 실행마다 발생하는 `pip install` 대기 시간을 15~30초에서 2~3초로 줄여줍니다.

---

## 5. 실무에서 마주치는 트러블슈팅 및 운영 노하우

### 트러블슈팅 1: 크론 스케줄이 정각에 실행되지 않는 현상
GitHub Actions의 `schedule` 이벤트는 GitHub 전체 인프라의 러너 대기 큐(Queue) 상태에 따라 최대 10~30분가량 실행이 지연될 수 있습니다. 정각(예: `00분`, `30분`)에는 전 세계의 수많은 워크플로가 몰리기 때문에 큐 정체가 심해집니다.
- **해결책:** 크론 분 단위를 정각 대신 어긋난 임의의 분(예: `0 23 * * *` 대신 `17 23 * * *` 또는 `43 23 * * *`)으로 지정하세요. 러너 할당 대기열이 한산하여 지연 없이 거의 즉각 실행됩니다.

### 트러블슈팅 2: 60일간 커밋이 없을 때 Actions가 자동 비활성화되는 현상
GitHub 정책상 퍼블릭/프라이빗 상관없이 **60일 동안 아무런 커밋이나 활동이 없는 리포지토리의 예약된(scheduled) 워크플로는 자동으로 비활성화(Disabled)** 처리됩니다.
- **해결책:** 정기적인 봇 커밋을 유도하거나, 스크립트 실행 후 수집 일시나 로그를 담은 빈 파일(예: `last_run.txt`)을 갱신하여 깃 커밋&푸시하는 단계를 워크플로에 포함하면 리포지토리 활동이 유지되어 영구 가동됩니다.

### 트러블슈팅 3: 크롤링 대상 사이트의 403 Forbidden 차단
GitHub 러너의 IP 대역(Azure 클라우드 IP 풀)은 일반 가정용 IP와 달리 Cloudflare나 Akamai 같은 WAF(웹 애플리케이션 방화벽)에 쉽게 감지됩니다.
- **해결책:**
  1. 위 `main.py` 예시처럼 브라우저 형태의 현실적인 `User-Agent`와 `Accept-Language` 헤더를 반드시 명시합니다.
  2. 과도한 빈도의 요청을 지양하고 엔드포인트 간 `time.sleep()` 텀을 둡니다.
  3. 고난도 캡차(CAPTCHA)가 걸린 사이트라면 브라우저 자동화 라이브러리(Playwright headless)를 Actions 러너 내에서 실행하는 방식을 고려해보세요.

---

## 6. 결론 및 권장 워크플로우

인프라 구축과 서버 호스팅 비용 없이 온디맨드 서버리스 아키텍처로 강력한 알림 시스템을 완성했습니다.

### 3줄 핵심 요약
1. **서버 비용 0원 달성:** 월 수만 원의 고정 서버 비용 없이 GitHub Actions의 풍부한 무료 런타임을 크론 스케줄러로 활용할 수 있습니다.
2. **보안과 성능 최적화:** GitHub Secrets로 민감한 토큰을 보호하고, `actions/setup-python`의 `pip` 캐시를 통해 빌드 시간을 극적으로 단축합니다.
3. **간편한 확장성:** 파이썬의 방대한 데이터 수집 생태계와 텔레그램 Bot API를 결합하여 주식, 채용, 뉴스 등 무궁무진한 자동화 파이프라인으로 확장이 가능합니다.

지금 바로 빈 GitHub 리포지토리를 만들고, 위 코드를 푸시해 여러분만의 매일 아침 맞춤형 모닝 브리핑 비서를 무료로 구축해 보세요!
