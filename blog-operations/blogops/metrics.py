"""Read-only, site-scoped Google measurements.

Missing, malformed and unavailable values never become synthetic zero. Google
estimated earnings retain the report currency and are not finalized payments.
"""
import json
import math
import re
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote, urlsplit

from .config import site_config, state_dir, save_json
from .content import timestamp

SCOPES = ["https://www.googleapis.com/auth/adsense.readonly",
          "https://www.googleapis.com/auth/webmasters.readonly",
          "https://www.googleapis.com/auth/analytics.readonly"]
GA4_METRICS = ["screenPageViews", "activeUsers", "sessions", "engagedSessions"]
ADSENSE_METRICS = ["ESTIMATED_EARNINGS", "PAGE_VIEWS", "PAGE_VIEWS_RPM", "IMPRESSIONS", "CLICKS"]
GSC_PAGE_SIZE = 1000
GSC_MAX_PAGES = 10
LIST_MAX_PAGES = 20


def google_session():
    path = state_dir() / "auth/google-token.json"
    if not path.exists():
        return None
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import AuthorizedSession
    credentials = Credentials.from_authorized_user_file(path)
    return AuthorizedSession(credentials)


def unavailable(source, reason="not_connected"):
    return {"source": source, "status": reason, "metrics": None, "fetched_at": timestamp()}


def fetch_json(session, url, method="GET", **kwargs):
    response = session.request(method, url, timeout=25, **kwargs)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Invalid API response")
    return data


def _number(value, *, integer=False):
    if isinstance(value, bool) or value is None or value == "":
        raise ValueError("Missing numeric metric")
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("Invalid numeric metric") from None
    if not math.isfinite(result) or (integer and (result < 0 or not result.is_integer())):
        raise ValueError("Invalid numeric metric")
    return int(result) if integer else result


def _scope(cfg):
    parsed = urlsplit(str(cfg.get("url") or ""))
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Invalid site URL scope")
    if parsed.port not in (None, 80 if parsed.scheme == "http" else 443):
        raise ValueError("Unsupported site URL port")
    host = parsed.hostname.lower().rstrip(".")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host):
        raise ValueError("Invalid site hostname")
    base_path = parsed.path.rstrip("/")
    prefix = f"{parsed.scheme}://{host}{base_path}"
    return {"host": host, "scheme": parsed.scheme, "path": base_path, "prefix": prefix,
            "regex": "^" + re.escape(prefix) + r"(?:/|[?#]|$)"}


def _in_scope(url, scope):
    try:
        parsed = urlsplit(url)
        path = parsed.path.rstrip("/")
        return (parsed.scheme == scope["scheme"] and parsed.hostname == scope["host"]
                and parsed.port in (None, 80 if parsed.scheme == "http" else 443)
                and not parsed.username and not parsed.password
                and (path == scope["path"] or path.startswith(scope["path"] + "/")))
    except (ValueError, TypeError):
        return False


def _property_covers_site(prop, scope):
    if prop.startswith("sc-domain:"):
        domain = prop.removeprefix("sc-domain:").lower().rstrip(".")
        return bool(domain) and (scope["host"] == domain or scope["host"].endswith("." + domain))
    try:
        property_scope = _scope({"url": prop})
        return _in_scope(scope["prefix"], property_scope)
    except ValueError:
        return False


def _list_all(session, url, key):
    """Bounded pagination; an incomplete list must not imply no matching site/issues."""
    records, seen = [], set()
    token = None
    for _ in range(LIST_MAX_PAGES):
        params = {"pageSize": 1000}
        if token:
            params["pageToken"] = token
        data = fetch_json(session, url, params=params)
        page = data.get(key, [])
        if not isinstance(page, list) or any(not isinstance(row, dict) for row in page):
            raise ValueError("Invalid paginated response")
        records.extend(page)
        token = data.get("nextPageToken")
        if not token:
            return records
        if not isinstance(token, str) or token in seen:
            raise ValueError("Invalid pagination token")
        seen.add(token)
    raise ValueError("Pagination incomplete")


