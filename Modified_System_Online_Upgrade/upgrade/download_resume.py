"""Choose how a ranged download may be written.

A partial file is appended only when the response is a 206 range that starts
at the byte already on disk. A 200, or a 206 that contains the whole file,
replaces the partial file. Any other range or length is refused.
"""

import re

_RANGE = re.compile(r"bytes (\d+)-(\d+)/(\d+|\*)")


def _header(headers, name):
    if not headers:
        return None
    for key, value in headers.items():
        if str(key).lower() == name:
            return value
    return None


def _length(value):
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return "invalid"
    if number < 0:
        return "invalid"
    return number


def plan_resume(file_size, status_code, headers):
    """Return ``(mode, kept_bytes, body_size)`` or None when nothing may be written.

    ``kept_bytes`` is the valid prefix already on disk. ``body_size`` is the
    number of bytes the response claims to add. ``mode`` is ``wb`` to replace
    the file or ``ab`` to append.
    """
    if file_size < 0:
        file_size = 0
    length = _length(_header(headers, "content-length"))
    if length == "invalid":
        return None
    if file_size == 0 or status_code == 200:
        return ("wb", 0, 0 if length is None else length)
    if status_code != 206:
        return None
    match = _RANGE.fullmatch(str(_header(headers, "content-range") or "").strip())
    if match is None:
        return None
    start = int(match.group(1))
    end = int(match.group(2))
    total = None if match.group(3) == "*" else int(match.group(3))
    span = end - start + 1
    if span <= 0:
        return None
    if length is not None and length != span:
        return None
    body_size = span if length is None else length
    if start == file_size and (total is None or start <= total):
        return ("ab", file_size, body_size)
    if start == 0 and total is not None and body_size == total:
        return ("wb", 0, body_size)
    return None


def plan_retry(file_size, status_code, headers):
    """Return an append plan, or None when a retry body must not be written.

    The file is already open. Only a 206 that continues at ``file_size`` may
    be appended. A 200, or any other range, is refused.
    """
    plan = plan_resume(file_size, status_code, headers)
    if plan is None or plan[0] != "ab" or plan[1] != file_size:
        return None
    return plan
