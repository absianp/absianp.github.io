---
title: '서버 비용 0원: 깃허브 액션(GitHub Actions) 스케줄러로 파이썬 자동화 크롤러 구축하기'
heroImage: '/images/thumbnails/2026-09-11-0-github-actions.svg'
description: 매월 나가는 클라우드 서버 비용 없이 깃허브 액션(GitHub Actions) cron 스케줄러와 파이썬으로 웹 크롤러를 자동화하고
  디스코드 알림 및 깃 자동 커밋까지 연동하는 실전 가이드입니다.
pubDate: '2026-09-11'
category: 개발 & 테크
tags:
- 깃허브액션
- 파이썬자동화
- CICD
- 서버리스
- 웹크롤링
author: 앱시안 (absian)
readingTime: 8 min read
featured: false
draft: false
faqs:
- question: GitHub Actions의 cron 트리거가 정확한 시간에 실행되지 않는 이유는 무엇인가요?
  answer: GitHub Actions의 스케줄러는 전 세계 공유 러너 인프라에서 대기열(Queue) 방식으로 처리됩니다. 특히 매시 정각(00분,
    30분)에는 수많은 글로벌 사용자의 워크플로우가 동시에 몰려 수 분에서 최대 30분까지 지연될 수 있습니다. 이를 완화하려면 cron 분 단위를
    정각 대신 '14분', '37분' 등 불규칙한 숫자로 지정해보세요.
- question: 크롤링한 데이터를 리포지토리에 커밋할 때 GITHUB_TOKEN 권한 오류가 발생합니다. 어떻게 해결하나요?
  answer: 'GitHub 워크플로우 파일 상단에 ''permissions: contents: write'' 구문을 반드시 추가해야 합니다.
    또한 저장소의 Settings > Actions > General 메뉴 하단의 ''Workflow permissions'' 설정에서 ''Read
    and write permissions'' 옵션이 선택되어 있는지 확인하세요.'
- question: 동적 렌더링(자바스크립트 실행)이 필요한 사이트도 깃허브 액션에서 크롤링할 수 있나요?
  answer: 네, 가능합니다. 워크플로우 실행 단계에서 Playwright나 헤드리스 크롬(Puppeteer/Selenium)을 설치하여 실행할
    수 있습니다. 다만 브라우저 바이너리 설치와 헤드리스 구동으로 인해 실행 시간이 일반 HTTP 요청 방식보다 길어지므로, 비공개 저장소의 경우
    월 2,000분 무료 쿼터 소진 속도를 모니터링해야 합니다.
---

# 서버 비용 0원: 깃허브 액션(GitHub Actions) 스케줄러로 파이썬 자동화 크롤러 구축하기

매일 아침 특정 사이트의 공지사항, 환율, 주가 지수, 또는 채용 공고를 주기적으로 수집하고 싶지만, 이를 위해 AWS EC2나 Lightsail 같은 가상 사설 서버(VPS)를 24시간 켜두는 것은 비용과 관리 측면에서 매우 비효율적입니다. 한 달에 몇 번 돌지도 않는 가벼운 스크립트를 위해 매달 $5~$10씩 클라우드 비용을 지불하고 있지는 않으신가요?

소프트웨어 엔지니어링의 본질은 불필요한 오버헤드를 제거하는 데 있습니다. 본 가이드에서는 GitHub에서 기본 제공하는 CI/CD 도구인 **GitHub Actions**의 `cron` 스케줄러를 활용하여, **인프라 유지비 0원**으로 무중단 파이썬 자동화 크롤러를 구축하는 실전 파이프라인을 다룹니다. 코드 실행부터 수집된 데이터의 깃(Git) 자동 커밋, 그리고 디스코드(Discord) 웹훅 알림 연동까지 단계별로 완벽히 마스터해보세요.

---

## 1. 왜 깃허브 액션(GitHub Actions)인가? (배경 및 장단점 분석)

전통적인 주기적 배치(Batch) 작업은 리눅스 서버의 `crontab`에 스크립트를 등록하거나 AWS Lambda + EventBridge 조합을 사용하는 것이 일반적이었습니다. 하지만 GitHub Actions를 스케줄러로 활용하면 다음과 같은 강력한 이점을 누릴 수 있습니다.

