"""One subprocess per site avoids cached imports crossing repository boundaries."""
import argparse
import json
import sys
from pathlib import Path

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("mode",choices=["images","queue","publish","reconcile","reject"])
    parser.add_argument("--pipeline",required=True)
    parser.add_argument("--input",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    sys.path.insert(0,str(Path(args.pipeline).resolve()))
    from modules.configuration import load_configuration
    config=load_configuration(args.pipeline)
    config.setdefault("telegram",{})["enabled"]=False  # The calling UI reports the result once.
    payload=json.loads(Path(args.input).read_text())
    if args.mode=="images":
        from modules.gpt_images import prepare_article_images
        result=prepare_article_images(payload["article"],config)
    elif args.mode=="queue":
        from modules.draft_queue import DraftApprovalQueue
        queue=DraftApprovalQueue(args.pipeline)
        workflow=payload["article"].get("operations",{}).get("workflow_id")
        matches=[x for x in queue._load_data() if workflow and x.get("article",{}).get("operations",{}).get("workflow_id")==workflow]
        if matches:
            if matches[0]["article"]!=payload["article"]:
                raise ValueError("Workflow already queued with different content")
            ident=matches[0]["draft_id"]
        else:
            ident=queue.add_draft(payload["article"],payload["review"],topic=payload["topic"])
        result={"draft_id":ident,"status":"pending_review"}
    elif args.mode=="reject":
        from modules.draft_queue import DraftApprovalQueue
        queue=DraftApprovalQueue(args.pipeline)
        item=queue.get_draft(payload["draft_id"])
        if not item or item.get("status") not in ("pending_review","approved") or item.get("publication",{}).get("commit_sha"):
            raise ValueError("Only an unpublished draft can be rejected")
        ok=queue.mark_rejected(item["draft_id"],"Operator deferred publication")
        result={"status":"rejected" if ok else "failed","message":"보류했습니다." if ok else "보류 상태 저장 실패"}
    else:
        if Path(args.pipeline,"daily_kpop_pipeline.py").exists():
            import daily_kpop_pipeline as pipeline
        else:
            import main_pipeline as pipeline
        if args.mode=="publish":
            if payload.get("human_approved") is not True:
                raise PermissionError("Human approval required")
            ok,message=pipeline.publish_queued_draft(config,payload["draft_id"],human_approved=True,
                                                   expected_review_token=payload.get("expected_review_token"))
        else:
            ok,message=pipeline.reconcile_queued_draft(config,payload["draft_id"])
        result={"published":ok,"message":message}
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,default=str))

if __name__=="__main__":
    main()
