---
title: LiteLLM과 연동하는 폐쇄망·하이브리드 LLM 옵저버빌리티 도구 완벽 비교 (온프레미스 AI 모니터링)
description: 사내 보안 규제와 망분리 환경을 충족하면서도 LLM 서비스의 토큰 비용, 지연 시간, 응답 품질을 정밀하게 추적하는 사내 구축형(Self-hosted)
  옵저버빌리티 도구(Langfuse, Arize Phoenix 등)를 심층 비교 분석합니다.
pubDate: '2026-09-01'
category: AI & 생산성
tags:
- LLM옵저버빌리티
- LiteLLM
- 온프레미스AI
- 폐쇄망모니터링
- AI옵저버빌리티
- Langfuse
author: 앱시안 (absian)
readingTime: 8 min read
featured: false
draft: false
faqs:
- question: 완전 격리된 오프라인 폐쇄망 환경에서 Langfuse나 Phoenix 설치 시 외부 의존성 문제는 없나요?
  answer: 사전에 모든 Docker 이미지(Web, Worker, PostgreSQL, Redis, MinIO)를 tar 파일로 패키징하여
    사내 프라이빗 레지스트리(Harbor 등)로 반입해야 합니다. 또한, 컨테이너 실행 시 `TELEMETRY_ENABLED=false` 설정을
    부여하여 외부 수집 서버 호출을 차단하고, 프론트엔드 에셋이 외부 CDN 대신 로컬 번들에서 로드되는 최신 정식 릴리스 버전을 사용하는지 확인해야
    합니다.
- question: 애플리케이션에 직접 SDK를 심는 방식과 LiteLLM 프록시 콜백을 사용하는 방식의 차이는 무엇인가요?
  answer: 애플리케이션 SDK 방식은 체인 내부의 세부 함수 실행 과정(RAG 임베딩 생성, 리랭킹 단계 등)까지 세밀하게 추적할 수 있지만
    모든 개발팀의 코드를 수정해야 하는 운영 부담이 큽니다. 반면 LiteLLM 프록시 콜백 방식은 코드 수정 없이 게이트웨이 레벨에서 전사적인
    입출력, 토큰 비용, 레이턴시를 100% 강제 수집할 수 있어 엔터프라이즈 중앙 거버넌스 수립에 훨씬 유리합니다. 대규모 조직에서는 두 방식을
    결합하는 하이브리드 접근을 권장합니다.
- question: 사내 자체 구축한 로컬 vLLM 모델의 토큰 비용도 모니터링 도구에서 계산할 수 있나요?
  answer: 네, 가능합니다. 기본적으로 로컬 모델은 API 비용이 $0으로 표시되지만, LiteLLM의 커스텀 모델 가격표(`model_prices_and_context_window.json`)
    또는 Langfuse의 모델 단가 설정(Model Pricing Table)에 로컬 모델 식별자와 가상 토큰 단가(인프라 GPU 운영비 기반
    추산 금액)를 매핑해 두면 상용 모델과 동일하게 비용 대시보드에서 정확히 집계됩니다.
---

## 엔터프라이즈 LLM 도입의 최대 난제: '블랙박스'와 '데이터 유출'

최근 사내 업무 자동화, 고객 응대 챗봇, RAG(검색 증강 생성) 기반 지식 관리 시스템 구축을 위해 대형 언어 모델(LLM)을 도입하는 기업이 폭발적으로 늘고 있습니다. 하지만 공공기관, 금융권, 제조 R&D 등 엄격한 망분리 및 데이터 거버넌스가 요구되는 엔터프라이즈 환경에서는 상용 클라우드 SaaS 모니터링 도구를 그대로 사용할 수 없는 현실적인 벽에 부딪힙니다.

프롬프트와 모델 응답 데이터에는 고객의 개인정보(PII)나 기업 내부 핵심 기밀이 고스란히 포함될 수 있기 때문입니다. 그렇다고 해서 모니터링을 포기한다면, 예상치 못한 토큰 비용 폭증, 서비스 응답 지연(Latency), 할루시네이션(환각 현상)에 의한 응답 품질 저하를 전혀 감지할 수 없는 '블랙박스' 상태에 놓이게 됩니다.

