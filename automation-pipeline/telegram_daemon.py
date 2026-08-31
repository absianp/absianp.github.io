import os
import json
import re
import yaml
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

# In-memory storage for pending items
pending_topics = {}
pending_edits = {}

CONTENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", config.get("github", {}).get("blog_content_dir", "../blog-frontend/src/content/blog"))
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 <b>앱시안 블로그 자동화 & 수정 봇입니다.</b>\n\n"
        "✨ <b>새 글 작성:</b>\n"
        "• 주제나 참고 자료/URL 입력\n"
        "• 예: <code>/write 비트코인 10만불 돌파 소식</code>\n\n"
        "✏️ <b>기존 글 수정:</b>\n"
        "• 블로그 URL과 함께 수정 요청사항 입력\n"
        "• 예: <code>https://absianp.github.io/blog/2026-08-31-llm-qwen-27b/ 벤치마크 비교표 보강하고 제목 더 매력적으로 수정해줘</code>\n"
        "• 또는 <code>/edit [URL] [수정사항]</code>",
        parse_mode="HTML"
    )

async def handle_write_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = " ".join(context.args) if context.args else ""
    if not user_text:
        await update.message.reply_text("⚠️ 작성할 주제나 자료를 입력해주세요.\n예: /write 최근 AI 트렌드")
        return
    await process_user_input(update.message, user_text, context)

async def handle_edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = " ".join(context.args) if context.args else ""
    if not user_text:
        await update.message.reply_text("⚠️ 수정할 블로그 글 URL과 수정 요청사항을 함께 입력해주세요.\n예: /edit https://absianp.github.io/blog/2026-08-31-llm-qwen-27b/ 제목 변경해줘")
        return
    await route_message(update.message, user_text, context)

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await route_message(update.message, user_text, context)

async def route_message(message, user_text, context):
    # Check if the message contains an existing blog URL for editing
    blog_url_match = re.search(r"absianp\.github\.io/blog/([^/\s?#]+)", user_text)
    if blog_url_match or user_text.strip().startswith("/edit"):
        await process_edit_input(message, user_text, blog_url_match, context)
    else:
        await process_user_input(message, user_text, context)

