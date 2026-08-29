import os
import json
import requests
from typing import Dict, Any, Optional

class TelegramNotifier:
    """
    모바일 텔레그램을 통해 사용자에게 초안 요약 및 SEO 점수를 전송하고
    원클릭 승인(Publish) 인터페이스를 제공하는 알림 모듈
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.enabled = config.get("telegram", {}).get("enabled", False)
        self.bot_token = config.get("telegram", {}).get("bot_token") or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = config.get("telegram", {}).get("chat_id") or os.getenv("TELEGRAM_CHAT_ID")
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None

    def send_review_request(self, article: Dict[str, Any], inspection: Dict[str, Any]) -> bool:
        """
        초안 검토 요청 메시지를 텔레그램으로 발송
        """
        if not self.enabled or not self.bot_token or not self.chat_id:
            print("ℹ️ 텔레그램 알림이 비활성화되어 있거나 토큰이 설정되지 않았습니다 (CLI 승인 모드로 대체).")
            return False

        title = article.get("title", "")
        category = article.get("category", "")
        score = inspection.get("score", 0)
        char_count = inspection.get("char_count", 0)
        risk = inspection.get("policy_risk", "None")

        message = (
            f"🔔 *[새 블로그 글 검토 요청]*\n\n"
            f"📌 *제목*: {title}\n"
            f"🏷️ *카테고리*: {category}\n"
            f"📊 *품질 점수*: `{score}/100점`\n"
            f"📝 *분량*: `{char_count:,}자` | *애드센스 리스크*: `{risk}`\n\n"
            f"💬 *요약*: {article.get('description', '')}\n\n"
            f"👉 아래 버튼을 누르면 GitHub Pages에 즉시 자동 배포됩니다."
        )

        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "🚀 즉시 배포 (Publish)", "callback_data": "approve_publish"},
                    {"text": "🔄 주제 재생성", "callback_data": "regenerate"}
                ],
                [
                    {"text": "❌ 이번 초안 취소", "callback_data": "cancel"}
                ]
            ]
        }

        try:
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "reply_markup": json.dumps(reply_markup)
            }
            res = requests.post(f"{self.api_url}/sendMessage", json=payload, timeout=10)
            return res.status_code == 200
        except Exception as e:
            print(f"[TelegramNotifier] 전송 예외 발생: {e}")
            return False

    def send_performance_report(self, report_text: str) -> bool:
        """주간/월간 운영 모니터링 리포트 전송"""
        if not self.enabled or not self.bot_token or not self.chat_id:
            return False

        try:
            payload = {
                "chat_id": self.chat_id,
                "text": report_text,
                "parse_mode": "Markdown"
            }
            res = requests.post(f"{self.api_url}/sendMessage", json=payload, timeout=10)
            return res.status_code == 200
        except Exception:
            return False
