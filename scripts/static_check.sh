#!/bin/bash
# Syntax and document checks only. This script does not execute app or flash scripts.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

echo "compileall"
python3 -m compileall -q .
find . -type d -name '__pycache__' -prune -exec rm -rf {} +

echo "bash -n"
checked=0
while IFS= read -r -d '' file; do
    shebang="$(head -n 1 "$file" || true)"
    case "$shebang" in
        '#!/bin/bash'|'#!/usr/bin/env bash')
            bash -n "$file"
            checked=$((checked + 1))
            ;;
        '#!/bin/zsh'|'#!/usr/bin/env zsh')
            echo "skip zsh (not parsed by bash): $file"
            ;;
        *)
            echo "skip unexpected shebang in $file: $shebang" >&2
            exit 1
            ;;
    esac
done < <(find . -type f \( -name '*.sh' -o -path './Modify_System_Tools/mod_tools/mod_tools' \) -print0)

if [ "$checked" -lt 1 ]; then
    echo "no bash scripts were checked" >&2
    exit 1
fi
echo "bash scripts checked: $checked"

echo "json"
python3 - << 'PY'
import json
import pathlib
import sys

root = pathlib.Path(".")
failed = 0
count = 0
for path in root.rglob("*.json"):
    if ".git" in path.parts:
        continue
    count += 1
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        failed += 1
        print(f"{path}: {exc}", file=sys.stderr)
if count == 0:
    print("no json files found", file=sys.stderr)
    sys.exit(1)
if failed:
    sys.exit(1)
print(f"json files parsed: {count}")
PY

echo "docs"
python3 - << 'PY'
import pathlib
import sys

readme = pathlib.Path("README.md").read_text(encoding="utf-8")
bezel = pathlib.Path("Bezel_Custom_Manager/README.md").read_text(encoding="utf-8")
settings = pathlib.Path("Modify_System_Settings/README.md").read_text(encoding="utf-8")
errors = []

def forbid(text, needle, label):
    if needle in text:
        errors.append(label)

forbid(readme, "conv=fdata", "README still documents conv=fdata")
forbid(readme, "mkfs.fat", "README still tells you to format the whole device")
forbid(readme, "releases/download/20260605/flash_dd", "README still links the 20260605 flash-script assets")
forbid(readme, "RGG35xx", "README still has the RGG35xx typo")
forbid(readme, "RG35xx-P-RG35xx-H-Modification", "README still links the old wiki repo name")
if "flash_dd_with_gpt.sh" not in readme or "flash_dd_with_gpt.MacOS.sh" not in readme:
    errors.append("README no longer points at the in-repo flash scripts")
if "Anbernic-H700-RG-xx-StockOS-Modification/wiki" not in readme:
    errors.append("README wiki link is missing")

forbid(
    bezel,
    "Alternatively, delete `/mnt/mod/ctrl/configs/system.cfg`",
    "Bezel README still says to delete system.cfg",
)
if "/mnt/mmc/anbernic/custom/" not in bezel:
    errors.append("Bezel README no longer names the per-system cfg path")

if settings.rstrip().endswith("```"):
    errors.append("Settings README still ends with a stray fence")

if errors:
    print("\n".join(errors), file=sys.stderr)
    sys.exit(1)
print("doc guards passed")
PY

echo "static checks passed"
