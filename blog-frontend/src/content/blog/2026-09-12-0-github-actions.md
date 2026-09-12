---
title: GitHub Actions로 아침 RSS 링크를 텔레그램에 보내기
description: Python으로 RSS 제목과 링크를 읽어 텔레그램에 보내고 GitHub Actions에서 예약 실행합니다. 비용 조건, 중복 발송과 예약 지연의 한계를 함께 설명합니다.
pubDate: '2026-09-12'
category: 개발 & 테크
tags:
- GitHub Actions
- RSS
- 텔레그램
- Python
author: 앱시안 (absian)
readingTime: 9 min read
featured: false
draft: false
faqs:
- question: 예약을 오전 8시 17분으로 하면 그 시각에 꼭 오나요?
  answer: GitHub 예약 실행은 지연되거나 누락될 수 있습니다. 예제의 23:17 UTC는 한국 시각 다음 날 08:17 예약이지만 정확한 수신 시각을 보장하지 않습니다.
- question: 한 번 실행한 링크는 다음 날 제외되나요?
  answer: 이 예제는 전송 이력을 저장하지 않아 피드 상단이 같으면 같은 링크를 다시 보냅니다. 새 항목만 발송하려면 지속 저장소와 상태 관리가 추가로 필요합니다.
updatedDate: '2026-09-12'
---

PC를 계속 켜 두지 않고 아침에 RSS의 새 제목과 링크를 확인하고 싶다면 GitHub Actions에서 짧은 스크립트를 실행할 수 있습니다. 아래 예제는 지정한 RSS 2.0 피드의 앞쪽 세 항목을 텔레그램으로 보내는 구성입니다.

