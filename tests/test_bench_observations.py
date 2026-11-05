import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.bench_fixture import write_happy
from bench.probe import collect_observations


class ObservationTests(unittest.TestCase):
    def test_happy_fixture_is_ok(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_happy(root)
            before = sorted(p.relative_to(root).as_posix()
                            for p in root.rglob("*"))
            found = collect_observations(root)
            after = sorted(p.relative_to(root).as_posix()
                           for p in root.rglob("*"))
        self.assertEqual(before, after)
        self.assertEqual(found["board"]["value"], "RG34xxSP")
        self.assertEqual(found["os_date"]["value"], "20251105")
        self.assertEqual(found["cpu_model"]["value"], "TestCPU")
        self.assertEqual(found["cpu_count"]["value"], 1)
        self.assertEqual(found["mem_total_kib"]["value"], 524288)
        self.assertEqual(found["mem_available_kib"]["value"], 262144)
        self.assertEqual(found["cpu_freq_khz"]["value"], 1008000)
        self.assertEqual(found["cpu_governor"]["value"], "ondemand")
        self.assertEqual(found["thermal_millic"]["value"], 45000)
        self.assertEqual(found["mounts"]["/mnt/mmc"]["status"], "ok")
        self.assertNotIn("\n", found["python"]["value"])

    def test_missing_board_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_happy(root)
            Path(root, "mnt/vendor/oem/board.ini").unlink()
            found = collect_observations(root)
        self.assertEqual(found["board"]["status"], "unavailable")
        self.assertEqual(found["board"]["reason"], "enoent")
        self.assertNotIn("value", found["board"])

    def test_short_os_date_is_unsupported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_happy(root)
            path = Path(root, "mnt/vendor/oem/version.ini")
            path.write_text("2026\n", encoding="utf-8")
            found = collect_observations(root)
        self.assertEqual(found["os_date"]["status"], "unsupported")
        self.assertEqual(found["os_date"]["reason"], "not_eight_digits")

    def test_cpu_model_missing_is_unsupported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_happy(root)
            path = Path(root, "proc/cpuinfo")
            path.write_text("processor : 0\n", encoding="utf-8")
            found = collect_observations(root)
        self.assertEqual(found["cpu_model"]["status"], "unsupported")
        self.assertEqual(
            found["cpu_model"]["reason"], "cpu_model_missing")
        self.assertEqual(found["cpu_count"]["value"], 1)

    def test_missing_memavailable_key(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_happy(root)
            path = Path(root, "proc/meminfo")
            path.write_text(
                "MemTotal: 524288 kB\nMemFree: 10 kB\n",
                encoding="utf-8")
            found = collect_observations(root)
        self.assertEqual(
            found["mem_available_kib"]["reason"], "missing_key")
        encoded = json.dumps(found)
        self.assertNotIn("bandwidth", encoded)


if __name__ == "__main__":
    unittest.main()
