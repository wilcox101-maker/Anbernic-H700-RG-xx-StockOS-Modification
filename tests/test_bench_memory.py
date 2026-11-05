import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bench.probe import ok, bad, run_page_touch
from tests.test_bench_cpu import Clock


class MemoryTests(unittest.TestCase):
    def test_skip_when_available_missing(self):
        calls = []

        def allocate(size):
            calls.append(size)
            return bytearray(size)

        sample = run_page_touch(
            bad("unavailable", "missing_key"),
            Clock([0.0]), {"reason": None}, 20.0, allocate)
        self.assertEqual(sample["reason"], "memavailable_unavailable")
        self.assertEqual(calls, [])

    def test_skip_when_below_32_mib(self):
        calls = []

        def allocate(size):
            calls.append(size)
            return bytearray(size)

        sample = run_page_touch(
            ok(1024), Clock([0.0]), {"reason": None}, 20.0, allocate)
        self.assertEqual(sample["reason"], "low_available_memory")
        self.assertEqual(calls, [])

    def test_one_allocation_when_headroom_exists(self):
        calls = []

        def allocate(size):
            calls.append(size)
            return bytearray(size)

        sample = run_page_touch(
            ok(262144), Clock([0.0]), {"reason": None}, 20.0, allocate)
        self.assertEqual(sample["status"], "ok")
        self.assertEqual(calls, [8388608])
        self.assertEqual(sample["passes"][0]["bytes_touched"], 2048)
        self.assertNotIn("bandwidth", sample)

    def test_cancel_does_not_allocate(self):
        calls = []

        def allocate(size):
            calls.append(size)
            return bytearray(size)

        sample = run_page_touch(
            ok(262144), Clock([0.0]),
            {"reason": "cancelled"}, 20.0, allocate)
        self.assertEqual(sample["reason"], "cancelled")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
