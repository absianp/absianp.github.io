---
title: Cloudflare Pages와 Supabase로 공개 공지 목록 만들기
description: 정적 HTML에서 Supabase의 공개 공지만 읽는 예제로 RLS, 브라우저용 키, Pages 배포 디렉터리와 오류 확인 방법을 설명합니다.
pubDate: '2026-09-10'
category: 개발 & 테크
tags:
- Cloudflare Pages
- Supabase
- RLS
- 정적HTML
author: 앱시안 (absian)
readingTime: 7 min read
featured: false
draft: false
faqs:
- question: 브라우저에 Supabase 키가 보여도 괜찮나요?
  answer: 이 예제는 공개를 전제로 한 publishable key를 사용합니다. 실제 데이터 접근은 테이블 권한과 RLS로 제한해야 합니다. secret 키나 service_role 키는 브라우저에
    넣으면 안 됩니다.
- question: 공개 공지가 안 보이면 RLS를 꺼도 되나요?
  answer: RLS를 끄기보다 테이블 이름, SELECT 권한, anon 정책과 published 값을 확인하세요. 관리자 권한 조회 성공과 브라우저 익명 조회 성공은 구분해야 합니다.
updatedDate: '2026-09-12'
---

Cloudflare Pages에 HTML을 올리고 Supabase에서 공지 목록을 읽는 작은 예제를 만들어 보겠습니다. 로그인이나 글쓰기를 한꺼번에 붙이지 않고, **공개한 공지만 누구나 읽을 수 있는지**를 먼저 확인하는 구성입니다.

Pages는 화면 파일을 제공하고 Supabase는 데이터를 제공합니다. 아래 코드는 문서에 맞춰 작성한 학습용 예제이며 실제 클라우드 계정에서 배포·권한 검증을 완료한 결과로 소개하는 것은 아닙니다. 운영에 사용하기 전에는 마지막의 읽기·쓰기 권한 검사를 본인 프로젝트에서 진행하세요.

## Supabase에 연습용 테이블을 만듭니다

