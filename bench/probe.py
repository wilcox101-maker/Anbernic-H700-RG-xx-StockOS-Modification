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
