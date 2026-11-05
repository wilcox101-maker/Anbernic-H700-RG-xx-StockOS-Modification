# Device-free regression tests

These tests cover three current updater failures. They do not change the updater, do not write to a device, and do not execute `install.sh` or the update shell scripts.

Run them from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

No extra packages are required. The harness stubs `PIL`, `sdl2`, and `requests` before import so `upgrade.py` and `launcher.py` do not open a network connection and do not unpack `module.zip` onto `/`.

## What is green today

Characterization tests describe the code as it is, including bugs. They pass while the bug remains. A fix makes them fail, which is the signal to update them in the same change.

Acceptance tests describe the intended behavior. They use `unittest.expectedFailure`. While the bug remains, the failure is expected and the suite stays green. If a fix makes an acceptance test pass, unittest reports an unexpected success and the suite fails until that marker is removed. Do not delete a characterization test just to make CI green.

| Test | Kind | Current behavior locked in |
| --- | --- | --- |
| `test_known_dates_keep_their_channels` | Anchor | `20240101` and `20251101` stay on `source/` (the older date does not offer append), `20251206` selects `390/`, `20260520` selects `400/` |
| `test_current_*_selects_400_channel` | Characterization | Missing, empty, or `Unknown` version.ini selects `400/` and offers append |
| `test_acceptance_*_does_not_select_400_or_offer_append` | Acceptance, expected failure | Unknown OS must not select `400/` or offer append |
| `test_current_failed_install_reports_success_and_reboots` | Characterization | `install.sh` return code 1 still shows Installation Complete and reboots |
| `test_acceptance_failed_install_does_not_reboot_or_report_complete` | Acceptance, expected failure | A failed install must not reboot or report completion |
| `test_current_http_200_appends_partial_file` | Characterization | HTTP 200 appends the full body onto a partial file in both downloaders |
| `test_acceptance_http_200_replaces_partial_file` | Acceptance, expected failure | HTTP 200 should leave exactly the response body |
| `test_current_cancel_leaves_the_partial_archive` | Characterization | Cancelling an app update leaves the partial file in place |
| `test_acceptance_cancel_does_not_leave_the_archive` | Acceptance, expected failure | Cancel should not leave that archive behind |
| `test_current_shell_extracts_app_archive_without_a_checksum` | Characterization, source only | Both update scripts `tar -xf` `/tmp/app.tar.gz` and then delete it, with no checksum |
| `test_acceptance_shell_checks_the_archive_before_extract` | Acceptance, expected failure, source only | Those branches should verify the archive before extract |

The shell cases only read the script text. They do not run `update.sh` or `Modified_System_Online_Upgrade.sh`. The install case intercepts `subprocess.run` and refuses `os.system`. The fixture `install.sh` would only write `/tmp/anbernic-regression-install-canary`; the test fails if that file appears.
