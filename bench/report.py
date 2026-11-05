"""Laptop report. Comparison never runs on the handheld."""

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
        one = left["observations"].get(key, {})
        two = right["observations"].get(key, {})
        if one.get("status") != "ok" or two.get("status") != "ok":
            return {
                "status": "skipped",
                "reason": "match_key_not_ok",
                "key": key,
            }
        if one.get("value") != two.get("value"):
            return {
                "status": "skipped",
                "reason": "match_key_mismatch",
                "key": key,
            }
    deltas = []
    pairs = zip(left["samples"], right["samples"])
    for one, two in pairs:
        if one.get("status") != "ok" or two.get("status") != "ok":
            deltas.append({
                "id": one["id"],
                "status": "skipped",
                "reason": "sample_not_ok",
            })
            continue
        deltas.append({
            "id": one["id"],
            "status": "ok",
            "seconds_min_right_minus_left": (
                two["seconds_min"] - one["seconds_min"]
            ),
        })
    return {"status": "ok", "deltas": deltas}


def _wrap(text, width=80):
    lines = []
    for raw in text.split("\n"):
        line = raw
        if line == "":
            lines.append("")
            continue
        while len(line) > width:
            cut = line.rfind(" ", 0, width + 1)
            if cut <= 0:
                cut = width
            lines.append(line[:cut].rstrip())
            line = line[cut:].lstrip()
        lines.append(line)
    return lines


def _value_line(key, obs):
    if obs.get("status") != "ok":
        return "- `%s`: status `%s`, reason `%s`" % (
            key, obs.get("status"), obs.get("reason"))
    value = obs["value"]
    if key == "cpu_freq_khz":
        shown = "%s kHz (%s MHz)" % (value, int(value) // 1000)
    else:
        shown = value
    return "- `%s`: `%s`" % (key, shown)


def _mount_line(key, obs):
    if obs.get("status") != "ok":
        return "- `%s`: status `%s`, reason `%s`" % (
            key, obs.get("status"), obs.get("reason"))
    return "- `%s`: total `%s`, free `%s`" % (
        key, obs["total_bytes"], obs["free_bytes"])


def _sample_line(sample):
    if sample.get("status") == "ok":
        return (
            "- `%s`: status `ok`, seconds min `%s`, "
            "median `%s`, max `%s`"
        ) % (
            sample["id"],
            sample["seconds_min"],
            sample["seconds_median"],
            sample["seconds_max"],
        )
    return "- `%s`: status `skipped`, reason `%s`" % (
        sample["id"], sample.get("reason"))


def _comparison(left, right):
    if right is None:
        return "Status `skipped`, reason `single_run`."
    found = compare(left, right)
    if found["status"] != "ok":
        return "Status `skipped`, reason `%s`, key `%s`." % (
            found["reason"], found["key"])
    lines = []
    for delta in found["deltas"]:
        if delta["status"] != "ok":
            lines.append(
                "- `%s`: status `skipped`, reason `%s`" % (
                    delta["id"], delta["reason"]))
        else:
            lines.append(
                "- `%s` right minus left `%s`" % (
                    delta["id"],
                    delta["seconds_min_right_minus_left"]))
    return "\n".join(lines)


def render_report(left, right=None):
    parts = [
        "# RG34xxSP probe report",
        "",
        "## Hardware observations",
        "",
    ]
    observations = left["observations"]
    order = (
        "python", "board", "os_date", "kernel", "cpu_model",
        "cpu_count", "mem_total_kib", "mem_available_kib",
        "mem_free_kib", "cpu_freq_khz", "cpu_governor",
        "thermal_millic",
    )
    for key in order:
        parts.append(_value_line(key, observations[key]))
    parts.append("")
    for key, obs in observations["mounts"].items():
        parts.append(_mount_line(key, obs))
    parts.extend([
        "",
        "## Performance timings",
        "",
        "These timings are Python-level synthetic samples.",
        "They are not native CPU performance, DRAM bandwidth,",
        "or emulator FPS.",
        "They do not claim zero physical writes.",
        "The OS may log SSH, update atime, or use swap.",
        "",
    ])
    for sample in left["samples"]:
        parts.append(_sample_line(sample))
    parts.extend([
        "",
        "## Comparison",
        "",
        _comparison(left, right),
        "",
    ])
    text = "\n".join(_wrap("\n".join(parts)))
    if not text.endswith("\n"):
        text += "\n"
    return text
