import html
import json
from pathlib import Path
from .config import settings,state_dir,save_json
from .store import Store
from .content import timestamp

def load_report(name):
    path=state_dir()/"reports"/name
    return json.loads(path.read_text()) if path.exists() else None

def render(store=None):
    store=store or Store()
    entries=[]
    for site,cfg in settings()["sites"].items():
        inv=load_report(site+"-inventory.json")
        metrics=load_report(site+"-metrics.json")
        entries.append({"id":site,"name":cfg["name"],"inventory":inv,"metrics":metrics})
    tasks=store.list()
    payload={"created_at":timestamp(),"sites":entries,"usage":store.usage(),
             "tasks":[{k:t[k] for k in ("id","site","kind","provider","state","error")} for t in tasks],
             "limits":settings()["limits"],"scheduling":"Old timers disabled. New AI generation is on demand only."}
    save_json(state_dir()/"reports/dashboard.json",payload)
    cards=[]
    issues=[]
    for entry in entries:
        inv=entry["inventory"] or {}
        measured=entry["metrics"] or {}
        metriclines=[]
        for source in ("adsense","search_console","ga4"):
            record=measured.get("sources",{}).get(source,{"status":"not_collected"})
            values=record.get("metrics")
            metriclines.append(f'<li><b>{html.escape(source)}</b>: {html.escape(record["status"])}'+
                               (f'<p>기간: {html.escape(str(record.get("period","미확인")))} · 통화: {html.escape(str(record.get("currency") or "해당 없음"))}</p><pre>{html.escape(json.dumps(values,ensure_ascii=False,indent=2))}</pre>' if values is not None else ' · 실측 값 미확인')+'</li>')
        cards.append(f'<article><h2>{html.escape(entry["name"])}</h2><p>공개 설정 글 {inv.get("public_posts","미확인")}편 · 기술 차단 {inv.get("blocker_count","미확인")} · 검토 항목 {inv.get("review_count","미확인")}</p><p>애드센스: {html.escape(measured.get("adsense_state","unknown"))}</p><ul>{"".join(metriclines)}</ul></article>')
        for post in inv.get("posts",[]):
            for issue in post["issues"]:
                issues.append('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in
                                           (entry["name"],post.get("title",post["slug"]),issue["severity"],issue["code"],issue["detail"]))+'</tr>')
    usage=''.join('<tr>'+''.join('<td>'+html.escape(str(row.get(k,"")))+'</td>' for k in ("day","provider","calls","seconds"))+'</tr>' for row in payload["usage"])
    content='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>블로그 운영 현황</title><style>body{font:16px/1.65 system-ui,sans-serif;background:#f3f5f9;color:#152239;margin:0;padding:32px;max-width:1400px;margin:auto}h1{font-size:30px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}article,section{background:white;padding:24px;border-radius:12px;margin-bottom:20px}h2{font-size:21px}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:10px;text-align:left;border-bottom:1px solid #e5eaf1}pre{white-space:pre-wrap;font-size:13px}p.note{color:#50627c}ul{padding-left:20px}</style><h1>블로그 승인·수익 운영 현황</h1><p class="note">실측이 연결되지 않은 값은 미확인으로 표시합니다. 광고 수익은 Google 추정 수익이며 확정 지급액과 다릅니다. 기존 예약 실행은 중지되어 있습니다.</p><main>'''+''.join(cards)+f'''</main><section><h2>실행 사용량</h2><p>초기 호출 한도: Codex {payload["limits"]["codex_calls_per_day"]}회 / agy {payload["limits"]["agy_calls_per_day"]}회 · 전체 신규 글 {payload["limits"]["new_workflows_per_day"]}편/일. 호출에는 실패·예약도 포함되며 실제 요금 추정값이 아닙니다.</p><table><thead><tr><th>일자</th><th>도구</th><th>호출</th><th>실행 초</th></tr></thead><tbody>{usage}</tbody></table></section><section><h2>기존 글의 조치 목록</h2><p>권리·금액 검토 표시는 확정 위반 판정이 아닙니다.</p><table><thead><tr><th>사이트</th><th>글</th><th>분류</th><th>항목</th><th>내용</th></tr></thead><tbody>{''.join(issues)}</tbody></table></section><p class="note">생성 시각 {payload["created_at"]}</p></html>'''
    path=state_dir()/"reports/dashboard.html"
    path.write_text(content)
    return str(path)

def brief(site):
    inv=load_report(site+"-inventory.json") or {}
    snapshot=load_report(site+"-metrics.json") or {}
    lines=[settings()["sites"][site]["name"],f"공개 설정 글: {inv.get('public_posts','미확인')}편",f"차단: {inv.get('blocker_count','미확인')} / 검토: {inv.get('review_count','미확인')}",f"애드센스 상태: {snapshot.get('adsense_state','미확인')}"]
    for source,record in snapshot.get("sources",{}).items():
        lines.append(f"{source}: {record['status']}"+(f" {json.dumps(record['metrics'],ensure_ascii=False)} · 기간 {record.get('period','미확인')} · 통화 {record.get('currency') or '해당 없음'}" if record.get("metrics") is not None else " · 수치 미확인"))
    return '\n'.join(lines)
