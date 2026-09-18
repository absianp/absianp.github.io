"""Roles are policy, not model guesses or score-based approvals."""
ROUTES = {
    "inventory": "code", "audit": "code", "metrics": "code", "evidence": "code",
    "queue_draft": "code", "reconcile": "code",
    "source_summary": "agy", "metadata": "agy", "report_summary": "agy", "triage": "agy",
    "plan": "codex", "draft": "codex", "review": "codex", "images": "codex", "experiment": "codex"
}


def route(kind):
    if kind not in ROUTES:
        raise ValueError("Unknown task kind")
    return ROUTES[kind]


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def validate_auxiliary(result, kind, evidence=()):
    schemas = {
        "source_summary": {"sources", "escalation_reason"},
        "metadata": {"description", "tags", "escalation_reason"},
        "report_summary": {"summary", "actions", "escalation_reason"},
        "triage": {"issues", "escalation_reason"},
    }
    if kind not in schemas:
        raise ValueError("Unknown auxiliary task kind")
    if not isinstance(result, dict):
        raise ValueError("Worker result must be an object")
    if set(result) - schemas[kind]:
        raise ValueError("Auxiliary worker exceeded scope")
    if result.get("escalation_reason") is not None:
        raise ValueError("Worker requested Codex review or returned invalid escalation state")
    if kind == "source_summary":
        if not isinstance(evidence, (list, tuple)):
            raise ValueError("Invalid source evidence")
        sources = {}
        for item in evidence:
            if not isinstance(item, dict) or not _text(item.get("id")) or not isinstance(item.get("text"), str) or item["id"] in sources:
                raise ValueError("Invalid or duplicate source evidence")
            sources[item["id"]] = item
        if not isinstance(result.get("sources"), list) or not result["sources"]:
            raise ValueError("Missing source extraction")
        for item in result["sources"]:
            if not isinstance(item, dict) or not _text(item.get("source_id")):
                raise ValueError("Invalid source extraction")
            source = sources.get(item["source_id"])
            if not source or not _text(item.get("quote")) or item["quote"] not in source["text"]:
                raise ValueError("Source quote cannot be traced to the fetched document")
            if not _text(item.get("summary")):
                raise ValueError("Source summary missing")
    elif kind == "metadata":
        if not _text(result.get("description")):
            raise ValueError("Description missing")
        if not isinstance(result.get("tags"), list) or any(not _text(tag) for tag in result["tags"]):
            raise ValueError("Tags must be nonempty strings")
    elif kind == "report_summary":
        if not _text(result.get("summary")):
            raise ValueError("Report summary missing")
        if not isinstance(result.get("actions"), list) or any(not _text(action) for action in result["actions"]):
            raise ValueError("Report actions must be a list of strings")
    elif kind == "triage":
        if not isinstance(result.get("issues"), list):
            raise ValueError("Triage issues must be a list")
        for item in result["issues"]:
            if not isinstance(item, dict) or not _text(item.get("code")) or not _text(item.get("reason")):
                raise ValueError("Triage issue requires a code and reason")
            priority = item.get("priority")
            valid_priority = type(priority) is int and 0 <= priority <= 3
            if isinstance(priority, str):
                valid_priority = priority.lower() in ("p0", "p1", "p2", "p3", "blocker", "high", "medium", "low")
            if not valid_priority:
                raise ValueError("Triage priority must be 0–3, P0–P3, blocker/high/medium/low")
    return result
