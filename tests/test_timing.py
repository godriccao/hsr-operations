import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import benchmark
import codex_timing


class TimingContract(unittest.TestCase):
    def setUp(self):
        self.rows = [json.loads(line) for line in (ROOT / 'examples/timing.synthetic.jsonl').read_text().splitlines()]

    def test_first_frame_and_categories(self):
        # Independent synthetic contract: menu 4000ms, multi-frame movement 18000ms.
        result = benchmark.summarize(self.rows)
        self.assertEqual(result['overall']['median_ms'], 11000)
        self.assertEqual(result['categories']['menu']['median_ms'], 4000)
        self.assertEqual(result['categories']['movement']['median_ms'], 18000)
        self.assertEqual(result['paired_acknowledgements'], 3)

    def test_unknown_and_nonoperable_excluded(self):
        result = benchmark.summarize(self.rows)
        self.assertEqual(result['overall']['sample_count'], 2)
        self.assertEqual(result['excluded'], {'not_operable': 1, 'operability_unknown': 1})
        self.assertEqual(result['overall']['target_unverified_count'], 1)

    def test_mismatched_ack_is_invalid(self):
        rows = copy.deepcopy(self.rows[:1])
        rows[0]['events'][-1]['command'] = 'keys|W|80'
        self.assertEqual(len(benchmark.summarize(rows)['invalid']), 1)

    def test_missing_ack_and_overlap_rejected(self):
        for events in ([{'type': 'dispatch', 't_ms': 4000, 'command': 'keys|M|80'}],
                       [{'type': 'dispatch', 't_ms': 4000, 'command': 'keys|M|80'},
                        {'type': 'dispatch', 't_ms': 4100, 'command': 'keys|M|80'}]):
            row = copy.deepcopy(self.rows[0])
            row['events'] = events
            self.assertEqual(len(benchmark.summarize([row])['invalid']), 1)

    def test_original_parser_multiframe_and_receipts(self):
        rows = [row for row in codex_timing.samples(codex_timing.events(ROOT / 'examples/session.synthetic.jsonl', 16))
                if row['capture_tool'] == 'CuaScreenshot']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['observation_frames'], 2)
        self.assertEqual(rows[0]['first_frame_to_first_bridge_dispatch_ms'], 18000)
        self.assertEqual(rows[0]['frame_to_first_bridge_dispatch_ms'], 3000)
        self.assertEqual(rows[0]['bridge_dispatches'], 2)
        self.assertEqual(rows[0]['bridge_acknowledgements'], 2)
        self.assertIsNone(rows[0]['context_compaction_ms'])
        self.assertEqual(rows[0]['unattributed_before_check_ms'], 2400)

    def test_compaction_and_reasoning_share_the_precheck_window(self):
        rows = list(codex_timing.samples([
            (0, 100, "McpToolCall", "ObsScreenshot", None, None),
            (120, 200, "ContextCompaction", None, None, None),
            (120, 200, "ContextCompaction", None, None, None),
            (170, 240, "ContextCompaction", None, None, None),
            (270, 360, "ContextCompaction", None, None, None),
            (160, 280, "Reasoning", None, None, None),
            (300, 310, "McpToolCall", "ControlStatus", "ready", None),
            (320, 400, "CommandExecution", None, None, ([330], 1)),
        ]))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["context_compaction_ms"], 150)
        self.assertEqual(rows[0]["recorded_reasoning_ms"], 120)
        self.assertEqual(rows[0]["unattributed_before_check_ms"], 20)
        self.assertEqual(rows[0]["frame_to_first_bridge_dispatch_ms"], 230)

    def test_compaction_before_new_frame_is_not_reassigned(self):
        rows = list(codex_timing.samples([
            (20, 100, "McpToolCall", "ObsScreenshot", None, None),
            (140, 320, "ContextCompaction", None, None, None),
            (280, 300, "McpToolCall", "ObsScreenshot", None, None),
            (310, 370, "ContextCompaction", None, None, None),
            (400, 410, "McpToolCall", "ControlStatus", "ready", None),
            (420, 500, "CommandExecution", None, None, ([430], 1)),
        ]))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["observation_frames"], 2)
        self.assertEqual(rows[0]["context_compaction_ms"], 60)
        self.assertEqual(rows[0]["unattributed_before_check_ms"], 40)
        self.assertEqual(rows[0]["frame_to_first_bridge_dispatch_ms"], 130)
        self.assertEqual(rows[0]["first_frame_to_first_bridge_dispatch_ms"], 330)

    def test_obs_frame_and_prefixed_ack(self):
        rows = [row for row in codex_timing.samples(codex_timing.events(ROOT / 'examples/session.synthetic.jsonl', 16))
                if row['capture_tool'] == 'ObsScreenshot']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['screenshot_ms'], 43)
        self.assertEqual(rows[0]['first_frame_to_first_bridge_dispatch_ms'], 857)
        self.assertEqual(rows[0]['bridge_acknowledgements'], 1)

    def run_timing(self, *arguments):
        return subprocess.run(
            [sys.executable, str(ROOT / 'tools/codex_timing.py'),
             str(ROOT / 'examples/session.synthetic.jsonl'),
             '--capture', 'CuaScreenshot', '--bridge-only', *arguments],
            capture_output=True, text=True,
        )

    def test_verified_first_and_returned_frames_share_one_dispatch(self):
        result = self.run_timing('--stable-frame', '2023-11-14T22:13:20.100Z',
                                 '--stable-returned-frame', '2023-11-14T22:13:35.100Z')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['verified_actionable_wait'], {
            'first_frames_epoch_ms': [1700000000100],
            'returned_frames_epoch_ms': [],
            'sample_count': 1,
            'idle_lower_bound_ms': 18000,
        })

    def test_verified_returned_frame_uses_its_own_delay(self):
        result = self.run_timing('--stable-returned-frame', '2023-11-14T22:13:35.100Z')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['verified_actionable_wait'], {
            'first_frames_epoch_ms': [],
            'returned_frames_epoch_ms': [1700000015100],
            'sample_count': 1,
            'idle_lower_bound_ms': 3000,
        })

    def test_unpaired_or_empty_verified_frame_is_an_error(self):
        for option, timestamp, message in (
            ('--stable-frame', '2023-11-14T22:13:35.100Z', 'requested first frame'),
            ('--stable-returned-frame', '2023-11-14T22:13:20.100Z', 'requested returned frame'),
            ('--stable-returned-frame', '', 'invalid timestamp value'),
        ):
            with self.subTest(option=option, timestamp=timestamp):
                result = self.run_timing(option, timestamp)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(message, result.stderr)

    def test_verified_wait_is_opt_in(self):
        result = self.run_timing()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(json.loads(result.stdout)), {'sample_count', 'samples', 'medians_ms'})

    def test_only_independent_cua_capture_counts(self):
        import tempfile
        code = 'await window.getScreenshot(); nodeRepl.write(Date.now());'
        calls = [(code, False), (code + ' await window.click(100, 100);', False), (code, True)]
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / 'session.jsonl'
            rows = []
            for script, is_error in calls:
                rows.append({'payload': {'type': 'item_completed', 'started_at_ms': 10, 'completed_at_ms': 11,
                                         'item': {'type': 'McpToolCall', 'server': 'cua_repl', 'tool': 'js',
                                                  'status': 'completed', 'arguments': {'code': script},
                                                  'result': {'isError': is_error}}}})
            log.write_text('\n'.join(map(json.dumps, rows)), encoding='utf-8')
            tools = [event[3] for event in codex_timing.events(log, 16)]
        self.assertEqual(tools, ['CuaScreenshot', 'js', 'js'])

    def test_ack_old_wrong_command_not_counted(self):
        output = 'ack 1700000000000 keys|W|80\ndispatch 1700000000100 keys|M|80\nack 1700000000200 keys|W|80'
        dispatches, paired = codex_timing.bridge_receipts(output, 1700000000000, 1700000001000)
        self.assertEqual(dispatches, [1700000000100])
        self.assertEqual(paired, 0)


if __name__ == '__main__':
    unittest.main()
