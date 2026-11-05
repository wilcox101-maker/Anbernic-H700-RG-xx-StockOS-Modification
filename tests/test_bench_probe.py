import io
import json
import signal
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bench import probe
from tests.bench_fixture import write_happy
from tests.test_bench_cpu import Clock


class ProbeTests(unittest.TestCase):
    def test_cancel_skips_both_and_does_not_allocate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_happy(root)
            calls = []
            found = probe.run_probe(
                root, Clock([0.0]),
                lambda size: calls.append(size),
                {"reason": "cancelled"})
        self.assertEqual(found["samples"][0]["reason"], "cancelled")
        self.assertEqual(found["samples"][1]["reason"], "cancelled")
        self.assertEqual(calls, [])
        self.assertEqual(
            [item["id"] for item in found["samples"]],
            ["python_integer_loop", "python_page_touch"])

    def test_timeout_does_not_start_memory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_happy(root)
            calls = []
            found = probe.run_probe(
                root, Clock([0.0, 0.0, 3.0]),
                lambda size: calls.append(size),
                {"reason": None})
        self.assertEqual(found["samples"][0]["reason"], "timeout")
        self.assertEqual(found["samples"][1]["reason"], "timeout")
        self.assertEqual(calls, [])

    def test_low_memory_still_runs_cpu(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_happy(root)
            mem = Path(root, "proc/meminfo")
            mem.write_text(
                "MemTotal: 524288 kB\n"
                "MemAvailable: 1024 kB\n"
                "MemFree: 1024 kB\n",
                encoding="utf-8")
            calls = []
            found = probe.run_probe(
                root, Clock([0.0]),
                lambda size: calls.append(size),
                {"reason": None})
        self.assertEqual(found["samples"][0]["status"], "ok")
        self.assertEqual(
            found["samples"][1]["reason"], "low_available_memory")
        self.assertEqual(calls, [])

    def test_source_has_no_write_api(self):
        text = Path(ROOT, "bench/probe.py").read_text(encoding="utf-8")
        for banned in (
            "write_text", "subprocess", "socket", "systemctl",
            "PYTHONPYCACHEPREFIX",
        ):
            self.assertNotIn(banned, text)

    def test_main_prints_one_json_object(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_happy(root)
            previous = (
                signal.getsignal(signal.SIGINT),
                signal.getsignal(signal.SIGTERM),
            )
            stdout = io.StringIO()
            real = sys.stdout
            sys.stdout = stdout
            try:
                code = probe.main(str(root))
            finally:
                sys.stdout = real
                signal.signal(signal.SIGINT, previous[0])
                signal.signal(signal.SIGTERM, previous[1])
        self.assertEqual(code, 0)
        document = json.loads(stdout.getvalue())
        self.assertIn("observations", document)
        self.assertTrue(stdout.getvalue().endswith("\n"))

    def test_handler_exit_codes(self):
        stop = {}
        probe.handle_signal(stop, signal.SIGINT, None)
        self.assertEqual(stop["exit"], 130)
        probe.handle_signal(stop, signal.SIGTERM, None)
        self.assertEqual(stop["reason"], "cancelled")
        self.assertEqual(stop["exit"], 143)


if __name__ == "__main__":
    unittest.main()
