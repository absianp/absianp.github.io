import os
import json
import re
import random
from typing import List, Dict, Any
from templates.prompt_templates import KEYWORD_HARVESTER_SYSTEM_PROMPT
from integrations.antigravity_runner import AntigravityRunner

class KeywordHarvester:
    """
    Antigravity CLI / SDK 또는 RSS 트렌드를 분석하여
    수익화 및 SEO에 최적화된 블로그 포스팅 주제를 발굴하는 에이전트
    """

    def __init__(self, config: Dict[str, Any], api_key: str = None):
        self.config = config
        self.categories = config.get("content", {}).get("categories", [])
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.antigravity_runner = AntigravityRunner(config)
        self.rss_sources = [
            "https://feeds.feedburner.com/TechCrunch/",
            "https://news.ycombinator.com/rss",
            "https://www.theverge.com/rss/index.xml",
        ]

    def fetch_trending_keywords(self) -> List[str]:
        collected_titles = []
        try:
            import feedparser
            for url in self.rss_sources[:2]:
                try:
                    feed = feedparser.parse(url)
                    for entry in feed.entries[:5]:
                        collected_titles.append(entry.title)
                except Exception:
                    pass
        except ImportError:
            pass

        if not collected_titles:
            collected_titles = [
                "Generative AI Workflow Automation 2026",
                "Python Automation for Passive Income",
                "Best Open Source Productivity Tools",
                "Web Performance Optimization for SEO",
            ]
        return collected_titles

    def harvest_ideas(self, target_category: str = None) -> List[Dict[str, Any]]:
        selected_cat = None
        if target_category:
            for cat in self.categories:
                if cat["slug"] == target_category or cat["name"] == target_category:
                    selected_cat = cat
                    break
        if not selected_cat and self.categories:
            selected_cat = random.choice(self.categories)

        category_name = selected_cat["name"] if selected_cat else "AI & 생산성"
        seed_keywords = selected_cat.get("keywords", []) if selected_cat else ["AI 자동화", "부업 블로그"]

        user_prompt = f"""
카테고리: {category_name}
시드 키워드 풀: {', '.join(seed_keywords)}
최근 트렌드 참고: {', '.join(self.fetch_trending_keywords()[:3])}

위 데이터를 바탕으로 검색량은 꾸준하면서도 구글 애드센스 고단가 광고가 잘 붙고 클릭률이 높은 실전 포스팅 주제 후보 3개를 JSON 리스트로 제안해주세요.
"""

        # 1. Antigravity CLI / SDK 우선 실행
        raw_output = self.antigravity_runner.generate_text(
            system_prompt=KEYWORD_HARVESTER_SYSTEM_PROMPT,
            user_prompt=user_prompt
        )

        if raw_output:
            try:
                clean_json = re.sub(r"^```json\s*", "", raw_output.strip())
                clean_json = re.sub(r"\s*```$", "", clean_json)
                ideas = json.loads(clean_json)
                if isinstance(ideas, list) and len(ideas) > 0:
                    return ideas
            except Exception:
                pass

        # 2. Gemini API 호출 시도
        if self.api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                model = genai.GenerativeModel(
                    model_name=self.config.get("agent", {}).get("model_name", "gemini-2.5-flash"),
                    system_instruction=KEYWORD_HARVESTER_SYSTEM_PROMPT,
                    generation_config={"response_mime_type": "application/json"}
                )
                response = model.generate_content(user_prompt)
                ideas = json.loads(response.text)
                if isinstance(ideas, list) and len(ideas) > 0:
                    return ideas
            except Exception as e:
                print(f"[KeywordHarvester] API 호출 예외: {e}")

        # 3. Fallback 아이디어
        return self._generate_fallback_ideas(category_name, seed_keywords)

    def _generate_fallback_ideas(self, category: str, keywords: List[str]) -> List[Dict[str, Any]]:
        base_keyword = random.choice(keywords) if keywords else "생산성 AI 툴"
        return [
            {
                "title": f"2026년 업무 속도 5배 높이는 {base_keyword} 실전 활용법 총정리",
                "target_keyword": f"{base_keyword} 활용법",
                "search_intent": f"{base_keyword}를 실무에 바로 적용하여 시간을 절약하고 싶은 사용자",
                "category": category,
                "tags": [base_keyword, "업무효율", "AI자동화", "2026트렌드"],
                "key_points": [
                    "초보자를 위한 핵심 기능 세팅",
                    "실무 적용 단계별 예시 및 템플릿",
                    "무료 버전 vs 유료 버전 차이점 비교"
                ]
            },
            {
                "title": f"비전공자도 10분 만에 끝내는 {base_keyword} 자동화 파이프라인 만들기",
                "target_keyword": f"{base_keyword} 자동화 튜토리얼",
                "search_intent": "코딩 지식 없이 자동화 수익 및 생산성 시스템을 구축하려는 사용자",
                "category": category,
                "tags": [base_keyword, "노코드", "파이프라인", "부업"],
                "key_points": [
                    "노코드 툴과의 연동 방법",
                    "반복 업무 90% 자동화 시나리오",
                    "실제 트래픽 및 성과 분석"
                ]
            }
        ]
