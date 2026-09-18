"""Offline regressions for source scope, measurement validity and auth failures."""
import json
import os
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from blogops import metrics

START = date(2026, 9, 1)
END = date(2026, 9, 15)
HOST = "target.example"
ACCOUNT = "accounts/pub-1234567890123456"
OTHER_ACCOUNT = "accounts/pub-9999999999999999"
CFG = {"url": "https://target.example", "gsc_property": "https://target.example/", "ga4_property": "123"}
SITE = {"domain": HOST, "reportingDimensionId": "site123", "state": "READY"}


def gsc_row(url="https://target.example/post/", clicks=2, impressions=10):
    return {"keys": [url], "clicks": clicks, "impressions": impressions}


def ga4_report(host=HOST, values=None):
    names = list(reversed(metrics.GA4_METRICS))
    return {"dimensionHeaders": [{"name": "hostName"}],
            "metricHeaders": [{"name": name} for name in names],
            "rows": [{"dimensionValues": [{"value": host}],
                      "metricValues": [{"value": value} for value in (values or ["0", "0", "0", "0"])]}],
            "metadata": {"timeZone": "Asia/Seoul"}}


def adsense_report(currency="KRW", values=None, totals=False):
    names = list(reversed(metrics.ADSENSE_METRICS))
    headers = []
    for name in names:
        header = {"name": name}
        if name in ("ESTIMATED_EARNINGS", "PAGE_VIEWS_RPM") and currency:
            header["currencyCode"] = currency
        headers.append(header)
    row = {"cells": [{"value": value} for value in (values or ["0", "0", "0", "0", "0"])]}
    report = {"headers": headers, "startDate": {"year": 2026, "month": 9, "day": 1},
              "endDate": {"year": 2026, "month": 9, "day": 15}}
    report.update({"totals": row} if totals else {"rows": [row]})
    return report


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {"BLOGOPS_STATE_DIR": self.temp.name})
        env.start()
        self.addCleanup(env.stop)
        network = patch("requests.sessions.Session.request", side_effect=AssertionError("No live APIs in collector tests"))
        network.start()
        self.addCleanup(network.stop)
        self.session = object()

    def adsense(self, report=None, policy=None, cfg=None):
        responses = [{"accounts": [{"name": ACCOUNT}]}, {"sites": [SITE]},
                     report if report is not None else adsense_report(),
                     policy if policy is not None else {"policyIssues": []}]
        with patch("blogops.metrics.fetch_json", side_effect=responses) as fetch:
            result = metrics.adsense(self.session, cfg or CFG, START, END)
        return result, fetch

    def test_gsc_unrelated_property_rejected_without_request(self):
        for prop in ("https://other.example/", "sc-domain:other.example", "https://target.example/other/"):
            with self.subTest(prop=prop), patch("blogops.metrics.fetch_json") as fetch:
                result = metrics.search_console(self.session, {**CFG, "gsc_property": prop}, START, END)
                self.assertEqual(result["status"], "property_scope_mismatch")
                self.assertIsNone(result["metrics"])
                fetch.assert_not_called()

    def test_gsc_domain_property_still_filters_and_checks_host(self):
        with patch("blogops.metrics.fetch_json", return_value={"rows": [gsc_row()]}) as fetch:
            result = metrics.search_console(self.session, {**CFG, "gsc_property": "sc-domain:example"}, START, END)
        expression = fetch.call_args.kwargs["json"]["dimensionFilterGroups"][0]["filters"][0]["expression"]
        self.assertTrue(expression.startswith("^https://target\\.example"))
        self.assertEqual(result["metrics"], {"clicks": 2, "impressions": 10})
        self.assertIn("returned page rows", result["coverage"])

    def test_gsc_out_of_scope_response_cannot_become_measured(self):
        for url in ("https://other.example/a", "https://target.example.evil/a", "http://target.example/a"):
            with self.subTest(url=url), patch("blogops.metrics.fetch_json", return_value={"rows": [gsc_row(url)]}):
                with self.assertRaises(ValueError):
                    metrics.search_console(self.session, CFG, START, END)

    def test_gsc_path_scope_has_boundary(self):
        cfg = {**CFG, "url": "https://target.example/blog"}
        with patch("blogops.metrics.fetch_json", return_value={"rows": [gsc_row("https://target.example/blog/a")]}):
            self.assertEqual(metrics.search_console(self.session, cfg, START, END)["status"], "measured")
        with patch("blogops.metrics.fetch_json", return_value={"rows": [gsc_row("https://target.example/blogger/a")]}):
            with self.assertRaises(ValueError):
                metrics.search_console(self.session, cfg, START, END)

    def test_gsc_pagination_and_duplicate_rows(self):
        pages = [{"rows": [gsc_row("https://target.example/a"), gsc_row("https://target.example/b")]},
                 {"rows": [gsc_row("https://target.example/c")]}]
        with patch("blogops.metrics.GSC_PAGE_SIZE", 2), patch("blogops.metrics.fetch_json", side_effect=pages) as fetch:
            result = metrics.search_console(self.session, CFG, START, END)
        self.assertEqual(result["metrics"]["clicks"], 6)
        self.assertEqual(fetch.call_args.kwargs["json"]["startRow"], 2)
        self.assertFalse(result["truncated"])
        pages[1] = pages[0]
        with patch("blogops.metrics.GSC_PAGE_SIZE", 2), patch("blogops.metrics.fetch_json", side_effect=pages):
            with self.assertRaises(ValueError):
                metrics.search_console(self.session, CFG, START, END)

    def test_gsc_page_limit_is_explicitly_partial(self):
        with patch("blogops.metrics.GSC_PAGE_SIZE", 1), patch("blogops.metrics.GSC_MAX_PAGES", 1), patch("blogops.metrics.fetch_json", return_value={"rows": [gsc_row()]}):
            result = metrics.search_console(self.session, CFG, START, END)
        self.assertTrue(result["truncated"])

    def test_gsc_missing_nonfinite_negative_metrics_rejected(self):
        for value in (None, "NaN", "Infinity", -1, True, 0.2):
            with self.subTest(value=value), patch("blogops.metrics.fetch_json", return_value={"rows": [gsc_row(clicks=value)]}):
                with self.assertRaises(ValueError):
                    metrics.search_console(self.session, CFG, START, END)

    def test_gsc_optional_ctr_and_position_are_finite_and_valid(self):
        for metric, value in (("ctr", "NaN"), ("ctr", 1.1), ("position", -1)):
            row = {**gsc_row(), metric: value}
            with self.subTest(metric=metric, value=value), patch("blogops.metrics.fetch_json", return_value={"rows": [row]}):
                with self.assertRaises(ValueError):
                    metrics.search_console(self.session, CFG, START, END)

    def test_gsc_no_rows_unknown_explicit_zero_measured(self):
        with patch("blogops.metrics.fetch_json", return_value={"rows": []}):
            self.assertIsNone(metrics.search_console(self.session, CFG, START, END)["metrics"])
        with patch("blogops.metrics.fetch_json", return_value={"rows": [gsc_row(clicks=0, impressions=0)]}):
            self.assertEqual(metrics.search_console(self.session, CFG, START, END)["metrics"], {"clicks": 0, "impressions": 0})

    def test_ga4_valid_zero_uses_named_headers_and_exact_host(self):
        with patch("blogops.metrics.fetch_json", return_value=ga4_report()) as fetch:
            result = metrics.ga4(self.session, CFG, START, END)
        self.assertEqual(result["metrics"], {key: 0 for key in metrics.GA4_METRICS})
        self.assertEqual(result["timezone"], "Asia/Seoul")
        body = fetch.call_args.kwargs["json"]
        self.assertEqual(body["dimensions"], [{"name": "hostName"}])
        self.assertEqual(body["dimensionFilter"]["filter"]["stringFilter"]["value"], HOST)

    def test_ga4_path_site_also_filters_page_location(self):
        with patch("blogops.metrics.fetch_json", return_value=ga4_report()) as fetch:
            metrics.ga4(self.session, {**CFG, "url": CFG["url"] + "/blog/"}, START, END)
        expression = fetch.call_args.kwargs["json"]["dimensionFilter"]["andGroup"]["expressions"][1]
        self.assertEqual(expression["filter"]["fieldName"], "pageLocation")
        self.assertIn("/blog", expression["filter"]["stringFilter"]["value"])

    def test_ga4_wrong_host_truncated_headers_and_nonfinite_rejected(self):
        cases = [ga4_report(host="other.example"), ga4_report(values=["NaN", "0", "0", "0"])]
        truncated = ga4_report()
        truncated["metricHeaders"].pop()
        cases.append(truncated)
        duplicate = ga4_report()
        duplicate["metricHeaders"][0] = duplicate["metricHeaders"][1]
        cases.append(duplicate)
        truncated_rows = ga4_report()
        truncated_rows["rowCount"] = 2
        cases.append(truncated_rows)
        extra_rows = ga4_report()
        extra_rows["rows"] *= 2
        cases.append(extra_rows)
        for payload in cases:
            with self.subTest(payload=payload), patch("blogops.metrics.fetch_json", return_value=payload):
                with self.assertRaises(ValueError):
                    metrics.ga4(self.session, CFG, START, END)

    def test_ga4_empty_response_does_not_imply_zero(self):
        with patch("blogops.metrics.fetch_json", return_value={"rows": []}):
            result = metrics.ga4(self.session, CFG, START, END)
        self.assertEqual(result["status"], "no_rows")
        self.assertIsNone(result["metrics"])

    def test_adsense_site_scope_currency_and_zero_retained(self):
        result, fetch = self.adsense()
        self.assertEqual(result["status"], "measured")
        self.assertEqual(result["currency"], "KRW")
        self.assertEqual(result["metrics"]["ESTIMATED_EARNINGS"], 0)
        params = fetch.call_args_list[2].kwargs["params"]
        self.assertIn(("filters", "OWNED_SITE_ID==site123"), params)
        self.assertIn(("filters", "DOMAIN_CODE==target.example"), params)
        self.assertEqual(result["period"], [str(START), str(END)])

    def test_adsense_totals_without_rows_are_measured_if_explicit(self):
        result, _ = self.adsense(adsense_report(totals=True))
        self.assertEqual(result["status"], "measured")
        self.assertEqual(result["metrics"]["CLICKS"], 0)

    def test_adsense_no_rows_unknown_not_zero(self):
        result, _ = self.adsense({"rows": []})
        self.assertEqual(result["status"], "no_rows")
        self.assertIsNone(result["metrics"])
        self.assertIsNone(result["currency"])
        self.assertEqual(result["site_state"], "READY")

    def test_adsense_invalid_currency_header_numbers_period_rejected(self):
        cases = [adsense_report(currency=None), adsense_report(values=["0", "0", "0", "0", "NaN"])]
        mixed = adsense_report()
        next(header for header in mixed["headers"] if header["name"] == "ESTIMATED_EARNINGS")["currencyCode"] = "USD"
        cases.append(mixed)
        truncated = adsense_report()
        truncated["headers"].pop()
        cases.append(truncated)
        duplicate = adsense_report()
        duplicate["headers"][0] = duplicate["headers"][1]
        cases.append(duplicate)
        wrong_period = adsense_report()
        wrong_period["endDate"]["day"] = 14
        cases.append(wrong_period)
        for payload in cases:
            with self.subTest(payload=payload):
                result, _ = self.adsense(payload)
                self.assertEqual(result["status"], "collection_failed:ValueError")
                self.assertIsNone(result["metrics"])
                self.assertIsNone(result["currency"])
                self.assertEqual(result["site_state"], "READY")

    def test_adsense_paginates_accounts_sites_and_policy_issues(self):
        responses = [
            {"accounts": [], "nextPageToken": "accounts-2"}, {"accounts": [{"name": ACCOUNT}]},
            {"sites": [], "nextPageToken": "sites-2"}, {"sites": [SITE]}, adsense_report(),
            {"policyIssues": [{"site": "other.example"}], "nextPageToken": "policy-2"},
            {"policyIssues": [{"site": HOST, "action": "WARNED"}]}]
        with patch("blogops.metrics.fetch_json", side_effect=responses) as fetch:
            result = metrics.adsense(self.session, CFG, START, END)
        self.assertEqual(result["policy_issues"], [{"site": HOST, "action": "WARNED"}])
        self.assertEqual(fetch.call_args_list[1].kwargs["params"]["pageToken"], "accounts-2")
        self.assertEqual(fetch.call_args_list[3].kwargs["params"]["pageToken"], "sites-2")
        self.assertEqual(fetch.call_args_list[6].kwargs["params"]["pageToken"], "policy-2")

    def test_adsense_duplicate_account_match_is_not_arbitrarily_selected(self):
        responses = [{"accounts": [{"name": ACCOUNT}, {"name": OTHER_ACCOUNT}]}, {"sites": [SITE]}, {"sites": [SITE]}]
        with patch("blogops.metrics.fetch_json", side_effect=responses) as fetch:
            result = metrics.adsense(self.session, CFG, START, END)
        self.assertEqual(result["status"], "ambiguous_site_account")
        self.assertIsNone(result["metrics"])
        self.assertEqual(fetch.call_count, 3)

    def test_adsense_configured_account_verified_exactly(self):
        with patch("blogops.metrics.fetch_json", return_value={"name": OTHER_ACCOUNT}) as fetch:
            result = metrics.adsense(self.session, {**CFG, "adsense_account": ACCOUNT}, START, END)
        self.assertEqual(result["status"], "account_mapping_mismatch")
        self.assertEqual(fetch.call_count, 1)
        self.assertTrue(fetch.call_args.args[1].endswith(ACCOUNT))

    def test_adsense_path_site_not_reported_as_whole_host(self):
        with patch("blogops.metrics.fetch_json") as fetch:
            result = metrics.adsense(self.session, {**CFG, "url": CFG["url"] + "/blog"}, START, END)
        self.assertEqual(result["status"], "path_scope_not_supported")
        self.assertIsNone(result["metrics"])
        fetch.assert_not_called()

    def test_policy_failure_unknown_instead_of_empty_clean_list(self):
        result, _ = self.adsense(policy=RuntimeError("secret API url token"))
        self.assertEqual(result["policy_status"], "unavailable")
        self.assertIsNone(result["policy_issues"])
        self.assertNotIn("secret API", str(result))

    def test_pagination_loop_or_truncation_cannot_imply_no_rows(self):
        with patch("blogops.metrics.fetch_json", return_value={"sites": [], "nextPageToken": "same"}):
            with self.assertRaises(ValueError):
                metrics._list_all(self.session, "https://adsense.googleapis.com/v2/test", "sites")
        with patch("blogops.metrics.LIST_MAX_PAGES", 1), patch("blogops.metrics.fetch_json", return_value={"sites": [], "nextPageToken": "next"}):
            with self.assertRaises(ValueError):
                metrics._list_all(self.session, "https://adsense.googleapis.com/v2/test", "sites")

    def test_collect_auth_failure_is_sanitized_and_persisted_as_unknown(self):
        with patch("blogops.metrics.site_config", return_value=CFG), patch("blogops.metrics.google_session", side_effect=ValueError("SECRET TOKEN")):
            result = metrics.collect("test")
        for source in result["sources"].values():
            self.assertEqual(source["status"], "authentication_failed:ValueError")
            self.assertIsNone(source["metrics"])
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertTrue((Path(self.temp.name) / "reports/test-metrics.json").exists())

    def test_collect_api_failure_never_serializes_secrets(self):
        with patch("blogops.metrics.site_config", return_value=CFG), patch("blogops.metrics.fetch_json", side_effect=RuntimeError("SECRET TOKEN IN URL")):
            result = metrics.collect("test", session=self.session)
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertTrue(all(source["metrics"] is None for source in result["sources"].values()))


if __name__ == "__main__":
    unittest.main()
