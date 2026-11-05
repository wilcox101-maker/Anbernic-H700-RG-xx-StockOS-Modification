# RG34xxSP benchmark design

This file is the approved spec, including the non-volatile constraint.
It does not add a probe, a test, or a device command. Earlier audit
permission does not approve the harness. The plan is a separate
document, and the harness is still not implemented.

SSH on the RG34XXSP is already working. The approved shape is one
standard-library probe, aimed at a short Python CPU loop and a bounded
Python memory sample. An existing SSH client is only the transport. The
probe prints one JSON document on stdout. The laptop stores that JSON and
renders Markdown. The handheld run is RAM and CPU only. It makes no
intentional persistent write: no result file, no upload, no install, no
temporary file, and no bytecode file.

## What this is not

These samples are Python-level synthetic timings. They are not native CPU
throughput, not DRAM bandwidth, and not emulator frame rates. Hardware
lines (board, OS date, kernel, CPU identity, memory counters, mounts,
frequency, thermal) are observations. They are not performance results.
Nothing here is full benchmark coverage.

Version 1 has no storage test. The probe and the SSH command must not
write under `/tmp`, `/mnt/mmc`, `/mnt/sdcard`, `/mnt/vendor`, `/mnt/mod`,
or anywhere else on the handheld. They must not flash, install, reboot,
change a service, change a config file, or enable SSH. They must not
embed a host, user, password, or key. The address `172.16.3.175` is
runtime configuration the operator supplies. It is not a default in
source or in tests. The probe does not import `upgrade.py`,
`launcher.py`, or any SDL module.

The operating system may still write. An SSH daemon can append a log,
a read can update atime, and the kernel can page memory to swap. Those
effects are OS-managed. Meeting this spec does not mean zero physical
writes, and the report must not claim that.

## Probe

One Python file, imported nowhere by the apps. It uses only the standard
library: `json`, `os`, `signal`, `sys`, `time`, `statistics`, and
`pathlib`. A `root` argument defaults to `/` on a device and to a fixture
directory in tests. Every read is `root` joined with a relative path. The
probe never opens a path for writing.

Stdout is one UTF-8 JSON object and a trailing newline. There is no other
stdout. Stderr is empty when the object was written. Exit `0` after a
complete object. Exit `2` when the object could not be written. After
`SIGINT`, exit `130`. After `SIGTERM`, exit `143`. Both of those still
print the object first.

## Status values

Every observation and every sample has one of these statuses:

- `ok` means the value was interpreted, or the sample finished inside its
  deadline.
- `unavailable` means the path is missing, `OSError` was raised, or a
  meminfo key is absent. The reason is `enoent`, `oserror`, or
  `missing_key`.
- `unsupported` means the file was read and does not have the shape below.
  The reason is named in that rule.
- `skipped` means a sample was not finished on purpose. Reasons are only
  `cancelled`, `timeout`, `probe_budget`, `memavailable_unavailable`, and
  `low_available_memory`.

An `ok` observation carries `value`. A non-ok observation has `reason`
and no `value`. A `skipped` sample has `reason`. It may record steps or
bytes actually completed. It must not invent `seconds_min` when no
repeat finished.

## Hardware observations

These keys are always present. They are not timings. A path that cannot
be read is `unavailable` (`enoent` or `oserror`). `unsupported` is only
for a file that was read and fails the shape rule.

- `python` is the first line of `sys.version`, always `ok`.
- `board` reads `mnt/vendor/oem/board.ini`. The value is the first line,
  stripped. An empty line is `unsupported`, reason `empty`.
- `os_date` reads `mnt/vendor/oem/version.ini`. The value is the first
  line, stripped, and it must be eight digits. A non-calendar
  eight-digit string is still `ok`. Otherwise `unsupported`, reason
  `not_eight_digits`.
- `kernel` reads `proc/version`. The value is the first line, stripped.
  An empty line is `unsupported`, reason `empty`.
- `cpu_model` reads `proc/cpuinfo`. The value is the text after the first
  colon on the last `model name` line, or else the last `Hardware` line,
  stripped. If neither line exists, `unsupported`, reason
  `cpu_model_missing`.
- `cpu_count` is the number of `proc/cpuinfo` lines whose stripped text
  starts with `processor`. Zero is `unsupported`, reason
  `no_processor_lines`. A missing cpuinfo file makes both CPU keys
  `unavailable`, not `unsupported`.
