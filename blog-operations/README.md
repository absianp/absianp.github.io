# Codex + agy 블로그 운영

Codex가 총괄·본문·이미지·근거 검토를 맡고 agy가 자료 정리·메타데이터를 맡습니다. HTTP/파일 검사와 지표 계산은 코드가 수행합니다. 기존 생성·보고 타이머는 중지한 상태이며 새 AI 생성은 요청할 때만 실행됩니다.

## 실행

```bash
cd ~/BLOG/auto_blog_system/blog-operations
PYTHON=../automation-pipeline/venv/bin/python3
$PYTHON manage.py status
$PYTHON manage.py audit --site all
$PYTHON manage.py metrics --site all
$PYTHON manage.py report
```

실측 미연결·수집 실패·API 빈 응답은 실제 0과 구분합니다. GitHub 저장소 조회를 블로그 방문으로 사용하지 않습니다. 수익은 계정 전체를 중복 집계하지 않고 사이트별로 분리하며 실제 통화·기간을 표시합니다. 추정 광고 수익과 확정 지급액은 다릅니다.

운영 상태·작업·근거·보고서는 `~/.local/state/blog-operations/`에 저장됩니다. 기존 글과 JSON 대기열은 보존합니다. `BLOGOPS_STATE_DIR`와 `BLOGOPS_BLOG_ROOT`로 격리된 테스트 경로를 지정할 수 있습니다.

## 계정 연결

사용자 소유 Google Cloud 프로젝트의 OAuth **데스크톱 앱** 클라이언트 JSON을 준비하고 AdSense Management API, Search Console API, Google Analytics Data API를 활성화합니다. 아래 명령은 브라우저에서 사용자가 계정과 읽기 권한을 선택하게 합니다. 자격증명을 대화나 Git에 붙여 넣지 마세요.

```bash
$PYTHON manage.py connect-google --client-secrets /절대경로/client.json
$PYTHON manage.py configure-site --site absian --ga4-property 실제숫자속성ID
$PYTHON manage.py metrics --site all
```

각 Search Console 기본 URL 속성은 `sites.json`에 있으며 해당 속성에 접근 권한이 있어야 합니다. GA4 측정 ID `G-...`와 숫자 속성 ID는 다릅니다. OAuth 연결 실패·심사 사유·본인확인 등 계정에서만 알 수 있는 항목은 운영자가 확인해야 합니다. 연결 전에는 수익을 예측값으로 채우지 않습니다.

## 글 한 편의 협업 흐름

```bash
$PYTHON manage.py draft --site absian \
  --topic '주제' --source 'https://공식출처/문서' \
  --value '독자가 얻을 구체적인 원본 가치' --run
```

흐름: 출처 수집 → agy 출처 발췌 → Codex 기획 → Codex 작성 → agy 메타데이터 → GPT 이미지 3장 → Codex 원문·이미지 검토 → 기존 대기열 등록. 원본 가치와 공식 출처가 필요합니다. 자료가 부족하거나 중요한 주장·이미지 오류가 있으면 보류합니다. 근거 인용의 존재를 코드로 검사하지만 사실 전체의 완전한 증명을 뜻하지 않으므로 최종 사람 검토를 유지합니다.

사용자 검토 뒤에만 발행하며, 푸시 후에는 Pages 작업과 공개 글·이미지 해시가 확인되어야 완료 처리합니다. 중간 단계가 실패하면 기존 결과를 유지합니다. 기존 글 개선은 같은 명령에 `--existing-slug 정확한슬러그`를 추가합니다. 기존 글을 근거로 간주하지 않고 제공한 공식 출처로 다시 검토합니다. 신규·수정 작업은 동일한 하루 작업 한도를 공유합니다.

```bash
$PYTHON manage.py queue
$PYTHON manage.py retry 워크플로ID
$PYTHON manage.py run 워크플로ID
$PYTHON manage.py approve --site absian 초안ID --reviewed
$PYTHON manage.py reconcile --site absian 초안ID
```

`--reviewed`는 해당 본문·이미지·출처를 실제로 확인했다는 운영자의 승인입니다. 글이 바뀌면 승인이 무효화됩니다. 생성 모델은 승인하지 못합니다. `reconcile`은 승인된 배포를 다시 확인하며 새 글을 만들거나 다시 승인하지 않습니다.

## 실행 기록과 준비된 이미지 연결

실제 실행한 예제·테스트 보고서는 `draft --verification-file /절대경로/보고서.json`으로 전달합니다. 옵션을 반복해 검증된 `.py` 코드와 관측 `.md`를 함께 보낼 수 있습니다. 생성 시점의 내용·SHA256을 작업 큐에 저장하고 웹 출처와 구분합니다. 모델에게 실제 실행하지 않은 결과를 제공하면 안 됩니다.

