import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from tools import achievement_catalog as catalog


FIXTURE = catalog.ROOT / 'examples' / 'achievement-catalog.synthetic.jsonl'


class AchievementCatalogTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / 'cache'
        self.active = self.output / 'current.json'
        self.manifest = b'{"hsr":{"live":"4.7","latest":"4.7.51","available":["4.7","4.7.51"]}}'

    def invoke(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = catalog.main(['--output', str(self.output), *args])
        return code, json.loads(stdout.getvalue()) if stdout.getvalue() else None, stderr.getvalue()

    def seed(self):
        result, preview, _ = self.invoke('--input', str(FIXTURE), '--version', '4.7')
        self.assertEqual(result, 0)
        self.assertEqual(preview['mode'], 'saved')
        self.assertEqual((preview['from_version'], preview['rows'], len(preview['added'])), (None, 10, 10))
        return self.active.read_bytes()

    def test_formal_manifest_excludes_beta(self):
        with patch.object(catalog, 'fetch', side_effect=[self.manifest, FIXTURE.read_bytes()]) as fetch:
            code, report, _ = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(report['to_version'], '4.7')
        self.assertEqual(fetch.call_args_list[1].args, (catalog.CATALOG_URL.format(version='4.7'),))
        self.assertEqual(json.loads(self.active.read_bytes())['source']['origin'], 'download')
        with self.assertRaisesRegex(ValueError, 'major.minor'):
            catalog.select_version(self.manifest, '4.7.51')

    def test_repeat_titles_keep_distinct_ids(self):
        previous = json.loads(self.seed())
        self.assertEqual(previous['source']['origin'], 'local_input')
        self.assertIsNone(previous['source']['url'])
        self.assertEqual([row['id'] for row in previous['items'] if row['name'] == '合成重复标题'], [1001, 1002])
        self.assertEqual(previous['items'][1]['show_type'], 'ShowAfterFinish')

    def test_new_version_with_same_rows_does_not_report_all_changed(self):
        self.seed()
        code, data, _ = self.invoke('--input', str(FIXTURE), '--version', '4.8')
        self.assertEqual(code, 0)
        self.assertEqual((data['added'], data['removed'], data['changed']), ([], [], []))
        self.assertEqual(sorted(p.name for p in self.output.iterdir()), ['current.json'])
        self.assertEqual(json.loads(self.active.read_bytes())['version'], '4.8')

    def test_same_version_reports_add_remove_and_fields(self):
        old = self.seed()
        update = json.loads(FIXTURE.read_bytes())
        rows = update['1']['list']
        rows[0]['desc'] = '另一条合成文案'
        rows[0]['rarity'] = 'High'
        rows[1]['id'] = 1003
        fixture = self.root / 'update.json'
        fixture.write_text(json.dumps(update), encoding='utf-8')
        inputs = ('--input', str(fixture), '--version', '4.7')
        code, preview, _ = self.invoke(*inputs, '--dry-run')
        self.assertEqual(code, 0)
        self.assertEqual(preview['mode'], 'preview')
        self.assertEqual(self.active.read_bytes(), old)
        self.assertEqual(sorted(p.name for p in self.output.iterdir()), ['current.json'])
        code, result, _ = self.invoke(*inputs)
        self.assertEqual(code, 0)
        self.assertEqual(result['added'], [1003])
        self.assertEqual(result['removed'], [1002])
        self.assertEqual(result['changed'], [{'id': 1001, 'fields': ['description', 'jade', 'rarity']}])
        self.assertNotEqual(result['from_sha256'], result['sha256'])
        self.assertNotEqual(self.active.read_bytes(), old)
        self.assertEqual(self.invoke(*inputs)[1]['mode'], 'unchanged')

    def test_bad_manifest_and_duplicate_ids_keep_old_bytes(self):
        old = self.seed()
        with patch.object(catalog, 'fetch', return_value=b'{"hsr":{"available":["4.7"]}}'):
            self.assertEqual(self.invoke()[0], 1)
        bad = json.loads(FIXTURE.read_bytes())
        bad['1']['list'][1]['id'] = 1001
        with patch.object(catalog, 'fetch', side_effect=[self.manifest, json.dumps(bad).encode()]):
            code, _, error = self.invoke()
        self.assertEqual(code, 1)
        self.assertIn('duplicate achievement ID', error)
        self.assertEqual(self.active.read_bytes(), old)

    def test_rate_limit_and_timeout_never_retry_or_replace(self):
        old = self.seed()
        for failure, message in ((HTTPError(catalog.MANIFEST_URL, 429, 'Rate limited', None, None), 'HTTP 429'),
                                 (TimeoutError('timed out'), 'source unavailable')):
            with self.subTest(failure=failure), patch.object(catalog, 'urlopen', side_effect=failure) as request:
                code, _, error = self.invoke()
                self.assertEqual(code, 1)
                self.assertIn(message, error)
                request.assert_called_once()
                self.assertEqual(self.active.read_bytes(), old)

    def test_failed_final_write_preserves_current_and_retry_recovers(self):
        previous = self.seed()
        write = catalog.atomic_json

        def fail_current(path, data):
            if path == self.active:
                raise OSError('simulated final-write failure')
            write(path, data)

        args = ('--input', str(FIXTURE), '--version', '4.8')
        with patch.object(catalog, 'atomic_json', side_effect=fail_current):
            self.assertEqual(self.invoke(*args)[0], 1)
        self.assertEqual(self.active.read_bytes(), previous)
        self.assertEqual(self.invoke(*args)[0], 0)
        self.assertEqual(sorted(p.name for p in self.output.iterdir()), ['current.json'])

    def test_dry_run_first_read_does_not_create_cache(self):
        self.assertEqual(self.invoke('--input', str(FIXTURE), '--version', '4.7', '--dry-run')[0], 0)
        self.assertFalse(self.output.exists())

    def test_second_updater_cannot_fetch_until_lock_released(self):
        old = self.seed()
        with catalog.update_lock(self.output), patch.object(catalog, 'fetch') as fetch:
            result, _, error = self.invoke()
            self.assertEqual(result, 1)
            self.assertIn('update-in-progress', error)
            fetch.assert_not_called()
        self.assertEqual(self.active.read_bytes(), old)
        self.assertFalse((self.output / 'update-in-progress').exists())

    def test_older_source_never_replaces_active_version(self):
        previous = self.seed()
        code, _, error = self.invoke('--input', str(FIXTURE), '--version', '4.6')
        self.assertEqual(code, 1)
        self.assertIn('older than the active version', error)
        self.assertEqual(self.active.read_bytes(), previous)
        self.assertEqual(sorted(p.name for p in self.output.iterdir()), ['current.json'])
