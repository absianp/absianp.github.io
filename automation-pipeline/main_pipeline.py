#!/usr/bin/env python3
"""
🚀 Auto Blog System - Master Agent Pipeline Orchestrator
GitHub Pages + Google AdSense 자동화 부업 블로그 시스템 실행 엔트리포인트
"""

import os
import sys
import yaml
import argparse
from pathlib import Path
from dotenv import load_dotenv

# 로컬 모듈 로드
from agents.keyword_harvester import KeywordHarvester
from agents.content_writer import ContentWriter
from agents.policy_inspector import PolicyInspector
from agents.performance_tracker import PerformanceTracker
from integrations.github_publisher import GitHubPublisher
from integrations.telegram_bot import TelegramNotifier
from integrations.google_indexing import GoogleIndexing

def load_configuration() -> dict:
    """설정 파일(config.yaml) 및 환경 변수 로드"""
    base_dir = Path(__file__).parent
    env_file = base_dir / "config" / ".env"
    if env_file.exists():
        load_dotenv(env_file)
    else:
        load_dotenv()

    config_file = base_dir / "config" / "config.yaml"
    if not config_file.exists():
        print(f"❌ 설정 파일을 찾을 수 없습니다: {config_file}")
        sys.exit(1)

    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config

def run_pipeline(mode: str = "interactive", target_category: str = None, manual_topic: str = None, auto_approve: bool = False):
    config = load_configuration()

    print("=" * 60)
    print("🤖 [Auto Blog System] 에이전트 파이프라인 가동 시작")
    print(f"📌 블로그: {config.get('site', {}).get('title')} ({config.get('site', {}).get('url')})")
    print("=" * 60)

    # 1. 에이전트 및 인티그레이션 초기화
    harvester = KeywordHarvester(config)
    writer = ContentWriter(config)
    inspector = PolicyInspector(config)
    publisher = GitHubPublisher(config)
    telegram = TelegramNotifier(config)
    indexing = GoogleIndexing(config)
    tracker = PerformanceTracker(config)

    # 모니터링 리포트 모드
    if mode == "report":
        print("\n📊 [성과 모니터링 리포트 생성 중...]")
        report_data = tracker.generate_weekly_report()
        print(report_data["report_markdown"])
        if telegram.enabled:
            telegram.send_performance_report(report_data["report_markdown"])
            print("📲 텔레그램으로 성과 보고서가 발송되었습니다.")
        return

    # 2. 주제 선정 (사용자 직접 입력 or 에이전트 자동 발굴)
    chosen_topic = None
    if manual_topic:
        print(f"\n✍️ 사용자 지정 주제 수신: '{manual_topic}'")
        chosen_topic = {
            "title": manual_topic,
            "category": target_category or "AI & 생산성",
            "target_keyword": manual_topic,
            "tags": ["AI", "테크", "가이드", "부업"],
            "key_points": ["핵심 개념 및 필요성", "실전 단계별 적용법", "효율 극대화 꿀팁"]
        }
    else:
        print(f"\n🔍 [1단계: 자료 수집 및 키워드 발굴] 카테고리={target_category or '전체'}")
        ideas = harvester.harvest_ideas(target_category)
        
        if mode == "interactive" and not auto_approve:
            print("\n💡 발굴된 포스팅 주제 후보:")
            for idx, idea in enumerate(ideas, 1):
                print(f"  [{idx}] {idea['title']}")
                print(f"      (카테고리: {idea['category']} | 타겟 키워드: {idea.get('target_keyword', '')})")
            
            print("  [0] 사용자가 직접 다른 주제 입력")
            choice = input("\n👉 발행할 주제 번호를 선택하세요 (기본값: 1): ").strip()
            
            if choice == "0":
                user_title = input("👉 작성하고 싶은 주제를 입력하세요: ").strip()
                chosen_topic = {
                    "title": user_title,
                    "category": target_category or "AI & 생산성",
                    "target_keyword": user_title,
                    "tags": ["가이드", "테크", "추천"],
                    "key_points": ["기초 개념", "실전 가이드", "FAQ"]
                }
            else:
                try:
                    idx = int(choice) - 1 if choice else 0
                    chosen_topic = ideas[idx]
                except (ValueError, IndexError):
                    chosen_topic = ideas[0]
        else:
            chosen_topic = ideas[0]

    print(f"\n🎯 최종 선정된 주제: '{chosen_topic['title']}'")

    # 3. 심층 콘텐츠 작성 (Content Writer)
    print("\n✍️ [2단계: AI 심층 아티클 작성 중... (1,500자 이상 + FAQ + 애드센스 슬롯)]")
    article = writer.write_article(chosen_topic)
    print(f"✅ 글 작성 완료! 제목: {article['title']}")

    # 4. 사전 품질 & 정책 검증 (Policy Inspector)
    print("\n🔎 [3단계: SEO 점수 및 애드센스 정책 사전 검증]")
    inspection = inspector.inspect_article(article)
    print(inspection["summary"])
    if inspection["strengths"]:
        print("  🌟 강점:", ", ".join(inspection["strengths"][:2]))
    if inspection["improvements"]:
        print("  ⚠️ 보완점:", ", ".join(inspection["improvements"][:2]))

    # 5. 사용자 검토 및 최종 승인 (Human-in-the-Loop)
    approved = False
    if auto_approve:
        approved = True
        print("\n⚡ [자동 모드] 승인 생략 후 즉시 배포 진행.")
    elif telegram.enabled:
        print("\n📲 텔레그램으로 검토 요청을 전송했습니다. 모바일에서 [승인] 버튼을 눌러주세요.")
        telegram.send_review_request(article, inspection)
        # Fallback to CLI confirmation
        confirm = input("\n👉 배포를 승인하시겠습니까? (y/N): ").strip().lower()
        approved = confirm in ["y", "yes"]
    else:
        print("\n" + "=" * 50)
        print(f"📖 [초안 미리보기] {article['title']}")
        print(f"📝 설명: {article['description']}")
        print(f"🏷️ 카테고리: {article['category']} | 태그: {', '.join(article['tags'])}")
        print("=" * 50)
        confirm = input("\n👉 위 포스트를 GitHub Pages에 즉시 배포(Publish)하시겠습니까? (Y/n): ").strip().lower()
        approved = confirm in ["", "y", "yes"]

    # 6. 배포 및 구글 색인 요청
    if approved:
        print("\n🚀 [4단계: Astro 블로그 저장소에 글 게시 (Git Commit)]")
        published_path = publisher.publish_article(article)
        print(f"🎉 성공적으로 게시되었습니다: {published_path}")

        print("\n📡 [5단계: 구글 검색엔진 크롤러 색인 요청 (Sitemap Ping)]")
        indexing.ping_sitemap()
        print("✨ 모든 에이전트 작업이 성공적으로 완료되었습니다!")
    else:
        print("\n🚫 사용자에 의해 배포가 취소되었습니다.")

def main():
    parser = argparse.ArgumentParser(description="Auto Blog System Master Pipeline")
    parser.add_argument("--mode", choices=["interactive", "auto", "report"], default="interactive", help="실행 모드")
    parser.add_argument("--category", type=str, default=None, help="타겟 카테고리 (예: ai-productivity, tech-dev, side-income)")
    parser.add_argument("--topic", type=str, default=None, help="사용자 지정 포스팅 주제")
    parser.add_argument("--approve", action="store_true", help="사용자 승인 절차 없이 즉시 배포")

    args = parser.parse_args()
    run_pipeline(
        mode=args.mode,
        target_category=args.category,
        manual_topic=args.topic,
        auto_approve=args.approve
    )

if __name__ == "__main__":
    main()