- **완전 무과금 인프라**: 공개(Public) 저장소는 무료 실행 시간이 **무제한**이며, 비공개(Private) 저장소 역시 매월 **2,000분**의 무료 빌드 타임을 기본 제공합니다. 1회 실행에 1분 미만이 소요되는 경량 크롤러라면 하루 수십 번을 실행해도 한도를 넘지 않습니다.
- **GitOps 기반 데이터 영속화**: 크롤링한 JSON, CSV 데이터를 별도의 데이터베이스나 S3 버킷 없이 GitHub 저장소 자체에 `git push`하여 변경 이력을 자동으로 버전 관리할 수 있습니다.
- **보안 환경 변수 격리**: 민감한 API 토큰, 웹훅 URL을 `GitHub Secrets`를 통해 암호화하여 안전하게 주입할 수 있습니다.

다만, GitHub Actions 러너는 공유 인프라에서 구동되므로 트래픽이 몰리는 시간대에는 `cron` 실행이 수 분에서 수십 분 지연될 수 있다는 점(정확한 실시간성 부족)을 고려해야 합니다. 따라서 1초 단위의 정밀 배치가 아닌, 주기적 정보 수집 및 리포팅에 가장 최적화되어 있습니다.

---

## 2. 단계별 실전 구현 가이드

### Step 1: 디렉터리 구조 설계

프로젝트 루트 디렉터리에 다음과 같이 워크플로우 파일과 소스 코드를 배치합니다.

```bash
my-crawler/
├── .github/
│   └── workflows/
│       └── crawler.yml       # GitHub Actions 워크플로우 정의 파일
├── data/
│   └── latest_data.json      # 크롤링 결과가 저장될 파일
├── src/
│   └── crawler.py            # 크롤러 및 웹훅 전송 파이썬 스크립트
├── requirements.txt          # 파이썬 의존성 패키지 목록
└── README.md
```

### Step 2: 의존성 및 파이썬 크롤러 스크립트 작성

먼저 필요한 패키지를 `requirements.txt`에 명시합니다.

```text
requests>=2.31.0
beautifulsoup4>=4.12.0
```

다음으로 웹 데이터를 수집하고, 결과를 JSON 파일로 저장한 뒤, 디스코드 채널로 알림을 발송하는 `src/crawler.py`를 작성합니다.

```python
import os
import json
import datetime
import requests
from bs4 import BeautifulSoup

def fetch_target_data():
    """대상 웹사이트에서 최신 데이터를 스크래핑합니다."""
    url = "https://news.ycombinator.com/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, "html.parser")
    items = []
    
    # 상위 5개 타이틀 수집 예제
    rows = soup.select(".titleline > a")[:5]
    for idx, row in enumerate(rows, start=1):
        items.append({
            "rank": idx,
            "title": row.get_text(strip=True),
            "link": row.get("href")
        })
    return items

def save_to_json(data):
    """데이터를 data/latest_data.json 경로에 저장합니다."""
    os.makedirs("data", exist_ok=True)
    filepath = os.path.join("data", "latest_data.json")
    
    payload = {
        "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "count": len(data),
        "items": data
    }
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[INFO] Data saved to {filepath}")

def send_discord_notification(data):
    """디스코드 웹훅으로 요약 리포트를 전송합니다."""
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("[WARN] DISCORD_WEBHOOK_URL not found. Skipping alert.")
        return

    fields = []
    for item in data:
        fields.append({
            "name": f"#{item['rank']} {item['title'][:40]}",
            "value": f"[링크 바로가기]({item['link']})",
            "inline": False
        })

    embed = {
        "title": "📢 자동 수집 크롤러 데일리 리포트",
        "description": f"수집 시간(UTC): {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}",
        "color": 3447003,
        "fields": fields
    }

    resp = requests.post(webhook_url, json={"embeds": [embed]}, timeout=10)
    if resp.status_code == 204:
        print("[INFO] Discord alert sent successfully.")
    else:
        print(f"[ERROR] Failed to send Discord alert: {resp.status_code}, {resp.text}")

if __name__ == "__main__":
    print("[START] Starting Crawler Task...")
    scraped_data = fetch_target_data()
    save_to_json(scraped_data)
    send_discord_notification(scraped_data)
    print("[SUCCESS] Crawler Task Completed.")
```

