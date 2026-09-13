---
title: 파이썬 자동화 스크립트 작성 시 API 호출 제한(Rate Limit) 대응과 안전한 환경변수 관리법
description: 파이썬 자동화 스크립트 운영 시 발생하는 HTTP 429 호출 제한 오류를 지수 백오프로 해결하고, API 키 유출을 방지하기
  위한 python-dotenv 환경변수 분리 및 체크포인트 설계 방법을 다룹니다.
category: 개발 & 테크
tags:
- 파이썬 자동화
- API 연동
- 예외 처리
- python-dotenv
- 보안 가이드
pubDate: '2026-09-13'
author: 앱시안 (absian)
readingTime: 8분
featured: false
draft: false
faqs:
- question: '429 에러가 발생했을 때 고정 시간(예: time.sleep(1))으로만 대기하면 왜 문제가 되나요?'
  answer: 고정 시간 대기는 일시적인 네트워크 병목이나 서버 큐 누적 상황을 충분히 해소하지 못할 수 있습니다. 또한 여러 워커 스크립트가
    동시에 같은 주기로 재시도하면 다시 동시에 429를 유발하는 쏠림 현상(Thundering Herd)이 발생합니다. 점진적으로 대기 시간을
    늘리는 지수 백오프와 난수 지연(Jitter)을 함께 적용해야 안전합니다.
- question: 실수로 .env 파일이 깃허브 공개 저장소에 커밋되어 올라갔을 때는 어떻게 대처하나요?
  answer: 단순히 다음 커밋에서 .env를 삭제하더라도 커밋 히스토리에 키가 그대로 남아있습니다. 즉시 해당 API 제공사 콘솔에 접속하여
    기존 키를 무효화(Revoke)하고 재발급받아야 합니다. 이후 git filter-repo나 BFG Repo-Cleaner 등의 도구로 Git
    히스토리에서 해당 커밋 내역을 영구 제거해야 합니다.
- question: 체크포인트 저장 시 JSON 파일과 SQLite 중 어떤 것을 선택해야 하나요?
  answer: 수천 건 이하의 단일 스크립트 순차 처리 환경에서는 설정이 간편한 JSON 파일로도 충분합니다. 그러나 처리 데이터가 수만 건 이상이거나
    여러 프로세스가 동시에 상태를 읽고 써야 하는 환경이라면 원자적(Atomic) 트랜잭션과 인덱싱을 지원하는 SQLite를 사용하는 것이 안전합니다.
heroImage: /images/thumbnails/2026-09-13-api-rate-limit.svg
---

<!-- article-illustration:absian-2026-09-13-api-rate-limit-01 -->
<figure class="article-illustration" style="margin: 2em 0;">
  <img src="/images/articles/absian-2026-09-13-api-rate-limit-01.webp" alt="파이썬 자동화 스크립트 작성 시 API 호출 제한(Rate Limit) 대응과 안전한 환경변수 관리법 - 주요 기술 아키텍처 설명 다이어그램" width="1536" height="1024" loading="lazy" decoding="async" style="display: block; width: 100%; max-width: 100%; height: auto; border-radius: 0.75rem;" />
  <figcaption style="margin-top: 0.65em; font-size: 0.95em; line-height: 1.6; color: #475569;">주요 기술 아키텍처의 핵심 구조와 워크플로우를 정리한 다이어그램입니다. AI로 제작한 설명용 이미지입니다.</figcaption>
</figure>
<!-- /article-illustration:absian-2026-09-13-api-rate-limit-01 -->

파이썬으로 외부 API를 연동해 자동화 스크립트를 실행할 때 가장 빈번하게 발생하는 문제는 API 키 하드코딩으로 인한 보안 위험과 요청 횟수 초과에 따른 `HTTP 429 (Too Many Requests)` 오류입니다.

안정적인 자동화 파이프라인을 구축하려면 민감 정보를 코드 외부로 분리하고, 호출 제한 도달 시 점진적으로 대기 시간을 늘리는 지수 백오프(Exponential Backoff) 및 작업 중단에 대비한 체크포인트 저장 로직을 적용해야 합니다.

---

### 1. 작업 환경 및 패키지 준비

본 튜토리얼은 표준적인 파이썬 환경을 기준으로 작성되었습니다.

* **권장 환경**: Python 3.10 이상
* **주요 패키지**:
  * `python-dotenv`: 로컬 `.env` 파일의 환경변수 로드
  * `requests`: HTTP 통신
  * `tenacity`: 지수 백오프 및 재시도 로직 구현

다음 명령어로 필요한 라이브러리를 설치합니다.