- `mem_total_kib`, `mem_available_kib`, and `mem_free_kib` read
  `proc/meminfo` lines `MemTotal:`, `MemAvailable:`, and `MemFree:`. The
  value is the integer on that line. The line must contain `kB`, or the
  status is `unsupported`, reason `unit_not_kib`. A missing line is
  `unavailable`, reason `missing_key`. If the file itself cannot be
  read, all three are `unavailable` with the I/O reason.
- `cpu_freq_khz` reads
  `sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq`. The stripped
  file must be one integer, kept in kHz. Otherwise `unsupported`, reason
  `not_integer`.
- `cpu_governor` reads
  `sys/devices/system/cpu/cpu0/cpufreq/scaling_governor`. The stripped
  file must be non-empty. Otherwise `unsupported`, reason `empty`.
- `thermal_millic` reads `sys/class/thermal/thermal_zone0/temp`. The
  stripped file must be one integer, kept in millidegrees. Otherwise
  `unsupported`, reason `not_integer`.
- `mounts` uses `statvfs` and stores `total_bytes` and `free_bytes`.

`mounts` always has `/mnt/mmc`, `/mnt/sdcard`, `/tmp`, `/mnt/vendor`, and
`/mnt/mod`. A missing path is `unavailable`, reason `enoent`. A present
path uses `statvfs` and status `ok` with `total_bytes` and `free_bytes`.
If `statvfs` raises `OSError`, that mount is `unavailable`, reason
`oserror`.
Frequency and thermal are metadata. If those sysfs nodes are absent, the
status is `unavailable` and the samples still run. The numbers are not
converted into a claim that the chip is idle or hot.

`board.ini` and `version.ini` are recorded as read. This spec does not
guess the lines on the user's card.

## Performance samples

Samples live in a `samples` array, separate from `observations`. Each
object has `id`, `class` (`performance`), `level` (`python_synthetic`),
and `status`. The JSON must not contain a field named `bandwidth`,
`mb_per_second`, or `fps`.

`samples` always contains `python_integer_loop` and then
`python_page_touch`. The probe budget is 20 seconds from the injected
clock at start (default `time.perf_counter`). At each loop check the
first matching reason wins: `cancelled` if the signal flag is set, else
`probe_budget` if the 20 second budget is spent, else `timeout` if that
repeat or pass deadline is spent. The signal handler only sets a flag.
No later sample starts after any of those reasons. The later sample
is `skipped` with that same reason, and its allocator is not called.

### `python_integer_loop`

This is a CPython integer loop, not a native CPU benchmark.

- Three repeats, each aimed at 200000 steps.
- Body, starting from `x = 1`: `x = (x * 1103515245 + 12345) & 0x7fffffff`.
- Every 10000 steps, compare the injected clock with a 2.0 second
  deadline for that repeat.
- A repeat that crosses the deadline stops, status `skipped`, reason
  `timeout`, and records the steps completed. Later repeats do not start.
- A finished repeat is `ok` and stores `iterations` and `seconds`.
- `seconds_min`, `seconds_median`, and `seconds_max` use only `ok`
  repeats. The sample is `ok` only when all three repeats are `ok`.
  Otherwise its status is the first skip reason. If no repeat is `ok`,
  the three aggregate fields are absent.

### `python_page_touch`

This allocates and touches memory from Python. It is not a RAM-bandwidth
test and it does not call `mlock`, change swap, or allocate more than the
cap.

- Cap is one `bytearray` of 8388608 bytes (8 MiB).
- If `mem_available_kib` is not `ok`, do not allocate. Sample status
  `skipped`, reason `memavailable_unavailable`.
- If available bytes are below four times the cap (32 MiB), do not
  allocate. Sample status `skipped`, reason `low_available_memory`.
- Otherwise each pass writes `offset & 0xff` at every 4096-byte stride.
  Up to three passes. The deadline is 2.0 seconds per pass, checked
  every 256 strides.
- An `ok` pass records `bytes_touched` and `seconds`.
  `bytes_touched` is the number of byte stores finished in that pass,
  one store per stride, not a span and not a rate. Aggregate
  `seconds_min`, `seconds_median`, and `seconds_max` follow the CPU
  rule. The allocator argument defaults to `bytearray` and is called
  with `8388608` only when the sample proceeds. `finally` drops the
  buffer before JSON is printed.

`MemTotal` is only an observation. The sample size does not grow with it.

## Comparison

The laptop compares two saved JSON objects. It does not compare on the
device. One JSON file produces no comparison; the report says `skipped`,
reason `single_run`.