### Step 3: GitHub Secrets 환경 변수 등록

디스코드 웹훅 URL과 같은 민감 정보는 코드에 하드코딩해서는 안 됩니다.

1. GitHub 저장소의 **Settings** 탭으로 이동합니다.
2. 좌측 메뉴에서 **Secrets and variables** > **Actions**를 클릭합니다.
3. **New repository secret** 버튼을 누르고 Name에 `DISCORD_WEBHOOK_URL`, Value에 디스코드 채널 웹훅 주소를 입력한 뒤 저장합니다.


<!-- article-illustration:absian-2026-09-11-0-github-actions-01 -->
<figure class="article-illustration" style="margin: 2em 0;">
  <img src="/images/articles/absian-2026-09-11-0-github-actions-01.webp" alt="예약 신호로 실행한 작업이 자료를 파일로 남긴 뒤 종료되는 그림" width="1536" height="1024" loading="lazy" decoding="async" style="display: block; width: 100%; max-width: 100%; height: auto; border-radius: 0.75rem;" />
  <figcaption style="margin-top: 0.65em; font-size: 0.95em; line-height: 1.6; color: #475569;">예약 작업의 실행, 수집 결과 저장과 종료를 나누어 확인합니다. AI로 제작한 설명용 이미지입니다.</figcaption>
</figure>
<!-- /article-illustration:absian-2026-09-11-0-github-actions-01 -->

### Step 4: 워크플로우 YAML 작성 (`.github/workflows/crawler.yml`)

이제 스케줄링을 제어할 GitHub Actions 워크플로우를 정의합니다. UTC 시간 기준 매일 오전 0시(한국 시간 오전 9시)에 실행되도록 설정하고, 수동 디버깅을 위해 `workflow_dispatch` 트리거를 포함합니다.

```yaml
name: Daily Scheduled Python Crawler

on:
  schedule:
    # UTC 기준 00:00 (KST 기준 매일 오전 09:00)
    - cron: '0 0 * * *'
  workflow_dispatch: # Actions 탭에서 수동 실행 버튼 활성화

permissions:
  contents: write # 깃 커밋 및 푸시 권한 명시

jobs:
  run-crawler:
    runs-on: ubuntu-latest

    steps:
      - name: Check out repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip' # 패키지 캐싱으로 빌드 시간 대폭 단축

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Execute Crawler
        env:
          DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}
        run: |
          python src/crawler.py

      - name: Commit and Push if changes exist
        run: |
          git config --global user.name "github-actions[bot]"
          git config --global user.email "github-actions[bot]@users.noreply.github.com"
          git add data/
          
          # 변경 사항이 있을 때만 커밋 수행 (무한 루프 방지 [skip ci] 포함)
          if git diff --staged --quiet; then
            echo "No data changes detected. Skipping commit."
          else
            git commit -m "chore: update crawled data $(date +'%Y-%m-%d') [skip ci]"
            git push
          fi
```

---

## 3. 자동화 인프라 도구 비교 분석

파이썬 자동화 스크립트를 주기적으로 구동할 수 있는 3가지 대표적인 인프라를 비교해보겠습니다.

