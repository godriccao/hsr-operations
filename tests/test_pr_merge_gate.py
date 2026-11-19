import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import pr_merge_gate as gate

HEAD = 'a' * 40
BASE = 'b' * 40


def summary(head=HEAD, status='completed', unresolved=False):
    state = {name: {'commit_sha': head, 'status': status,
                    'has_any_findings': unresolved, 'has_unresolved_findings': unresolved}
             for name in ('code_review', 'security_review')}
    return {'id': 1, 'updated_at': '2026-01-01T00:00:00Z',
            'user': {'id': gate.BOT_ID, 'login': gate.BOT_LOGIN, 'type': 'Bot'},
            'performed_via_github_app': {'id': gate.APP_ID},
            'body': '<!-- codex-pull-request-review-summary -->\n'
                    '<!-- codex-review-state:v1 ' + json.dumps(state) + ' -->'}


class FakeAPI:
    def __init__(self):
        self.comments = [summary()]
        self.pr = {'state': 'open', 'draft': False, 'head': {'sha': HEAD},
                   'base': {'ref': 'main', 'sha': BASE},
                   'mergeable': True, 'mergeable_state': 'clean'}
        self.reviews = []
        self.threads = False
        self.run = {'event': 'pull_request', 'head_sha': HEAD, 'run_number': 1,
                    'status': 'completed', 'conclusion': 'success'}
        self.check = {'name': 'verify', 'app': {'slug': 'github-actions'},
                      'status': 'completed', 'conclusion': 'success'}
        self.merge_base = BASE
        self.writes = []
        self.evaluations = 0

    def request(self, path, data=None, method='GET'):
        if path == '/pulls/1':
            self.evaluations += 1
            return self.pr
        if path.endswith('/merge'):
            self.writes.append((path, data, method))
            return {'merged': True, 'sha': 'c' * 40}
        if path.endswith('/dispatches'):
            self.writes.append((path, data, method))
            return None
        if '/compare/' in path:
            return {'merge_base_commit': {'sha': self.merge_base}}
        if path.endswith('/status'):
            return {'statuses': [], 'state': 'pending'}
        raise AssertionError(path)

    def pages(self, path, key=None):
        if path.endswith('/comments'): return self.comments
        if path.endswith('/reactions'): return []
        if path.endswith('/reviews'): return self.reviews
        if '/actions/' in path: return [self.run]
        if '/check-runs' in path: return [self.check]
        raise AssertionError(path)

    def unresolved_threads(self, number):
        return self.threads


class MergeContract(unittest.TestCase):
    def test_success_binds_reviewed_sha_and_reevaluates(self):
        api = FakeAPI()
        result = gate.merge_one(api, 1)
        self.assertTrue(result['merged'])
        self.assertEqual(api.evaluations, 2)
        self.assertEqual(api.writes, [('/pulls/1/merge', {'sha': HEAD, 'merge_method': 'squash'}, 'PUT'),
                         ('/actions/workflows/offline.yml/dispatches', {'ref': 'main'}, 'POST')])

    def test_spoofed_or_missing_review_never_merges(self):
        for key, value in [('user', {'id': 1, 'login': gate.BOT_LOGIN, 'type': 'Bot'}),
                           ('performed_via_github_app', {'id': 1}), ('body', 'All checks passed')]:
            api = FakeAPI()
            api.comments[0][key] = value
            self.assertFalse(gate.merge_one(api, 1)['merged'])
            self.assertEqual(api.writes, [])

    def test_stale_running_findings_and_unknown_block(self):
        for record in [summary('d'*40), summary(status='running'), summary(unresolved=True),
                       summary(unresolved=None), summary(status='failed')]:
            api = FakeAPI(); api.comments = [record]
            self.assertFalse(gate.merge_one(api, 1)['merged'])
            self.assertEqual(api.writes, [])

    def test_new_running_summary_overrides_old_positive(self):
        api = FakeAPI()
        newer = summary(status='running'); newer['updated_at'] = '2026-01-02T00:00:00Z'
        api.comments.append(newer)
        self.assertFalse(gate.merge_one(api, 1)['merged'])

    def test_draft_failed_ci_unresolved_threads_and_changes_request_block(self):
        for kind in ['draft', 'failed_ci', 'threads', 'changes_requested', 'stale_base']:
            api = FakeAPI()
            if kind == 'draft': api.pr['draft'] = True
            elif kind == 'failed_ci': api.run['conclusion'] = 'failure'
            elif kind == 'threads': api.threads = True
            elif kind == 'changes_requested': api.reviews = [{'user': {'id': 7}, 'state': 'CHANGES_REQUESTED'}]
            else: api.merge_base = 'd'*40
            self.assertFalse(gate.merge_one(api, 1)['merged'])
            self.assertEqual(api.writes, [])

    def test_head_change_before_write_blocks(self):
        api = FakeAPI()
        request = api.request
        def changing(path, data=None, method='GET'):
            if path == '/pulls/1' and api.evaluations == 1:
                api.pr = copy.deepcopy(api.pr)
                api.pr['head']['sha'] = 'd' * 40
            return request(path, data, method)
        api.request = changing
        self.assertFalse(gate.merge_one(api, 1)['merged'])
        self.assertEqual(api.writes, [])

    def test_dry_run_does_not_write(self):
        api = FakeAPI()
        result = gate.merge_one(api, 1, dry_run=True)
        self.assertEqual(result['reason'], 'ready to merge')
        self.assertEqual(api.writes, [])

    def test_security_without_booleans_requires_new_overall_clearance(self):
        record = summary()
        state = json.loads(gate.MARKER.findall(record['body'])[0])
        state['security_review']['has_any_findings'] = None
        state['security_review']['has_unresolved_findings'] = None
        record['body'] = '<!-- codex-pull-request-review-summary -->\n<!-- codex-review-state:v1 ' + json.dumps(state) + ' -->'
        reaction = {'user': {'id': gate.BOT_ID, 'login': gate.BOT_LOGIN},
                    'content': '+1', 'created_at': '2026-01-01T00:00:01Z'}
        self.assertFalse(gate.review_verdict([record], HEAD)[0])
        self.assertTrue(gate.review_verdict([record], HEAD, [reaction])[0])
        reaction['created_at'] = '2025-12-31T23:59:59Z'
        self.assertFalse(gate.review_verdict([record], HEAD, [reaction])[0])


if __name__ == '__main__':
    unittest.main()
