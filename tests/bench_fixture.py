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
