# Device-free regression tests

These tests cover three updater failure paths. OS version checks require a missing or malformed date to stay fail-closed. The install, download, and shell checks still describe bugs that are open. Nothing here writes to a device or executes `install.sh` or the update shell scripts.

Run them from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

No extra packages are required. The harness stubs `PIL`, `sdl2`, and `requests` before import so `upgrade.py` and `launcher.py` do not open a network connection and do not unpack `module.zip` onto `/`.

## What is green today

Characterization tests for a bug that is still present describe that bug and pass while it remains. A fix makes them fail, which is the signal to update them in the same change. Once a bug is fixed, those tests assert the corrected behavior.

Acceptance tests for bugs that are still open use `unittest.expectedFailure`. While the bug remains, the failure is expected and the suite stays green. If a fix makes an acceptance test pass, unittest reports an unexpected success and the suite fails until that marker is removed. Do not delete a characterization test just to make CI green.

| Test | Kind | Behavior locked in |
| --- | --- | --- |
| `test_known_dates_keep_their_channels` | Anchor | `20240101` stays on `source/` and does not qualify; `20251101` stays on `source/` and does qualify; `20251206` selects `390/`; `20260520` selects `400/` |
| `test_missing_version_does_not_qualify`, `test_literal_unknown_does_not_qualify`, `test_empty_version_file_does_not_qualify`, `test_malformed_versions_do_not_qualify` | Corrected behavior | Missing, empty, Unknown, and malformed version.ini stay on `source/` and do not qualify for append or mod update |
| `test_acceptance_*_does_not_select_400_or_offer_append` | Promoted acceptance | Same fail-closed contract for missing, empty, and Unknown |
| `test_current_failed_install_reports_success_and_reboots` | Characterization | `install.sh` return code 1 still shows Installation Complete and reboots |
| `test_acceptance_failed_install_does_not_reboot_or_report_complete` | Acceptance, expected failure | A failed install must not reboot or report completion |
| `test_current_http_200_appends_partial_file` | Characterization | HTTP 200 appends the full body onto a partial file in both downloaders |
| `test_acceptance_http_200_replaces_partial_file` | Acceptance, expected failure | HTTP 200 should leave exactly the response body |
| `test_current_cancel_leaves_the_partial_archive` | Characterization | Cancelling an app update leaves the partial file in place |
| `test_acceptance_cancel_does_not_leave_the_archive` | Acceptance, expected failure | Cancel should not leave that archive behind |
| `test_current_shell_extracts_app_archive_without_a_checksum` | Characterization, source only | Both update scripts `tar -xf` `/tmp/app.tar.gz` and then delete it, with no checksum |
| `test_acceptance_shell_checks_the_archive_before_extract` | Acceptance, expected failure, source only | Those branches should verify the archive before extract |

The shell cases only read the script text. They do not run `update.sh` or `Modified_System_Online_Upgrade.sh`. The install case intercepts `subprocess.run` and refuses `os.system`. The fixture `install.sh` would only write `/tmp/anbernic-regression-install-canary`; the test fails if that file appears.