> "측정할 수 없으면 통제할 수 없고, 통제할 수 없는 생성형 AI는 기업의 가장 치명적인 보안 및 비용 리스크가 됩니다."

본 아티클에서는 통일된 API 게이트웨이인 **LiteLLM**을 기반으로, 외부 인터넷 연결이 차단된 폐쇄망이나 하이브리드 클라우드 환경에서 안전하게 구동할 수 있는 **사내 구축형(Self-hosted) 오픈소스 LLM 옵저버빌리티 솔루션**을 비교 분석하고 실전 아키텍처 가이드를 제시합니다.

---

## 하이브리드 LLM 게이트웨이의 핵심 축, LiteLLM의 가치

여러 모델(사내 온프레미스 vLLM/Ollama, 외부 전용선 연계 Azure OpenAI 등)을 혼용하는 엔터프라이즈 환경에서 **LiteLLM**은 사실상의 표준 AI 게이트웨이로 자리 잡았습니다. 100여 개 이상의 LLM API를 표준 OpenAI 포맷으로 추상화해 주며, 부하 분산(Load Balancing), Fallback(장애 복구), 사용자별 토큰 할당량(Rate Limiting) 관리 기능을 제공합니다.

옵저버빌리티 관점에서 LiteLLM의 진정한 강점은 **'중앙 집중식 콜백(Callback) 파이프라인'**입니다. 개별 비즈니스 애플리케이션 코드에 SDK를 일일이 심지 않아도, LiteLLM 게이트웨이 설정만으로 모든 호출 메타데이터와 입출력 트레이스를 사내 모니터링 서버로 일괄 포워딩할 수 있습니다.

```yaml
# LiteLLM config.yaml 설정 예시 (사내 모니터링 연동)
model_list:
  - model_name: internal-llama3
    litellm_params:
      model: openai/meta-llama/Meta-Llama-3-70B-Instruct
      api_base: http://vllm-cluster.internal.net:8000/v1
      api_key: "EMPTY"

litellm_settings:
  # 게이트웨이 레벨에서 옵저버빌리티 도구로 자동 전파
  success_callback: ["langfuse"]
  failure_callback: ["langfuse"]

general_settings:
  master_key: sk-enterprise-master-token
```

---

## 주요 사내 구축형(Self-Hosted) LLM 옵저버빌리티 도구 심층 비교

폐쇄망 내 격리된 환경(Air-gapped) 또는 프라이빗 VPC 내에 직접 설치하여 구동 가능한 대표 오픈소스 옵저버빌리티 도구 3종을 분석해 보겠습니다.

### 1. Langfuse: 종합 AI 거버넌스 및 트레이싱의 표준
**Langfuse**는 현재 오픈소스 LLM 엔지니어링 플랫폼 중 가장 완성도 높은 생태계를 보유하고 있습니다. 단순 입출력 로깅을 넘어, 프롬프트 버전 관리, 사용자 피드백 수집, 데이터셋 큐레이션, LLM-as-a-judge 기반 자동 평가(Eval) 기능을 단일 플랫폼에서 제공합니다.

- **핵심 장점**: 직관적인 웹 대시보드, 강력한 세션/스레드 추적, LiteLLM 네이티브 지원(환경변수 등록만으로 즉시 연동 가능).
- **아키텍처**: Node.js/Next.js 웹 애플리케이션, PostgreSQL(메타데이터/소규모 트레이스), 대규모 환경을 위한 ClickHouse 기반 분산 저장 지원.
- **적합 대상**: 복잡한 체인(LangChain, LlamaIndex)이나 에이전트 워크플로우를 시각화하고 프롬프트 엔지니어링 생애주기 전반을 통제하려는 팀.

### 2. Arize Phoenix: OpenTelemetry 표준과 임베딩 시각화의 강자
**Arize Phoenix**는 AI 모델 평가와 RAG 파이프라인의 검색 품질 진단에 특화된 솔루션입니다. 완전한 OpenTelemetry(OTel) 표준을 준수하므로 벤더 종속 없이 기존 기업 APM(Datadog, Dynatrace 등) 파이프라인과 결합하기 용이합니다.

