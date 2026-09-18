"""Offline contracts for durable work, bounded budgets and review integrity."""
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import Mock, patch

from blogops import content, reports, routing
from blogops.config import save_json
from blogops.store import BudgetExceeded, Store


class OfflineCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        environment = patch.dict(os.environ, {'BLOGOPS_STATE_DIR': str(self.root / 'state')})
        environment.start()
        self.addCleanup(environment.stop)
        for target in ('requests.sessions.Session.request', 'urllib3.HTTPSConnectionPool.request', 'socket.getaddrinfo'):
            context = patch(target, side_effect=AssertionError('Network disabled in core tests'))
            context.start()
            self.addCleanup(context.stop)


class StoreTests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.store = Store(self.root / 'tasks.sqlite')

    def task(self, **kwargs):
        return self.store.enqueue('absian', 'draft', 'codex', {'topic': 'Example'}, **kwargs)

    def test_dedupe_returns_same_task_without_resetting_result(self):
        first = self.task(dedupe='same-request')
        self.store.finish(first, {'answer': 'saved'})
        second = self.task(dedupe='same-request')
        self.assertEqual(first, second)
        self.assertEqual(len(self.store.list()), 1)
        self.assertEqual(self.store.get(second)['result'], {'answer': 'saved'})
        self.assertEqual(self.store.get(second)['state'], 'succeeded')

    def test_dependency_must_exist_and_succeed_before_claim(self):
        parent = self.task()
        child = self.task(dependencies=[parent])
        missing = self.task(dependencies=['missing'])
        self.assertIsNone(self.store.claim(child))
        self.assertIsNone(self.store.claim(missing))
        self.store.finish(parent, error='Needs correction', state='needs_attention')
        self.assertIsNone(self.store.claim(child))
        self.store.finish(parent, {'evidence': 'done'})
        claimed = self.store.claim(child)
        self.assertEqual(claimed['state'], 'running')
        self.assertEqual(claimed['attempts'], 1)
        self.assertIsNone(self.store.claim(child))

    def test_atomic_batch_budget_failure_leaves_no_partial_reservation(self):
        self.store.reserve_call('codex', 'model', limit=3)
        with self.assertRaises(BudgetExceeded):
            self.store.reserve_calls('codex', 'model', limit=3, amount=3)
        self.assertEqual(self.store.usage()[0]['calls'], 1)
        calls = self.store.reserve_calls('codex', 'model', limit=3, amount=2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.store.usage()[0]['calls'], 3)

    def test_competing_budget_reservations_never_exceed_limit(self):
        def reserve(_):
            try:
                return self.store.reserve_calls('codex', 'model', limit=3, amount=2)
            except BudgetExceeded:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reserve, range(2)))
        self.assertEqual(sum(value is not None for value in results), 1)
        self.assertEqual(self.store.usage()[0]['calls'], 2)

    def test_failed_calls_still_count_and_provider_budgets_are_independent(self):
        ident = self.store.reserve_call('codex', 'model', limit=1)
        self.store.finish_call(ident, 'failed', 2)
        with self.assertRaises(BudgetExceeded):
            self.store.reserve_call('codex', 'model', limit=1)
        self.store.reserve_call('agy', 'model', limit=1)
        self.assertEqual({row['provider']: row['calls'] for row in self.store.usage()}, {'codex': 1, 'agy': 1})

    def test_invalid_batch_counts_do_not_consume_budget(self):
        for amount in (0, -1, True, 1.5):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                self.store.reserve_calls('codex', 'model', limit=8, amount=amount)
        self.assertEqual(self.store.usage(), [])

    def test_next_day_has_separate_budget(self):
        with patch('blogops.store.today', return_value='2026-09-18'):
            self.store.reserve_call('codex', 'model', limit=1)
        with patch('blogops.store.today', return_value='2026-09-19'):
            self.store.reserve_call('codex', 'model', limit=1)
        self.assertEqual(len(self.store.usage()), 2)

    def test_expired_worker_requires_attention_then_can_retry(self):
        ident = self.task()
        self.store.claim(ident, lease_seconds=-1)
        self.assertEqual(self.store.recover_expired(), 1)
        self.assertEqual(self.store.get(ident)['state'], 'needs_attention')
        self.assertTrue(self.store.retry(ident))
        claimed = self.store.claim(ident)
        self.assertEqual(claimed['attempts'], 2)
        self.assertEqual(claimed['state'], 'running')

    def test_live_worker_cannot_be_retried(self):
        ident = self.task()
        self.store.claim(ident)
        self.assertFalse(self.store.retry(ident))
        self.assertEqual(self.store.get(ident)['state'], 'running')

    def test_retry_workflow_recovers_expired_children_and_preserves_completed_stages(self):
        workflow = self.store.enqueue('absian', 'workflow', 'code', {})
        completed = self.task(parent=workflow)
        expired = self.task(parent=workflow)
        waiting = self.task(parent=workflow, dependencies=[expired])
        self.store.finish(completed, {'complete': True})
        self.store.claim(expired, lease_seconds=-1)
        self.store.finish(workflow, state='needs_attention')
        self.assertTrue(self.store.retry(workflow))
        self.assertEqual(self.store.get(workflow)['state'], 'workflow_pending')
        self.assertEqual(self.store.get(expired)['state'], 'queued')
        self.assertEqual(self.store.get(completed)['result'], {'complete': True})
        self.assertIsNone(self.store.claim(waiting))

    def test_expired_worker_cannot_complete_after_recovery(self):
        ident = self.task()
        self.store.claim(ident, lease_seconds=-1)
        self.store.recover_expired()
        try:
            self.store.finish(ident, {'late': 'untrusted result'})
        except (ValueError, RuntimeError):
            pass
        self.assertEqual(self.store.get(ident)['state'], 'needs_attention')
        self.assertIsNone(self.store.get(ident)['result'])

    def test_provider_lock_releases_after_exception(self):
        with self.assertRaisesRegex(ValueError, 'worker failed'):
            with self.store.lock('provider:codex'):
                with self.assertRaises(RuntimeError):
                    with self.store.lock('provider:codex'):
                        self.fail('Concurrent owner acquired live lock')
                raise ValueError('worker failed')
        with self.store.lock('provider:codex'):
            pass

    def test_old_lock_cleanup_cannot_remove_new_owner(self):
        old = self.store.lock('provider:codex', seconds=-1)
        old.__enter__()
        current = self.store.lock('provider:codex')
        current.__enter__()
        try:
            old.__exit__(None, None, None)
            with self.assertRaises(RuntimeError):
                with self.store.lock('provider:codex'):
                    self.fail('Old owner removed the replacement lease')
        finally:
            current.__exit__(None, None, None)