def collect(site, session=None):
    cfg = site_config(site)
    snapshot = {"site": site, "fetched_at": timestamp(), "sources": {}, "adsense_state": "unknown"}
    auth_error = None
    if session is None:
        try:
            session = google_session()
        except Exception as exc:
            auth_error = "authentication_failed:" + type(exc).__name__
    if session is None:
        snapshot["sources"] = {name: unavailable(name, auth_error or "not_connected")
                               for name in ("adsense", "search_console", "ga4")}
    else:
        end = date.today() - timedelta(days=3)
        start = end - timedelta(days=27)
        for name, collector in (("adsense", adsense), ("search_console", search_console), ("ga4", ga4)):
            try:
                snapshot["sources"][name] = collector(session, cfg, start, end)
            except Exception as exc:
                # Never serialize response bodies, token-bearing URLs or credential paths.
                snapshot["sources"][name] = unavailable(name, "collection_failed:" + type(exc).__name__)
        snapshot["adsense_state"] = snapshot["sources"]["adsense"].get("site_state", "unknown")
    save_json(state_dir() / "reports" / (site + "-metrics.json"), snapshot)
    return snapshot


def search_console(session, cfg, start, end):
    prop = cfg.get("gsc_property")
    if not isinstance(prop, str) or not prop:
        return unavailable("search_console", "property_not_configured")
    scope = _scope(cfg)
    if not _property_covers_site(prop, scope):
        return unavailable("search_console", "property_scope_mismatch")
    url = "https://www.googleapis.com/webmasters/v3/sites/" + quote(prop, safe="") + "/searchAnalytics/query"
    rows, seen, truncated = [], set(), False
    for page_number in range(GSC_MAX_PAGES):
        data = fetch_json(session, url, "POST", json={
            "startDate": str(start), "endDate": str(end), "dimensions": ["page"],
            "rowLimit": GSC_PAGE_SIZE, "startRow": page_number * GSC_PAGE_SIZE, "dataState": "final",
            "dimensionFilterGroups": [{"groupType": "and", "filters": [
                {"dimension": "page", "operator": "includingRegex", "expression": scope["regex"]}]}]})
        page = data.get("rows", [])
        if not isinstance(page, list) or len(page) > GSC_PAGE_SIZE:
            raise ValueError("Invalid Search Console rows")
        for row in page:
            keys = row.get("keys") if isinstance(row, dict) else None
            if not isinstance(keys, list) or len(keys) != 1 or not isinstance(keys[0], str) or not _in_scope(keys[0], scope):
                raise ValueError("Search Console returned an out-of-scope page")
            if keys[0] in seen:
                raise ValueError("Duplicate Search Console page row")
            seen.add(keys[0])
            clean = {"keys": keys, "clicks": _number(row.get("clicks"), integer=True),
                     "impressions": _number(row.get("impressions"), integer=True)}
            for metric in ("ctr", "position"):
                if metric in row:
                    value = _number(row[metric])
                    if value < 0 or (metric == "ctr" and value > 1):
                        raise ValueError("Invalid Search Console metric")
                    clean[metric] = value
            rows.append(clean)
        if len(page) < GSC_PAGE_SIZE:
            break
    else:
        truncated = True
    return {"source": "search_console", "status": "measured" if rows else "no_rows",
            "property": prop, "site_domain": scope["host"], "url_prefix": scope["prefix"],
            "period": [str(start), str(end)], "timezone": "America/Los_Angeles",
            "metrics": {"clicks": sum(row["clicks"] for row in rows),
                        "impressions": sum(row["impressions"] for row in rows)} if rows else None,
            "rows": rows, "truncated": truncated,
            "coverage": "returned page rows only; Search Console does not guarantee every row",
            "fetched_at": timestamp()}


