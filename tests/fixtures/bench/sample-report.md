# RG34xxSP probe report

## Hardware observations

- `python`: `3.10.0 fixture`
- `board`: `RG34xxSP`
- `os_date`: `20251105`
- `kernel`: `Linux version test`
- `cpu_model`: `TestCPU`
- `cpu_count`: `1`
- `mem_total_kib`: `524288`
- `mem_available_kib`: `262144`
- `mem_free_kib`: `131072`
- `cpu_freq_khz`: `1008000 kHz (1008 MHz)`
- `cpu_governor`: `ondemand`
- `thermal_millic`: `45000`

- `/mnt/mmc`: total `4096`, free `2048`
- `/mnt/sdcard`: total `4096`, free `2048`
- `/tmp`: total `4096`, free `2048`
- `/mnt/vendor`: total `4096`, free `2048`
- `/mnt/mod`: total `4096`, free `2048`

## Performance timings

These timings are Python-level synthetic samples.
They are not native CPU performance, DRAM bandwidth,
or emulator FPS.
They do not claim zero physical writes.
The OS may log SSH, update atime, or use swap.

- `python_integer_loop`: status `ok`, seconds min `0.0`, median `0.0`, max `0.0`
- `python_page_touch`: status `ok`, seconds min `0.0`, median `0.0`, max `0.0`

## Comparison

Status `skipped`, reason `single_run`.
