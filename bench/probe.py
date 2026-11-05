"""RAM and CPU probe. It never writes a file."""

from __future__ import annotations

import json
import os
import signal
import statistics
import sys
import time
from pathlib import Path

MOUNT_KEYS = (
    "/mnt/mmc",
    "/mnt/sdcard",
    "/tmp",
    "/mnt/vendor",
    "/mnt/mod",
)
ITERATIONS = 200000
CHECK_EVERY = 10000
REPEATS = 3
DEADLINE_SECONDS = 2.0


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
    early = stop_reason(stop, clock, budget_end, None)
    if early:
        return _skipped_memory(early)
    buf = None
    passes = []
    try:
        buf = allocate(ALLOCATION_BYTES)
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
        if buf is not None:
            del buf
    return _sample("python_page_touch", "passes", passes)


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


if __name__ == "__main__":
    sys.exit(main())