기존 운영 테이블과 분리된 연습 프로젝트에서 SQL 편집기를 사용합니다. RLS는 행마다 접근 가능 여부를 판단하는 PostgreSQL 기능입니다. 브라우저에서 데이터 API에 접근하도록 할 때는 테이블 권한과 RLS 정책을 함께 구성해야 합니다. [Supabase RLS 안내](https://supabase.com/docs/guides/database/postgres/row-level-security)

```sql
create table public.demo_notices (
  id bigint generated always as identity primary key,
  title text not null check (char_length(title) between 1 and 100),
  published boolean not null default false
);

alter table public.demo_notices enable row level security;

revoke all on public.demo_notices from anon, authenticated;
grant select on public.demo_notices to anon;

create policy "anonymous reads published notices"
on public.demo_notices
for select
to anon
using (published = true);

insert into public.demo_notices (title, published)
values
  ('공개한 연습 공지', true),
  ('아직 공개하지 않은 연습 공지', false);
```

이 정책은 로그인하지 않은 `anon` 역할의 읽기만 허용합니다. 브라우저에서 추가·수정·삭제하는 기능은 제공하지 않습니다. 예제를 다시 실행하면 테이블이나 정책이 이미 존재한다는 오류가 날 수 있으므로, 전체 SQL을 반복하기 전에 기존 생성 여부를 확인하세요.


<!-- article-illustration:absian-2026-09-10-2026-cloudflare-pages-supabase-01 -->
<figure class="article-illustration" style="margin: 2em 0;">
  <img src="/images/articles/absian-2026-09-10-2026-cloudflare-pages-supabase-01.webp" alt="공개 공지만 방문자에게 전달하고 비공개 행은 남겨 두는 권한 그림" width="1536" height="1024" loading="lazy" decoding="async" style="display: block; width: 100%; max-width: 100%; height: auto; border-radius: 0.75rem;" />
  <figcaption style="margin-top: 0.65em; font-size: 0.95em; line-height: 1.6; color: #475569;">화면에서 숨기는 것과 데이터베이스에서 접근을 제한하는 것은 구분해서 확인합니다. AI로 제작한 설명용 이미지입니다.</figcaption>
</figure>
<!-- /article-illustration:absian-2026-09-10-2026-cloudflare-pages-supabase-01 -->

## 공개용 키만 HTML에 넣습니다

Supabase 프로젝트 URL과 **publishable key**를 준비합니다. 이 키는 브라우저에 포함될 수 있는 공개용 키이며, 접근 가능한 데이터는 권한과 RLS로 제한합니다. `secret` 키나 기존 `service_role` 키는 HTML에 넣지 않습니다. [Supabase API 키 안내](https://supabase.com/docs/guides/getting-started/api-keys)

작업 폴더 안에 `public` 폴더를 만들고 아래 내용을 `public/index.html`로 저장합니다. 코드에 표시한 두 값을 본인의 연습 프로젝트 값으로 바꿉니다.

```html
<!doctype html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>공개 공지 목록</title>
</head>
<body>
  <h1>공지</h1>
  <p id="status" role="status">불러오는 중입니다.</p>
  <ul id="notices"></ul>
  <script type="module">
    const projectUrl = 'https://YOUR_PROJECT.supabase.co';
    const publishableKey = 'YOUR_PUBLISHABLE_KEY';
    const status = document.querySelector('#status');
    const list = document.querySelector('#notices');

    async function loadNotices() {
      const url = new URL('/rest/v1/demo_notices', projectUrl);
      url.searchParams.set('select', 'id,title');
      url.searchParams.set('order', 'id.desc');
      url.searchParams.set('limit', '20');
      const response = await fetch(url, {
        headers: { apikey: publishableKey },
        signal: AbortSignal.timeout(10000)
      });
      if (!response.ok) {
        throw new Error(`데이터 요청 실패: HTTP ${response.status}`);
      }
      const rows = await response.json();
      if (!Array.isArray(rows)) throw new Error('목록 형식이 아닙니다.');
      list.replaceChildren();
      for (const row of rows) {
        const item = document.createElement('li');
        item.textContent = row.title;
        list.append(item);
      }
      status.textContent = rows.length ? `${rows.length}개 공지` : '공개 공지가 없습니다.';
    }

    loadNotices().catch(error => {
      status.textContent = '공지를 불러오지 못했습니다.';
      console.error(error.message);
    });
  </script>
</body>
</html>
```

`innerHTML` 대신 `textContent`를 사용해 제목을 텍스트로 표시했습니다. HTML에서 필터로 숨기는 대신 데이터베이스의 RLS가 비공개 행을 제외하도록 구성한 점도 확인하세요.

## 로컬 확인 후 Pages에 연결합니다

작업 폴더에서 다음 명령으로 파일을 엽니다.

```bash
python3 -m http.server 8080 --directory public
```

브라우저에서 `http://127.0.0.1:8080`을 열어 공개 공지 한 건만 나타나는지 봅니다. 빈 목록이면 테이블 이름, 정책, 공개 여부를 확인합니다. 오류라면 개발자 도구의 Network에서 실제 상태 코드를 확인하고 프로젝트 URL과 키를 대조합니다.

Git 저장소에 `public/index.html`이 있도록 준비한 다음 Cloudflare Pages의 Git 연동에서 저장소와 배포 브랜치를 선택합니다. 이 예제는 빌드 과정이 없는 정적 HTML이므로 빌드 명령은 `exit 0`, 출력 디렉터리는 `public`으로 지정합니다. [Cloudflare 정적 HTML 배포 안내](https://developers.cloudflare.com/pages/framework-guides/deploy-anything/)

배포 후에는 `pages.dev` 주소에서도 같은 목록이 표시되는지 확인합니다. 404가 나오면 출력 디렉터리 최상위에 `index.html`이 있는지 먼저 봅니다.

## 공개 전에 권한을 확인합니다

브라우저 개발자 도구에서 요청 주소와 키는 볼 수 있습니다. 키를 숨겼다는 생각으로 권한 검사를 생략하면 안 됩니다.

- 같은 공개 키의 조회에서 `published=false`인 연습 행이 반환되지 않는지 확인합니다.
- 연습 프로젝트에서 같은 키로 추가·수정·삭제를 요청해 허용되지 않는지 확인합니다.
- 관리자 키로 성공한 조회를 익명 사용자 권한 검증으로 사용하지 않습니다.
- 확인 후에도 다른 테이블에 의도치 않은 권한이 열려 있지 않은지 검토합니다.

무료 사용 가능 범위는 서비스별 제한과 선택한 플랜에 따라 달라집니다. 실제 사용 전에 [Pages 제한](https://developers.cloudflare.com/pages/platform/limits/)과 [Supabase 요금·한도](https://supabase.com/pricing)를 확인하세요. 이 구성을 영구적으로 비용이 들지 않는 서비스라고 부를 수는 없습니다.
