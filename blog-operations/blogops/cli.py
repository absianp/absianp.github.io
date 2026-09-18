import argparse
import json
from pathlib import Path
from .config import settings,site_config,state_dir,save_json
from .content import inventory
from .metrics import collect,connect_google
from .reports import render
from .routing import route
from .store import Store
from .workflows import create_workflow,run_task,run_workflow,legacy

def output(data):
    print(json.dumps(data,ensure_ascii=False,indent=2,default=str))

def main(argv=None):
    parser=argparse.ArgumentParser(description="Codex 총괄 + agy 실무 블로그 운영")
    sub=parser.add_subparsers(dest="command",required=True)
    for kind in ("audit","metrics","status","queue","report"):
        cmd=sub.add_parser(kind)
        cmd.add_argument("--site",choices=list(settings()["sites"])+["all"],default="all")
        if kind=="audit":cmd.add_argument("--live",action="store_true")
    workflow=sub.add_parser("draft")
    workflow.add_argument("--site",required=True,choices=settings()["sites"])
    workflow.add_argument("--topic",required=True)
    workflow.add_argument("--source",action="append",required=True)
    workflow.add_argument("--value",required=True,help="독자가 얻는 원본 가치")
    workflow.add_argument("--run",action="store_true")
    workflow.add_argument("--existing-slug",help="기존 URL을 유지하며 글을 수정")
    workflow.add_argument("--verification-file",action="append",default=[],help="실제 테스트 기록·검증된 예제 파일")
    workflow.add_argument("--image-assets",help="기존·준비된 이미지의 경로와 SHA256 JSON")
    task=sub.add_parser("task")
    task.add_argument("--site",required=True,choices=settings()["sites"])
    task.add_argument("--kind",required=True,choices=["report_summary","triage","plan","experiment"])
    task.add_argument("--input",required=True)
    task.add_argument("--run",action="store_true")
    for command in ("run","retry"):
        p=sub.add_parser(command);p.add_argument("id")
    for command in ("approve","reconcile"):
        p=sub.add_parser(command);p.add_argument("--site",required=True,choices=settings()["sites"]);p.add_argument("draft_id")
        if command=="approve":p.add_argument("--reviewed",action="store_true",required=True,help="해당 글·이미지·출처를 사람이 검토했다는 명시적 승인")
    auth=sub.add_parser("connect-google");auth.add_argument("--client-secrets",required=True)
    configure=sub.add_parser("configure-site");configure.add_argument("--site",required=True,choices=settings()["sites"]);configure.add_argument("--ga4-property");configure.add_argument("--gsc-property")
    bot=sub.add_parser("bot");bot.add_argument("--site",required=True,choices=settings()["sites"])
    args=parser.parse_args(argv)
    store=Store()
    store.recover_expired()
    if args.command=="connect-google":return output(connect_google(args.client_secrets))
    if args.command=="configure-site":
        path=state_dir()/"settings.json"
        data=json.loads(path.read_text()) if path.exists() else {}
        site=data.setdefault("sites",{}).setdefault(args.site,{})
        for attr in ("ga4_property","gsc_property"):
            value=getattr(args,attr)
            if value:site[attr]=value
        save_json(path,data);return output({"site":args.site,"configured":list(site)})
    if args.command=="bot":
        from .bot import run
        return run(args.site)
    if args.command=="draft":
        ident=create_workflow(args.site,args.topic,args.source,args.value,store,existing_slug=args.existing_slug,verification_files=args.verification_file,image_assets=json.loads(Path(args.image_assets).read_text()) if args.image_assets else None)
        return output(run_workflow(ident,store) if args.run else {"workflow_id":ident,"status":"queued"})
    if args.command=="task":
        payload=json.loads(Path(args.input).read_text())
        ident=store.enqueue(args.site,args.kind,route(args.kind),payload)
        return output(run_task(ident,store) if args.run else {"task_id":ident})
    if args.command=="retry":return output({"retried":store.retry(args.id)})
    if args.command=="run":
        task=store.get(args.id)
        if not task:raise ValueError("Unknown task")
        return output(run_workflow(args.id,store) if task["kind"]=="workflow" else run_task(args.id,store))
    if args.command in ("approve","reconcile"):
        return output(legacy(args.site,"publish" if args.command=="approve" else "reconcile",{"draft_id":args.draft_id,"human_approved":args.command=="approve"}))
    sites=list(settings()["sites"]) if args.site=="all" else [args.site]
    if args.command=="audit":
        result=[inventory(site,args.live) for site in sites]
        render(store)
        return output([{k:v for k,v in item.items() if k!="posts"} for item in result])
    if args.command=="metrics":
        result=[collect(site) for site in sites];render(store);return output(result)
    if args.command=="report":return output({"path":render(store)})
    if args.command=="queue":
        return output([{"id":x["id"],"site":x["site"],"kind":x["kind"],"provider":x["provider"],"state":x["state"],"error":x["error"]} for x in store.list() if x["site"] in sites])
    return output({"sites":sites,"usage":store.usage(),"limits":settings()["limits"],"report":render(store),"generation_schedule":"disabled; demand only"})

if __name__=="__main__":
    main()
