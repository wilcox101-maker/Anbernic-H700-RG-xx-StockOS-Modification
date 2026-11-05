# RG34xxSP Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standard-library probe that prints one JSON document
for a short Python CPU loop and a bounded Python memory sample, plus
a laptop report and a mocked SSH runner that stores results only on
the laptop.

**Architecture:** `bench/probe.py` reads a fixture or handheld root
and returns observations plus two samples. `bench/report.py` renders
Markdown and compares two JSON objects. `bench/ssh_run.py` pipes the
probe source to remote `python3 -B -` and writes files only under a
local directory. Tests call the functions in process. They do not
open a socket or the laptop `/proc`.

**Tech Stack:** CPython standard library, `unittest`, existing
`markdownlint-cli2` 0.23.2 with library defaults. No pytest. No new
package.

## Global Constraints

- RAM and CPU only. No storage sample.
- No intentional persistent write on the handheld: no result file, no
  upload, no install, no temporary file, no bytecode file, no service
  change, no config change, no firmware write, and no kernel write.
- Remote argv is `python3 -B -`. Do not set `PYTHONPYCACHEPREFIX`.
- Do not claim zero physical writes. SSH logs, read atime, and swap
  are OS-managed and may still happen.
- `172.16.3.175` is the operator's runtime address. It is not a
  default in source or tests. No user, password, or key is assumed.
- Samples stay `python_integer_loop` (200000 steps, 3 repeats, 2.0
  second deadline, check every 10000) and `python_page_touch` (8388608
  bytes, stride 4096, 3 passes, 2.0 second deadline, check every 256
  strides, skip unless `MemAvailable` is at least 33554432 bytes).
- Probe budget is 20 seconds. Stop order is `cancelled`, then
  `probe_budget`, then `timeout`.
- JSON forbids keys `bandwidth`, `mb_per_second`, and `fps`.
- Laptop tests use a fixture root. Do not read the laptop `/proc` or
  `/sys`, and do not connect to the handheld.
- Markdown uses markdownlint 0.41.1 defaults. Do not disable a rule.

## File structure

- Create `bench/__init__.py`. Empty marker so `bench.probe` imports.
- Create `bench/probe.py`. Observations, both samples, stdout, exit
  codes. Read-only.
- Create `bench/report.py`. Markdown and comparison.
- Create `bench/ssh_run.py`. Laptop SSH command and local files.
- Create `tests/bench_fixture.py`. Happy-path fixture writer.
- Create `tests/test_bench_observations.py`.
- Create `tests/test_bench_cpu.py`.
- Create `tests/test_bench_memory.py`.
- Create `tests/test_bench_probe.py`.
- Create `tests/test_bench_report.py`.
- Create `tests/test_bench_ssh.py`.
- Create `tests/fixtures/bench/sample-report.md`. Checked-in report.
- Modify `.gitignore`. Ignore `bench-results/`.
- Modify `package.json`. Lint the checked-in report too.

---

### Task 1: Hardware observations

**Files:**

- Create: `bench/__init__.py`
- Create: `bench/probe.py`
- Create: `tests/bench_fixture.py`
- Test: `tests/test_bench_observations.py`

**Interfaces:**

- Consumes: nothing from earlier tasks.
- Produces: `read_text(root, relative) -> tuple`,
  `collect_observations(root) -> dict`, and
  `write_happy(root) -> None`. An ok observation is
  `{"status": "ok", "value": ...}`. Any other observation is
  `{"status": "...", "reason": str}` and has no `value`.
  `collect_observations` always returns `python`, `board`,
  `os_date`, `kernel`, `cpu_model`, `cpu_count`,
  `mem_total_kib`, `mem_available_kib`, `mem_free_kib`,
  `cpu_freq_khz`, `cpu_governor`, `thermal_millic`, and `mounts`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_bench_observations -v`

Expected: FAIL with `ModuleNotFoundError` for `tests.bench_fixture`
or `bench.probe`.

- [ ] **Step 3: Write the minimal implementation**

`bench/__init__.py` is an empty file.

`tests/bench_fixture.py`:

```python
from pathlib import Path


