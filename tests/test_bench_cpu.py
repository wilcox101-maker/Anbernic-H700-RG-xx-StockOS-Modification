import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bench.probe import run_integer_loop, stop_reason


class Clock:
    def __init__(self, values):
        self.values = list(values)
        self.last = 0.0

    def __call__(self):
        if self.values:
            self.last = self.values.pop(0)
        return self.last


class CpuTests(unittest.TestCase):
    def test_three_repeats_finish(self):
        sample = run_integer_loop(Clock([0.0]), {"reason": None}, 20.0)
        self.assertEqual(sample["status"], "ok")
        self.assertEqual(len(sample["repeats"]), 3)
        self.assertEqual(sample["repeats"][0]["iterations"], 200000)
        self.assertIn("seconds_median", sample)

    def test_deadline_skips_later_repeats(self):
        clock = Clock([0.0, 3.0])
        sample = run_integer_loop(clock, {"reason": None}, 20.0)
        self.assertEqual(sample["status"], "skipped")
        self.assertEqual(sample["reason"], "timeout")
        self.assertEqual(len(sample["repeats"]), 1)
        self.assertEqual(sample["repeats"][0]["iterations"], 0)
        self.assertNotIn("seconds_min", sample)

    def test_cancel_wins_over_timeout(self):
        clock = Clock([0.0, 3.0])
        sample = run_integer_loop(
            clock, {"reason": "cancelled"}, 20.0)
        self.assertEqual(sample["reason"], "cancelled")

    def test_stop_order_is_cancel_then_budget_then_timeout(self):
        self.assertEqual(
            stop_reason({"reason": "cancelled"}, Clock([100.0]), 0.0, 0.0),
            "cancelled")
        self.assertEqual(
            stop_reason({"reason": None}, Clock([20.0]), 20.0, 100.0),
            "probe_budget")
        self.assertEqual(
            stop_reason({"reason": None}, Clock([3.0]), 20.0, 2.0),
            "timeout")
        self.assertIsNone(
            stop_reason({"reason": None}, Clock([1.0]), 20.0, 2.0))


if __name__ == "__main__":
    unittest.main()
