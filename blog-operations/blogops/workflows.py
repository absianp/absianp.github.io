import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from .config import ROOT,settings,site_config,state_dir,save_json
from .content import collect_evidence,content_issues,digest,inventory,validate_review,image_urls,local_asset,read_post,image_manifest,local_evidence,validate_verified_code
from .routing import route,validate_auxiliary
from .runners import Runner,RunnerError
from .store import Store,BudgetExceeded,today

STAGES=["evidence","source_summary","plan","draft","metadata","images","review","queue_draft"]

def legacy(site,mode,payload):
    cfg=site_config(site)
    python=Path(cfg["pipeline"])/"venv/bin/python3"
    with tempfile.TemporaryDirectory(prefix="blogops-bridge-") as tmp:
        source,output=Path(tmp)/"input.json",Path(tmp)/"output.json"
        source.write_text(json.dumps(payload,ensure_ascii=False))
        result=subprocess.run([str(python),str(ROOT/"blogops/legacy_worker.py"),mode,"--pipeline",cfg["pipeline"],
                               "--input",str(source),"--output",str(output)],cwd=cfg["pipeline"],capture_output=True,text=True,
                              timeout=3000 if mode=="images" else 180)
        if result.returncode or not output.exists():
            raise RunnerError(f"Site {mode} worker failed; inspect local service logs (exit {result.returncode})")
        value=json.loads(output.read_text())
        if mode in ("publish","reconcile","reject"):
            path=Path(cfg["pipeline"])/"data/draft_queue.json"
            if path.exists():
                queue=json.loads(path.read_text())
                item=next((x for x in queue if x.get("draft_id")==payload["draft_id"]),{})
                workflow=item.get("article",{}).get("operations",{}).get("workflow_id")
                if workflow:
                    store=Store()
                    if store.get(workflow):store.finish(workflow,{"draft_id":payload["draft_id"],"publication":value},state=item.get("status","needs_attention"))
        return value

def create_workflow(site,topic,urls,original_value,store=None,existing_slug=None,verification_files=(),image_assets=None):
    store=store or Store()
    cfg=site_config(site)
    if not topic.strip() or not original_value.strip() or not urls:
        raise ValueError("Topic, primary-source URLs and original reader value are required")
    verified=local_evidence(verification_files)
    existing_article=None
    if existing_slug:
        import re
        if not re.fullmatch(r"[a-zA-Z0-9가-힣_-]+",existing_slug):raise ValueError("Invalid existing post slug")
        path=Path(cfg["root"])/"blog-frontend/src/content/blog"/(existing_slug+".md")
        meta,body=read_post(path)
        existing_article={**meta,"markdown_content":body}
    with store.lock("create-workflow"):
        current=store.list()
        active=[x for x in current if x["kind"]=="workflow" and x["site"]==site and x["state"] not in ("published","rejected")]
        if len(active)>=settings()["limits"]["pending_per_site"]:
            raise BudgetExceeded("Site review backlog limit reached")
        from datetime import datetime
        from zoneinfo import ZoneInfo
        todays=[x for x in current if x["kind"]=="workflow" and datetime.fromtimestamp(x["created"],ZoneInfo("Asia/Seoul")).date().isoformat()==today()]
        if len(todays)>=settings()["limits"]["new_workflows_per_day"]:
            raise BudgetExceeded("Daily new draft limit reached; prioritize existing drafts")
        payload={"topic":topic,"urls":urls,"original_value":original_value,"site":site}
        if verified:payload["verification_records"]=verified
        if image_assets is not None:payload["image_assets"]=image_assets
        if existing_slug:
            payload.update(existing_slug=existing_slug,existing_article=existing_article)
        workflow=store.enqueue(site,"workflow","code",payload)
        store.finish(workflow,{"status":"queued"},state="workflow_pending")
        deps=[]
        for kind in STAGES:
            task=store.enqueue(site,kind,route(kind),payload,dependencies=deps,parent=workflow,dedupe=f"{workflow}:{kind}")
            deps=[task]
        return workflow

def inputs(store,parent):
    return {x["kind"]:x["result"] for x in store.list(parent=parent) if x["state"]=="succeeded"}

def article_from(results):
    article=dict(results["draft"])
    if "metadata" in results:
        article.update({k:v for k,v in results["metadata"].items() if k in ("description","tags")})
    return results.get("images",article)

