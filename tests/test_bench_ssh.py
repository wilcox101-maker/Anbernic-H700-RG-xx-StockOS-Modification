import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bench.ssh_run import build_command, run_remote


class Completed:
    def __init__(self, code, stdout):
        self.returncode = code
        self.stdout = stdout


class SshTests(unittest.TestCase):
    def test_command_uses_stdin_and_no_bytecode(self):
        command = build_command("user@example.invalid", "id_test")
        self.assertEqual(command[-3:], ["python3", "-B", "-"])
        self.assertIn("BatchMode=yes", command)
        self.assertNotIn("StrictHostKeyChecking=no", command)
        self.assertNotIn("172.16.3.175", command)

    def test_missing_target_does_not_call_runner(self):
        calls = []

        def runner(*args, **kwargs):
            calls.append(kwargs)
            return Completed(0, b"{}")

        with tempfile.TemporaryDirectory() as temporary:
            err = Path(temporary, "err.txt")
            real_err = sys.stderr
            sys.stderr = err.open("w", encoding="utf-8")
            try:
                code = run_remote(
                    "print(1)\n", "", "id_test", Path(temporary),
                    runner, datetime(2026, 11, 5, tzinfo=timezone.utc))
            finally:
                sys.stderr.close()
                sys.stderr = real_err
            stderr = err.read_text(encoding="utf-8")
            text = Path(temporary, "20261105T000000Z.json").read_text(
                encoding="utf-8")
        self.assertEqual(code, 2)
        self.assertEqual(calls, [])
        self.assertEqual(stderr, "ssh failed\n")
        self.assertNotIn("id_test", stderr)
        self.assertEqual(
            json.loads(text)["observations"]["ssh"]["reason"],
            "ssh_failed")

    def test_runner_gets_source_and_local_files(self):
        seen = {}

        def runner(command, input, timeout, capture_output):
            seen["command"] = command
            seen["input"] = input
            seen["timeout"] = timeout
            body = json.dumps({
                "observations": {"python": {
                    "status": "ok", "value": "3.10"}},
                "samples": [],
            }).encode("utf-8")
            return Completed(0, body)

        with tempfile.TemporaryDirectory() as temporary:
            err = Path(temporary, "err.txt")
            real_err = sys.stderr
            sys.stderr = err.open("w", encoding="utf-8")
            try:
                code = run_remote(
                    "SOURCE", "user@example.invalid", "SECRET-ID",
                    Path(temporary), runner,
                    datetime(2026, 11, 5, 20, 15, tzinfo=timezone.utc))
            finally:
                sys.stderr.close()
                sys.stderr = real_err
            stderr = err.read_text(encoding="utf-8")
            saved = Path(temporary, "20261105T201500Z.json").read_text(
                encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertEqual(seen["timeout"], 60)
        self.assertEqual(seen["input"], b"SOURCE")
        self.assertIn("SECRET-ID", seen["command"])
        self.assertNotIn("SECRET-ID", stderr)
        self.assertNotIn("example.invalid", stderr)
        self.assertIn("3.10", saved)

    def test_timeout_is_ssh_failed(self):
        def runner(command, input, timeout, capture_output):
            raise subprocess.TimeoutExpired(command, timeout)

        with tempfile.TemporaryDirectory() as temporary:
            err = Path(temporary, "err.txt")
            real_err = sys.stderr
            sys.stderr = err.open("w", encoding="utf-8")
            try:
                code = run_remote(
                    "SOURCE", "user@example.invalid", "id_test",
                    Path(temporary), runner,
                    datetime(2026, 11, 5, tzinfo=timezone.utc))
            finally:
                sys.stderr.close()
                sys.stderr = real_err
            stderr = err.read_text(encoding="utf-8")
            text = Path(temporary, "20261105T000000Z.json").read_text(
                encoding="utf-8")
        self.assertEqual(code, 2)
        self.assertEqual(stderr, "ssh failed\n")
        self.assertNotIn("example.invalid", stderr)
        self.assertNotIn("id_test", stderr)
        self.assertEqual(
            json.loads(text)["observations"]["ssh"]["reason"],
            "ssh_failed")

    def test_nonzero_and_bad_json_are_ssh_failed(self):
        def nonzero(command, input, timeout, capture_output):
            return Completed(255, b"denied")

        def bad_json(command, input, timeout, capture_output):
            return Completed(0, b"not-json")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            err = root / "err.txt"
            real_err = sys.stderr
            sys.stderr = err.open("w", encoding="utf-8")
            try:
                code = run_remote(
                    "SOURCE", "user@example.invalid", "SECRET-ID",
                    root / "a", nonzero,
                    datetime(2026, 11, 5, tzinfo=timezone.utc))
                code_json = run_remote(
                    "SOURCE", "user@example.invalid", "SECRET-ID",
                    root / "b", bad_json,
                    datetime(2026, 11, 5, tzinfo=timezone.utc))
            finally:
                sys.stderr.close()
                sys.stderr = real_err
            stderr = err.read_text(encoding="utf-8")
            failed = json.loads(
                (root / "a" / "20261105T000000Z.json").read_text(
                    encoding="utf-8"))
            broken = json.loads(
                (root / "b" / "20261105T000000Z.json").read_text(
                    encoding="utf-8"))
        self.assertEqual(code, 2)
        self.assertEqual(code_json, 2)
        self.assertEqual(
            failed["observations"]["ssh"]["reason"], "ssh_failed")
        self.assertEqual(
            broken["observations"]["ssh"]["reason"], "ssh_failed")
        self.assertNotIn("SECRET-ID", stderr)
        self.assertNotIn("example.invalid", stderr)
        self.assertEqual(stderr, "ssh failed\nssh failed\n")

    def test_option_like_target_does_not_call_runner(self):
        calls = []

        def runner(*args, **kwargs):
            calls.append(args)
            return Completed(0, b"{}")

        with tempfile.TemporaryDirectory() as temporary:
            err = Path(temporary, "err.txt")
            real_err = sys.stderr
            sys.stderr = err.open("w", encoding="utf-8")
            try:
                code = run_remote(
                    "SOURCE", "-oStrictHostKeyChecking=no", "SECRET-ID",
                    Path(temporary), runner,
                    datetime(2026, 11, 5, tzinfo=timezone.utc))
            finally:
                sys.stderr.close()
                sys.stderr = real_err
            stderr = err.read_text(encoding="utf-8")
        self.assertEqual(code, 2)
        self.assertEqual(calls, [])
        self.assertEqual(stderr, "ssh failed\n")
        self.assertNotIn("StrictHostKeyChecking", stderr)
        self.assertNotIn("SECRET-ID", stderr)

    def test_unsafe_identity_does_not_call_runner(self):
        calls = []

        def runner(*args, **kwargs):
            calls.append(args)
            return Completed(0, b"{}")

        with tempfile.TemporaryDirectory() as temporary:
            err = Path(temporary, "err.txt")
            real_err = sys.stderr
            sys.stderr = err.open("w", encoding="utf-8")
            try:
                dashed = run_remote(
                    "SOURCE", "user@example.invalid",
                    "-oProxyCommand=echo",
                    Path(temporary) / "a", runner,
                    datetime(2026, 11, 5, tzinfo=timezone.utc))
                newline = run_remote(
                    "SOURCE", "user@example.invalid", "id\nsecret",
                    Path(temporary) / "b", runner,
                    datetime(2026, 11, 5, tzinfo=timezone.utc))
            finally:
                sys.stderr.close()
                sys.stderr = real_err
            stderr = err.read_text(encoding="utf-8")
        self.assertEqual(dashed, 2)
        self.assertEqual(newline, 2)
        self.assertEqual(calls, [])
        self.assertEqual(stderr, "ssh failed\nssh failed\n")
        self.assertNotIn("ProxyCommand", stderr)
        self.assertNotIn("example.invalid", stderr)

    def test_missing_ssh_binary_is_ssh_failed(self):
        def runner(command, input, timeout, capture_output):
            raise FileNotFoundError(command[0])

        with tempfile.TemporaryDirectory() as temporary:
            err = Path(temporary, "err.txt")
            real_err = sys.stderr
            sys.stderr = err.open("w", encoding="utf-8")
            try:
                code = run_remote(
                    "SOURCE", "user@example.invalid", "SECRET-ID",
                    Path(temporary), runner,
                    datetime(2026, 11, 5, tzinfo=timezone.utc))
            finally:
                sys.stderr.close()
                sys.stderr = real_err
            stderr = err.read_text(encoding="utf-8")
            text = Path(temporary, "20261105T000000Z.json").read_text(
                encoding="utf-8")
        self.assertEqual(code, 2)
        self.assertEqual(stderr, "ssh failed\n")
        self.assertNotIn("SECRET-ID", stderr)
        self.assertEqual(
            json.loads(text)["observations"]["ssh"]["reason"],
            "ssh_failed")

    def test_main_without_config_does_not_call_runner(self):
        from bench.ssh_run import main
        calls = []

        def runner(*args, **kwargs):
            calls.append(args)
            raise AssertionError("ssh should not run")

        with tempfile.TemporaryDirectory() as temporary:
            err = Path(temporary, "err.txt")
            real_err = sys.stderr
            sys.stderr = err.open("w", encoding="utf-8")
            try:
                code = main(
                    environ={}, runner=runner, outdir=Path(temporary))
            finally:
                sys.stderr.close()
                sys.stderr = real_err
            stderr = err.read_text(encoding="utf-8")
            saved = list(Path(temporary).glob("*.json"))
        self.assertEqual(code, 2)
        self.assertEqual(calls, [])
        self.assertEqual(stderr, "ssh failed\n")
        self.assertEqual(len(saved), 1)


if __name__ == "__main__":
    unittest.main()