- **핵심 장점**: 벡터 임베딩 클러스터링 시각화(UMAP)를 기본 탑재하여 지식 베이스 검색 누락 지점을 빠르게 파악 가능, 파이썬 네이티브 환경에서 초경량 단일 컨테이너로 기동 가능.
- **아키텍처**: 경량 Python/FastAPI 백엔드, DuckDB 또는 SQLite/PostgreSQL 지원.
- **적합 대상**: RAG 기반 검색 품질 평가가 최우선 과제이며, OTel 표준 텔레메트리 파이프라인을 사내 인프라와 결합하려는 엔지니어링 조직.

### 3. OpenLLMetry (Traceloop): 표준 OTel 컬렉터 기반 경량 수집기
**OpenLLMetry**는 독자적인 대시보드 제공보다는 다양한 LLM 라이브러리와 서비스의 트레이스를 표준 OpenTelemetry 스팬(Span)으로 규격화해 주는 프레임워크입니다.

- **핵심 장점**: 이미 사내에 Grafana Tempo, Jaeger, Prometheus 등으로 구성된 모니터링 인프라가 갖춰져 있는 경우, 추가 UI 도구 도입 없이 기존 대시보드에 LLM 지표를 통합 가능.
- **아키텍처**: 표준 OTel Collector 연계 아키텍처.
- **적합 대상**: 기존 IT 인프라 APM 모니터링 체계와 LLM 지표를 단일 창구로 일원화해야 하는 엔터프라이즈 운영팀.

### 사내 구축형 LLM 옵저버빌리티 솔루션 기능 비교표

| 비교 항목 | Langfuse (Self-hosted) | Arize Phoenix | OpenLLMetry / OTel | Helicone (Self-hosted) |
| :--- | :--- | :--- | :--- | :--- |
| **배포 방식** | Docker Compose / K8s Helm | Docker / Python Package | OTel Collector / SDK | Docker Compose |
| **아키텍처 유형** | SDK / 비동기 텔레메트리 수집 | OTel 트레이서 기반 | OTel 표준 에이전트 | 리버스 프록시 / SDK |
| **주요 강점** | 트레이싱, 비용 추적, 프롬프트 관리, Eval | RAG 임베딩 시각화, 평가 벤치마크 | 벤더 중립성, 기존 APM 통합 | 프록시 캐싱, 비용 절감 모니터링 |
| **스토리지 백엔드** | PostgreSQL, ClickHouse, Redis | DuckDB, SQLite, PostgreSQL | 기존 OTel 백엔드 (Tempo 등) | PostgreSQL, ClickHouse |
| **폐쇄망 설치 난이도**| 보통 (Postgres, S3/MinIO 필요) | 매우 쉬움 (단일 컨테이너 가능) | 쉬움 (OTel 인프라 의존) | 다소 복잡 (프록시 네트워크 구성) |
| **라이선스** | FSL-1.1-Apache-2.0 / MIT | Apache 2.0 | Apache 2.0 | Apache 2.0 |

---

## 폐쇄망·망분리 환경을 위한 실전 하이브리드 아키텍처 전략

보안 규제를 100% 충족하면서도 안정적인 모니터링 체계를 구축하기 위해서는 다음과 같은 네트워크 분리 및 데이터 흐름 설계가 필수적입니다.

### 1. 망 분리 네트워크 토폴로지 설계

- **내부 업무망(Internal Zone)**: 클라이언트 애플리케이션(사내 ERP, 메신저 등)이 위치하며 오직 내부 LiteLLM Proxy 주소로만 통신합니다.
- **AI 인프라망(Private AI Zone)**: LiteLLM Gateway, 온프레미스 서빙 인프라(vLLM, TensorRT-LLM), 그리고 Langfuse 모니터링 스택(Next.js, Postgres, MinIO)이 격리된 서브넷에 상주합니다.
- **DMZ / 아웃바운드 게이트웨이**: 만약 외부 상용 LLM(OpenAI 등)을 일부 병용해야 하는 하이브리드 환경이라면, 오직 LiteLLM 프록시 노드만 특정 포트(TLS 443)를 통해 화이트리스트 기반 외부 통신을 수행하며, 모니터링 서버(Langfuse)는 외부 통신이 원천 차단된 내부망에 머무릅니다.