def prompt(kind,cfg,payload,results):
    source=results.get("evidence",[])
    request_payload={k:v for k,v in payload.items() if k not in ("verification_records","image_assets")}
    common={"site":{"name":cfg["name"],"language":cfg["language"],"focus":cfg["focus"]},"request":request_payload,
            "evidence":source,"previous":{k:v for k,v in results.items() if k not in ("evidence","images")}}
    instruction={
      "source_summary":"Extract supporting source passages. Return {sources:[{source_id,quote,summary}],escalation_reason:null}. Every quote must be an exact substring of the supplied source text. No new facts.",
      "plan":"Plan one useful article. Return {reader_problem,original_value,outline,claims_to_verify}. Reject fabricated experiments/experience. Original value must be possible using supplied facts; do not pretend tests happened.",
      "draft":"If request.existing_article is present, revise that post for the requested reader value while preserving useful verified parts. Treat existing claims as unverified; recheck against provided evidence. Write one complete publishable draft as JSON with title,description,category,tags,markdown_content,faqs. Include source links and relevant reference dates. No unfinished placeholders, false experience, promises of income, medical prescriptions, or copied lyrics. K-Pop lessons use original everyday examples, never lyric quotation or translation; include artist,songTitle,genre,difficulty (Beginner/Intermediate/Advanced) when relevant. Match site language. Do not include images or frontmatter; a later stage generates images. All material factual claims must come from provided evidence. Operator-supplied test artifacts describe observations only in their recorded environment; distinguish injected faults from physical hardware tests. If a verified Python script is provided, reproduce it exactly in one Python code block without rewriting it. Cite official web sources by URL; do not expose local absolute paths or include fabricated web links for local artifacts. Article test dates and counts must match the records. If inadequate, return {error:reason}.",
      "metadata":"Improve only description and tags, based on the existing article. Return {description:string,tags:[string],escalation_reason:null}. Do not return or change body/title or add unsupported facts.",
      "review":"Independently check the supplied final article and attached images against the full source texts, not just previous summaries. Return {decision:pass|revise,rights:clear|needs_review,original_value:string,requires_expert_review:boolean,coverage_checked:boolean,issues:[string],claims:[{claim,source_id,quote,assessment:supported|unsupported}]}. Each claim must be an exact substring (whole statement/sentence) in the article; quote must be a meaningful exact substring of the source. Cover all material factual claims, especially EVERY date, financial number, percent and benefit claim. Set coverage_checked only after checking the entire article. Mark unsupported or conflicting claims, image/text mistakes, insufficient original value and incomplete notes. For K-Pop disallow lyric reproduction/translation and verify Korean grammar. For health/personal financial advice require expert review. Generated illustrations cannot serve as proof of real use. When uncertain use revise. Do not claim human or Google approval.",
      "report_summary":"Summarize the supplied measured report in Korean. Preserve unavailable values, never fill them with estimates. Return {summary:string,actions:[string],escalation_reason:null}.",
      "triage":"Classify supplied inspection issues. Return {issues:[{code,priority,reason}],escalation_reason:null}. Do not invent observations.",
      "experiment":"Propose one bounded experiment only from supplied measured data. Return {hypothesis,change,measurement,stop_conditions,insufficient_data:boolean}. Do not predict revenue or declare a winner without adequate data."
    }[kind]
    if kind=="review":
        common.pop("previous")
        common["request"]={key:value for key,value in request_payload.items() if key!="existing_article"}
        common["final_article"]=article_from(results)
        validate_verified_code(common["final_article"],source)
        common["verified_python_identity_checked"]=any(item.get("kind")=="operator_supplied_test_artifact"
            and str(item.get("title","")).endswith(".py") for item in source)
        instruction+=(" Keep the JSON concise: group related factual prose into at most 40 exact claim excerpts, "
                      "using only the relevant source quote (at most 900 characters per quote). "
                      "Do not repeat entire scripts or enumerate every code token as a separate claim. "
                      "When verified_python_identity_checked is true, deterministic code has already confirmed the "
                      "article Python block matches the supplied tested script byte for byte. Still review its stated "
                      "behavior and limitations, prose, FAQs, and images for conflicts. Claims should cite exact excerpts "
                      "from title, description, or markdown_content; report FAQ problems in issues. "
                      "Do not drop unsupported claims to meet the output bound; use revise if coverage is inadequate.")
    return instruction+"\nINPUT DATA:\n"+json.dumps(common,ensure_ascii=False,default=str)

