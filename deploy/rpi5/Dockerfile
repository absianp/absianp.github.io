# ARM64 & Raspberry Pi 5 호환 경량 Dockerfile
FROM python:3.11-slim-bookworm

WORKDIR /app

# 필수 의존성 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    cron \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# 패키지 복사 및 설치
COPY automation-pipeline/requirements.txt /app/automation-pipeline/
RUN pip install --no-cache-dir -r /app/automation-pipeline/requirements.txt

COPY blog-frontend/package.json /app/blog-frontend/
RUN cd /app/blog-frontend && npm install --production=false

# 전체 프로젝트 소스 복사
COPY . /app/

WORKDIR /app/automation-pipeline

# 엔트리포인트 실행
CMD ["python3", "main_pipeline.py", "--mode", "auto", "--approve"]
