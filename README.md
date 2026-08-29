# 🚀 GitHub Pages + AdSense AI 자동화 수익형 블로그 시스템

> **비용 0원(100% 평생 무료 호스팅)**으로 운영되는 GitHub Pages 기반의 초고속 Astro 블로그와 **AI 에이전트 자동화 파이프라인**을 결합한 부업 수익화 솔루션입니다.
> 사용자의 노동은 최소화(주제 제안/승인, 원클릭 발행, 모바일 성과 보고 수신)하고 자료 수집, 1,500자+ 심층 글 작성, SEO/애드센스 슬롯 최적화, 정적 배포 및 구글 색인 요청을 에이전트가 전자동으로 수행합니다.

---

## 🌟 핵심 특징 및 장점

1. **💸 완전 무료 호스팅 (서버 유지비 0원)**:
   - GitHub Pages + Fastly CDN을 통해 트래픽 비용 없이 평생 무료 운영.
2. **⚡ 구글 Core Web Vitals 100점 (초고속 SEO)**:
   - **Astro SSG** 엔진 적용으로 자바스크립트 0KB 번들, 0.5초 이내 로딩.
   - Schema.org 구조화 데이터(`BlogPosting`, `FAQPage`), OpenGraph, 자동 `sitemap.xml`, `rss.xml` 기본 탑재.
3. **💰 구글 애드센스(Google AdSense) 수익 최적화**:
   - 상단 배너, 본문 문맥 내(In-Article), 본문 하단, 사이드바, 멀티플렉스 반응형 광고 슬롯 컴포넌트(`AdSense.astro`) 사전 배치.
   - 애드센스 필수 승인 요건인 `About`, `Privacy Policy`, `Terms`, `Contact`, `ads.txt` 완비.
4. **🤖 멀티 에이전트 파이프라인 (Python + Gemini)**:
   - **키워드 하베스터 (`keyword_harvester.py`)**: 검색량 대비 경쟁이 적은 롱테일 키워드 및 트렌드 발굴.
   - **콘텐츠 라이터 (`content_writer.py`)**: 1,500~2,500자 이상의 심층 마크다운, 비교 분석표, FAQ 생성.
   - **정책 감사관 (`policy_inspector.py`)**: SEO 점수, 애드센스 금칙어/품질 사전 검토.
   - **텔레그램 알림 봇 (`telegram_bot.py`)**: 모바일에서 요약/SEO 점수 확인 후 **원클릭 승인(Publish)**.
   - **퍼블리셔 & 색인 (`github_publisher.py` & `google_indexing.py`)**: Git 자동 커밋 및 구글봇 크롤링 핑 전송.
   - **성과 모니터링 (`performance_tracker.py`)**: 주간 트래픽, 인기 검색어, 애드센스 예상 수익 보고.

---

## 📂 프로젝트 구조

