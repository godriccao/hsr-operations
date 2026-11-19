"""Event-driven PR merge gate. Reads trusted base code only; never executes PR code."""
import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request

BOT_ID = 199175422
BOT_LOGIN = 'chatgpt-codex-connector[bot]'
APP_ID = 1144995
MARKER = re.compile(r'<!-- codex-review-state:v1 (\{.*?\}) -->', re.DOTALL)


def review_verdict(comments, head, reactions=()):
    trusted = [c for c in comments if c.get('user', {}).get('id') == BOT_ID
               and c.get('user', {}).get('login') == BOT_LOGIN
               and c.get('user', {}).get('type') == 'Bot'
               and (c.get('performed_via_github_app') or {}).get('id') == APP_ID
               and '<!-- codex-pull-request-review-summary -->' in c.get('body', '')]
    if not trusted:
        return False, 'no trusted Codex review summary'
    latest = max(trusted, key=lambda c: (c.get('updated_at', ''), c.get('id', 0)))
    matches = MARKER.findall(latest['body'])
    if len(matches) != 1:
        return False, 'missing or ambiguous structured review state'
    try:
        state = json.loads(matches[0])
    except ValueError:
        return False, 'invalid structured review state'
    if not isinstance(state, dict) or not isinstance(state.get('code_review'), dict):
        return False, 'missing code review'
    # Security review, when present, must finish too. Unknown states fail closed.
    needs_overall_clear = False
    for name, result in state.items():
        if name not in ('code_review', 'security_review') or not isinstance(result, dict):
            return False, 'unknown review kind or state'
        if result.get('commit_sha') != head:
            return False, name + ': stale head'
        if result.get('status') != 'completed':
            return False, name + ': not completed'
        if (name == 'security_review' and result.get('has_any_findings') is None
                and result.get('has_unresolved_findings') is None):
            # Native security reports currently omit finding booleans. Its final
            # trusted thumbs-up means all reviews completed without findings.
            # Require it AFTER the current summary update so an old-head reaction
            # cannot authorize a new commit. Unknown code-review booleans still block.
            needs_overall_clear = True
        elif result.get('has_unresolved_findings') is not False:
            return False, name + ': unresolved or unknown findings'
    if needs_overall_clear:
        fresh_positive = any(
            r.get('user', {}).get('id') == BOT_ID
            and r.get('user', {}).get('login') == BOT_LOGIN
            and r.get('content') == '+1'
            and bool(latest.get('updated_at'))
            and r.get('created_at', '') >= latest['updated_at']
            for r in reactions)
        if not fresh_positive:
            return False, 'awaiting fresh overall Codex clearance'
    return True, 'trusted reviews completed for current head'


class GitHub:
    def __init__(self, repository, token):
        self.repository = repository
        self.base = 'https://api.github.com/repos/' + repository
        self.token = token

    def request(self, suffix, data=None, method='GET'):
        # All paths are fixed repository API routes, never PR-supplied URLs.
        url = self.base + suffix
        headers = {'Authorization': 'Bearer ' + self.token,
                   'Accept': 'application/vnd.github+json',
                   'X-GitHub-Api-Version': '2022-11-28'}
        body = json.dumps(data).encode() if data is not None else None
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status == 204:
                return None
            return json.load(response)

    def pages(self, suffix, key=None):
        result = []
        for page in range(1, 101):
            separator = '&' if '?' in suffix else '?'
            data = self.request(suffix + f'{separator}per_page=100&page={page}')
            values = data[key] if key else data
            result.extend(values)
            if len(values) < 100:
                return result
        raise RuntimeError('API pagination limit reached; cannot establish complete state')

    def unresolved_threads(self, number):
        owner, name = self.repository.split('/')
        cursor = None
        while True:
            query = '''query($owner:String!,$name:String!,$number:Int!,$cursor:String) {
              repository(owner:$owner,name:$name) { pullRequest(number:$number) {
                reviewThreads(first:100,after:$cursor) {
                  nodes { isResolved }
                  pageInfo { hasNextPage endCursor }
                }
              } }
            }'''
            request = urllib.request.Request('https://api.github.com/graphql',
                data=json.dumps({'query': query, 'variables': {
                    'owner': owner, 'name': name, 'number': number, 'cursor': cursor}}).encode(),
                headers={'Authorization': 'Bearer ' + self.token,
                         'Content-Type': 'application/json'}, method='POST')
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.load(response)
            if data.get('errors'):
                raise RuntimeError('Cannot verify review thread state')
            threads = data['data']['repository']['pullRequest']['reviewThreads']
            if any(not thread['isResolved'] for thread in threads['nodes']):
                return True
            if not threads['pageInfo']['hasNextPage']:
                return False
            cursor = threads['pageInfo']['endCursor']


