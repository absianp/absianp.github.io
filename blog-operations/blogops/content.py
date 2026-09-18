import hashlib
import ipaddress
import json
import re
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit
import certifi
import urllib3
import yaml
from bs4 import BeautifulSoup
from .config import site_config, state_dir, save_json

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()

def timestamp():
    return datetime.now(timezone.utc).isoformat()

def safe_get(url, *, max_bytes=1500000, timeout=20):
    """Fetch public HTTPS resources; no cookies, credentials or executable browser."""
    for _ in range(5):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,443):
            raise ValueError("Only public HTTPS URLs without credentials are allowed")
        addresses = socket.getaddrinfo(parsed.hostname,443,type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise ValueError("Source host is not public")
        # Connect to the validated IP, while verifying TLS for the original host.
        # This also avoids .netrc credentials and ambient proxy configuration.
        pool=urllib3.HTTPSConnectionPool(addresses[0][4][0],port=443,assert_hostname=parsed.hostname,
                                        server_hostname=parsed.hostname,cert_reqs="CERT_REQUIRED",ca_certs=certifi.where())
        response=None
        try:
            request_path=(parsed.path or "/")+("?"+parsed.query if parsed.query else "")
            response=pool.request("GET",request_path,
                                  headers={"Host":parsed.hostname,"User-Agent":"BlogOperations/1.0 (content verification)"},
                                  timeout=urllib3.Timeout(connect=min(10,timeout),read=timeout),
                                  redirect=False,retries=False,preload_content=False)
            if response.status in (301,302,303,307,308):
                url=urljoin(url,response.headers["Location"])
                continue
            if response.status!=200:
                raise ValueError(f"HTTP status {response.status}")
            chunks, size = [], 0
            for chunk in response.stream(65536,decode_content=True):
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError("Resource exceeds size limit")
                chunks.append(chunk)
            return {"url":url,"status":response.status,"content_type":response.headers.get("Content-Type",""),"body":b"".join(chunks)}
        finally:
            if response is not None:response.close()
            pool.close()
    raise ValueError("Too many redirects")

def collect_evidence(urls):
    if not 1 <= len(urls) <= 6:
        raise ValueError("Provide 1–6 primary source URLs")
    records = []
    for url in dict.fromkeys(urls):
        response = safe_get(url)
        if "html" not in response["content_type"] and "text/plain" not in response["content_type"]:
            raise ValueError("Use an accessible HTML/text source; PDFs need a reviewed text extraction")
        soup = BeautifulSoup(response["body"],"html.parser")
        title = soup.title.get_text(" ",strip=True) if soup.title else url
        for tag in soup(["script","style","nav","footer","header"]):
            tag.decompose()
        fragment=unquote(urlsplit(url).fragment)
        selected=soup
        if fragment:
            anchor=soup.find(id=fragment)
            if anchor is None:raise ValueError("Source section anchor not found")
            selected=anchor.find_parent("dl") if anchor.name=="dt" else anchor
            if selected is None:selected=anchor
        text = selected.get_text(" ",strip=True)
        if len(text) < 100:
            raise ValueError("Source text too short or inaccessible")
        record = {"id":hashlib.sha256(response["url"].encode()).hexdigest()[:16],"url":response["url"],
                  "title":title,"retrieved_at":timestamp(),"sha256":hashlib.sha256(response["body"]).hexdigest(),
                  "text":text[:20000],"truncated":len(text)>20000,"selection":("fragment:"+fragment if fragment else "document_start")}
        save_json(state_dir()/"evidence"/(record["id"]+".json"),record)
        records.append(record)
    return records

def local_evidence(paths):
    """Snapshot explicitly supplied local test artifacts, never pretend they are web sources."""
    records=[]
    for path in paths:
        path=Path(path).expanduser().resolve(strict=True)
        if not path.is_file() or path.suffix not in (".json",".py",".md",".txt"):
            raise ValueError("Unsupported local evidence artifact")
        raw=path.read_bytes()
        if len(raw)>160000:raise ValueError("Local evidence artifact is too large")
        text=raw.decode("utf-8")
        sha=hashlib.sha256(raw).hexdigest()
        record={"id":"local-"+sha[:16],"kind":"operator_supplied_test_artifact","title":path.name,
                "source_path":str(path),"sha256":sha,"text":text,"retrieved_at":timestamp(),"truncated":False}
        if record["id"] not in {r["id"] for r in records}:records.append(record)
    return records

def read_post(path):
    raw = Path(path).read_text(encoding="utf-8")
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", raw,re.S)
    if not match:
        raise ValueError("Missing frontmatter")
    meta = yaml.safe_load(match.group(1))
    if not isinstance(meta,dict):
        raise ValueError("Invalid frontmatter")
    return meta, match.group(2)

def image_urls(article):
    body = article.get("markdown_content", "")
    urls = re.findall(r'<img\b[^>]*\bsrc=[\"\']([^\"\']+)',body,re.I)
    urls += re.findall(r'!\[[^\]]*\]\(([^\s)]+)',body)
    if article.get("heroImage"):
        urls.append(article["heroImage"])
    return sorted(set(urls))

def local_asset(root,url):
    if urlsplit(url).scheme or url.startswith("//"):
        return None
    public = (Path(root)/"blog-frontend/public").resolve()
    path = (public/unquote(urlsplit(url).path).lstrip("/")).resolve()
    if not path.is_relative_to(public):
        raise ValueError("Asset escapes public directory")
    return path

def image_manifest(article,root):
    manifest=[]
    for url in image_urls(article):
        path=local_asset(root,url)
        if path is None or not path.is_file():
            raise ValueError("Review requires existing repository images")
        manifest.append({"url":url,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
    return manifest

def prose_text(value):
    """Remove Markdown code samples before applying prose-only checks."""
    if not isinstance(value, str):
        return ""
    lines = []
    fence = None
    for line in value.splitlines(keepends=True):
        raw = line.rstrip("\r\n")
        if fence:
            if re.fullmatch(r" {0,3}" + re.escape(fence[0]) + "{" + str(fence[1]) + r",}[ \t]*", raw):
                fence = None
            lines.append("\n")
            continue
        opening = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", raw)
        if opening and (opening[1][0] != "`" or "`" not in opening[2]):
            fence = (opening[1][0], len(opening[1]))
            lines.append("\n")
        else:
            lines.append(line)
    # Match inline code with its actual delimiter length, including double ticks.
    return re.sub(r"(`+)(?!`)(.+?)(?<!`)\1(?!`)", "", "".join(lines), flags=re.S)


def claim_prose(value):
    text = re.sub(r"<[^>]+>", "", prose_text(value))
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return re.sub(r"https?://[^\s<>]+", "", text)


def content_issues(article,site):
    issues = []
    if not isinstance(article, dict):
        return [{"severity":"blocker","code":"missing_field","detail":"article"}]
    body = article.get("markdown_content")
    title = article.get("title")
    for field in ("title","description","category","markdown_content"):
        if not isinstance(article.get(field),str) or not article[field].strip():
            issues.append({"severity":"blocker","code":"missing_field","detail":field})
    body = body if isinstance(body, str) else ""
    title = title if isinstance(title, str) else ""
    prose = prose_text(body)
    if re.search(r'\[(?:💡|🔍)[^\]]*\]|(?m:^\s*TODO\s*:)|\{\{[^}]+\}\}',prose):
        issues.append({"severity":"blocker","code":"unfinished_marker","detail":"해결되지 않은 작성/출처 확인 메모"})
    if re.search(r'(?:승인|수익|완치).{0,12}100\s*%|100\s*%.{0,12}(?:승인|수익|완치)',title):
        issues.append({"severity":"blocker","code":"guarantee_claim","detail":"승인·수익·치료 보장 표현"})
    if site == "kpop" and re.search(r'(?im)^#{1,5}\s*.*(?:lyrics breakdown|original lyrics|가사 전문)|\*\*Hangul\*\*\s*:',body):
        issues.append({"severity":"review","code":"lyrics_rights","detail":"가사 재현의 권리·출처 확인 필요"})
    if site == "goldenlife" and re.search(r'\d[\d,.]*\s*(?:만\s*원|만원|원|%)',prose):
        issues.append({"severity":"review","code":"dated_financial_claim","detail":"금액·비율의 기준일과 대상 조건 대조 필요"})
    return issues

def inventory(site, check_live=False):
    config = site_config(site)
    root = Path(config["root"])
    tracked_result = subprocess.run(["git","-C",str(root),"ls-files","-z"],capture_output=True,check=True)
    tracked = set(tracked_result.stdout.decode().split("\0"))
    records, drafts = [], 0
    fingerprints = {}
    for path in sorted((root/"blog-frontend/src/content/blog").glob("*.md")):
        try:
            meta,body = read_post(path)
        except Exception as exc:
            records.append({"slug":path.stem,"issues":[{"severity":"blocker","code":"parse_error","detail":type(exc).__name__}]})
            continue
        if meta.get("draft") is True:
            drafts += 1
            continue
        article = {**meta,"markdown_content":body}
        issues = content_issues(article,site)
        refs = image_urls(article)
        for url in refs:
            try:
                asset = local_asset(root,url)
                if asset and not asset.is_file():
                    issues.append({"severity":"blocker","code":"missing_image","detail":url})
                elif asset and str(asset.relative_to(root)) not in tracked:
                    issues.append({"severity":"blocker","code":"untracked_image","detail":url})
            except ValueError:
                issues.append({"severity":"blocker","code":"invalid_image_path","detail":url})
        normalized = re.sub(r'[^a-z0-9가-힣]','',body.lower())
        key = hashlib.sha256(normalized.encode()).hexdigest()
        if key in fingerprints:
            issues.append({"severity":"review","code":"duplicate_body","detail":fingerprints[key]})
        fingerprints[key] = path.stem
        url = config["url"]+"/blog/"+path.stem+"/"
        if check_live:
            try:
                page = safe_get(url)
                soup = BeautifulSoup(page["body"],"html.parser")
                for image in soup.find_all("img",src=True):
                    image_url = urljoin(url,image["src"])
                    if urlsplit(image_url).hostname != urlsplit(config["url"]).hostname:
                        continue
                    try:
                        safe_get(image_url,max_bytes=10000000)
                    except Exception as exc:
                        issues.append({"severity":"blocker","code":"live_image_failed","detail":image_url,"error":type(exc).__name__})
            except Exception as exc:
                issues.append({"severity":"blocker","code":"live_page_failed","detail":type(exc).__name__})
        records.append({"slug":path.stem,"title":meta.get("title"),"url":url,"path":str(path),"image_count":len(refs),"issues":issues})
    report = {"site":site,"checked_at":timestamp(),"scope":"public HTTP + local" if check_live else "local public-configured posts",
              "public_posts":len(records),"draft_posts":drafts,"posts":records,
              "blocker_count":sum(x["severity"]=="blocker" for p in records for x in p["issues"]),
              "review_count":sum(x["severity"]=="review" for p in records for x in p["issues"])}
    save_json(state_dir()/"reports"/(site+"-inventory.json"),report)
    return report

def validate_verified_code(article,evidence):
    """Keep explicitly supplied Python examples identical to their tested snapshot."""
    if not isinstance(evidence,(list,tuple)) or any(not isinstance(item,dict) for item in evidence):
        raise ValueError("Invalid source evidence")
    scripts=[item for item in evidence if item.get("kind")=="operator_supplied_test_artifact"
             and isinstance(item.get("title"),str) and Path(item["title"]).suffix.lower()==".py"]
    if not scripts:return
    blocks=re.findall(r"^```python[ \t]*\n(.*?)^```[ \t]*$",article.get("markdown_content",""),re.M|re.S)
    for script in scripts:
        source=script.get("text","")
        if not isinstance(source,str) or not source or hashlib.sha256(source.encode()).hexdigest()!=script.get("sha256"):
            raise ValueError("Verified Python evidence snapshot is invalid")
        if blocks.count(source)!=1:
            raise ValueError("Verified Python script must appear unchanged in one Python code block")

def validate_review(article,review,evidence,site):
    validate_verified_code(article,evidence)
    issues = content_issues(article,site)
    if any(i["severity"]=="blocker" for i in issues):
        raise ValueError("Content has unresolved blocking checks")
    if not isinstance(review, dict):
        raise ValueError("Independent review must be an object")
    if review.get("decision") != "pass" or not isinstance(review.get("issues"), list) or review["issues"] or review.get("rights") != "clear":
        raise ValueError("Independent review requires revision")
    original_value = review.get("original_value")
    if not isinstance(original_value, str) or not original_value.strip() or not isinstance(review.get("claims"),list) or not review["claims"]:
        raise ValueError("Missing original value or claim verification")
    if not isinstance(evidence, (list, tuple)) or not evidence:
        raise ValueError("Source evidence is missing")
    sources = {}
    for item in evidence:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"] or not isinstance(item.get("text"), str):
            raise ValueError("Invalid source evidence")
        if item["id"] in sources:
            raise ValueError("Duplicate source evidence ID")
        sources[item["id"]] = item
    article_text = "\n".join(article[field] for field in ("title", "description", "markdown_content"))
    covered = []
    for claim in review["claims"]:
        if not isinstance(claim, dict) or not isinstance(claim.get("source_id"), str):
            raise ValueError("Invalid claim verification record")
        source = sources.get(claim["source_id"])
        quote = claim.get("quote")
        statement = claim.get("claim")
        if not isinstance(statement,str) or len(statement.strip())<8 or statement not in article_text:
            raise ValueError("Verified claim must identify an exact statement in the article")
        if claim.get("assessment") != "supported" or not source or not isinstance(quote,str) or len(quote.strip())<12 or quote not in source["text"]:
            raise ValueError("Claim evidence is missing or cannot be traced")
        covered.extend(line.strip() for line in claim_prose(statement).splitlines() if line.strip())
    prose = claim_prose(article_text)
    # Bounded coverage check; this does not prove the truth of every statement.
    numeric = re.compile(
        r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)|"
        r"[$€£₩]\s*\d[\d,.]*|"
        r"\b(?:USD|KRW|EUR|GBP)\s*\d[\d,.]*|"
        r"\d[\d,.]*\s*(?:%|만\s*원|원|달러|USD\b|KRW\b|EUR\b|GBP\b|년|시간|minutes?\b|hours?\b|dollars?\b|percent\b)", re.I)
    for line in prose.splitlines():
        for match in numeric.finditer(line):
            if not any(match.group() in statement and statement in line for statement in covered):
                raise ValueError("A numeric/date claim is not mapped to reviewed evidence")
    if review.get("coverage_checked") is not True:
        raise ValueError("Reviewer must explicitly inspect material claim coverage")
    if review.get("requires_expert_review") is not False:
        raise ValueError("Expert review required before publication")
    if site == "kpop" and any(i["code"]=="lyrics_rights" for i in issues):
        raise ValueError("New K-Pop lessons must use original examples rather than reproduce lyrics")
    return {"status":"passed","article_hash":digest(article),"review_hash":digest(review),"evidence_ids":list(sources),"checked_at":timestamp()}
