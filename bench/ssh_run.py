"""Laptop transport. It does not write on the handheld."""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from bench.report import render_report


def build_command(target, identity):
    return [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=15",
        "-i", identity,
        target,
        "python3", "-B", "-",
    ]


def failure_document():
    return {
        "observations": {
            "ssh": {"status": "unavailable", "reason": "ssh_failed"}
        },
        "samples": [],
    }


def _stamp(now):
    return now.strftime("%Y%m%dT%H%M%SZ")


def _store(outdir, now, document):
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = _stamp(now)
    json_path = outdir / (stamp + ".json")
    md_path = outdir / (stamp + ".md")
    json_path.write_text(
        json.dumps(document, sort_keys=True) + "\n",
        encoding="utf-8")
    md_path.write_text(render_report(document), encoding="utf-8")


def _fail(outdir, now):
    _store(Path(outdir), now, failure_document())
    sys.stderr.write("ssh failed\n")
    return 2


def _safe_target(value):
    if not isinstance(value, str) or value == "":
        return False
    if value.startswith("-"):
        return False
    return not any(ch in value for ch in "\n\r\x00 \t")


def _safe_identity(value):
    if not isinstance(value, str) or value.strip() == "":
        return False
    if value.startswith("-"):
        return False
    return not any(ch in value for ch in "\n\r\x00")


def run_remote(source, target, identity, outdir, runner, now):
    if not _safe_target(target) or not _safe_identity(identity):
        return _fail(outdir, now)
    command = build_command(target, identity)
    try:
        completed = runner(
            command,
            input=source.encode("utf-8"),
            timeout=60,
            capture_output=True,
        )
    except (subprocess.TimeoutExpired, OSError):
        return _fail(outdir, now)
    if getattr(completed, "returncode", 1) != 0:
        return _fail(outdir, now)
    try:
        payload = completed.stdout
        document = json.loads(payload.decode("utf-8"))
    except (AttributeError, UnicodeError, json.JSONDecodeError, TypeError):
        return _fail(outdir, now)
    if isinstance(document, dict):
        observations = document.get("observations")
        samples = document.get("samples")
    else:
        observations = None
        samples = None
    if not isinstance(observations, dict) or not isinstance(samples, list):
        return _fail(outdir, now)
    _store(Path(outdir), now, document)
    return 0


def probe_source():
    path = Path(__file__).with_name("probe.py")
    return path.read_text(encoding="utf-8")


def main(environ=None, runner=None, outdir=None):
    if environ is None:
        environ = os.environ
    if runner is None:
        runner = subprocess.run
    if outdir is None:
        outdir = Path("bench-results")
    return run_remote(
        probe_source(),
        environ.get("ANBERNIC_SSH_TARGET", ""),
        environ.get("ANBERNIC_SSH_IDENTITY", ""),
        Path(outdir),
        runner,
        datetime.now(timezone.utc),
    )


if __name__ == "__main__":
    sys.exit(main())