| 비교 항목 | GitHub Actions (스케줄러) | AWS Lambda + EventBridge | 클라우드 VPS (AWS Lightsail 등) |
| :--- | :--- | :--- | :--- |
| **월간 인프라 비용** | **0원 (완전 무료)**<br>(Public 무제한 / Private 월 2,000분) | **0원 ~ 소액 과금**<br>(프리티어 초과 시 호출당 비용 발생) | **매월 $3.5 ~ $10 고정 비용**<br>(인스턴스 상시 가동 필수) |
| **환경 구성 난이도** | **매우 낮음**<br>(YAML 파일 하나로 OS 및 패키지 정의) | **보통**<br>(ZIP 아카이빙 또는 컨테이너 이미지 빌드 필요) | **높음**<br>(OS 패치, 방화벽, Linux crontab 수동 설정) |
| **최대 실행 시간** | **단일 작업당 최대 6시간 (360분)** | **호출당 최대 15분** | **무제한 (24시간 상시 데몬 가능)** |
| **스케줄 정시성** | **상대적 (수 분~수십 분 큐 대기 가능)** | **절대적 (초 단위 정밀 트리거)** | **절대적 (시스템 로컬 cron 정확 구동)** |
| **데이터 저장 방식** | **Git 저장소 자동 커밋 (GitOps)** | S3 버킷, DynamoDB 등 외부 스토리지 필수 | 로컬 파일시스템, SQLite 직접 저장 가능 |
| **최적 추천 시나리오** | **일/주 단위 배치 수집, 정적 리포팅, 개인 프로젝트** | 초/분 단위 실시간 이벤트 처리, 대규모 API 트리거 | 실시간 웹소켓 연결, 24시간 헤드리스 브라우저 구동 |

---

## 4. 실무 트러블슈팅 및 성능 최적화 팁

### 1) GitHub `cron` 스케줄 지연(Delay) 극복법
GitHub Actions의 `schedule` 이벤트는 전 세계 수많은 개발자의 작업과 동일한 큐를 공유합니다. 특히 정각(예: `0 0 * * *`)이나 30분 단위에는 부하가 집중되어 실행이 최대 30분 이상 지연될 수 있습니다.
> **💡 실무 팁**: 정각 실행을 피해 `17 0 * * *`처럼 분 단위를 임의의 소수(Prime number)로 지정하면 대기열 병목을 피하고 훨씬 빠르게 러너를 할당받을 수 있습니다.

### 2) 깃 자동 커밋 시 `[skip ci]` 필수 명시
데이터를 수집한 후 변경된 JSON을 다시 리포지토리에 푸시할 때, 커밋 메시지에 `[skip ci]` 키워드를 누락하면 푸시 이벤트에 의해 워크플로우가 다시 트리거되는 무한 빌드 루프에 빠질 수 있습니다. 커밋 명령문에 반드시 `[skip ci]` 또는 `[ci skip]`을 포함하세요.

### 3) 러너 실행 시간 단축으로 쿼터 절약하기
- **캐싱 적극 활용**: `actions/setup-python`의 `cache: 'pip'` 옵션을 켜두면 매번 패키지를 다운로드하지 않고 캐시된 레이어를 재사용하므로 실행 시간이 10~20초 이상 단축됩니다.
- **경량 라이브러리 선택**: 무거운 Selenium 대신 `requests`와 `BeautifulSoup`을 우선 고려하고, 동적 렌더링이 필수적인 경우에만 Playwright Headless 모드를 최소화하여 구동하세요.

### 4) `403 Forbidden` 차단 대응
GitHub Actions 러너의 Azure 공인 IP 대역은 일부 사이트의 WAF(Cloudflare, Akamai 등)에서 봇으로 인지하여 차단할 수 있습니다. 헤더에 실제 브라우저와 유사한 `User-Agent`와 `Accept-Language`를 반드시 정의하고, 세션 간 무작위 딜레이(`time.sleep`)를 부여하는 것이 안전합니다.

---

## 5. 결론 및 권장 워크플로우

### 📌 3줄 핵심 요약
1. **비용 0원 달성**: GitHub Actions의 `schedule` 트리거를 활용하면 고정 서버 비용 없이 완벽한 서버리스 파이썬 배치 파이프라인을 구축할 수 있습니다.
2. **GitOps 파이프라인**: 데이터 수집 결과물을 `git commit`으로 리포지토리에 직접 영속화하여 별도의 DB 없이도 버전 관리가 가능합니다.
3. **안전한 모니터링**: `GitHub Secrets`를 통한 보안 토큰 관리와 디스코드/텔레그램 웹훅을 결합해 안정적인 장애 대응 및 리포팅 체계를 완성할 수 있습니다.

수동으로 확인하던 웹 데이터가 있다면, 지금 바로 저장소에 `.github/workflows/crawler.yml`을 추가하고 `workflow_dispatch` 버튼을 눌러 첫 번째 무료 자동화 파이프라인을 가동해보세요.
