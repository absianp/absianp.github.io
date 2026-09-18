"""On-demand operator UI. Starting the bot does not generate articles or send reports."""
import asyncio
import io
import hashlib
import json
import logging
from pathlib import Path
from .config import site_config,state_dir
from .content import digest,inventory,local_asset,image_urls
from .metrics import collect
from .reports import brief,render
from .store import Store
from .workflows import create_workflow,run_workflow,legacy

def credentials(site):
    from dotenv import dotenv_values
    cfg=site_config(site)
    values={}
    for path in (Path(cfg["root"])/".env",Path(cfg["pipeline"])/"config/.env",Path(cfg["pipeline"])/".env"):
        if path.exists():values.update({k:v for k,v in dotenv_values(path).items() if v})
    if not values.get("TELEGRAM_BOT_TOKEN") or not values.get("TELEGRAM_CHAT_ID"):
        raise ValueError("Telegram credentials missing")
    return values

def drafts(site):
    path=Path(site_config(site)["pipeline"])/"data/draft_queue.json"
    if not path.exists():return []
    data=json.loads(path.read_text())
    if not isinstance(data,list):raise ValueError("Invalid review queue")
    return data

def find_draft(site,ident):
    matches=[x for x in drafts(site) if x.get("draft_id")==ident]
    if len(matches)!=1:raise ValueError("정확한 초안 ID가 필요합니다.")
    return matches[0]

