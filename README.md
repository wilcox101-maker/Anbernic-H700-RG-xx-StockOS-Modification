# Anbernic H700 Stock OS Modification

Stock OS Modification is a project built on the StockOS of Anbernic, which is enhanced through modifications to achieve a better user experience.

## Supported handheld models
- RG35xx Plus (RG35xx 2024)
- RG35xx H
- RG35xxSP
- RG28xx
- RG40xx H
- RG40xx V
- RGcube XX
- RG34xx
- RG34xx SP
- RG35xx PRO
- RGSP

## Include content
1. Modified Stock OS images that support automatic partition expansion
2. Package files that support lossless upgrades
3. As a template package for customizing system themes
4. Open source resources
5. Other additional tools

## Important tips
### Use imaging software to write the image file to TF1  
- Windows: [Rufus (recommended)](https://rufus.ie/) or [rpi-imager](https://github.com/raspberrypi/rpi-imager/releases)  
- Linux: [rpi-imager (recommended)](https://github.com/raspberrypi/rpi-imager/releases) or [flash_dd_with_gpt.sh](flash_dd_with_gpt.sh)  
- Mac OS: [rpi-imager (recommended)](https://github.com/raspberrypi/rpi-imager/releases) or [flash_dd_with_gpt.MacOS.sh](flash_dd_with_gpt.MacOS.sh)

Those script links are the copies in this repository, so they match the commit you are reading. They are not the files attached to GitHub release `20260605`. Compared with that release:

- The Linux script there accepts a bare device name such as `sdb` and prefixes `/dev/`. The script in this repository asks for a full path such as `/dev/sdb`.
- The macOS script there lists both `.img` and `.IMG`, and its `dd` command does not use `status=progress`. The script in this repository lists `.img` only, and its `dd` command includes `status=progress`.

Raspberry Pi Imager is still the recommended writer. The macOS script in this repository does not repair the GPT.

### When using programs such as BalenaEtcher and DD flash TF on MacOS or Linux systems, automatic partitioning will fail.
   - Solution: https://github.com/cbepx-me/Anbernic-H700-RG-xx-StockOS-Modification/issues/68

## Troubleshooting
### No partitions after flashing with the Linux script
If the card shows no partitions, do not zero the device and do not format it. The conversion name `fdata` is not valid for `dd`, and formatting the whole device does not repair the backup GPT.

Reflash with `./flash_dd_with_gpt.sh` from this repository. When the script asks whether to repair the GPT, accept the prompt. `gdisk` has to be installed (`sudo apt install gdisk`). That step relocates the backup GPT to the end of the card. See https://github.com/cbepx-me/Anbernic-H700-RG-xx-StockOS-Modification/issues/68

The macOS script does not include that repair. On Mac, write the image again with Raspberry Pi Imager.

These notes describe the scripts in this repository. They were checked by reading those scripts and by rejecting the `fdata` conversion on a scratch file. No card was written.


## PortMaster related issues should be raised here:
https://github.com/kai4man/PortMaster-for-StockOS-MOD

### Compatible Games:
[**📋 Check the Working Ports List**](https://docs.google.com/spreadsheets/d/1UlxRCSIfNkZIiCMAgo8eFqKhsIbrLA_1d3lFdVyS4q8/edit?gid=0) - regularly updated spreadsheet with tested games.

## For more information, please visit
https://github.com/cbepx-me/Anbernic-H700-RG-xx-StockOS-Modification/wiki

## Download
### 1. 64-bit Stock OS Mod image:
- RG28xx, RG34xx, RG34xx SP, RGcubexx, RG35xx PRO, RGSP:

https://drive.google.com/drive/folders/1zTtl8n5zpaRsxwIX7ncG-7sgwzf5Aym-?usp=sharing

- RG35xx PLUS (RG35xx 2024), RG35xx H, RG35xx SP, RG40xx H, RG40xx V:

https://drive.google.com/drive/folders/1ilDbBQP8XB4IVQfhnxde8Diu0fQdDPI9?usp=sharing

### 2. 64-bit Stock OS Mod Upgrade Package & other:

https://drive.google.com/drive/folders/1uwCkGX3H-K09pj0VbB6hkS8I0_qhzrGY?usp=sharing

### 3. RG28xx and RG35xx 2024 offline installation of PortMaster:

https://drive.google.com/drive/folders/1JP4g8DuRsBq1LgPPKWBKh6Zt2VMt1EJn?usp=sharing