### 2. 세부 지표 추적 및 비용 최적화 전략

1. **TTFT(Time to First Token) 및 지연 시간 분해**: 온프레미스 GPU 클러스터의 부하 상태를 점검하기 위해 전체 응답 시간뿐만 아니라 첫 토큰 생성 시간(TTFT)과 추론 처리 속도(Tokens per Second)를 세부 지표로 분리하여 모니터링하세요.
2. **가상 토큰 비용(Virtual Cost Mapping)**: 온프레미스 로컬 모델은 API 비용이 0원으로 기록되기 쉽습니다. LiteLLM의 `model_prices_and_context_window.json` 설정을 오버라이드하여, 사내 서버 하드웨어 감가상각 및 전력 비용을 반영한 가상 단가(예: 1M 토큰당 $0.5)를 부여함으로써 실질적인 조직별 AI ROI를 측정할 수 있습니다.
3. **PII 마스킹 필터 결합**: LiteLLM 전단 또는 Langfuse 인제스천 파이프라인에 Presidio 같은 로컬 데이터 마스킹 엔진을 연동하여, 로깅 단계에서 주민등록번호, 계좌번호 등 민감 데이터가 평문으로 저장되지 않도록 암호화/비식별 조치하세요.

---

## 사내 구축 및 운영 시 반드시 챙겨야 할 실전 꿀팁

- **원격 텔레메트리 강제 비활성화**: 대부분의 오픈소스 도구는 익명 사용 통계를 외부 서버로 전송하려는 기본 설정을 가지고 있습니다. 폐쇄망 배포 시 `TELEMETRY_ENABLED=false`, `DO_NOT_TRACK=true` 환경 변수를 모든 컨테이너에 반드시 주입하세요.
- **정적 에셋 오프라인 로컬화**: 일부 대시보드 UI가 외부 CDN(Google Fonts, cdnjs 등)에서 CSS/폰트를 불러오도록 하드코딩되어 있으면 폐쇄망 브라우저에서 화면이 깨질 수 있습니다. 정적 자원이 컨테이너 이미지 내부에 온전히 패키징된 정식 릴리스 버전을 검증 후 채택하세요.
- **로그 파티셔닝 및 보관 주기(TTL) 수립**: 임베딩 벡터와 대화 로그가 누적되면 수억 건의 트레이스로 인해 관계형 DB(PostgreSQL)가 급격히 느려집니다. 일 단위 파티셔닝을 적용하고, 90일 이상 지난 상세 트레이스는 압축 보관(S3 호환 MinIO)하거나 요약 메타데이터만 남기고 삭제하는 라이프사이클 룰을 정의하세요.

---

## 결론: 안전하고 투명한 엔터프라이즈 AI를 향하여

1. **데이터 주권 수호**: 엔터프라이즈 환경의 LLM 모니터링은 프라이빗 인프라 내에서 데이터가 완결되는 사내 구축형(Self-hosted) 구조가 필수입니다.
2. **거버넌스 통합**: LiteLLM 게이트웨이의 중앙 집중식 콜백 구조를 활용하면 애플리케이션 수정 없이 전사 모델 사용량, 비용, 지연 시간을 단일 창구에서 통제할 수 있습니다.
3. **목적별 도구 선택**: 종합적인 대화 추적 및 프롬프트 관리가 목적이라면 **Langfuse**를, 정밀한 RAG 검색 평가와 OTel 표준 호환이 우선이라면 **Arize Phoenix**를 도입하는 것이 최선의 전략입니다.

지금 바로 사내 개발망에 LiteLLM과 Self-hosted Langfuse를 구성하여, 감춰져 있던 LLM 인프라의 성능과 비용 지표를 투명하게 시각화해 보세요.