```bash
pip install python-dotenv requests tenacity
```

> **[실행 검증 안내]**
> 본 문서에 수록된 파이썬 예제 코드는 표준 라이브러리 규격 및 공식 문서 기반으로 작성되었으나, 개별 서드파티 API 서버와의 라이브 연동에 대한 **실행 검증은 미실시**된 상태입니다. 실무 적용 전 대상 API 명세서에 맞춰 단위 테스트를 진행하시기 바랍니다.

---

### 2. .env 파일과 .gitignore를 활용한 환경변수 분리

소스 코드 내부에 API Key나 비밀번호를 직접 작성(하드코딩)하면 GitHub 등의 원격 저장소에 노출될 위험이 큽니다. 환경변수를 파일로 분리하고 버전 관리 대상에서 제외해야 합니다.

#### (1) `.env` 파일 작성
프로젝트 루트 디렉터리에 `.env` 파일을 생성하고 키-값 쌍으로 설정합니다.

```env
# .env
API_BASE_URL=https://api.example.com/v1
SERVICE_API_KEY=your_actual_api_key_here
MAX_RETRIES=5
```

#### (2) `.gitignore` 등록
`.env` 파일이 Git 커밋에 포함되지 않도록 `.gitignore` 파일에 추가합니다.

```gitignore
# .gitignore
.env
__pycache__/
*.log
```

#### (3) 파이썬 스크립트에서 환경변수 로드 [실행 검증 미실시]

```python
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL")
API_KEY = os.getenv("SERVICE_API_KEY")

# 필수 환경변수 검증
if not API_KEY:
    raise ValueError("환경변수 'SERVICE_API_KEY'가 설정되지 않았습니다. .env 파일을 확인하세요.")
```

* **예상 결과**: `.env`에 정의된 키 값이 메모리에 로드되어 `os.getenv()`로 접근 가능합니다.
* **오류 대처**: 만약 `API_KEY`가 `None`으로 반환된다면, 실행 경로(CWD)와 `.env` 파일의 위치가 일치하는지 확인하거나 `load_dotenv(dotenv_path="경로/.env")`로 명시적 경로를 지정해야 합니다.

---

### 3. HTTP 429 오류 대응: 지수 백오프(Exponential Backoff) 재시도

API 제공사는 서버 부하를 방지하기 위해 분당/초당 호출 횟수(Rate Limit)를 제한합니다. 한도를 초과하면 `429 Too Many Requests` 상태 코드를 반환합니다. 이때 즉시 재요청을 반복하면 IP 차단으로 이어질 수 있으므로 점진적으로 대기 시간을 늘려야 합니다.

#### (1) `tenacity` 라이브러리를 활용한 재시도 구현 [실행 검증 미실시]

`tenacity`는 조건부 재시도와 무작위 지터(Jitter, 동시 재요청 충돌 방지용 임의 지연)를 쉽게 구현할 수 있도록 돕습니다.

```python
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
    retry_if_exception_type
)

class RateLimitException(Exception):
    """429 Too Many Requests 발생 시 던질 사용자 정의 예외"""
    pass

# 지수 백오프 설정: 최소 1초부터 최대 60초까지 대기하며 지터 추가, 최대 5회 시도
@retry(
    retry=retry_if_exception_type(RateLimitException),
    wait=wait_random_exponential(multiplier=1, max=60),
    stop=stop_after_attempt(5),
    reraise=True
)
def fetch_data_with_backoff(url: str, headers: dict) -> dict:
    response = requests.get(url, headers=headers, timeout=10)
    
    if response.status_code == 429:
        # 서버가 Retry-After 헤더를 제공하는지 확인
        retry_after = response.headers.get("Retry-After")
        print(f"[경고] Rate Limit 도달. HTTP 429 발생 (서버 안내 Retry-After: {retry_after})")
        raise RateLimitException("Rate limit exceeded")
        
    response.raise_for_status()
    return response.json()
```

* **동작 방식**: 429 응답이 오면 `RateLimitException`을 발생시키고, `tenacity` 데코레이터가 대기 시간을 늘려가며 최대 5회까지 재시도합니다.
* **오류 대처**: 최대 재시도 횟수 초과 후 발생하는 예외는 상위 호출부에서 `try-except`로 포착하여 로깅 후 스크립트를 안전하게 정지시켜야 합니다.

#### (2) 표준 `urllib3` 기반의 Retry 대안 [실행 검증 미실시]
외부 라이브러리 의존성을 최소화하려면 `requests.adapters.HTTPAdapter`와 `urllib3.util.Retry`를 조합할 수도 있습니다.