```
auto_blog_system/
├── blog-frontend/                    # Astro 기반 초고속 정적 블로그
│   ├── src/
│   │   ├── components/
│   │   │   ├── AdSense.astro         # 반응형 애드센스 광고 슬롯 (상단/본문/하단)
│   │   │   ├── SEO.astro             # Meta/OG/Twitter/JSON-LD 구조화 데이터
│   │   │   ├── Header.astro / Footer.astro
│   │   │   ├── TableOfContents.astro # 아티클 자동 목차
│   │   │   └── Card.astro            # 포스트 카드 컴포넌트
│   │   ├── content/
│   │   │   ├── config.ts             # Zod 스키마 검증
│   │   │   └── blog/                 # 에이전트가 자동 생성하는 마크다운 글 (.md)
│   │   ├── pages/
│   │   │   ├── index.astro           # 메인 홈 (히어로, 카테고리, 최신글)
│   │   │   ├── blog/                 # 전체 글 목록 및 상세 [slug].astro
│   │   │   ├── categories/ & tags/   # 카테고리/태그별 아카이브 (내부 링크 SEO)
│   │   │   ├── about.astro           # 애드센스 필수: 소개 페이지
│   │   │   ├── privacy-policy.astro  # 애드센스 필수: 개인정보처리방침
│   │   │   ├── terms.astro           # 애드센스 필수: 이용약관
│   │   │   ├── contact.astro         # 애드센스 필수: 문의하기 페이지
│   │   │   ├── sitemap.xml.ts        # 자동 생성 사이트맵
│   │   │   └── rss.xml.ts            # RSS 피드
│   │   └── styles/global.css
│   ├── public/
│   │   ├── ads.txt                   # 구글 애드센스 본인 인증 파일
│   │   └── robots.txt                # 검색엔진 크롤러 허용 설정
│   └── astro.config.mjs
│
├── automation-pipeline/              # AI 에이전트 자동화 파이프라인
│   ├── config/
│   │   ├── config.yaml               # 사이트 정보, 애드센스 ID, 타겟 카테고리 설정
│   │   └── .env                      # API 키 (GEMINI_API_KEY, TELEGRAM_BOT_TOKEN 등)
│   ├── agents/
│   │   ├── keyword_harvester.py      # 자료 수집 및 롱테일 키워드 발굴
│   │   ├── content_writer.py         # 1,500자+ 심층 글 및 FAQ 작성
│   │   ├── policy_inspector.py       # 품질 및 애드센스 정책 검토 (채점기)
│   │   └── performance_tracker.py    # 주간 성과 및 수익 리포트 생성
│   ├── integrations/
│   │   ├── telegram_bot.py           # 모바일 원클릭 승인 텔레그램 연동
│   │   ├── github_publisher.py       # Git 자동 커밋 및 배포 트리거
│   │   └── google_indexing.py        # 구글봇 빠른 색인(Sitemap Ping) 요청
│   ├── templates/prompt_templates.py # 고품질 전문 프롬프트 템플릿
│   ├── main_pipeline.py              # 파이프라인 통합 실행기 (CLI)
│   └── requirements.txt
│
└── .github/
    └── workflows/
        ├── deploy.yml                # Push 시 GitHub Pages 자동 빌드 & 배포 CI/CD
        └── agent-cron.yml            # (옵션) 매일 자동 글 작성 및 발행 크론
```

---

## ⚡ 빠른 시작 및 실행 방법

### 1. 블로그 로컬 프리뷰 실행
```bash
cd blog-frontend
npm run dev
# 브라우저에서 http://localhost:3000 접속
```

### 2. 정적 사이트 빌드 테스트
```bash
cd blog-frontend
ASTRO_TELEMETRY_DISABLED=1 npx astro build
# 1초 이내에 dist/ 정적 파일 생성 완료
```

### 3. AI 에이전트 파이프라인 실행
```bash
cd automation-pipeline

# (1) 대화형 인터랙티브 모드 (추천: 후보 주제 중 선택 후 발행)
python3 main_pipeline.py --mode interactive

# (2) 사용자 직접 주제 지정 발행 모드
python3 main_pipeline.py --topic "2026 노션 AI 실전 템플릿 제작법"

# (3) 완전 무인 자동 모드 (GitHub Actions 크론용)
python3 main_pipeline.py --mode auto --approve

# (4) 주간 운영 성과 모니터링 리포트 확인
python3 main_pipeline.py --mode report
```

---

## 🌐 GitHub Pages 무료 배포 설정 (3단계)

1. **GitHub 저장소 생성 및 코드 Push**:
   ```bash
   git init
   git add .
   git commit -m "feat: initial commit for auto blog system"
   git remote add origin https://github.com/당신의유저네임/저장소이름.git
   git push -u origin main
   ```
2. **GitHub Pages 활성화**:
   - 저장소 **Settings** $\rightarrow$ **Pages** 메뉴 진입
   - **Source**를 `Deploy from a branch`에서 **`GitHub Actions`**로 변경.
3. 코드 Push 시 `.github/workflows/deploy.yml`이 자동 실행되어 1분 안에 전 세계에 블로그가 무료 배포됩니다.

---

## 💰 구글 애드센스 승인 및 연동 가이드

1. **기본 글 15~20개 발행**:
   - `python3 main_pipeline.py --mode auto --approve` 명령으로 다양한 카테고리의 글을 15~20편 자동 생성합니다.
2. **구글 애드센스 신청**:
   - [Google AdSense](https://adsense.google.com)에 로그인하여 사이트 URL 등록.
   - 발급된 퍼블리셔 ID(`ca-pub-XXXXXXXXXXXXXXXX`)를 `automation-pipeline/config/config.yaml`과 `blog-frontend/public/ads.txt`에 입력.
3. **구글 서치 콘솔 등록**:
   - 구글 서치 콘솔에 사이트 주소를 등록하고 `https://당신의도메인/sitemap.xml`을 사이트맵으로 제출.