def review_fingerprint(item,root):
    assets=[]
    for url in image_urls(item["article"]):
        path=local_asset(root,url)
        if path is None or not path.is_file():
            raise ValueError("검토할 로컬 이미지가 없거나 외부 이미지입니다.")
        assets.append({"url":url,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
    return digest({"article":item["article"],"existing_slug":item.get("existing_slug"),"assets":assets})

def article_review_token(article):
    return hashlib.sha256(json.dumps(article,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()[:12]

def run(site):
    from telegram import InlineKeyboardButton,InlineKeyboardMarkup
    from telegram.ext import ApplicationBuilder,CommandHandler,CallbackQueryHandler,MessageHandler,filters
    cfg=site_config(site)
    creds=credentials(site)
    chat=str(creds["TELEGRAM_CHAT_ID"])
    admin=str(creds.get("TELEGRAM_ADMIN_USER_ID",chat))
    logging.getLogger("httpx").setLevel(logging.CRITICAL)
    logging.getLogger("httpcore").setLevel(logging.CRITICAL)
    store=Store()
    store.recover_expired()
    with store.db() as db:
        db.execute("CREATE TABLE IF NOT EXISTS reviewed_revisions (site TEXT,draft_id TEXT,admin TEXT,hash TEXT,PRIMARY KEY(site,draft_id,admin))")
    app=ApplicationBuilder().token(creds["TELEGRAM_BOT_TOKEN"]).concurrent_updates(True).build()

    def authorized(update):
        return update.effective_chat and str(update.effective_chat.id)==chat and update.effective_user and str(update.effective_user.id)==admin

    async def reply(update,text,**kwargs):
        await update.effective_message.reply_text(text[:4000],**kwargs)

    async def status(update,context):
        if authorized(update):await reply(update,brief(site)+"\n\nCodex 총괄 · agy 일반 작업\n자동 생성 예약: 중지\n/queue /repair /write /audit /metrics /usage")

    async def queue(update,context):
        if not authorized(update):return
        pending=[x for x in drafts(site) if x.get("status") not in ("published","rejected")]
        await reply(update,f"대기·배포 확인 중 {len(pending)}편. 최근 10편을 표시합니다.")
        for item in sorted(pending,key=lambda x:x.get("created_at",""),reverse=True)[:10]:
            ident=item["draft_id"]
            markup=InlineKeyboardMarkup([[InlineKeyboardButton("글·이미지 검토",callback_data="ops_review:"+ident)]])
            await reply(update,f"{item.get('title','')}\n{ident}\n상태: {item.get('status')}",reply_markup=markup)

    async def review_id(update,ident):
        item=find_draft(site,ident)
        article=item["article"]
        body=article.get("markdown_content","")
        report=item.get("review",{})
        summary=f"{article.get('title','')}\n{report.get('summary_for_user','')}\n근거 검토: {report.get('review_status','미확인')}\n첨부된 본문·이미지·출처를 확인한 뒤 승인하세요."
        await reply(update,summary)
        document=io.BytesIO((article.get("title","")+"\n\n"+body).encode())
        await update.effective_message.reply_document(document,filename=ident+".md")
        for url in image_urls(article)[:3]:
            path=local_asset(cfg["root"],url)
            if path and path.is_file():
                with path.open("rb") as image:
                    await update.effective_message.reply_photo(image)
        fingerprint=review_fingerprint(item,cfg["root"])
        with store.db() as db:
            db.execute("INSERT OR REPLACE INTO reviewed_revisions VALUES(?,?,?,?)",(site,ident,admin,fingerprint))
        markup=InlineKeyboardMarkup([[InlineKeyboardButton("검토 후 발행 승인",callback_data="ops_approve:"+ident+":"+fingerprint[:12]),InlineKeyboardButton("보류",callback_data="ops_reject:"+ident)]])
        await reply(update,"이 버전의 본문·이미지 발행을 승인할 수 있습니다.",reply_markup=markup)

    async def review(update,context):
        if authorized(update):await review_id(update,context.args[0] if context.args else "")

    async def approve_id(update,ident,token=None):
        item=find_draft(site,ident)
        fingerprint=review_fingerprint(item,cfg["root"])
        with store.db() as db:
            seen=db.execute("SELECT hash FROM reviewed_revisions WHERE site=? AND draft_id=? AND admin=?",(site,ident,admin)).fetchone()
        if not seen or seen[0]!=fingerprint or (token is not None and token!=fingerprint[:12]):
            await reply(update,"이 버전의 검토 기록이 없습니다. /review "+ident+" 로 실제 글·이미지를 먼저 확인하세요.")
            return
        await reply(update,"승인한 버전의 발행 검사를 시작합니다.")
        result=await asyncio.to_thread(legacy,site,"publish",{"draft_id":ident,"human_approved":True,"expected_review_token":article_review_token(item["article"])})
        await reply(update,result["message"])
        if not result["published"]:
            state=find_draft(site,ident).get("status")
            if state in ("pushed","deployment_pending"):
                context_task=watch_deployment(update,ident)
                app.create_task(context_task,update=update)

    async def watch_deployment(update,ident):
        # Only follows a concrete user-approved publication; no scheduled generation.
        for _ in range(12):
            await asyncio.sleep(30)
            result=await asyncio.to_thread(legacy,site,"reconcile",{"draft_id":ident})
            if result["published"]:
                await reply(update,"공개 글·이미지 검증까지 완료됐습니다.\n"+result["message"])
                return
        await reply(update,"아직 배포 완료를 확인하지 못했습니다. 승인·푸시 기록은 보존했습니다. /reconcile "+ident+" 로 다시 확인할 수 있습니다.")

    async def approve(update,context):
        if authorized(update):await approve_id(update,context.args[0] if context.args else "")

    async def reconcile(update,context):
        if not authorized(update):return
        result=await asyncio.to_thread(legacy,site,"reconcile",{"draft_id":context.args[0] if context.args else ""})
        await reply(update,result["message"])

    async def audit(update,context):
        if not authorized(update):return
        await reply(update,"모델 호출 없이 로컬 글·이미지를 점검합니다.")
        await asyncio.to_thread(inventory,site)
        render(store)
        await reply(update,brief(site))

    async def metrics(update,context):
        if not authorized(update):return
        await asyncio.to_thread(collect,site)
        render(store)
        await reply(update,brief(site))

    async def usage(update,context):
        if authorized(update):await reply(update,json.dumps(store.usage(),ensure_ascii=False,indent=2))

    async def write(update,context):
        if not authorized(update):return
        text=" ".join(context.args)
        parts=[x.strip() for x in text.split("|",2)]
        if len(parts)!=3:
            await reply(update,"사용법: /write 주제 | 독자가 얻을 구체적 가치 | 공식 출처 URL1 URL2\n하루 전체 신규 글 1편 한도이며 생성 후에는 검토를 기다립니다.")
            return
        ident=create_workflow(site,parts[0],parts[2].split(),parts[1],store)
        await reply(update,"Codex·agy 협업 작업을 등록했습니다.\n"+ident)
        async def generate():
            result=await asyncio.to_thread(run_workflow,ident,store)
            await reply(update,f"작업 상태: {result['state']}\n"+json.dumps(result.get("result"),ensure_ascii=False))
            if result["state"]=="pending_review":
                await reply(update,"/review "+result["result"]["draft_id"])
        app.create_task(generate(),update=update)

    async def repair(update,context):
        if not authorized(update):return
        parts=[x.strip() for x in " ".join(context.args).split("|",2)]
        if len(parts)!=3:
            await reply(update,"사용법: /repair 기존글슬러그 | 수정 목적·독자 가치 | 공식출처URL1 URL2")
            return
        ident=create_workflow(site,"기존 글 개선: "+parts[0],parts[2].split(),parts[1],store,existing_slug=parts[0])
        await reply(update,"기존 URL을 유지하는 수정 작업을 등록했습니다. 검토 뒤에 발행합니다.\n"+ident)
        async def generate():
            result=await asyncio.to_thread(run_workflow,ident,store)
            await reply(update,f"수정 작업 상태: {result['state']}\n"+json.dumps(result.get("result"),ensure_ascii=False))
            if result["state"]=="pending_review":await reply(update,"/review "+result["result"]["draft_id"])
        app.create_task(generate(),update=update)

    async def callback(update,context):
        if not authorized(update):return
        await update.callback_query.answer()
        parts=update.callback_query.data.split(":",2)
        action,ident=parts[:2]
        if action=="ops_review":await review_id(update,ident)
        elif action=="ops_approve":await approve_id(update,ident,parts[2] if len(parts)==3 else "")
        elif action=="ops_reject":
            result=await asyncio.to_thread(legacy,site,"reject",{"draft_id":ident})
            await reply(update,result["message"])

    async def reject(update,context):
        if not authorized(update):return
        ident=context.args[0] if context.args else ""
        result=await asyncio.to_thread(legacy,site,"reject",{"draft_id":ident})
        await reply(update,result["message"])

    async def error(update,context):
        if update and authorized(update):
            await reply(update,"작업을 완료하지 못했습니다: "+type(context.error).__name__+". 기존 글·대기열은 유지됩니다. /ops 또는 /queue 로 확인해 주세요.")

    for name,handler in (("start",status),("ops",status),("queue",queue),("review",review),("approve",approve),("reconcile",reconcile),("audit",audit),("metrics",metrics),("usage",usage),("write",write),("repair",repair),("reject",reject)):
        app.add_handler(CommandHandler(name,handler))
    app.add_handler(CallbackQueryHandler(callback,pattern=r"^ops_(review|approve|reject):"))
    app.add_error_handler(error)
    app.run_polling(drop_pending_updates=False)