def write_happy(root):
    files = {
        "mnt/vendor/oem/board.ini": "RG34xxSP\n",
        "mnt/vendor/oem/version.ini": "20251105\n",
        "proc/version": "Linux version test\n",
        "proc/cpuinfo": "processor : 0\nmodel name : TestCPU\n",
        "proc/meminfo": (
            "MemTotal: 524288 kB\n"
            "MemAvailable: 262144 kB\n"
            "MemFree: 131072 kB\n"
        ),
        "sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq": (
            "1008000\n"
        ),
        "sys/devices/system/cpu/cpu0/cpufreq/scaling_governor": (
            "ondemand\n"
        ),
        "sys/class/thermal/thermal_zone0/temp": "45000\n",
    }
    for relative, text in files.items():
        path = Path(root).joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    for name in (
        "mnt/mmc", "mnt/sdcard", "tmp", "mnt/vendor", "mnt/mod"
    ):
        Path(root).joinpath(*name.split("/")).mkdir(
            parents=True, exist_ok=True)
```

`bench/probe.py` for this task:

```python
"""RAM and CPU probe. It never writes a file."""

from __future__ import annotations

import os
import sys
from pathlib import Path

MOUNT_KEYS = (
    "/mnt/mmc",
    "/mnt/sdcard",
    "/tmp",
    "/mnt/vendor",
    "/mnt/mod",
)


def read_text(root, relative):
    path = Path(root).joinpath(*relative.split("/"))
    try:
        return path.read_text(encoding="utf-8"), None
    except FileNotFoundError:
        return None, "enoent"
    except OSError:
        return None, "oserror"


def ok(value):
    return {"status": "ok", "value": value}


def bad(status, reason):
    return {"status": status, "reason": reason}


def _line(text, reason):
    if reason:
        return bad("unavailable", reason)
    value = ""
    if text.splitlines():
        value = text.splitlines()[0].strip()
    if value == "":
        return bad("unsupported", "empty")
    return ok(value)


def _date(text, reason):
    if reason:
        return bad("unavailable", reason)
    value = ""
    if text.splitlines():
        value = text.splitlines()[0].strip()
    if len(value) == 8 and value.isdigit():
        return ok(value)
    return bad("unsupported", "not_eight_digits")


def _cpu(text, reason):
    if reason:
        missing = bad("unavailable", reason)
        return missing, missing
    model = None
    hardware = None
    count = 0
    for line in text.splitlines():
        if line.strip().startswith("processor"):
            count += 1
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip() == "model name":
            model = value.strip()
        elif key.strip() == "Hardware":
            hardware = value.strip()
    chosen = model or hardware
    if chosen:
        model_obs = ok(chosen)
    else:
        model_obs = bad("unsupported", "cpu_model_missing")
    if count:
        count_obs = ok(count)
    else:
        count_obs = bad("unsupported", "no_processor_lines")
    return model_obs, count_obs


def _mem(text, reason, label):
    if reason:
        return bad("unavailable", reason)
    prefix = label + ":"
    for line in text.splitlines():
        if not line.startswith(prefix):
            continue
        parts = line.split()
        if "kB" not in parts or len(parts) < 2:
            return bad("unsupported", "unit_not_kib")
        if not parts[1].isdigit():
            return bad("unsupported", "unit_not_kib")
        return ok(int(parts[1]))
    return bad("unavailable", "missing_key")


def _integer(text, reason):
    if reason:
        return bad("unavailable", reason)
    token = text.strip()
    digits = token[1:] if token.startswith("-") else token
    if digits.isdigit() and digits != "":
        return ok(int(token))
    return bad("unsupported", "not_integer")


def _mounts(root):
    mounts = {}
    for key in MOUNT_KEYS:
        path = Path(root).joinpath(*key[1:].split("/"))
        if not path.exists():
            mounts[key] = bad("unavailable", "enoent")
            continue
        try:
            usage = os.statvfs(path)
        except OSError:
            mounts[key] = bad("unavailable", "oserror")
            continue
        mounts[key] = {
            "status": "ok",
            "total_bytes": usage.f_frsize * usage.f_blocks,
            "free_bytes": usage.f_frsize * usage.f_bavail,
        }
    return mounts