def ga4(session, cfg, start, end):
    prop = cfg.get("ga4_property")
    if not prop or not str(prop).isdigit():
        return unavailable("ga4", "property_not_configured")
    scope = _scope(cfg)
    host_filter = {"filter": {"fieldName": "hostName", "stringFilter": {
        "matchType": "EXACT", "value": scope["host"], "caseSensitive": False}}}
    filters = host_filter
    if scope["path"]:
        filters = {"andGroup": {"expressions": [host_filter, {"filter": {
            "fieldName": "pageLocation", "stringFilter": {
                "matchType": "PARTIAL_REGEXP", "value": scope["regex"], "caseSensitive": True}}}]}}
    data = fetch_json(session, f"https://analyticsdata.googleapis.com/v1beta/properties/{prop}:runReport", "POST", json={
        "dateRanges": [{"startDate": str(start), "endDate": str(end)}],
        "dimensions": [{"name": "hostName"}], "metrics": [{"name": name} for name in GA4_METRICS],
        "dimensionFilter": filters})
    rows = data.get("rows", [])
    if not isinstance(rows, list):
        raise ValueError("Invalid GA4 rows")
    values = None
    if rows:
        names = [header.get("name") for header in data.get("metricHeaders", [])]
        dimension_names = [header.get("name") for header in data.get("dimensionHeaders", [])]
        if data.get("rowCount") is not None and _number(data["rowCount"], integer=True) != 1:
            raise ValueError("Unexpected GA4 report row count")
        if len(rows) != 1 or len(names) != len(GA4_METRICS) or set(names) != set(GA4_METRICS) or dimension_names != ["hostName"]:
            raise ValueError("Invalid GA4 report headers or rows")
        dimensions = rows[0].get("dimensionValues", [])
        cells = rows[0].get("metricValues", [])
        if len(dimensions) != 1 or str(dimensions[0].get("value", "")).lower() != scope["host"] or len(cells) != len(names):
            raise ValueError("Invalid GA4 site or metric values")
        values = {name: _number(cell.get("value"), integer=True) for name, cell in zip(names, cells)}
    metadata = data.get("metadata") or {}
    return {"source": "ga4", "status": "measured" if values is not None else "no_rows",
            "property": str(prop), "site_domain": scope["host"], "url_prefix": scope["prefix"],
            "period": [str(start), str(end)], "timezone": metadata.get("timeZone"), "metrics": values,
            "data_loss_from_other_row": metadata.get("dataLossFromOtherRow"),
            "subject_to_thresholding": metadata.get("subjectToThresholding"), "fetched_at": timestamp()}


def _report_date(value):
    if not isinstance(value, dict):
        raise ValueError("Missing report period")
    return date(int(value["year"]), int(value["month"]), int(value["day"]))


def _adsense_values(data, start, end):
    rows = data.get("rows", [])
    if not isinstance(rows, list):
        raise ValueError("Invalid AdSense rows")
    row = data.get("totals")
    if not row:
        if len(rows) > 1:
            raise ValueError("Unexpected multiple AdSense rows without totals")
        row = rows[0] if rows else None
    if row is None:
        return None, None
    headers, cells = data.get("headers", []), row.get("cells", [])
    names = [header.get("name") for header in headers]
    if len(names) != len(ADSENSE_METRICS) or set(names) != set(ADSENSE_METRICS) or len(cells) != len(names):
        raise ValueError("Incomplete or duplicate AdSense metric headers")
    if _report_date(data.get("startDate")) != start or _report_date(data.get("endDate")) != end:
        raise ValueError("AdSense report period mismatch")
    currencies = set()
    for header in headers:
        if header["name"] in ("ESTIMATED_EARNINGS", "PAGE_VIEWS_RPM"):
            code = header.get("currencyCode")
            if not isinstance(code, str) or not re.fullmatch(r"[A-Z]{3}", code):
                raise ValueError("AdSense report currency missing")
            currencies.add(code)
    if len(currencies) != 1:
        raise ValueError("AdSense report currency mismatch")
    values = {name: _number(cell.get("value"), integer=name in ("PAGE_VIEWS", "IMPRESSIONS", "CLICKS"))
              for name, cell in zip(names, cells)}
    return values, next(iter(currencies))