A delta is printed only when every match key is `ok` on both sides and
the values are equal. The keys are `python`, `board`, `os_date`,
`cpu_model`, `cpu_count`, `cpu_freq_khz`, and `cpu_governor`. Thermal is
shown beside each run and is not a match key. Comparison reasons
(`single_run`, `match_key_not_ok`, `match_key_mismatch`,
`sample_not_ok`) belong to the report, not to a sample. If a match
key is not `ok`, comparison is `skipped`, reason `match_key_not_ok`,
and no delta is printed. Unequal values use reason
`match_key_mismatch` and name the first key. When the keys match,
each sample that is `ok` on both sides prints `seconds_min` of the
right file minus `seconds_min` of the left
file. A sample that is not `ok` on either side prints no delta and
`skipped`, reason `sample_not_ok`. No ranking and no faster-device
sentence.

## SSH transport

SSH stays outside the probe. The later laptop command refuses to run
unless `ANBERNIC_SSH_TARGET` is set to `user@host` and
`ANBERNIC_SSH_IDENTITY` is a path the operator already has. Neither value
is given a default, committed, or logged in full. The command is
`ssh -o BatchMode=yes -o ConnectTimeout=15` with that identity and
target, running remote `python3 -B -`, and the probe source is the
remote stdin. `-B` stops CPython from writing a bytecode file. The
command does not set `PYTHONPYCACHEPREFIX`. It does not copy a file
to the handheld.
`BatchMode` means a missing key fails instead of asking for a password.
Host-key checking stays at the SSH default. There is no
`StrictHostKeyChecking=no`, no `systemctl`, and no credential file in
git.

The laptop writes `<outdir>/<utc-stamp>.json` and the Markdown beside it.
`<outdir>` is an argument, default `bench-results` in the current
directory, and that directory is gitignored when the command exists. A
failed SSH client produces a local JSON record with observation `ssh`
status `unavailable`, reason `ssh_failed`, and no invented device fields.
The laptop stops the SSH client after 60 seconds. The probe's own 20
second budget stops a runaway loop if that client limit fails.

No connection is made while this spec is under review.

## Laptop tests

Tests are `unittest`, with no new dependency. They call the probe in
process against a temporary fixture root. They must not read the laptop
`/proc` or `/sys`, and they must not open a socket. The fixture is a
directory tree of the paths listed above. The probe takes `clock`
(default `time.perf_counter`) and `allocate` (default `bytearray`) so a
deadline test returns immediately.

Required cases:

- RG34xxSP fixture with proc, sysfs, and oem files: observations `ok`,
  both samples `ok`, and no file under the fixture changes.
- Missing `board.ini`: `board` is `unavailable`, samples still follow
  the memory rule.
- `version.ini` value `2026`: `os_date` is `unsupported`.
- cpuinfo without `model name` or `Hardware`: `cpu_model` is
  `unsupported`.
- meminfo without `MemAvailable`: the memory sample is `skipped` and
  `allocate` is not called.
- `MemAvailable` below 32 MiB: memory sample `skipped`, CPU sample still
  runs.
- Clock that jumps past 2 seconds: the current sample is `skipped`,
  reason `timeout`.
- Cancel flag already set: samples are `skipped`, reason `cancelled`,
  and the JSON is still complete.
- Two JSON objects with equal match keys: the report includes numeric
  deltas. One mismatched key: comparison `skipped` and no delta.
- Rendered Markdown for the fixture report has zero markdownlint
  findings under the same defaults as the README.

## Markdown and CI

The report sections, in order, are hardware observations, performance
timings, and comparison. The timings section states the Python-synthetic
limit in the first paragraph, and it states that the run does not
claim zero physical writes. Frequency in Markdown may also show
integer-divided MHz next to the raw kHz. Thermal stays in millidegrees.

`npm run lint:readme` runs `markdownlint-cli2` 0.23.2 (`markdownlint`
0.41.1) with library defaults and no rule file. It lints `README.md`,
`docs/superpowers/specs/**/*.md`, and `docs/superpowers/plans/**/*.md`.
When fixture Markdown is added, that file is included in the same
command. No rule is disabled to clear a warning.

## Implementation gate

The design is approved only with the non-volatile constraint above.
The next document is the implementation plan. The probe, the laptop
runner, the fixture tests, and the `bench-results` gitignore are still
not in this tree. Do not connect to the handheld to review either
document.