def collect_observations(root):
    board, board_reason = read_text(root, "mnt/vendor/oem/board.ini")
    date, date_reason = read_text(root, "mnt/vendor/oem/version.ini")
    kernel, kernel_reason = read_text(root, "proc/version")
    cpu, cpu_reason = read_text(root, "proc/cpuinfo")
    mem, mem_reason = read_text(root, "proc/meminfo")
    freq, freq_reason = read_text(
        root, "sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
    gov, gov_reason = read_text(
        root, "sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    thermal, thermal_reason = read_text(
        root, "sys/class/thermal/thermal_zone0/temp")
    model, count = _cpu(cpu, cpu_reason)
    return {
        "python": ok(sys.version.splitlines()[0]),
        "board": _line(board, board_reason),
        "os_date": _date(date, date_reason),
        "kernel": _line(kernel, kernel_reason),
        "cpu_model": model,
        "cpu_count": count,
        "mem_total_kib": _mem(mem, mem_reason, "MemTotal"),
        "mem_available_kib": _mem(mem, mem_reason, "MemAvailable"),
        "mem_free_kib": _mem(mem, mem_reason, "MemFree"),
        "cpu_freq_khz": _integer(freq, freq_reason),
        "cpu_governor": _line(gov, gov_reason),
        "thermal_millic": _integer(thermal, thermal_reason),
        "mounts": _mounts(root),
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest tests.test_bench_observations -v`

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add bench/__init__.py bench/probe.py tests/bench_fixture.py \
  tests/test_bench_observations.py
git commit -m "Read handheld facts from a fixture root."
```

---

### Task 2: Python integer loop

**Files:**

- Modify: `bench/probe.py`
- Test: `tests/test_bench_cpu.py`

**Interfaces:**

- Consumes: `ok` and `bad` from `bench/probe.py`.
- Produces: `stop_reason(stop, clock, budget_end, deadline)`
  returns `str` or `None`. `run_integer_loop(clock, stop, budget_end)`
  returns a dict with `id` `python_integer_loop`, `class`
  `performance`, `level` `python_synthetic`, `status`, and
  `repeats`. Each repeat has `status` and `iterations`. An `ok`
  repeat also has `seconds`. `seconds_min`, `seconds_median`, and
  `seconds_max` exist only when at least one repeat is `ok`.

- [ ] **Step 1: Write the failing test**

```python
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bench.probe import run_integer_loop


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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_bench_cpu -v`

Expected: FAIL with `ImportError` for `run_integer_loop`.

- [ ] **Step 3: Add the loop to `bench/probe.py`**

```python
import statistics

ITERATIONS = 200000
CHECK_EVERY = 10000
REPEATS = 3
DEADLINE_SECONDS = 2.0


def stop_reason(stop, clock, budget_end, deadline):
    if stop and stop.get("reason") == "cancelled":
        return "cancelled"
    now = clock()
    if now >= budget_end:
        return "probe_budget"
    if deadline is not None and now >= deadline:
        return "timeout"
    return None


def _aggregates(parts):
    good = [part["seconds"] for part in parts if part["status"] == "ok"]
    if not good:
        return {}
    return {
        "seconds_min": min(good),
        "seconds_median": statistics.median(good),
        "seconds_max": max(good),
    }


def _sample(name, part_key, parts):
    sample = {
        "id": name,
        "class": "performance",
        "level": "python_synthetic",
        part_key: parts,
    }
    sample.update(_aggregates(parts))
    if parts and all(part["status"] == "ok" for part in parts):
        sample["status"] = "ok"
    else:
        sample["status"] = "skipped"
        for part in parts:
            if part["status"] != "ok":
                sample["reason"] = part["reason"]
                break
        if "reason" not in sample:
            sample["reason"] = "timeout"
    return sample


def run_integer_loop(clock, stop, budget_end):
    repeats = []
    for _ in range(REPEATS):
        start = clock()
        deadline = start + DEADLINE_SECONDS
        steps = 0
        value = 1
        reason = None
        while steps < ITERATIONS:
            if steps % CHECK_EVERY == 0:
                reason = stop_reason(
                    stop, clock, budget_end, deadline)
                if reason:
                    break
            value = (value * 1103515245 + 12345) & 0x7FFFFFFF
            steps += 1
        repeat = {"iterations": steps}
        if reason:
            repeat["status"] = "skipped"
            repeat["reason"] = reason
            repeats.append(repeat)
            break
        repeat["status"] = "ok"
        repeat["seconds"] = clock() - start
        repeats.append(repeat)
    return _sample("python_integer_loop", "repeats", repeats)
```

Keep the `value` update. It is the workload. Do not delete it as unused.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest tests.test_bench_cpu tests.test_bench_observations -v`

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add bench/probe.py tests/test_bench_cpu.py
git commit -m "Time a bounded Python integer loop."
```

---

### Task 3: Bounded memory sample

**Files:**

- Modify: `bench/probe.py`
- Test: `tests/test_bench_memory.py`

**Interfaces:**

- Consumes: `stop_reason`, `_sample`, `DEADLINE_SECONDS`.
- Produces: `run_page_touch` with arguments `mem_available`,
  `clock`, `stop`, `budget_end`, and `allocate=bytearray`.
  The dict `id` is `python_page_touch` and it has `passes`.
  `allocate` is called with `8388608` only when the sample
  proceeds. `bytes_touched` counts byte stores.

- [ ] **Step 1: Write the failing test**

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_bench_memory -v`

Expected: FAIL with `ImportError` for `run_page_touch`.

- [ ] **Step 3: Add the memory sample**

```python
ALLOCATION_BYTES = 8388608
STRIDE = 4096
PASSES = 3
STRIDE_CHECK = 256
HEADROOM_BYTES = ALLOCATION_BYTES * 4


def _skipped_memory(reason):
    return {
        "id": "python_page_touch",
        "class": "performance",
        "level": "python_synthetic",
        "status": "skipped",
        "reason": reason,
    }


def run_page_touch(mem_available, clock, stop, budget_end,
                   allocate=bytearray):
    if mem_available.get("status") != "ok":
        return _skipped_memory("memavailable_unavailable")
    if mem_available["value"] * 1024 < HEADROOM_BYTES:
        return _skipped_memory("low_available_memory")
    buf = allocate(ALLOCATION_BYTES)
    passes = []
    try:
        for _ in range(PASSES):
            start = clock()
            deadline = start + DEADLINE_SECONDS
            touched = 0
            offset = 0
            reason = None
            while offset < ALLOCATION_BYTES:
                if touched % STRIDE_CHECK == 0:
                    reason = stop_reason(
                        stop, clock, budget_end, deadline)
                    if reason:
                        break
                buf[offset] = offset & 0xFF
                offset += STRIDE
                touched += 1
            one = {"bytes_touched": touched}
            if reason:
                one["status"] = "skipped"
                one["reason"] = reason
                passes.append(one)
                break
            one["status"] = "ok"
            one["seconds"] = clock() - start
            passes.append(one)
    finally:
        del buf
    return _sample("python_page_touch", "passes", passes)
```

`touched % STRIDE_CHECK == 0` fires on the first store and every 256
stores. `bytes_touched` is that store count. A full pass stores
`8388608 / 4096` bytes, which is 2048.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest tests.test_bench_memory -v`

Expected: `OK`. The headroom case allocates one 8 MiB buffer on the
laptop and releases it. It does not touch a handheld.

- [ ] **Step 5: Commit**

```bash
git add bench/probe.py tests/test_bench_memory.py
git commit -m "Touch one bounded Python buffer."
```

---

### Task 4: Probe document, stdout, and stop flags

**Files:**

- Modify: `bench/probe.py`
- Test: `tests/test_bench_probe.py`

**Interfaces:**

- Consumes: `collect_observations`, `run_integer_loop`, `run_page_touch`.
- Produces: `run_probe(root="/", clock=None, allocate=bytearray, stop=None)`
  returns a dict. `handle_signal(stop, signum, frame)` returns
  `None`. `main(root="/")` returns `int`. `samples` is the CPU
  sample, then the memory sample. A non-ok CPU sample copies its
  `reason` onto the memory sample and does not call `allocate`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_bench_probe -v`

Expected: FAIL with `AttributeError` for `run_probe`.

- [ ] **Step 3: Add assembly and stdout**

```python
import json
import signal
import time


def run_probe(root="/", clock=None, allocate=bytearray, stop=None):
    if clock is None:
        clock = time.perf_counter
    if stop is None:
        stop = {"reason": None}
    observations = collect_observations(root)
    budget_end = clock() + 20.0
    cpu = run_integer_loop(clock, stop, budget_end)
    if cpu["status"] != "ok":
        memory = {
            "id": "python_page_touch",
            "class": "performance",
            "level": "python_synthetic",
            "status": "skipped",
            "reason": cpu["reason"],
        }
    else:
        memory = run_page_touch(
            observations["mem_available_kib"],
            clock, stop, budget_end, allocate)
    return {"observations": observations, "samples": [cpu, memory]}


def handle_signal(stop, signum, _frame):
    stop["reason"] = "cancelled"
    if signum == signal.SIGINT:
        stop["exit"] = 130
    else:
        stop["exit"] = 143


def main(root="/"):
    stop = {"reason": None}
    signal.signal(
        signal.SIGINT, lambda s, f: handle_signal(stop, s, f))
    signal.signal(
        signal.SIGTERM, lambda s, f: handle_signal(stop, s, f))
    try:
        document = run_probe(root=root, stop=stop)
        sys.stdout.write(json.dumps(document, sort_keys=True))
        sys.stdout.write("\n")
    except Exception:
        sys.stderr.write("probe failed\n")
        return 2
    return stop.get("exit", 0)
```

`sort_keys=True` keeps samples in insertion order and sorts dict keys.
Do not add a `bandwidth` field.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest tests.test_bench_probe -v`

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add bench/probe.py tests/test_bench_probe.py
git commit -m "Assemble the probe JSON on stdout."
```

---

### Task 5: Markdown report and comparison

**Files:**

- Create: `bench/report.py`
- Test: `tests/test_bench_report.py`

**Interfaces:**

- Consumes: a probe document from `run_probe`.
- Produces: `compare(left, right)` returns a dict.
  `render_report(document, other=None)` returns `str`. Match keys,
  in order, are `python`, `board`, `os_date`, `cpu_model`,
  `cpu_count`, `cpu_freq_khz`, and `cpu_governor`. A skipped
  compare has `reason` and `key`. An ok compare has `deltas`.
  Each delta has `seconds_min_right_minus_left` or `reason`
  `sample_not_ok`.

- [ ] **Step 1: Write the failing test**

```python
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
        return run_probe(
            root, Clock([0.0]), bytearray, {"reason": None})


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

    def test_first_mismatch_blocks_deltas(self):
        left = document()
        right = document()
        right["observations"]["board"] = {
            "status": "ok", "value": "RG28xx"}
        found = compare(left, right)
        self.assertEqual(found["reason"], "match_key_mismatch")
        self.assertEqual(found["key"], "board")
        self.assertNotIn("deltas", found)

    def test_long_kernel_wraps(self):
        doc = document()
        doc["observations"]["kernel"] = {
            "status": "ok", "value": "K" * 200}
        text = render_report(doc)
        self.assertTrue(all(len(line) <= 80 for line in text.splitlines()))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_bench_report -v`

Expected: FAIL with `ModuleNotFoundError` for `bench.report`.

- [ ] **Step 3: Write `bench/report.py`**

```python
"""Laptop Markdown. No handheld writes."""

MATCH_KEYS = (
    "python",
    "board",
    "os_date",
    "cpu_model",
    "cpu_count",
    "cpu_freq_khz",
    "cpu_governor",
)


def compare(left, right):
    for key in MATCH_KEYS:
        left_obs = left["observations"][key]
        right_obs = right["observations"][key]
        if left_obs.get("status") != "ok" or right_obs.get("status") != "ok":
            return {
                "status": "skipped",
                "reason": "match_key_not_ok",
                "key": key,
            }
        if left_obs.get("value") != right_obs.get("value"):
            return {
                "status": "skipped",
                "reason": "match_key_mismatch",
                "key": key,
            }
    deltas = []
    pairs = zip(left["samples"], right["samples"])
    for left_sample, right_sample in pairs:
        if left_sample["status"] == "ok" and right_sample["status"] == "ok":
            deltas.append({
                "id": left_sample["id"],
                "seconds_min_right_minus_left": (
                    right_sample["seconds_min"]
                    - left_sample["seconds_min"]
                ),
            })
        else:
            deltas.append({
                "id": left_sample["id"],
                "status": "skipped",
                "reason": "sample_not_ok",
            })
    return {"status": "ok", "deltas": deltas}


def _chunks(text, width=72):
    flat = " ".join(str(text).splitlines())
    pieces = []
    while flat:
        pieces.append(flat[:width])
        flat = flat[width:]
    return pieces or [""]


def _obs_lines(key, obs):
    lines = ["- `%s`: %s" % (key, obs["status"]), ""]
    if obs["status"] == "ok" and key == "cpu_freq_khz":
        mhz = int(obs["value"]) // 1000
        shown = "%s kHz (%s MHz)" % (obs["value"], mhz)
        lines.insert(1, "")
        for piece in _chunks(shown):
            lines.insert(-1, "  `%s`" % piece)
        return lines
    if obs["status"] == "ok" and "value" in obs:
        for piece in _chunks(obs["value"]):
            lines.insert(-1, "  `%s`" % piece)
        return lines
    if "reason" in obs:
        lines.insert(-1, "  reason `%s`" % obs["reason"])
    return lines


def render_report(document, other=None):
    lines = ["# RG34xxSP probe report", "", "## Hardware observations", ""]
    for key, obs in document["observations"].items():
        if key == "mounts":
            lines.extend(["- `mounts`", ""])
            for path, mount in obs.items():
                lines.extend(_obs_lines(path, mount))
            continue
        lines.extend(_obs_lines(key, obs))
    lines.extend([
        "## Performance timings",
        "",
        "These timings are Python-level synthetic samples. They",
        "are not native CPU throughput, not DRAM bandwidth, and",
        "not emulator frame rates. They do not claim zero",
        "physical writes. The OS may log SSH, update atime, or",
        "use swap.",
        "",
    ])
    for sample in document["samples"]:
        lines.extend([
            "### %s" % sample["id"],
            "",
            "Status `%s`." % sample["status"],
            "",
        ])
        if "seconds_min" in sample:
            lines.append("`seconds_min` `%s`." % sample["seconds_min"])
            lines.append("")
    lines.extend(["## Comparison", ""])
    if other is None:
        lines.append("Status `skipped`, reason `single_run`.")
    else:
        found = compare(document, other)
        if found["status"] != "ok":
            lines.append(
                "Status `skipped`, reason `%s`, key `%s`."
                % (found["reason"], found["key"]))
        else:
            for delta in found["deltas"]:
                if "seconds_min_right_minus_left" in delta:
                    lines.append(
                        "- `%s` right minus left `%s`"
                        % (delta["id"],
                           delta["seconds_min_right_minus_left"]))
                else:
                    lines.append(
                        "- `%s` skipped, reason `sample_not_ok`"
                        % delta["id"])
    lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest tests.test_bench_report -v`

Expected: `OK`, and every rendered line has length at most 80.

- [ ] **Step 5: Commit**

```bash
git add bench/report.py tests/test_bench_report.py
git commit -m "Render observations apart from synthetic timings."
```

---

### Task 6: Lint the checked-in report

**Files:**

- Create: `tests/fixtures/bench/sample-report.md`
- Modify: `package.json`
- Test: `tests/test_bench_report.py`

**Interfaces:**

- Consumes: `render_report` and `write_happy`.
- Produces: a fixture report with zero markdownlint findings. The npm
  script lints `tests/fixtures/bench/**/*.md` with the same defaults.

- [ ] **Step 1: Write the failing lint check**

Append this test to `tests/test_bench_report.py`:

```python
    def test_checked_in_report_matches_renderer(self):
        doc = document()
        text = render_report(doc)
        path = ROOT / "tests/fixtures/bench/sample-report.md"
        self.assertEqual(path.read_text(encoding="utf-8"), text)
```

Generate the file once from that same `document()` call while the
clock is `Clock([0.0])`, so `seconds_min` is `0.0`. Commit the bytes
the renderer prints. Do not hand-edit a second copy.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_bench_report -v`

Expected: FAIL with `FileNotFoundError`.

- [ ] **Step 3: Add the fixture and the lint path**

Write `tests/fixtures/bench/sample-report.md` with the renderer
output. In `package.json`, add one final argument to the
`lint:readme` command:

```text
tests/fixtures/bench/**/*.md
```

Keep the README, spec, and plan arguments. Quote this glob the
same way.

- [ ] **Step 4: Run the test and the linter**

Run: `python3 -m unittest tests.test_bench_report -v`

Expected: `OK`.

Run: `npm run lint:readme`

Expected: `Summary: 0 issues` for README, the spec, the plan, and
`tests/fixtures/bench/sample-report.md`.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/bench/sample-report.md tests/test_bench_report.py \
  package.json
git commit -m "Lint the checked-in probe report."
```

---

### Task 7: Laptop SSH runner

**Files:**

- Create: `bench/ssh_run.py`
- Modify: `.gitignore`
- Test: `tests/test_bench_ssh.py`

**Interfaces:**

- Consumes: `render_report`.
- Produces: `build_command(target, identity)` returns a list.
  `failure_document()` returns a dict.
  `run_remote(source, target, identity, outdir, runner, now)`
  returns `int`. Missing target or identity does not call
  `runner`. The command is `ssh`, `-o`, `BatchMode=yes`, `-o`,
  `ConnectTimeout=15`, `-i`, identity, target, `python3`, `-B`,
  `-`. `runner` is called with `input` bytes and `timeout=60`.
  Results go to `outdir/<stamp>.json` and `.md`. Stderr is
  `ssh failed\n` or empty. It never contains the target or the
  identity.

- [ ] **Step 1: Write the failing test**

```python
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
            code = run_remote(
                "print(1)\n", "", "id_test", Path(temporary),
                runner, datetime(2026, 11, 5, tzinfo=timezone.utc))
            text = Path(temporary, "20261105T000000Z.json").read_text(
                encoding="utf-8")
        self.assertEqual(code, 2)
        self.assertEqual(calls, [])
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
            code = run_remote(
                "SOURCE", "user@example.invalid", "id_test",
                Path(temporary), runner,
                datetime(2026, 11, 5, tzinfo=timezone.utc))
            text = Path(temporary, "20261105T000000Z.json").read_text(
                encoding="utf-8")
        self.assertEqual(code, 2)
        self.assertEqual(
            json.loads(text)["observations"]["ssh"]["reason"],
            "ssh_failed")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_bench_ssh -v`

Expected: FAIL with `ModuleNotFoundError` for `bench.ssh_run`.

- [ ] **Step 3: Write the runner and ignore local results**

Add `bench-results/` to `.gitignore`.

`bench/ssh_run.py`:

```python
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


def run_remote(source, target, identity, outdir, runner, now):
    if not target or not identity:
        _store(Path(outdir), now, failure_document())
        sys.stderr.write("ssh failed\n")
        return 2
    command = build_command(target, identity)
    try:
        completed = runner(
            command,
            input=source.encode("utf-8"),
            timeout=60,
            capture_output=True,
        )
    except subprocess.TimeoutExpired:
        _store(Path(outdir), now, failure_document())
        sys.stderr.write("ssh failed\n")
        return 2
    if completed.returncode != 0:
        _store(Path(outdir), now, failure_document())
        sys.stderr.write("ssh failed\n")
        return 2
    document = json.loads(completed.stdout.decode("utf-8"))
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
```

Do not give `ANBERNIC_SSH_TARGET` a default host. Do not call `main`
from the tests. An operator later runs, with a user and key they
already have:

```bash
ANBERNIC_SSH_TARGET=<user>@172.16.3.175 \
  ANBERNIC_SSH_IDENTITY=<existing-key-path> \
  python3 -m bench.ssh_run
```

That command is not part of the test suite and must not be run while
implementing this plan.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest tests.test_bench_ssh -v`

Expected: `OK`. No SSH process is started.

- [ ] **Step 5: Run the whole local gate**

Run: `python3 -m unittest discover -s tests -q`

Expected: the previous 30 tests still report `OK (expected failures=2)`,
plus the new bench tests, with no unexpected failures.

Run: `bash scripts/static_check.sh`

Expected: `static checks passed`.

Run: `npm run lint:readme`

Expected: `0 issues`.

- [ ] **Step 6: Commit**

```bash
git add bench/ssh_run.py tests/test_bench_ssh.py .gitignore
git commit -m "Store SSH probe results only on the laptop."
```

## Spec coverage

- Non-volatile handheld rule, `-B`, and no upload: Task 4 source ban
  and Task 7 command.
- OS log, atime, and swap honesty: Task 5 report paragraph.
- Observations and statuses: Task 1.
- CPU workload and deadlines: Task 2.
- Memory cap, headroom, and `bytes_touched`: Task 3.
- Cancel, timeout, budget, and stdout: Task 4.
- Comparison and Markdown sections: Task 5.
- Fixture markdownlint: Task 6.
- Runtime address and no embedded credentials: Task 7.
- No storage, firmware, kernel, or service work: no task adds them.

## Not in this plan

Do not connect to `172.16.3.175` while executing the tasks. Do not
enable SSH. Do not print a claim of full benchmark coverage or of
zero physical writes.