def adsense(session, cfg, start, end):
    base = "https://adsense.googleapis.com/v2/"
    scope = _scope(cfg)
    # A host report cannot isolate path-mounted sites without configured URL channels.
    if scope["path"]:
        return unavailable("adsense", "path_scope_not_supported")
    account_mapping = cfg.get("adsense_account")
    if account_mapping:
        if not isinstance(account_mapping, str) or not re.fullmatch(r"accounts/pub-\d{16}", account_mapping):
            return unavailable("adsense", "account_mapping_invalid")
        accounts = [fetch_json(session, base + account_mapping)]
        if accounts[0].get("name") != account_mapping:
            return unavailable("adsense", "account_mapping_mismatch")
    else:
        accounts = _list_all(session, base + "accounts", "accounts")
    matches = []
    for account in accounts:
        name = account.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"accounts/pub-\d{16}", name):
            raise ValueError("Invalid AdSense account resource")
        for site in _list_all(session, base + name + "/sites", "sites"):
            if str(site.get("domain") or "").lower().rstrip(".") == scope["host"]:
                matches.append((account, site))
    if not matches:
        return unavailable("adsense", "site_not_accessible")
    if len(matches) != 1:
        return unavailable("adsense", "ambiguous_site_account")
    account, site = matches[0]
    dimension = site.get("reportingDimensionId")
    if not isinstance(dimension, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", dimension):
        raise ValueError("Invalid AdSense site reporting ID")
    record = {"source": "adsense", "status": "no_rows", "account": account["name"],
              "site_domain": scope["host"], "site_state": site.get("state", "unknown"),
              "period": [str(start), str(end)], "timezone": "ACCOUNT_TIME_ZONE",
              "account_timezone": (account.get("timeZone") or {}).get("id"),
              "currency": None, "metrics": None,
              "revenue_kind": "Google estimated earnings, not finalized payment",
              "policy_issues": None, "policy_status": "unavailable", "fetched_at": timestamp()}
    params = [("dateRange", "CUSTOM"), ("reportingTimeZone", "ACCOUNT_TIME_ZONE"),
              ("filters", "OWNED_SITE_ID==" + dimension), ("filters", "DOMAIN_CODE==" + scope["host"])]
    for prefix, day in (("startDate", start), ("endDate", end)):
        params.extend([(prefix + ".year", day.year), (prefix + ".month", day.month), (prefix + ".day", day.day)])
    params.extend(("metrics", metric) for metric in ADSENSE_METRICS)
    try:
        data = fetch_json(session, base + account["name"] + "/reports:generate", params=params)
        values, currency = _adsense_values(data, start, end)
        record.update(metrics=values, currency=currency, status="measured" if values is not None else "no_rows",
                      warnings=data.get("warnings", []))
    except Exception as exc:
        record["status"] = "collection_failed:" + type(exc).__name__
    try:
        issues = _list_all(session, base + account["name"] + "/policyIssues", "policyIssues")
        record["policy_issues"] = [issue for issue in issues if str(issue.get("site") or "").lower().rstrip(".") == scope["host"]]
        record["policy_status"] = "collected"
    except Exception:
        # Unknown policy state must not appear as an empty, clean policy list.
        pass
    return record


def connect_google(client_file):
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(str(Path(client_file).resolve()), SCOPES)
        credentials = flow.run_local_server(port=0, open_browser=True)
        save_json(state_dir() / "auth/google-token.json", json.loads(credentials.to_json()))
    except Exception as exc:
        raise ValueError("Google authorization failed: " + type(exc).__name__) from None
    return {"status": "connected", "scopes": SCOPES}
