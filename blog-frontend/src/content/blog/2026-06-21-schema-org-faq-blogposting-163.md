---
title: '블로그 JSON-LD 점검: BlogPosting 정보와 실제 화면 맞추기'
description: 제목, 작성자, 게시일이 실제 글과 일치하는 BlogPosting 예제를 만들고 구조화 데이터 검사 결과의 의미를 구분합니다.
pubDate: 2026-06-21
category: 개발 & 테크
tags:
- JSON-LD
- BlogPosting
- 구조화데이터
- 검색점검
author: 앱시안 (absian)
readingTime: 4 min read
featured: false
draft: false
faqs:
- question: FAQPage를 넣으면 Google FAQ 리치 결과가 나오나요?
  answer: Google은 2026년 5월 7일부터 FAQ 리치 결과를 표시하지 않는다고 공지했습니다. 본문의 질문과 답변은 독자에게 유용할 때 유지하되 검색 표시 효과를 약속하지 마세요.
- question: Rich Results Test를 통과하면 상위에 노출되나요?
  answer: 검사는 Google이 지원하는 구조화 데이터의 기술적 오류를 찾는 데 도움을 줍니다. 통과 자체가 검색 순위나 리치 결과 표시를 보장하지는 않습니다.
updatedDate: '2026-09-12'
---

구조화 데이터는 글에 없는 신뢰를 덧붙이는 장치가 아닙니다. 글의 제목, 작성자, 날짜 같은 정보를 기계가 읽을 수 있는 형식으로 표현하는 것입니다. 화면에는 한 작성자가 있는데 JSON-LD에는 가상의 전문가를 적는 식으로 사용하면 오히려 정보가 어긋납니다.

먼저 오래된 FAQ 노출 안내를 바로잡을 필요가 있습니다. **Google은 2026년 5월 7일부터 FAQ 리치 결과를 검색에 표시하지 않는다고 공지했고, 6월에는 해당 기능 문서를 삭제했습니다.** FAQ 형식의 본문은 독자에게 도움이 될 때 유지할 수 있지만, 이를 넣으면 검색 결과를 더 크게 차지한다는 설명은 현재 기준에 맞지 않습니다. [Google Search 문서 변경 기록](https://developers.google.com/search/updates)

## BlogPosting에 넣을 값을 본문에서 가져옵니다

Google의 Article 문서는 `Article`, `NewsArticle`, `BlogPosting`에 대해 안내합니다. 블로그 글이라면 제목, 작성자, 게시일과 수정일 등 실제 정보를 일치시키는 것부터 시작할 수 있습니다. [Article 구조화 데이터 안내](https://developers.google.com/search/docs/appearance/structured-data/article)

아래는 이 글의 정보를 사용한 예시입니다. 같은 코드를 다른 글에 복사할 때는 값도 바꿔야 합니다.

```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "BlogPosting",
  "headline": "블로그 JSON-LD 점검: BlogPosting 정보와 실제 화면 맞추기",
  "description": "제목, 작성자, 게시일이 실제 글과 일치하는 BlogPosting 예제를 만들고 구조화 데이터 검사 결과의 의미를 구분합니다.",
  "datePublished": "2026-06-21",
  "dateModified": "2026-09-12",
  "author": {
    "@type": "Person",
    "name": "앱시안 (absian)"
  },
  "mainEntityOfPage": {
    "@type": "WebPage",
    "@id": "https://absianp.github.io/blog/2026-06-21-schema-org-faq-blogposting-163/"
  }
}
</script>
```

작성자 소개 페이지가 실제로 있다면 그 주소를 `author.url`로 연결할 수 있습니다. 대표 이미지도 존재하고 글을 설명하는 이미지일 때 추가합니다. 검사 항목을 채우려고 없는 사진, 경력, 수상 내역을 만들지는 않습니다.

## 게시일과 수정일을 따로 관리합니다

기존 글을 고쳤다고 최초 게시일을 오늘로 바꿀 필요는 없습니다. 최초 게시일은 유지하고 내용이 실질적으로 바뀐 날짜를 수정일로 기록합니다. 화면에 표시하는 날짜와 JSON-LD의 날짜가 다른 데이터에서 생성되지 않도록 같은 원본 필드를 사용하는 편이 관리하기 쉽습니다.

템플릿에서는 JSON 문자열을 직접 이어 붙이기보다 직렬화 함수를 사용해야 따옴표와 줄바꿈 때문에 JSON이 깨지는 것을 줄일 수 있습니다. HTML의 `script` 안에 넣는 경우에는 별도의 HTML 문맥 처리도 필요합니다. 예를 들어 JavaScript에서는 다음처럼 `<`를 이스케이프한 결과를 넣을 수 있습니다.

```javascript
const jsonForScript = JSON.stringify(articleData).replace(/</g, '\\u003c');
```

실제 적용 방식은 사용하는 프레임워크의 출력·이스케이프 기능에 맞춥니다. 이미 테마나 SEO 플러그인이 Article 데이터를 만들고 있다면 같은 데이터를 또 추가하기 전에 기존 출력을 확인하세요.

## 검사는 세 단계로 나눕니다

1. **문법 확인:** JSON의 쉼표, 따옴표와 객체 구조가 올바른지 봅니다. Markdown 글 안의 예제 코드와 실제 페이지의 JSON-LD는 별개입니다.
2. **페이지 대조:** 게시된 HTML에서 제목·작성자·날짜·URL을 화면과 비교합니다. 화면에 없는 정보를 마크업만으로 제공하지 않습니다.
3. **Google 기능 검사:** [Rich Results Test](https://search.google.com/test/rich-results)에 URL이나 코드를 넣어 Google이 지원하는 결과 형식의 오류를 확인합니다.

Schema.org 형식 자체를 확인하려면 [Schema Markup Validator](https://validator.schema.org/)도 사용할 수 있습니다. 여기서 형식이 유효하다는 결과와 Google 검색에서 특정 형태로 표시된다는 결과는 다릅니다. 구조화 데이터가 올바르더라도 검색 노출과 표시 방식은 보장되지 않습니다. [Google 구조화 데이터 일반 지침](https://developers.google.com/search/docs/appearance/structured-data/sd-policies)

## FAQ를 남길지 판단하는 기준

같은 질문을 모든 글에 붙이기보다 해당 글을 따라 하다가 생길 질문을 고릅니다. “이 서식이면 애드센스에 통과하나요?”보다 “이미 플러그인이 만든 JSON-LD가 있는데 추가해야 하나요?”가 이 글의 독자에게 더 유용합니다.

질문과 답변을 수정하면 화면과 데이터에도 함께 반영해야 합니다. 검색 결과의 크기를 늘리려는 목적이 아니라, 읽는 사람이 남은 문제를 해결할 수 있는지 보고 FAQ를 편집하세요.