def evaluate(api, number):
    pr = api.request(f'/pulls/{number}')
    head = pr['head']['sha']
    if pr['state'] != 'open' or pr.get('draft') or pr['base']['ref'] != 'main':
        return None, 'not an open, ready PR targeting main'
    ok, reason = review_verdict(api.pages(f'/issues/{number}/comments'), head,
                                api.pages(f'/issues/{number}/reactions'))
    if not ok:
        return None, reason
    latest_reviews = {}
    for review in api.pages(f'/pulls/{number}/reviews'):
        if review['state'] not in ('PENDING', 'COMMENTED'):
            latest_reviews[review['user']['id']] = review['state']
    if 'CHANGES_REQUESTED' in latest_reviews.values():
        return None, 'changes requested'
    if api.unresolved_threads(number):
        return None, 'unresolved review threads'
    runs = api.pages('/actions/workflows/offline.yml/runs?head_sha=' + head, 'workflow_runs')
    runs = [r for r in runs if r['event'] == 'pull_request' and r['head_sha'] == head]
    if not runs:
        return None, 'no pull-request offline verification run for head'
    run = max(runs, key=lambda r: (r['run_number'], r.get('run_attempt', 1)))
    if run['status'] != 'completed' or run['conclusion'] != 'success':
        return None, 'offline verification not successful'
    checks = api.pages(f'/commits/{head}/check-runs?filter=latest', 'check_runs')
    if not any(c['name'] == 'verify' and c['app']['slug'] == 'github-actions'
               and c['conclusion'] == 'success' for c in checks):
        return None, 'missing verify check'
    # This gate also creates a check. It cannot wait for itself, and a superseded
    # event invocation may be cancelled by the concurrency group. Offline verify
    # remains mandatory; all other independent checks still have to be healthy.
    independent = [c for c in checks if not (
        c['name'] == 'merge' and c['app']['slug'] == 'github-actions')]
    if any(c['status'] != 'completed' or c['conclusion'] not in ('success', 'neutral', 'skipped')
           for c in independent):
        return None, 'pending or failing check'
    statuses = api.request(f'/commits/{head}/status')
    if statuses['statuses'] and statuses['state'] != 'success':
        return None, 'pending or failing commit status'
    # A base update requires retesting the combined changes; do not merge stale branches.
    comparison = api.request(f'/compare/{pr["base"]["sha"]}...{head}')
    if comparison['merge_base_commit']['sha'] != pr['base']['sha']:
        return None, 'branch must include current main and be reviewed again'
    if pr.get('mergeable') is not True or pr.get('mergeable_state') != 'clean':
        return None, 'GitHub has not established a clean merge'
    return head, 'ready to merge'


def merge_one(api, number, dry_run=False):
    head, reason = evaluate(api, number)
    if head is None or dry_run:
        return {'pr': number, 'head': head, 'merged': False, 'reason': reason,
                'dry_run': dry_run}
    # Re-evaluate before the write; GitHub additionally guards the exact reviewed SHA
    # and enforces any repository protection rules at the merge endpoint.
    fresh_head, fresh_reason = evaluate(api, number)
    if fresh_head != head:
        return {'pr': number, 'merged': False, 'reason': fresh_reason}
    result = api.request(f'/pulls/{number}/merge',
                         {'sha': head, 'merge_method': 'squash'}, method='PUT')
    if not result.get('merged'):
        raise RuntimeError('GitHub declined the guarded merge')
    # A merge made with GITHUB_TOKEN does not emit another push workflow run.
    # Explicit dispatch is supported and tests the resulting main without a PAT.
    api.request('/actions/workflows/offline.yml/dispatches', {'ref': 'main'}, method='POST')
    return {'pr': number, 'head': head, 'merged': True, 'merge_sha': result['sha'],
            'post_merge_ci_dispatched': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pr', type=int)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    repo = os.environ.get('GITHUB_REPOSITORY', '')
    if repo != 'godriccao/hsr-operations':
        parser.error('This merge gate is scoped to godriccao/hsr-operations')
    api = GitHub(repo, os.environ['GITHUB_TOKEN'])
    numbers = [args.pr] if args.pr else [p['number'] for p in api.pages('/pulls?state=open')]
    for number in numbers:
        result = merge_one(api, number, args.dry_run)
        # GitHub has no reaction-created Actions trigger. A completed-summary event
        # may precede Codex's final reaction by a few seconds: bounded API-only wait.
        for _ in range(6):
            if result.get('reason') != 'awaiting fresh overall Codex clearance':
                break
            time.sleep(5)
            result = merge_one(api, number, args.dry_run)
        print(json.dumps(result))


if __name__ == '__main__':
    main()