검증 자료로 전달한 `.py` 파일은 원고의 단일 `python` 코드 블록에 원문 그대로 포함되어야 합니다. 초안과 최종 검토 단계에서 일치 여부를 검사합니다. 수정이 필요한 모델 결과도 작업 기록에 보존하므로, 거절 사유를 확인한 뒤 수정할 수 있습니다.

공식 문서 URL에 `#절`이 있으면 해당 절을 수집합니다. 절을 찾지 못하면 다른 문단으로 대체하지 않고 작업을 중단합니다.

`--image-assets /절대경로/assets.json`을 지정하면 검증한 기존·준비된 이미지 3장을 연결합니다. 각 항목에는 `role`(`thumbnail`, `body-1`, `body-2`), `/images/` 로컬 `url`, 실제 `sha256`, `provenance`(`reused` 또는 `generated`)가 필요합니다. 본문 이미지에는 `alt`, `caption`, 선택적으로 `before_heading`을 넣습니다. 지정한 H2 제목이 없으면 본문 끝에 넣습니다. 파일이 바뀌면 연결을 거부하고, 새 이미지 생성 호출은 하지 않습니다. 별도로 이미지를 생성했다면 그 호출은 운영 한도에 기록합니다. 최종 Codex 검토에는 연결한 실제 이미지가 첨부됩니다.

## 텔레그램

새 봇은 기존 사이트별 봇 토큰을 재사용합니다. 시작만으로 모델을 호출하거나 알림을 발송하지 않습니다. 기존 봇 데몬은 동시에 실행하면 안 됩니다.

- `/ops`: 사이트 점검·실측 상태
- `/queue`: 기존·신규 대기 초안
- `/review 초안ID`: 실제 본문·이미지 검토와 해당 버전 승인 버튼
- `/approve 초안ID`: 먼저 확인한 버전 승인
- `/reconcile 초안ID`: 이미 승인한 배포의 완료 확인
- `/reject 초안ID`: 미발행 초안 보류
- `/repair 기존글슬러그 | 수정 목적·독자 가치 | 공식출처URL1 URL2`: 기존 URL을 유지하는 수정 작업
- `/write 주제 | 독자에게 줄 가치 | 공식출처URL1 URL2`: 협업 생성 요청
- `/audit`, `/metrics`, `/usage`: 점검·실측·호출량 확인

현재 설정은 개인 관리자 Chat ID와 사용자 ID가 같은 개인 대화를 기본으로 합니다. 그룹을 쓰면 `TELEGRAM_ADMIN_USER_ID`를 추가해 관리자를 명시해야 합니다. 모델에게는 봇 토큰·Google 토큰을 전달하지 않습니다.

```bash
bash deploy/install_bots.sh
systemctl --user status blog-ops-bot@absian.service
```

## 비용과 실행 한도

초기 한도는 전체 신규 워크플로 하루 1개, Codex 하루 8호출, agy 하루 12호출, 사이트별 검토 대기 워크플로 6개입니다. 이미지 3장도 Codex 호출 3회로 예약합니다. 실패한 호출도 기록되며, 한도를 올리기 전에 실제 작업 결과를 확인합니다. 이 횟수는 OpenAI/agy의 요금표나 계정 잔여량을 뜻하지 않습니다.

기본 모델은 기존 GPT `gpt-6-astra`, 설치된 agy 목록에서 확인한 일반 작업 모델 `gemini-3.8-flash-low`입니다. agy가 항상 더 저렴하거나 빠르다고 가정하지 않습니다. 설정 재정의는 상태 디렉터리 `settings.json`의 `limits`·`providers`에서 합니다. 핵심 판단은 Codex 제한 시 agy로 자동 대체하지 않습니다.

agy 형식 오류는 한 번 재시도하고 계속 실패하면 Codex로 인계합니다. 원본 자료·변경 범위와 관계없는 결과는 검사에서 거부합니다. 어떤 방식도 Google의 승인이나 수익을 보장하지 않습니다.

## 검증

```bash
$PYTHON -m unittest discover -s tests -v
```

회귀 테스트는 임시 상태 디렉터리·가짜 API/모델 응답을 사용합니다. 실제 발행·광고 클릭·운영자 메시지는 테스트하지 않습니다. 실제 CLI 연결 시험은 작은 일반 작업으로 별도 실시하고 사용량을 기록합니다.

Codex 실행 참고: [공식 비대화형 실행 문서](https://learn.chatgpt.com/docs/non-interactive-mode).
