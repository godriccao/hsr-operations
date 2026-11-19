import copy
import importlib.util
import json
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
        rows = list(codex_timing.samples(codex_timing.events(ROOT / 'examples/session.synthetic.jsonl', 16)))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['observation_frames'], 2)
        self.assertEqual(rows[0]['first_frame_to_first_bridge_dispatch_ms'], 18000)
        self.assertEqual(rows[0]['frame_to_first_bridge_dispatch_ms'], 3000)
        self.assertEqual(rows[0]['bridge_dispatches'], 2)
        self.assertEqual(rows[0]['bridge_acknowledgements'], 2)

    def test_ack_old_wrong_command_not_counted(self):
        output = 'ack 1700000000000 keys|W|80\ndispatch 1700000000100 keys|M|80\nack 1700000000200 keys|W|80'
        dispatches, paired = codex_timing.bridge_receipts(output, 1700000000000, 1700000001000)
        self.assertEqual(dispatches, [1700000000100])
        self.assertEqual(paired, 0)


if __name__ == '__main__':
    unittest.main()
