import os
import json
import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

from integrations.telegram_bot import _load_env_file, TelegramNotifier
from integrations.antigravity_runner import AntigravityRunner
from main_pipeline import load_config, KeywordHarvester, ContentWriter, PolicyInspector, GitHubPublisher, GoogleIndexing
import asyncio

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

config = load_config()
_load_env_file()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# In-memory storage for pending topics
pending_topics = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 앱시안 블로그 자동화 봇입니다.\n"
        "작성하고 싶은 '주제'나 '참고 자료(텍스트/URL)'를 입력해주세요.\n"
        "예: /write 비트코인 10만불 돌파 소식"
    )

async def handle_write_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = " ".join(context.args) if context.args else ""
    if not user_text:
        await update.message.reply_text("⚠️ 작성할 주제나 자료를 입력해주세요.\n예: /write 최근 AI 트렌드")
        return
    await process_user_input(update.message, user_text, context)

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await process_user_input(update.message, user_text, context)

async def process_user_input(message, user_text, context):
    processing_msg = await message.reply_text("⏳ 입력하신 자료를 분석하여 포스팅 기획안을 작성 중입니다. (Antigravity CLI 가동 중...)")
    
    try:
        system_prompt = "당신은 수익화 블로그 기획 전문가입니다. 오직 유효한 JSON 형식으로만 응답해야 합니다."
        user_prompt = f"""
다음 사용자의 입력 자료나 주제를 바탕으로 블로그 포스팅 기획안을 작성해주세요.
반드시 마크다운 없이 순수 JSON 형식으로 응답하세요.

입력 자료: {user_text}

출력 JSON 형식:
{{
  "title": "클릭을 유도하는 매력적인 제목",
  "category": "AI & 생산성",
  "target_keyword": "핵심 롱테일 키워드",
  "tags": ["태그1", "태그2", "태그3"],
  "key_points": ["포인트1", "포인트2", "포인트3"]
}}
"""
        # Antigravity CLI / SDK 를 통해 텍스트 생성
        runner = AntigravityRunner(config)
        raw_output = runner.generate_text(system_prompt=system_prompt, user_prompt=user_prompt)
        
        if not raw_output:
            raise Exception("Antigravity 파이프라인에서 응답을 생성하지 못했습니다.")
            
        # Extract JSON block reliably using regex
        json_match = re.search(r"\{[\s\S]*\}", raw_output)
        if json_match:
            clean_json = json_match.group(0)
        else:
            clean_json = raw_output.strip()
        
        topic_data = json.loads(clean_json)
        topic_id = str(message.message_id)
        pending_topics[topic_id] = topic_data
        
        points_str = "\n".join([f"  • {kp}" for kp in topic_data.get("key_points", [])])
        reply_text = (
            f"🎯 <b>[포스팅 기획안]</b>\n"
            f"📌 제목: {topic_data.get('title')}\n"
            f"🏷️ 태그: {', '.join(topic_data.get('tags', []))}\n"
            f"📝 다룰 내용:\n{points_str}\n\n"
            f"이 기획안으로 글 작성을 진행할까요?"
        )
        
        keyboard = [
            [InlineKeyboardButton("✅ 작성 및 발행", callback_data=f"publish_{topic_id}")],
            [InlineKeyboardButton("❌ 취소", callback_data=f"cancel_{topic_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await processing_msg.edit_text(reply_text, reply_markup=reply_markup, parse_mode="HTML")
        
    except json.JSONDecodeError:
        logger.error(f"JSON 파싱 실패: {raw_output}")
        await processing_msg.edit_text(f"❌ 기획안 파싱 실패. AI가 JSON 형식을 반환하지 않았습니다.\n(결과: {raw_output[:100]}...)")
    except Exception as e:
        logger.error(f"Error in process_user_input: {e}")
        await processing_msg.edit_text(f"❌ 기획안 작성 중 오류가 발생했습니다: {e}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data.startswith("cancel_"):
        await query.edit_message_text("❌ 작성이 취소되었습니다.")
        return
        
    if data.startswith("publish_"):
        topic_id = data.split("_")[1]
        topic = pending_topics.get(topic_id)
        
        if not topic:
            await query.edit_message_text("⚠️ 세션이 만료되었거나 데이터를 찾을 수 없습니다. 다시 시도해주세요.")
            return
            
        await query.edit_message_text("✍️ Antigravity 에이전트가 본문을 작성하고 있습니다. 약 1~2분 정도 소요됩니다...")
        
        asyncio.create_task(run_interactive_pipeline_async(topic, query.message.chat_id, query.message.message_id, context))

async def run_interactive_pipeline_async(topic, chat_id, message_id, context):
    try:
        writer = ContentWriter(config)
        inspector = PolicyInspector(config)
        publisher = GitHubPublisher(config)
        telegram = TelegramNotifier(config)
        indexer = GoogleIndexing(config)
        
        # 2단계: 아티클 작성
        article = writer.write_article(topic)
        
        # 3단계: 정책 검사
        inspection = inspector.inspect_article(article)
        
        # 4단계: 발행
        saved_path = publisher.publish_article(article)
        site_url = config.get("site", {}).get("url", "https://absianp.github.io")
        post_slug = os.path.splitext(os.path.basename(saved_path))[0]
        full_post_url = f"{site_url.rstrip('/')}/blog/{post_slug}/"
        
        # 5단계: 색인 요청
        indexer.ping_sitemap()
        
        # 텔레그램 공식 알림 전송
        telegram.send_article_published(article, inspection, full_post_url)
        
        await context.bot.send_message(
            chat_id=chat_id, 
            text=f"🎉 성공적으로 게시되었습니다!\n\n🔗 {full_post_url}"
        )
        
    except Exception as e:
        logger.error(f"Error in pipeline: {e}")
        await context.bot.send_message(
            chat_id=chat_id, 
            text=f"❌ 글 작성 및 배포 중 오류가 발생했습니다: {e}"
        )

def main():
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set.")
        return
        
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("write", handle_write_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    logger.info("🤖 텔레그램 인터랙티브 봇 데몬 시작...")
    app.run_polling()

if __name__ == '__main__':
    main()