```python
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

def create_resilient_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1,  # 1초, 2초, 4초, 8초 ... 형태로 대기
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
```

---

### 4. 클라이언트 측 선제적 속도 제한(Rate Limiting)

429 오류를 사후에 처리하는 것보다, 클라이언트가 API의 분당 호출 허용량(예: 분당 60회 = 초당 1회)을 초과하지 않도록 선제적으로 제어하는 것이 바람직합니다.

#### 간단한 호출 간격 보장 로직 [실행 검증 미실시]

```python
import time

class SimpleRateLimiter:
    def __init__(self, calls_per_second: float = 1.0):
        self.interval = 1.0 / calls_per_second
        self.last_call = 0.0

    def wait(self):
        now = time.time()
        elapsed = now - self.last_call
        if elapsed < self.interval:
            time.sleep(self.interval - elapsed)
        self.last_call = time.time()
```

* **사용법**: API 호출 직전에 `limiter.wait()`를 호출하여 스크립트 실행 간격이 지정된 초당 호출 수를 넘지 않도록 맞춥니다.

---

### 5. 작업 중단에 대비한 로컬 체크포인트 저장 구조

대량의 데이터를 처리하던 중 네트워크 단절이나 일일 할당량 소진으로 스크립트가 강제 종료되면, 처음부터 다시 요청해야 하므로 비용과 쿼터가 낭비됩니다. 처리 완료된 ID나 인덱스를 파일에 지속적으로 기록해야 합니다.

#### JSON 기반 체크포인트 관리 예시 [실행 검증 미실시]

```python
import json
from pathlib import Path

CHECKPOINT_FILE = Path("checkpoint.json")

def load_checkpoint() -> set:
    if CHECKPOINT_FILE.exists():
        try:
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("completed_ids", []))
        except (json.JSONDecodeError, IOError):
            return set()
    return set()

def save_checkpoint(completed_ids: set):
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump({"completed_ids": list(completed_ids)}, f, indent=2)
```

* **활용 절차**:
  1. 작업 시작 전 `load_checkpoint()`로 이미 처리된 ID 목록을 불러옵니다.
  2. 전체 대상 목록 중 처리 완료된 ID를 필터링하여 제외합니다.
  3. 배치 단위(예: 매 20건 처리 시) 또는 단건 처리 완료 시 `save_checkpoint()`를 호출합니다.

---

### 6. 참고 공식 출처 및 확인 필요 항목

#### 공식 출처 링크
* [Python os.environ 공식 문서](https://docs.python.org/3/library/os.html)
* [python-dotenv 공식 PyPI 페이지](https://pypi.org/project/python-dotenv/)
* [Tenacity 공식 문서](https://tenacity.readthedocs.io/)
* [urllib3.util.Retry 공식 레퍼런스](https://urllib3.readthedocs.io/en/stable/reference/urllib3.util.html)

#### 확인 필요 항목
* **대상 API의 규격 확인 필요**: 연동하려는 외부 API 제공사마다 429 응답 시 `Retry-After` 헤더를 초(초 단위 숫자)로 반환하는지, HTTP 타임스탬프로 반환하는지 규격 확인이 필요합니다.
* **동시성 환경 검토 필요**: 단일 프로세스가 아닌 멀티 프로세스나 분산 워커 환경에서 실행할 경우, 파일 기반 체크포인트(JSON) 대신 Redis 또는 SQLite와 같은 트랜잭션 지원 저장소를 도입해야 동시성 충돌을 방지할 수 있습니다.

<!-- article-illustration:absian-2026-09-13-api-rate-limit-02 -->
<figure class="article-illustration" style="margin: 2em 0;">
  <img src="/images/articles/absian-2026-09-13-api-rate-limit-02.webp" alt="파이썬 자동화 스크립트 작성 시 API 호출 제한(Rate Limit) 대응과 안전한 환경변수 관리법 - 실전 적용 및 최적화 전략 실전 가이드 다이어그램" width="1536" height="1024" loading="lazy" decoding="async" style="display: block; width: 100%; max-width: 100%; height: auto; border-radius: 0.75rem;" />
  <figcaption style="margin-top: 0.65em; font-size: 0.95em; line-height: 1.6; color: #475569;">실전 적용 및 최적화 전략의 주요 구현 단계와 최적화 포인트를 정리한 다이어그램입니다. AI로 제작한 설명용 이미지입니다.</figcaption>
</figure>
<!-- /article-illustration:absian-2026-09-13-api-rate-limit-02 -->

