"""Attaching prepared assets never generates images or changes public files."""
import copy
import hashlib
from itertools import permutations
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from blogops.prepared_assets import attach_images


class PreparedAssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.public = self.root / 'blog-frontend/public'
        (self.public / 'images').mkdir(parents=True)
        self.article = {'title': 'Example', 'markdown_content': 'Introduction.\n\n## First\nFirst paragraph.\n\n## Second\nSecond paragraph.\n',
                        'nested': {'kept': ['unchanged']}}
        self.assets = []
        for role in ('thumbnail', 'body-1', 'body-2'):
            url = '/images/' + role + '.png'
            path = self.public / url.lstrip('/')
            path.write_bytes((role + '-fixture-image').encode())
            asset = {'role': role, 'url': url, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'provenance': 'reused'}
            if role != 'thumbnail':
                asset.update(alt='Helpful illustration ' + role, caption='Caption ' + role,
                             before_heading='First' if role == 'body-1' else 'Second')
            self.assets.append(asset)
        self.before_files = {path: path.read_bytes() for path in self.public.rglob('*') if path.is_file()}

    def attach(self, assets=None, article=None):
        return attach_images(article or self.article, self.assets if assets is None else assets, self.root)

    def test_verified_images_attach_before_exact_headings(self):
        result = self.attach()
        body = result['markdown_content']
        self.assertLess(body.index('provided-asset:body-1'), body.index('## First'))
        self.assertLess(body.index('provided-asset:body-2'), body.index('## Second'))
        self.assertEqual(result['heroImage'], '/images/thumbnail.png')
        self.assertEqual(result['image_preparation']['mode'], 'provided')
        self.assertEqual([asset['role'] for asset in result['image_preparation']['assets']], ['thumbnail', 'body-1', 'body-2'])
        self.assertNotIn('image_generation', result)
        self.assertNotIn('article_images', result)

    def test_no_model_process_network_or_file_mutation(self):
        original_article, original_assets = copy.deepcopy(self.article), copy.deepcopy(self.assets)
        with patch('subprocess.run', side_effect=AssertionError('No process execution')), patch('socket.create_connection', side_effect=AssertionError('No network')):
            result = self.attach()
        self.assertEqual(self.article, original_article)
        self.assertEqual(self.assets, original_assets)
        result['nested']['kept'].append('new')
        self.assertEqual(self.article['nested']['kept'], ['unchanged'])
        self.assertEqual(self.before_files, {path: path.read_bytes() for path in self.public.rglob('*') if path.is_file()})

    def test_stale_native_generation_metadata_is_removed_without_inventing_generation(self):
        article = {**self.article, 'heroImage': '/images/old.png', 'article_images': ['stale'],
                   'image_generation': {'status': 'complete', 'provider': 'codex_image_generation'}}
        result = self.attach(article=article)
        self.assertNotIn('image_generation', result)
        self.assertNotIn('article_images', result)
        self.assertEqual(result['heroImage'], self.assets[0]['url'])
        self.assertEqual(article['heroImage'], '/images/old.png')

    def test_all_input_permutations_produce_identical_output(self):
        expected = self.attach()
        for ordered in permutations(self.assets):
            self.assertEqual(self.attach(list(ordered)), expected)

    def test_missing_or_omitted_headings_append_in_role_order(self):
        assets = copy.deepcopy(self.assets)
        assets[1]['before_heading'] = 'Absent heading'
        assets[2].pop('before_heading')
        body = self.attach(assets)['markdown_content']
        self.assertTrue(body.startswith(self.article['markdown_content']))
        self.assertLess(body.index('provided-asset:body-1'), body.index('provided-asset:body-2'))

    def test_shared_heading_uses_body_role_order(self):
        assets = copy.deepcopy(self.assets)
        assets[2]['before_heading'] = 'First'
        body = self.attach(list(reversed(assets)))['markdown_content']
        self.assertLess(body.index('provided-asset:body-1'), body.index('provided-asset:body-2'))
        self.assertLess(body.index('provided-asset:body-2'), body.index('## First'))

    def test_heading_text_must_match_exactly_and_ignore_code_fences(self):
        article = {**self.article, 'markdown_content': '~~~md\n## First\n~~~\n## First Steps\nContent.\n'}
        body = self.attach(article=article)['markdown_content']
        self.assertTrue(body.startswith(article['markdown_content']))

    def test_markdown_closing_heading_marks_are_supported(self):
        article = {**self.article, 'markdown_content': '## First ##\nContent.\n## Second ###\nMore.\n'}
        body = self.attach(article=article)['markdown_content']
        self.assertLess(body.index('provided-asset:body-1'), body.index('## First'))
        self.assertLess(body.index('provided-asset:body-2'), body.index('## Second'))

    def test_existing_body_images_are_rejected_without_silent_deletion(self):
        for image in ('![inline](/images/a.png)', '![reference][img]', '![shortcut]',
                      '<img src="/images/a.png">', '<IMG SRC="https://other.example/a.png">',
                      '<picture><source srcset="/images/a.png"></picture>', '<svg><image href="x"/></svg>'):
            article = {**self.article, 'markdown_content': self.article['markdown_content'] + image}
            with self.subTest(image=image), self.assertRaises(ValueError):
                self.attach(article=article)
            self.assertTrue(article['markdown_content'].endswith(image))

    def test_code_example_of_image_markup_is_preserved(self):
        article = {**self.article, 'markdown_content': 'Example `![alt](url)` syntax.\n~~~html\n<img src="example.png">\n~~~\n'}
        result = self.attach(article=article)
        self.assertTrue(result['markdown_content'].startswith(article['markdown_content']))

    def test_body_text_and_url_are_html_escaped(self):
        assets = copy.deepcopy(self.assets)
        path = self.public / 'images/a"&b.png'
        path.write_bytes(b'special filename')
        assets[1].update(url='/images/a"&b.png', sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                         alt='" onerror="bad() & <x>', caption='<script>bad()</script> & "caption"')
        body = self.attach(assets)['markdown_content']
        self.assertIn('src="/images/a&quot;&amp;b.png"', body)
        self.assertIn('&lt;script&gt;bad()&lt;/script&gt;', body)
        self.assertNotIn('<script>bad()', body)
        self.assertNotIn('alt="" onerror=', body)

    def test_exactly_three_unique_roles_are_required(self):
        for assets in ([], self.assets[:2], self.assets + [self.assets[0]],
                       [self.assets[0], self.assets[1], {**self.assets[2], 'role': 'body-1'}],
                       [self.assets[0], self.assets[1], {**self.assets[2], 'role': 'unknown'}]):
            with self.subTest(assets=assets), self.assertRaises(ValueError):
                self.attach(assets)

    def test_duplicate_url_or_resolved_alias_is_rejected(self):
        for url in (self.assets[1]['url'], '/images/%62ody-1.png'):
            assets = copy.deepcopy(self.assets)
            assets[2].update(url=url, sha256=assets[1]['sha256'])
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.attach(assets)

    def test_external_traversal_query_fragment_and_control_paths_are_rejected(self):
        urls = ('https://other.example/a.png', '//other.example/a.png', '/other/a.png',
                '/images/../secret.png', '/images/%2e%2e/secret.png', '/images/../../secret.png',
                '/images/a.png?v=1', '/images/a.png#x', '/images//a.png', '/images/a%00.png',
                '/images/a\\b.png', '/images/a%5cb.png', '/images/a\nb.png')
        for url in urls:
            assets = copy.deepcopy(self.assets)
            assets[1]['url'] = url
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.attach(assets)

    def test_symlink_escape_is_rejected(self):
        outside = self.root / 'outside.png'
        outside.write_bytes(b'outside file')
        (self.public / 'images/link.png').symlink_to(outside)
        assets = copy.deepcopy(self.assets)
        assets[1].update(url='/images/link.png', sha256=hashlib.sha256(outside.read_bytes()).hexdigest())
        with self.assertRaises(ValueError):
            self.attach(assets)

    def test_public_directory_cannot_be_an_external_symlink(self):
        repo = self.root / 'other-repo'
        (repo / 'blog-frontend').mkdir(parents=True)
        (repo / 'blog-frontend/public').symlink_to(self.public, target_is_directory=True)
        with self.assertRaises(ValueError):
            attach_images(self.article, self.assets, repo)

    def test_missing_directory_or_hash_mismatch_fails_before_returning_article(self):
        for mutation in ({'url': '/images/missing.png'}, {'url': '/images/'}, {'sha256': '0' * 64}):
            assets = copy.deepcopy(self.assets)
            assets[1].update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.attach(assets)

    def test_full_file_hash_is_verified_beyond_first_chunk(self):
        path = self.public / 'images/body-1.png'
        prefix = b'x' * (1024 * 1024)
        path.write_bytes(prefix + b'end')
        assets = copy.deepcopy(self.assets)
        assets[1]['sha256'] = hashlib.sha256(prefix).hexdigest()
        with self.assertRaises(ValueError):
            self.attach(assets)
        assets[1]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        self.assertEqual(self.attach(assets)['image_preparation']['assets'][1]['sha256'], assets[1]['sha256'].lower())

    def test_body_labels_provenance_and_hash_format_are_required(self):
        for mutation in ({'alt': None}, {'caption': ''}, {'before_heading': 1}, {'before_heading': 'First\nSecond'},
                         {'provenance': 'unknown'}, {'sha256': '123'}, {'sha256': 'z' * 64}):
            assets = copy.deepcopy(self.assets)
            assets[1].update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.attach(assets)

    def test_generated_provenance_is_recorded_without_native_generation_metadata(self):
        assets = copy.deepcopy(self.assets)
        assets[1]['provenance'] = 'generated'
        result = self.attach(assets)
        self.assertEqual(result['image_preparation']['assets'][1]['provenance'], 'generated')
        self.assertNotIn('image_generation', result)

    def test_invalid_article_input_is_rejected(self):
        for article in (None, [], {}, {'markdown_content': None}, {'markdown_content': ' '}):
            with self.subTest(article=article), self.assertRaises(ValueError):
                attach_images(article, self.assets, self.root)


if __name__ == '__main__':
    unittest.main()
