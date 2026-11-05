import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bench.probe import run_probe
from bench.report import compare, render_report
from tests.bench_fixture import write_happy
from tests.test_bench_cpu import Clock


def document():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        write_happy(root)
        found = run_probe(
            root, Clock([0.0]), bytearray, {"reason": None})
    found["observations"]["python"] = {
        "status": "ok",
        "value": "3.10.0 fixture",
    }
    for key in found["observations"]["mounts"]:
        found["observations"]["mounts"][key] = {
            "status": "ok",
            "total_bytes": 4096,
            "free_bytes": 2048,
        }
    return found


class ReportTests(unittest.TestCase):
    def test_single_run_has_no_delta(self):
        text = render_report(document())
        self.assertIn("## Hardware observations", text)
        self.assertIn("## Performance timings", text)
        self.assertIn("Python-level synthetic", text)
        self.assertIn("zero physical writes", text)
        self.assertIn("reason `single_run`", text)
        self.assertNotIn("faster", text)
        self.assertTrue(all(len(line) <= 80 for line in text.splitlines()))

    def test_equal_keys_print_delta(self):
        left = document()
        right = document()
        right["samples"][0]["seconds_min"] = (
            left["samples"][0]["seconds_min"] + 0.25)
        found = compare(left, right)
        self.assertEqual(found["status"], "ok")
        self.assertEqual(
            found["deltas"][0]["seconds_min_right_minus_left"], 0.25)
        text = render_report(left, right)
        self.assertIn("0.25", text)

    def test_sample_not_ok_omits_numeric_delta(self):
        left = document()
        right = document()
        right["samples"][0]["status"] = "skipped"
        right["samples"][0]["reason"] = "timeout"
        found = compare(left, right)
        self.assertEqual(found["status"], "ok")
        self.assertEqual(found["deltas"][0]["reason"], "sample_not_ok")
        self.assertNotIn(
            "seconds_min_right_minus_left", found["deltas"][0])
        text = render_report(left, right)
        self.assertIn("sample_not_ok", text)
        self.assertTrue(all(len(line) <= 80 for line in text.splitlines()))

    def test_match_key_not_ok_names_the_key(self):
        left = document()
        right = document()
        right["observations"]["os_date"] = {
            "status": "unsupported", "reason": "not_eight_digits"}
        found = compare(left, right)
        self.assertEqual(found["reason"], "match_key_not_ok")
        self.assertEqual(found["key"], "os_date")
        self.assertNotIn("deltas", found)

    def test_first_mismatch_blocks_deltas(self):
        left = document()
        right = document()
        right["observations"]["board"] = {
            "status": "ok", "value": "RG28xx"}
        found = compare(left, right)
        self.assertEqual(found["reason"], "match_key_mismatch")
        self.assertEqual(found["key"], "board")
        self.assertNotIn("deltas", found)

    def test_checked_in_fixture_matches_renderer(self):
        path = Path(ROOT, "tests/fixtures/bench/sample-report.md")
        self.assertEqual(
            path.read_text(encoding="utf-8"),
            render_report(document()))

    def test_long_kernel_wraps(self):
        doc = document()
        doc["observations"]["kernel"] = {
            "status": "ok", "value": "K" * 200}
        text = render_report(doc)
        self.assertTrue(all(len(line) <= 80 for line in text.splitlines()))


if __name__ == "__main__":
    unittest.main()
