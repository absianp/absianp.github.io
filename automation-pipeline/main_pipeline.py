#!/usr/bin/env python3
import os
import sys
import yaml
import argparse
from datetime import datetime

# 에이전트 및 연동 모듈 로드
from agents.keyword_harvester import KeywordHarvester
from agents.content_writer import ContentWriter
from agents.policy_inspector import PolicyInspector
from agents.performance_tracker import PerformanceTracker
from integrations.github_publisher import GitHubPublisher
from integrations.google_indexing import GoogleIndexing
from integrations.telegram_bot import TelegramNotifier

def load_config(config_path: str = "config/config.yaml") -> dict:
    abs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), config_path))
    if not os.path.exists(abs_path):
        print(f"⚠️ 설정 파일을 찾을 수 없습니다: {abs_path}")
        return {}
    with open(abs_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def run_auto_pipeline(config: dict, auto_approve: bool = True, target_category: str = None):
    site_title = config.get("site", {}).get("title", "앱시안(absian)")
    site_url = config.get("site", {}).get("url", "https://absianp.github.io")
    print("=" * 60)
    print(f"🤖 [{site_title}] 에이전트 파이프라인 가동 시작")
    print(f"📌 블로그: {site_title} ({site_url})")
    print("=" * 60)

    # 0. 모듈 초기화
    harvester = KeywordHarvester(config)
    writer = ContentWriter(config)
    inspector = PolicyInspector(config)
    publisher = GitHubPublisher(config)
    indexer = GoogleIndexing(config)
    telegram = TelegramNotifier(config)

    # 1단계: 키워드 발굴 & 주제 선정
    print(f"\n🔍 [1단계: 자료 수집 및 키워드 발굴] 카테고리={target_category or '전체'}")
    ideas = harvester.harvest_ideas(target_category)
    if not ideas:
        print("❌ 키워드 발굴에 실패했습니다.")
        telegram.send_health_report({"error_details": "키워드 발굴 실패"}, is_alert=True)
        return

    selected_topic = ideas[0]
    title = selected_topic.get("title", "")
    print(f"\n🎯 최종 선정된 주제: '{title}'")

    # 📲 텔레그램 알림 1: 새로운 주제 탐색 보고
    telegram.send_topic_discovered(selected_topic)

    # 2단계: 심층 아티클 작성
    print("\n✍️ [2단계: AI 심층 아티클 작성 중... (1,500자 이상 + FAQ + 애드센스 슬롯)]")
    article = writer.write_article(selected_topic)
    print(f"✅ 글 작성 완료! 제목: {article.get('title', '')}")

    # 3단계: 애드센스 정책 & SEO 품질 검사
    print("\n🔎 [3단계: SEO 점수 및 애드센스 정책 사전 검증]")
    inspection = inspector.inspect(article)
    inspector.print_inspection_report(inspection)

    # 4단계: 퍼블리싱 및 배포
    print("\n🚀 [4단계: Astro 블로그 저장소에 글 게시 및 배포]")
    saved_path = publisher.publish_article(article)
    post_slug = os.path.splitext(os.path.basename(saved_path))[0]
    full_post_url = f"{site_url.rstrip('/')}/blog/{post_slug}/"
    print(f"🎉 성공적으로 게시되었습니다: {full_post_url}")

    # 📲 텔레그램 알림 2: 새 글 작성 및 배포 보고
    telegram.send_article_published(article, inspection, full_post_url)

    # 5단계: 검색엔진 크롤러 색인 요청
    print("\n📡 [5단계: 구글 검색엔진 크롤러 색인 요청 (Sitemap Ping)]")
    indexer.ping_sitemap()

    print("\n✨ 모든 에이전트 작업이 성공적으로 완료되었습니다!")

def main():
    parser = argparse.ArgumentParser(description="앱시안(absian) 자동화 블로그 파이프라인")
    parser.add_argument("--mode", choices=["auto", "trend", "interactive", "report", "morning_report", "evening_report", "revenue_report", "health", "test_telegram"], default="auto")
    parser.add_argument("--approve", action="store_true", help="초안 자동 승인 모드")
    parser.add_argument("--category", type=str, default=None, help="특정 카테고리 지정")
    args = parser.parse_args()

    config = load_config()
    telegram = TelegramNotifier(config)
    tracker = PerformanceTracker(config)

    if args.mode == "auto":
        run_auto_pipeline(config, auto_approve=True, target_category=args.category)

    elif args.mode == "trend":
        import subprocess
        print("📰 [최신 트렌드 RAG 자동 포스팅] 시작...")
        try:
            # daily_trend_generator.py 실행
            script_path = os.path.join(os.path.dirname(__file__), "daily_trend_generator.py")
            subprocess.run([sys.executable, script_path], check=True)
            print("✨ 트렌드 기반 포스팅이 생성되었습니다.")
        except subprocess.CalledProcessError as e:
            print(f"❌ 트렌드 스크립트 실행 실패: {e}")
            telegram.send_health_report({"error_details": f"daily_trend_generator.py 실행 실패: {e}"}, is_alert=True)

    elif args.mode == "morning_report":
        # 매일 아침 08:00 KST
        stats = tracker.get_site_statistics()
        print("🌅 [일일 아침 사이트 현황 보고 (08:00)] 전송 중...")
        telegram.send_daily_site_status("morning", stats)

    elif args.mode == "evening_report":
        # 매일 저녁 19:00 KST
        stats = tracker.get_site_statistics()
        revenue = tracker.get_adsense_statistics()
        print("🌆 [일일 저녁 사이트 현황 및 수익 보고 (19:00)] 전송 중...")
        telegram.send_daily_site_status("evening", stats)
        telegram.send_adsense_daily_report(revenue)

    elif args.mode == "revenue_report":
        revenue = tracker.get_adsense_statistics()
        print("💰 [광고 수익 현황 보고] 전송 중...")
        telegram.send_adsense_daily_report(revenue)

    elif args.mode == "health":
        health = tracker.get_system_health()
        print("🍓 [시스템 헬스 보고] 전송 중...")
        telegram.send_health_report(health)

    elif args.mode == "report":
        stats = tracker.get_site_statistics()
        revenue = tracker.get_adsense_statistics()
        telegram.send_daily_site_status("evening", stats)
        telegram.send_adsense_daily_report(revenue)

    elif args.mode == "test_telegram":
        print("📲 [텔레그램 5종 알림 테스트 발송 시작]...")
        sample_topic = {
            "title": "2026년 파이썬 업무 자동화로 매일 2시간 아끼는 법",
            "category": "개발 & 테크",
            "target_keyword": "파이썬 업무자동화",
            "tags": ["파이썬", "업무자동화", "생산성"],
            "key_points": ["반복 엑셀 취합 자동화", "텔레그램 알림 봇 연동", "라즈베리파이 24시간 스케줄러"]
        }
        telegram.send_topic_discovered(sample_topic)

        sample_article = {
            "title": "2026년 파이썬 업무 자동화로 매일 2시간 아끼는 법",
            "category": "개발 & 테크",
            "readingTime": "7 min read",
            "faqs": [{"question": "비전공자도 가능한가요?", "answer": "네, 가능합니다."}]
        }
        sample_inspection = {"score": 95, "char_count": 1850}
        telegram.send_article_published(sample_article, sample_inspection, "https://absianp.github.io/blog/2026-python-automation-routines/")

        stats = tracker.get_site_statistics()
        telegram.send_daily_site_status("morning", stats)
        telegram.send_daily_site_status("evening", stats)

        revenue = tracker.get_adsense_statistics()
        telegram.send_adsense_daily_report(revenue)

        health = tracker.get_system_health()
        telegram.send_health_report(health)
        print("✨ 5종 텔레그램 알림 테스트 전송 완료!")

if __name__ == "__main__":
    main()