class RoutingTests(OfflineCase):
    def test_roles_keep_editorial_review_with_codex_and_general_tasks_with_agy(self):
        for kind in ('draft', 'plan', 'review', 'images', 'experiment'):
            self.assertEqual(routing.route(kind), 'codex')
        for kind in ('source_summary', 'metadata', 'report_summary', 'triage'):
            self.assertEqual(routing.route(kind), 'agy')
        for kind in ('audit', 'metrics', 'evidence', 'queue_draft', 'reconcile'):
            self.assertEqual(routing.route(kind), 'code')
        with self.assertRaises(ValueError):
            routing.route('publish_without_approval')

    def test_source_summary_must_quote_the_given_source(self):
        evidence = [{'id': 'source', 'text': 'This is a verified source passage.'}]
        valid = {'sources': [{'source_id': 'source', 'quote': 'verified source passage', 'summary': 'Summary'}]}
        self.assertEqual(routing.validate_auxiliary(valid, 'source_summary', evidence), valid)
        invalid = copy.deepcopy(valid)
        invalid['sources'][0]['quote'] = 'invented source passage'
        with self.assertRaises(ValueError):
            routing.validate_auxiliary(invalid, 'source_summary', evidence)

    def test_metadata_cannot_change_article_body(self):
        valid = {'description': 'An accurate description', 'tags': ['Python'], 'escalation_reason': None}
        self.assertEqual(routing.validate_auxiliary(valid, 'metadata'), valid)
        with self.assertRaises(ValueError):
            routing.validate_auxiliary({**valid, 'markdown_content': 'replacement body'}, 'metadata')
        with self.assertRaises(ValueError):
            routing.validate_auxiliary({**valid, 'tags': [42]}, 'metadata')

    def test_explicit_auxiliary_escalation_never_passes(self):
        with self.assertRaises(ValueError):
            routing.validate_auxiliary({'escalation_reason': 'Evidence uncertain'}, 'triage')

    def test_report_summary_requires_nonempty_text_and_action_list(self):
        for value in ({}, {'summary': '', 'actions': []}, {'summary': 'Summary', 'actions': 'invented'}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                routing.validate_auxiliary(value, 'report_summary')

    def test_valid_report_and_triage_schemas_remain_usable(self):
        summary = {'summary': 'Traffic is not connected yet.', 'actions': ['Connect a measured source.'], 'escalation_reason': None}
        triage = {'issues': [{'code': 'missing_image', 'priority': 1, 'reason': 'A referenced local image is absent.'}]}
        self.assertEqual(routing.validate_auxiliary(summary, 'report_summary'), summary)
        self.assertEqual(routing.validate_auxiliary(triage, 'triage'), triage)
        with self.assertRaises(ValueError):
            routing.validate_auxiliary({}, 'unknown')

    def test_triage_requires_structured_issues(self):
        for value in ({}, {'issues': 'none'}, {'issues': [{'code': 'image', 'priority': '???'}]}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                routing.validate_auxiliary(value, 'triage')


class ContentTests(OfflineCase):
    def article(self, **changes):
        article = {'title': 'Spreadsheet examples', 'description': 'Learn how to read workbooks.',
                   'category': 'Development', 'markdown_content': 'Python can read spreadsheet files with openpyxl.'}
        article.update(changes)
        return article

    def review(self, **changes):
        value = {'decision': 'pass', 'rights': 'clear', 'original_value': 'An example readers can reproduce.',
                 'requires_expert_review': False, 'coverage_checked': True, 'issues': [],
                 'claims': [{'claim': 'Python can read spreadsheet files with openpyxl.', 'source_id': 'official',
                             'quote': 'Read and write spreadsheet files with openpyxl.', 'assessment': 'supported'}]}
        value.update(changes)
        return value

    def evidence(self):
        return [{'id': 'official', 'url': 'https://docs.example/guide',
                 'text': 'Read and write spreadsheet files with openpyxl. Official reference text.', 'sha256': 'sourcehash'}]

    def test_valid_review_binds_exact_article_and_review_hashes(self):
        article, review = self.article(), self.review()
        gate = content.validate_review(article, review, self.evidence(), 'absian')
        self.assertEqual(gate['status'], 'passed')
        self.assertEqual(gate['article_hash'], content.digest(article))
        self.assertEqual(gate['review_hash'], content.digest(review))
        self.assertNotEqual(gate['article_hash'], content.digest(self.article(description='Changed description')))

    def test_missing_claim_unrelated_statement_and_fabricated_quote_fail(self):
        for changes in ({'claim': None}, {'claim': 'A statement outside the article.'},
                        {'quote': 'A fabricated source quote.'}, {'source_id': 'missing'}, {'assessment': 'unsupported'}):
            review = self.review()
            review['claims'][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                content.validate_review(self.article(), review, self.evidence(), 'absian')

    def test_review_cannot_pass_uncertainty_or_required_expertise(self):
        for changes in ({'decision': 'revise'}, {'rights': 'needs_review'}, {'issues': ['Evidence conflict']},
                        {'coverage_checked': False}, {'requires_expert_review': True}, {'claims': []}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                content.validate_review(self.article(), self.review(**changes), self.evidence(), 'absian')

    def test_original_value_must_be_substantive_text(self):
        for value in (True, 3, '   '):
            with self.subTest(value=value), self.assertRaises(ValueError):
                content.validate_review(self.article(), self.review(original_value=value), self.evidence(), 'absian')

    def test_unmapped_numeric_currency_and_dates_block_review(self):
        for statement in ('The benefit increases by 20%.', '지원 금액은 30만원입니다.',
                          'The task takes 5 minutes.', 'The benefit is $500 per month.',
                          'Applications close on 2026-10-01.'):
            article = self.article(markdown_content=self.article()['markdown_content'] + '\n' + statement)
            with self.subTest(statement=statement), self.assertRaises(ValueError):
                content.validate_review(article, self.review(), self.evidence(), 'goldenlife')

    def test_invalid_review_source_and_claim_types_are_rejected_cleanly(self):
        cases = [(None, self.evidence()), (self.review(claims=[None]), self.evidence()),
                 (self.review(issues=None), self.evidence()), (self.review(), [None]),
                 (self.review(), self.evidence() * 2)]
        for review, evidence in cases:
            with self.subTest(review=review, evidence=evidence), self.assertRaises(ValueError):
                content.validate_review(self.article(), review, evidence, 'absian')

    def test_code_and_citation_url_dates_are_not_material_prose_claims(self):
        extra = '\n~~~~python\nTODO: {{ sample }}\nprice = "$500"\ndate = "2026-10-01"\n~~~\n~~~~\n[Source](https://docs.example/2026-10-01/reference)'
        article = self.article(markdown_content=self.article()['markdown_content'] + extra)
        self.assertEqual(content.validate_review(article, self.review(), self.evidence(), 'absian')['status'], 'passed')

    def test_numeric_description_is_also_reviewed(self):
        with self.assertRaises(ValueError):
            content.validate_review(self.article(description='Earn $500 per month.'), self.review(), self.evidence(), 'absian')

    def test_dollar_and_iso_date_claims_pass_when_source_mapping_exists(self):
        statement = 'The $500 benefit starts on 2026-10-01.'
        article = self.article(markdown_content=self.article()['markdown_content'] + '\n' + statement)
        review = self.review()
        review['claims'].append({'claim': statement, 'source_id': 'official', 'quote': statement, 'assessment': 'supported'})
        evidence = self.evidence()
        evidence[0]['text'] += ' ' + statement
        self.assertEqual(content.validate_review(article, review, evidence, 'goldenlife')['status'], 'passed')

    def test_numeric_statement_with_traceable_evidence_passes(self):
        statement = 'The task takes 5 minutes.'
        article = self.article(markdown_content=self.article()['markdown_content'] + '\n' + statement)
        review = self.review()
        review['claims'].append({'claim': statement, 'source_id': 'official', 'quote': statement, 'assessment': 'supported'})
        evidence = self.evidence()
        evidence[0]['text'] += ' ' + statement
        self.assertEqual(content.validate_review(article, review, evidence, 'absian')['status'], 'passed')

    def test_code_examples_do_not_trigger_prose_placeholder_check(self):
        for fence in ('```', '~~~'):
            body = 'Example syntax:\n' + fence + 'python\nTODO: example\nvalue = "{{ title }}"\n' + fence + '\n'
            with self.subTest(fence=fence):
                issues = content.content_issues(self.article(markdown_content=body), 'absian')
                self.assertFalse(any(issue['code'] == 'unfinished_marker' for issue in issues))
        issues = content.content_issues(self.article(markdown_content='The placeholder `{{ title }}` is sample syntax.'), 'absian')
        self.assertFalse(any(issue['code'] == 'unfinished_marker' for issue in issues))

    def test_real_prose_placeholders_and_missing_fields_block(self):
        for body in ('TODO: check the source', '내용을 {{ 작성 }} 하세요', '[🔍 출처 확인]'):
            with self.subTest(body=body):
                issues = content.content_issues(self.article(markdown_content=body), 'absian')
                self.assertTrue(any(issue['code'] == 'unfinished_marker' for issue in issues))
        issues = content.content_issues(self.article(title=''), 'absian')
        self.assertTrue(any(issue['code'] == 'missing_field' and issue['detail'] == 'title' for issue in issues))

    def test_non_string_body_yields_blocking_issue(self):
        for body in (None, [], 123):
            with self.subTest(body=body):
                issues = content.content_issues(self.article(markdown_content=body), 'absian')
                self.assertTrue(any(issue['code'] == 'missing_field' and issue['detail'] == 'markdown_content' for issue in issues))

    def test_kpop_lyrics_reproduction_cannot_pass_even_with_clear_claim(self):
        article = self.article(markdown_content=self.article()['markdown_content'] + '\n## Original lyrics\nSome text')
        with self.assertRaises(ValueError):
            content.validate_review(article, self.review(), self.evidence(), 'kpop')

    def test_local_assets_reject_traversal_and_symlink_escape(self):
        public = self.root / 'blog-frontend/public'
        public.mkdir(parents=True)
        for path in ('/../../outside.png', '/images/%2e%2e/%2e%2e/private.png'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                content.local_asset(self.root, path)
        (public / 'link').symlink_to(self.root / 'private', target_is_directory=True)
        with self.assertRaises(ValueError):
            content.local_asset(self.root, '/link/secret.png')
        self.assertEqual(content.local_asset(self.root, '/images/a.png?v=1#x'), public / 'images/a.png')
        self.assertIsNone(content.local_asset(self.root, 'https://cdn.example/a.png'))
        self.assertIsNone(content.local_asset(self.root, '//cdn.example/a.png'))

    def test_evidence_extracts_hashes_and_deduplicates_sources(self):
        url = 'https://docs.example/source'
        body = ('<html><title>Official source</title><script>ignore this</script><nav>Navigation</nav><main>'
                + 'Reliable explanatory source material. ' * 20 + '</main></html>').encode()
        response = {'url': url, 'content_type': 'text/html', 'body': body, 'status': 200}
        with patch('blogops.content.safe_get', return_value=response) as fetch:
            records = content.collect_evidence([url, url])
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(records[0]['sha256'], hashlib.sha256(body).hexdigest())
        self.assertNotIn('ignore this', records[0]['text'])
        self.assertNotIn('Navigation', records[0]['text'])
        saved = self.root / 'state/evidence' / (records[0]['id'] + '.json')
        self.assertEqual(json.loads(saved.read_text())['sha256'], records[0]['sha256'])

    def test_evidence_rejects_inaccessible_or_unreviewed_source_formats(self):
        with self.assertRaises(ValueError):
            content.collect_evidence([])
        for response in ({'url': 'https://docs.example/a', 'content_type': 'application/pdf', 'body': b'%PDF'},
                         {'url': 'https://docs.example/a', 'content_type': 'text/html', 'body': b'<p>tiny</p>'}):
            with self.subTest(response=response), patch('blogops.content.safe_get', return_value=response):
                with self.assertRaises(ValueError):
                    content.collect_evidence(['https://docs.example/a'])

    def test_evidence_truncation_preserves_full_response_hash(self):
        body = ('Source reference ' * 2000).encode()
        with patch('blogops.content.safe_get', return_value={'url': 'https://docs.example/a', 'content_type': 'text/plain', 'body': body}):
            record = content.collect_evidence(['https://docs.example/a'])[0]
        self.assertTrue(record['truncated'])
        self.assertEqual(len(record['text']), 20000)
        self.assertEqual(record['sha256'], hashlib.sha256(body).hexdigest())

    def test_source_fetch_rejects_private_addresses_and_url_credentials(self):
        for url in ('http://docs.example/a', 'https://user:secret@docs.example/a', 'https://docs.example:8443/a'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                content.safe_get(url)
        private = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))]
        with patch('blogops.content.socket.getaddrinfo', return_value=private), patch('blogops.content.urllib3.HTTPSConnectionPool') as pool:
            with self.assertRaises(ValueError):
                content.safe_get('https://docs.example/a')
            pool.assert_not_called()

    def test_source_fetch_pins_ip_and_checks_tls_hostname(self):
        public = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]
        response = Mock(status=200, headers={'Content-Type': 'text/html'})
        response.stream.return_value = [b'body']
        pool = Mock()
        pool.request.return_value = response
        with patch('blogops.content.socket.getaddrinfo', return_value=public), patch('blogops.content.urllib3.HTTPSConnectionPool', return_value=pool) as create:
            value = content.safe_get('https://docs.example/page?a=1')
        self.assertEqual(create.call_args.args[0], '93.184.216.34')
        self.assertEqual(create.call_args.kwargs['assert_hostname'], 'docs.example')
        self.assertEqual(create.call_args.kwargs['server_hostname'], 'docs.example')
        self.assertEqual(pool.request.call_args.args[:2], ('GET', '/page?a=1'))
        self.assertEqual(pool.request.call_args.kwargs['headers']['Host'], 'docs.example')
        self.assertEqual(value['body'], b'body')
        response.close.assert_called_once()
        pool.close.assert_called_once()

    def test_source_fetch_enforces_size_and_rechecks_redirect_address(self):
        public = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]
        private = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.0.1', 443))]
        response = Mock(status=200, headers={'Content-Type': 'text/html'})
        response.stream.return_value = [b'1234', b'5678']
        pool = Mock()
        pool.request.return_value = response
        with patch('blogops.content.socket.getaddrinfo', return_value=public), patch('blogops.content.urllib3.HTTPSConnectionPool', return_value=pool):
            with self.assertRaises(ValueError):
                content.safe_get('https://docs.example/a', max_bytes=5)
        response.status = 302
        response.headers = {'Location': 'https://private.example/a'}
        with patch('blogops.content.socket.getaddrinfo', side_effect=[public, private]), patch('blogops.content.urllib3.HTTPSConnectionPool', return_value=pool):
            with self.assertRaises(ValueError):
                content.safe_get('https://docs.example/a')

    def test_inventory_excludes_drafts_and_detects_untracked_images(self):
        posts = self.root / 'repo/blog-frontend/src/content/blog'
        assets = self.root / 'repo/blog-frontend/public/images'
        posts.mkdir(parents=True)
        assets.mkdir(parents=True)
        (assets / 'existing.png').write_bytes(b'not-needed-for-local-existence-check')
        template = '---\ntitle: Example\ndescription: Description\ncategory: General\n{extra}---\n{body}'
        (posts / 'public.md').write_text(template.format(extra='heroImage: /images/existing.png\n', body='Public content.'))
        (posts / 'draft.md').write_text(template.format(extra='draft: true\nheroImage: /images/missing.png\n', body='Draft content.'))
        with patch('blogops.content.site_config', return_value={'root': str(self.root / 'repo'), 'url': 'https://target.example'}), patch('blogops.content.subprocess.run', return_value=Mock(stdout=b'')):
            report = content.inventory('absian')
        self.assertEqual(report['public_posts'], 1)
        self.assertEqual(report['draft_posts'], 1)
        self.assertTrue(any(issue['code'] == 'untracked_image' for issue in report['posts'][0]['issues']))
        self.assertFalse(any(issue['code'] == 'missing_image' for issue in report['posts'][0]['issues']))


class ReportTests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.store = Store(self.root / 'tasks.sqlite')
        self.config = {'sites': {'absian': {'name': 'A&B'}}, 'limits': {
            'codex_calls_per_day': 8, 'agy_calls_per_day': 12, 'new_workflows_per_day': 1}}
        context = patch('blogops.reports.settings', return_value=self.config)
        context.start()
        self.addCleanup(context.stop)

    def save(self, name, data):
        save_json(self.root / 'state/reports' / name, data)

    def test_missing_reports_remain_unknown_in_dashboard_and_brief(self):
        path = Path(reports.render(self.store))
        html = path.read_text()
        data = json.loads(path.with_suffix('.json').read_text())
        self.assertIn('실측 값 미확인', html)
        self.assertIn('공개 설정 글 미확인편', html)
        self.assertIsNone(data['sites'][0]['metrics'])
        self.assertIn('공개 설정 글: 미확인편', reports.brief('absian'))
        self.assertIn('A&amp;B', html)

    def test_explicit_zero_currency_and_period_remain_distinct_from_unknown(self):
        self.save('absian-metrics.json', {'adsense_state': 'READY', 'sources': {
            'adsense': {'status': 'measured', 'metrics': {'ESTIMATED_EARNINGS': 0}, 'currency': 'KRW', 'period': ['2026-09-01', '2026-09-15']},
            'ga4': {'status': 'not_connected', 'metrics': None}}})
        html = Path(reports.render(self.store)).read_text()
        brief = reports.brief('absian')
        self.assertIn('KRW', html)
        self.assertIn('2026-09-01', html)
        self.assertIn('ESTIMATED_EARNINGS', html)
        self.assertIn('ga4: not_connected · 수치 미확인', brief)
        self.assertIn('"ESTIMATED_EARNINGS": 0', brief)
        self.assertIn('KRW', brief)
        self.assertNotIn('USD', brief)

    def test_report_escapes_untrusted_post_titles_and_issue_text(self):
        self.save('absian-inventory.json', {'public_posts': 1, 'draft_posts': 0, 'blocker_count': 1, 'review_count': 0,
            'posts': [{'slug': 'post', 'title': '<script>bad()</script>',
                       'issues': [{'severity': 'blocker', 'code': 'missing_image', 'detail': '<img src=x onerror=bad()>'}]}]})
        html = Path(reports.render(self.store)).read_text()
        self.assertNotIn('<script>bad()', html)
        self.assertNotIn('<img src=x', html)
        self.assertIn('&lt;script&gt;', html)


if __name__ == '__main__':
    unittest.main()