async def process_edit_input(message, user_text, blog_url_match, context):
    processing_msg = await message.reply_text("🔍 수정할 블로그 포스팅을 조회하고 수정안을 기획 중입니다. (Antigravity CLI 가동 중...)")
    
    slug = None
    if blog_url_match:
        slug = blog_url_match.group(1).rstrip("/")
    else:
        # Extract slug from /edit command if URL format is different
        parts = user_text.split()
        for p in parts:
            if "blog/" in p:
                slug = p.split("blog/")[-1].strip("/")
                break

    if not slug:
        await processing_msg.edit_text("❌ 수정할 글의 슬러그(URL)를 파싱하지 못했습니다. 블로그 링크를 정확히 입력해주세요.")
        return

    filepath = os.path.join(CONTENT_DIR, f"{slug}.md")
    if not os.path.exists(filepath):
        matched = [f for f in os.listdir(CONTENT_DIR) if f.startswith(slug) and f.endswith(".md")]
        if matched:
            filepath = os.path.join(CONTENT_DIR, matched[0])
            slug = os.path.splitext(matched[0])[0]
        else:
            await processing_msg.edit_text(f"❌ 해당 포스팅 파일(`{slug}.md`)을 블로그 저장소에서 찾을 수 없습니다.")
            return

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            original_raw = f.read()

        runner = AntigravityRunner(config)
        system_prompt = "당신은 전문 기술 블로그 에디터입니다. 기존 글을 사용자의 요청에 맞추어 보강 및 수정하고, 반드시 유효한 JSON 형식으로만 응답해야 합니다."
        user_prompt = f"""
[기존 포스팅 내용]
{original_raw}

[사용자 수정 요청사항]
{user_text}

위 사용자 요청사항을 반영하여 기존 글을 전면 수정/보강해주세요.
프론트매터 메타데이터(title, description, category, tags, faqs 등)와 본문(markdown_content)을 충실하게 작성하고,
무엇이 변경되었는지 핵심 요약(change_summary)을 포함하여 오직 유효한 JSON 형식으로 응답하세요.

출력 JSON 형식:
{{
  "title": "수정된 매력적인 제목",
  "new_slug": "사용자가 URL/슬러그 변경을 요청했거나, 제목에 맞게 영문 슬러그를 변경해야 할 경우에만 새로운 슬러그 지정 (예: 2026-08-31-qwen-27b-review). 변경이 불필요하면 기존 슬러그 그대로 유지",
  "description": "수정된 메타 디스크립션",
  "category": "카테고리",
  "tags": ["태그1", "태그2", "태그3"],
  "readingTime": "8 min read",
  "faqs": [
    {{"question": "질문1", "answer": "답변1"}},
    {{"question": "질문2", "answer": "답변2"}},
    {{"question": "질문3", "answer": "답변3"}}
  ],
  "change_summary": "수정된 핵심 사항 요약 (1~3줄)",
  "markdown_content": "수정된 본문 전체 내용 (마크다운 H2, H3, 표, 리스트 포함)"
}}
"""
        raw_output = runner.generate_text(system_prompt=system_prompt, user_prompt=user_prompt)
        if not raw_output:
            raise Exception("Antigravity 에디터 에이전트로부터 응답을 받지 못했습니다.")

        json_match = re.search(r"\{[\s\S]*\}", raw_output)
        clean_json = json_match.group(0) if json_match else raw_output.strip()
        
        modified_data = json.loads(clean_json)
        edit_id = str(message.message_id)
        pending_edits[edit_id] = {
            "slug": slug,
            "data": modified_data,
            "filepath": filepath
        }

        new_slug_info = ""
        new_slug = modified_data.get("new_slug")
        if new_slug and new_slug != slug:
            new_slug_info = f"\n🔗 <b>URL 변경</b>: <code>{slug}</code> ➔ <code>{new_slug}</code>"

        reply_text = (
            f"✏️ <b>[기존 포스팅 수정 기획안]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>대상 슬러그</b>: <code>{slug}</code>{new_slug_info}\n"
            f"📝 <b>수정된 제목</b>: <b>{modified_data.get('title')}</b>\n"
            f"🏷️ <b>태그</b>: #{', #'.join(modified_data.get('tags', []))}\n\n"
            f"💡 <b>주요 변경 사항</b>:\n"
            f"{modified_data.get('change_summary', '본문 및 구조 보강')}\n\n"
            f"위 수정 사항을 블로그에 즉시 반영하고 재배포할까요?"
        )

        keyboard = [
            [InlineKeyboardButton("✅ 수정 및 재배포", callback_data=f"apply_edit_{edit_id}")],
            [InlineKeyboardButton("❌ 취소", callback_data=f"cancel_edit_{edit_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await processing_msg.edit_text(reply_text, reply_markup=reply_markup, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error in process_edit_input: {e}")
        await processing_msg.edit_text(f"❌ 수정 기획안 작성 중 오류가 발생했습니다: {e}")

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
        runner = AntigravityRunner(config)
        raw_output = runner.generate_text(system_prompt=system_prompt, user_prompt=user_prompt)
        
        if not raw_output:
            raise Exception("Antigravity 파이프라인에서 응답을 생성하지 못했습니다.")
            
        json_match = re.search(r"\{[\s\S]*\}", raw_output)
        clean_json = json_match.group(0) if json_match else raw_output.strip()
        
        topic_data = json.loads(clean_json)
        topic_id = str(message.message_id)
        pending_topics[topic_id] = topic_data
        
        points_str = "\n".join([f"  • {kp}" for kp in topic_data.get("key_points", [])])
        reply_text = (
            f"🎯 <b>[새 포스팅 기획안]</b>\n"
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

    # Cancel actions
    if data.startswith("cancel_"):
        await query.edit_message_text("❌ 작업이 취소되었습니다.")
        return

    # Apply edit action
    if data.startswith("apply_edit_"):
        edit_id = data.split("apply_edit_")[1]
        edit_item = pending_edits.get(edit_id)
        if not edit_item:
            await query.edit_message_text("⚠️ 수정 세션이 만료되었거나 데이터를 찾을 수 없습니다.")
            return

        await query.edit_message_text("✍️ 수정된 내용을 저장하고 GitHub에 재배포하고 있습니다...")
        asyncio.create_task(run_edit_pipeline_async(edit_item, query.message.chat_id, context))
        return

    # New article publish action
    if data.startswith("publish_"):
        topic_id = data.split("_")[1]
        topic = pending_topics.get(topic_id)
        
        if not topic:
            await query.edit_message_text("⚠️ 세션이 만료되었거나 데이터를 찾을 수 없습니다. 다시 시도해주세요.")
            return
            
        await query.edit_message_text("✍️ Antigravity 에이전트가 본문을 작성하고 있습니다. 약 1~2분 정도 소요됩니다...")
        asyncio.create_task(run_interactive_pipeline_async(topic, query.message.chat_id, context))

async def run_edit_pipeline_async(edit_item, chat_id, context):
    try:
        slug = edit_item["slug"]
        article_data = edit_item["data"]
        new_slug = article_data.get("new_slug")
        publisher = GitHubPublisher(config)
        indexer = GoogleIndexing(config)
        
        saved_path, final_slug = publisher.update_existing_article(slug, article_data, new_slug=new_slug)
        site_url = config.get("site", {}).get("url", "https://absianp.github.io")
        full_post_url = f"{site_url.rstrip('/')}/blog/{final_slug}/"
        
        # Ping indexer
        indexer.ping_sitemap()
        
        slug_changed_note = f"\n🔗 <b>새 URL</b>: <a href=\"{full_post_url}\">{full_post_url}</a>\n" if final_slug != slug else ""

        msg = f"""🎉 <b>[포스팅 수정 및 재배포 완료]</b>
━━━━━━━━━━━━━━━━━━━━
📌 <b>제목</b>: <b>{article_data.get('title')}</b>
💡 <b>수정 사항</b>: {article_data.get('change_summary', '수정 완료')}{slug_changed_note}
🔗 <b>글 바로가기</b>:
<a href="{full_post_url}">{full_post_url}</a>

✨ <i>GitHub Pages에 성공적으로 반영 및 재배포되었습니다!</i>"""

        reply_markup = {
            "inline_keyboard": [
                [{"text": "🌐 수정된 글 확인하기", "url": full_post_url}]
            ]
        }
        
        await context.bot.send_message(
            chat_id=chat_id, 
            text=msg,
            parse_mode="HTML",
            disable_web_page_preview=False,
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in edit pipeline: {e}")
        await context.bot.send_message(
            chat_id=chat_id, 
            text=f"❌ 글 수정 및 재배포 중 오류가 발생했습니다: {e}"
        )

async def run_interactive_pipeline_async(topic, chat_id, context):
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
    app.add_handler(CommandHandler("edit", handle_edit_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    logger.info("🤖 텔레그램 인터랙티브 봇 데몬 시작...")
    app.run_polling()

if __name__ == '__main__':
    main()
