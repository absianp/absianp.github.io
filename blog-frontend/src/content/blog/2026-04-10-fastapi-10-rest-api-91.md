---
title: 'FastAPI 첫 API 만들기: 메모 등록·조회와 422 오류 확인'
description: Python 가상환경에 FastAPI를 설치하고 메모를 등록·조회하는 작은 API를 만듭니다. 요청 검증, 404·422 응답과 메모리 저장의 한계를 설명합니다.
pubDate: 2026-04-10
category: 개발 & 테크
tags:
- FastAPI
- Python
- REST API
- 입력검증
author: 앱시안 (absian)
readingTime: 5 min read
featured: true
draft: false
faqs:
- question: 서버를 다시 켜니 메모가 없어졌습니다. 오류인가요?
  answer: 예제는 메모리를 저장소로 사용하므로 재시작하면 데이터가 사라집니다. 데이터를 유지하려면 별도 데이터베이스 저장이 필요합니다.
- question: 422 오류는 서버가 고장 났다는 뜻인가요?
  answer: 이 예제에서는 요청 값이 정한 조건에 맞지 않을 때 422를 반환합니다. 빈 문자열, 공백만 있는 값, 최대 길이 초과부터 확인하세요.
updatedDate: '2026-09-12'
---

FastAPI를 처음 배울 때는 작은 요청 하나가 끝까지 흐르는 것을 보는 편이 좋습니다. 이 글에서는 메모를 등록하고 ID로 조회하는 API를 만듭니다. 데이터베이스나 로그인은 붙이지 않고, 입력이 잘못됐을 때 어떤 응답이 나오는지도 확인합니다.

## 작업 폴더와 가상환경 만들기

Python 3.10 이상이 필요합니다. macOS와 Linux 터미널에서 다음 명령을 실행합니다. 이미 쓰는 프로젝트와 섞이지 않도록 별도 폴더를 사용하세요.

```bash
mkdir fastapi-note-demo
cd fastapi-note-demo
python3 -m venv .venv
source .venv/bin/activate
python -m pip install 'fastapi[standard]'
```

Windows PowerShell에서는 가상환경 생성 후 `.venv\Scripts\Activate.ps1`로 활성화합니다. 설치한 버전을 기록하려면 `python -m pip freeze > requirements.txt`를 실행합니다. [FastAPI 시작 안내](https://fastapi.tiangolo.com/tutorial/first-steps/)

## main.py에 등록과 조회를 구현합니다

```python
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="메모 연습 API")
notes: dict[str, str] = {}


class NoteInput(BaseModel):
    text: str = Field(min_length=1, max_length=200)


class NoteOutput(BaseModel):
    id: str
    text: str


@app.post("/notes", response_model=NoteOutput, status_code=201)
def create_note(note: NoteInput):
    text = note.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="공백만 저장할 수 없습니다.")
    note_id = str(uuid4())
    notes[note_id] = text
    return {"id": note_id, "text": text}


@app.get("/notes/{note_id}", response_model=NoteOutput)
def get_note(note_id: str):
    if note_id not in notes:
        raise HTTPException(status_code=404, detail="메모를 찾을 수 없습니다.")
    return {"id": note_id, "text": notes[note_id]}
```

`NoteInput`은 요청 본문의 형태를 정의합니다. 빈 문자열이나 200자를 넘는 값은 검증에서 거절합니다. 공백만 있는 문자열은 길이가 1 이상일 수 있으므로 별도로 검사했습니다. `NoteOutput`은 성공 응답의 형태입니다. [요청 본문 설명](https://fastapi.tiangolo.com/tutorial/body/)

저장은 Python 딕셔너리에만 합니다. 서버를 재시작하면 메모가 사라지고, 서버 프로세스를 여러 개 띄우면 각 프로세스가 별도 데이터를 가집니다. 개인 연습용 예제에 해당하는 구조입니다.

## 개발 서버에서 직접 요청합니다

`main.py`가 있는 폴더에서 실행합니다.

```bash
fastapi dev main.py
```

다른 터미널에서 메모 한 건을 등록합니다.

```bash
curl -i -X POST 'http://127.0.0.1:8000/notes' \
  -H 'Content-Type: application/json' \
  -d '{"text":"회의 전에 자료 확인"}'
```

정상 처리되면 상태 코드는 `201`이고 응답에 `id`와 `text`가 있습니다. 생성된 ID는 매번 달라집니다. 그 값을 아래의 `응답에서-받은-id` 부분에 넣어 조회합니다.

```bash
curl -i 'http://127.0.0.1:8000/notes/응답에서-받은-id'
```

브라우저에서는 `http://127.0.0.1:8000/docs`의 API 문서에서도 요청할 수 있습니다. 문서가 열린다는 것과 실제 등록·조회가 성공한다는 것은 다르므로 두 요청을 모두 확인하세요.

## 잘못된 요청도 확인해야 예제가 완성됩니다

| 요청 | 기대하는 응답 |
|---|---|
| `{"text":"회의 전에 자료 확인"}` 등록 | 201, 생성된 ID와 저장한 텍스트 |
| 반환된 ID 조회 | 200, 같은 메모 |
| 존재하지 않는 ID 조회 | 404 |
| `{"text":""}` 등록 | 422 |
| `{"text":"   "}` 등록 | 422 |
| `{"text":"가"를 201번 반복한 문자열}` 등록 | 422 |

외부 서버 없이 애플리케이션 동작을 검사하려면 같은 폴더에 `check.py`를 저장해 실행할 수 있습니다.

```python
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)
created = client.post("/notes", json={"text": "회의 전에 자료 확인"})
assert created.status_code == 201
saved = created.json()
assert client.get(f"/notes/{saved['id']}").json() == saved
assert client.get("/notes/missing-id").status_code == 404
for text in ("", "   ", "가" * 201):
    assert client.post("/notes", json={"text": text}).status_code == 422
print("등록·조회·오류 응답 확인 완료")
```

```bash
python -m pip install httpx
python check.py
```

2026년 9월 12일 macOS의 Python 3.11.4, FastAPI 0.141.1, httpx 0.28.1 환경에서 위 검사를 실행해 등록·조회와 404·422 응답을 확인했습니다. 이 검사는 저장 흐름과 오류 응답을 확인합니다. 처리 속도 측정이나 외부 배포 검증은 아닙니다. 인터넷에 공개하려면 데이터베이스, 인증, HTTPS, 운영 로그 등 별도 구성이 필요합니다. [FastAPI 테스트 안내](https://fastapi.tiangolo.com/tutorial/testing/)