def run_task(ident,store=None):
    store=store or Store()
    task=store.claim(ident)
    if not task:
        return None
    cfg=site_config(task["site"])
    result_inputs=inputs(store,task["parent"]) if task["parent"] else {}
    result=None
    try:
        kind=task["kind"]
        if kind=="evidence":
            result=collect_evidence(task["payload"]["urls"])+task["payload"].get("verification_records",[])
        elif kind in ("audit","inventory"):
            result=inventory(task["site"],task["payload"].get("live",False))
        elif kind=="metrics":
            from .metrics import collect
            result=collect(task["site"])
        elif kind=="images" and task["payload"].get("image_assets") is not None:
            from .prepared_assets import attach_images
            result=attach_images(article_from(result_inputs),task["payload"]["image_assets"],cfg["root"])
        elif kind=="images":
            with store.lock("provider:codex",3100):
                calls=[]
                try:
                    calls=store.reserve_calls("codex",settings()["providers"]["codex_model"],settings()["limits"]["codex_calls_per_day"],ident,3)
                    start=time.monotonic()
                    result=legacy(task["site"],"images",{"article":article_from(result_inputs)})
                except Exception:
                    for call in calls:store.finish_call(call,"failed",0)
                    raise
                for call in calls:store.finish_call(call,"succeeded",(time.monotonic()-start)/3)
        elif kind=="queue_draft":
            article=article_from(result_inputs)
            gate=validate_review(article,result_inputs["review"],result_inputs["evidence"],task["site"])
            manifest=image_manifest(article,cfg["root"])
            if manifest!=result_inputs["review"].get("_reviewed_images"):
                raise ValueError("Images changed after independent review")
            gate["image_manifest"]=manifest
            article["operations"]={"workflow_id":task["parent"],"gate":gate,"review":result_inputs["review"]}
            review={"total_score":0,"verdict":"REVIEW_REQUIRED","is_approved":False,
                    "review_status":"evidence_checked_needs_human_review","summary_for_user":result_inputs["review"]["original_value"],
                    "operations":gate}
            result=legacy(task["site"],"queue",{"article":article,"review":review,"topic":task["payload"]})

        elif kind=="reconcile":
            result=legacy(task["site"],"reconcile",task["payload"])
        else:
            runner=Runner(store)
            request=prompt(kind,cfg,task["payload"],result_inputs)
            if task["provider"]=="agy":
                for attempt in range(2):
                    try:
                        result=runner.run("agy",request+("\nFollow the exact schema and source substrings; previous attempt failed validation." if attempt else ""),ident)
                        validate_auxiliary(result,kind,result_inputs.get("evidence",[]))
                        break
                    except (RunnerError,ValueError):
                        if attempt==1:
                            result=runner.run("codex",request+"\nTake over: agy failed bounded-output validation.",ident)
                            validate_auxiliary(result,kind,result_inputs.get("evidence",[]))
            else:
                images=[]
                if kind=="review":
                    reviewed_images=image_manifest(article_from(result_inputs),cfg["root"])
                    for url in image_urls(article_from(result_inputs)):
                        path=local_asset(cfg["root"],url)
                        if path and path.is_file():images.append(path)
                result=runner.run(task["provider"],request,ident,images=images)
                if kind=="review":result["_reviewed_images"]=reviewed_images
            if kind=="draft":
                validate_verified_code(result,result_inputs.get("evidence",[]))
                if task["payload"].get("existing_slug"):
                    result["existing_slug"]=task["payload"]["existing_slug"]
                    result["slug"]=task["payload"]["existing_slug"]
                if any(i["severity"]=="blocker" for i in content_issues(result,task["site"])):
                    raise ValueError("Draft needs substantive revision")
            if kind=="review":
                validate_review(article_from(result_inputs),result,result_inputs["evidence"],task["site"])
        if not store.finish(ident,result,expected_attempt=task["attempts"]):
            return {"status":"stale_worker","reason":"Task lease or attempt changed"}
        if kind=="queue_draft":store.finish(task["parent"],result,state="pending_review")
        return result
    except Exception as exc:
        state="budget_wait" if isinstance(exc,BudgetExceeded) else "needs_attention"
        safe_message=str(exc) if isinstance(exc,(RunnerError,BudgetExceeded,ValueError)) else type(exc).__name__
        saved=store.finish(ident,result,error=safe_message,state=state,expected_attempt=task["attempts"])
        if saved and task["parent"]:
            store.finish(task["parent"],{"task_id":ident,"reason":safe_message},state=state)
        return {"status":state,"reason":safe_message}

def run_workflow(ident,store=None):
    store=store or Store()
    store.recover_expired()
    parent=store.get(ident)
    if not parent or parent["kind"]!="workflow":
        raise ValueError("Unknown workflow")
    with store.lock("workflow:"+ident,14400):
        for task in store.list(parent=ident):
            if task["state"] in ("needs_attention","budget_wait","failed"):
                return store.get(ident)
            if task["state"]=="queued":
                run_task(task["id"],store)
                if store.get(task["id"])["state"]!="succeeded":
                    break
        return store.get(ident)