“정해진 시각에 반드시 보내는 알림”과는 용도를 구분해야 합니다. GitHub는 예약 실행이 혼잡한 시간에 지연될 수 있고, 부하가 충분히 크면 대기 중인 작업이 누락될 수 있다고 안내합니다. [GitHub 예약 실행 문서](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

## 연습할 RSS와 텔레그램 대화를 준비합니다

읽을 수 있도록 제공된 RSS 피드를 사용합니다. 이 예제는 일반 HTML 페이지나 Atom 피드를 파싱하지 않습니다. 접근이 거절되면 요청 권한과 피드 주소를 확인하고, 브라우저를 흉내 내서 차단을 우회하는 방식으로 확장하지 않습니다.

텔레그램에서는 공식 BotFather로 봇을 만들고 본인의 대화에서 시작 메시지를 보냅니다. 봇이 보내도록 허용된 대화의 chat ID를 준비합니다. 토큰과 chat ID를 확인하는 방법은 [Telegram 봇 시작 안내](https://core.telegram.org/bots/tutorial)와 [Bot API](https://core.telegram.org/bots/api)를 따릅니다.

GitHub 저장소에는 다음 설정을 준비합니다.

- Actions secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- Actions variable: `RSS_URL` — 읽을 RSS 2.0 주소

토큰은 로그에 출력하거나 소스에 적지 않습니다. [GitHub Actions secrets 사용 안내](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions)

## Python 파일을 먼저 로컬에서 확인합니다

추가 패키지가 필요하지 않도록 표준 라이브러리를 사용했습니다. `main.py`로 저장합니다.

```python
import argparse
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


MAX_FEED_BYTES = 1000000


def build_message(xml_bytes):
    root = ET.fromstring(xml_bytes)
    lines = []
    for item in root.findall("./channel/item"):
        title = " ".join((item.findtext("title") or "").split())
        link = (item.findtext("link") or "").strip()
        if not title or urlparse(link).scheme not in {"http", "https"}:
            continue
        entry = f"{title[:160]}\n{link}"
        candidate = "\n\n".join([*lines, entry])
        if len(candidate.encode("utf-16-le")) // 2 > 3500:
            continue
        lines.append(entry)
        if len(lines) == 3:
            break
    if not lines:
        raise ValueError("RSS 2.0에서 보낼 항목을 찾지 못했습니다.")
    return "\n\n".join(lines)


def fetch_feed(url):
    if urlparse(url).scheme != "https":
        raise ValueError("HTTPS RSS 주소가 필요합니다.")
    request = Request(url, headers={"User-Agent": "PersonalRSSDigest/1.0"})
    with urlopen(request, timeout=20) as response:
        content = response.read(MAX_FEED_BYTES + 1)
    if len(content) > MAX_FEED_BYTES:
        raise ValueError("예제에서 처리할 피드 크기를 넘었습니다.")
    return content


def send_telegram(text):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    body = urlencode({
        "chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text
    }).encode("utf-8")
    request = Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body)
    try:
        with urlopen(request, timeout=20) as response:
            result = json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"Telegram HTTP {error.code}") from None
    except (URLError, TimeoutError):
        raise RuntimeError("Telegram 응답을 확인하지 못했습니다. 대화를 확인하세요.") from None
    if not result.get("ok"):
        raise RuntimeError("Telegram이 전송을 승인하지 않았습니다.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()
    message = build_message(fetch_feed(os.environ["RSS_URL"]))
    if args.send:
        send_telegram(message)
        print("텔레그램 API 전송 성공 응답을 받았습니다.")
    else:
        print(message)


if __name__ == "__main__":
    main()
```

`python main.py`는 RSS를 읽고 터미널에만 출력합니다. 제목과 링크가 맞는지 본 뒤 `python main.py --send`로 테스트 대화에 전송합니다. 이 글을 작성하며 실제 계정으로 메시지를 보내거나 GitHub 예약 실행을 검증하지는 않았습니다.

텔레그램 텍스트 제한을 고려해 메시지를 짧게 구성했고 Markdown 해석 옵션은 사용하지 않았습니다. [sendMessage 문서](https://core.telegram.org/bots/api#sendmessage)


<!-- article-illustration:absian-2026-09-12-0-github-actions-01 -->
<figure class="article-illustration" style="margin: 2em 0;">
  <img src="/images/articles/absian-2026-09-12-0-github-actions-01.webp" alt="예약 작업이 RSS 링크를 골라 메시지로 전달하는 아침 알림 그림" width="1536" height="1024" loading="lazy" decoding="async" style="display: block; width: 100%; max-width: 100%; height: auto; border-radius: 0.75rem;" />
  <figcaption style="margin-top: 0.65em; font-size: 0.95em; line-height: 1.6; color: #475569;">예약 실행과 실제 수신 시각, 같은 링크의 재발송 여부는 따로 확인합니다. AI로 제작한 설명용 이미지입니다.</figcaption>
</figure>
<!-- /article-illustration:absian-2026-09-12-0-github-actions-01 -->

## 예약 실행 파일을 추가합니다

`.github/workflows/rss-digest.yml`에 아래 내용을 저장합니다. 예제는 시간대 옵션을 생략해 UTC 기준으로 `23:17`에 예약했으며, 한국 시각으로는 다음 날 오전 `08:17`입니다.

```yaml
name: Morning RSS digest
on:
  workflow_dispatch:
  schedule:
    - cron: '17 23 * * *'
permissions:
  contents: read
concurrency:
  group: morning-rss-digest
  cancel-in-progress: false
jobs:
  send:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Send RSS links
        env:
          RSS_URL: ${{ vars.RSS_URL }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python main.py --send
```

워크플로 파일은 기본 브랜치에 있어야 예약 실행됩니다. 수동 실행으로 설정을 먼저 확인하고, 그다음 실제 예약 실행 기록과 수신 메시지를 확인하세요. 현재 GitHub는 시간대를 명시하는 설정도 지원하지만 이 예제에서는 UTC 표현식을 사용했습니다.

액션 버전 태그는 변경될 수 있습니다. 운영 저장소에서는 사용하려는 공식 액션 버전을 검토한 뒤 커밋 SHA로 고정하는 방법을 검토하세요. [GitHub Actions 보안 강화 안내](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions)

## 알림이 안 왔을 때 확인할 순서

1. Actions에 실행 기록이 없는지, 실행 중인지, 실패했는지 먼저 확인합니다.
2. 기록이 없다면 기본 브랜치의 파일, 예약식, 워크플로 활성 상태를 봅니다.
3. 실패했다면 RSS 주소, secrets·variable 이름, 봇의 대화 접근 권한을 확인합니다.
4. 전송 단계에서 타임아웃됐다면 메시지가 실제로 도착했는지 보고 재실행을 결정합니다.

공개 저장소에서는 60일 동안 저장소 활동이 없으면 예약 워크플로가 자동 비활성화될 수 있습니다. 이를 비공개 저장소에도 동일하게 적용되는 규칙이라고 설명하면 안 됩니다. 정각을 피한 예약은 혼잡을 줄이기 위한 선택이며 지연이 없다는 보장은 아닙니다.

이 코드는 마지막 전송 항목을 저장하지 않습니다. 피드 상단이 그대로면 다음 날 같은 링크를 다시 보냅니다. 새로운 항목만 보내려면 항목 ID나 링크를 보관할 지속 저장소와 전송 상태 처리가 더 필요합니다. 워크플로 재실행도 중복 발송을 만들 수 있습니다.

## 비용은 저장소와 러너 조건으로 확인합니다

공개 저장소의 표준 GitHub 호스팅 러너와 비공개 저장소의 포함 사용량 조건은 다릅니다. 큰 러너와 초과 사용, 저장 공간에도 별도 조건이 있습니다. 결제 수단과 예산 설정을 확인하지 않고 “초과해도 절대 청구되지 않는다”고 판단하면 안 됩니다. [GitHub Actions 과금 안내](https://docs.github.com/en/billing/concepts/product-billing/github-actions)

예제 동작이 확인되면 먼저 며칠의 실행 시간과 실패 기록을 확인합니다. 정확한 시각, 재전송 보장, 중복 방지가 필요한 업무로 확대할 때는 그 요구사항을 별도로 설계해야 합니다.
