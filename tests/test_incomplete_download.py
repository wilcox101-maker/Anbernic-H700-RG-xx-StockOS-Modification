"""Partial downloads and the shell archive branch.

Download tests call the real ``_download_file`` methods. The HTTP response is
an in-memory stub, so nothing is contacted. The shell assertions read the
update scripts and do not execute them.
"""

import tempfile
import unittest
from pathlib import Path

from tests.harness import ROOT, app_archive_branch, load_launcher, load_upgrade, make_downloader

PARTIAL = b"PARTIAL-BYTES"
BODY = b"FULL-BODY-CONTENTS"
URL = "http://example.invalid/package.bin"

SHELLS = (
    ROOT / "Modified_System_Online_Upgrade/upgrade/update.sh",
    ROOT / "Modified_System_Online_Upgrade/Modified_System_Online_Upgrade.sh",
)


def http_200_resume(module, owner_name):
    owner = make_downloader(module, owner_name, BODY, slide=False)
    with tempfile.TemporaryDirectory(prefix="anbernic-download-") as temporary:
        target = Path(temporary) / "package.bin"
        target.write_bytes(PARTIAL)
        result = owner._download_file(URL, str(target), None, None)
        return {
            "result": result,
            "payload": target.read_bytes(),
            "range": owner.session.calls[0]["headers"].get("Range"),
            "status": owner.session.response.status_code,
        }


class IncompleteDownloadTests(unittest.TestCase):
    def test_current_http_200_appends_partial_file(self):
        """CHARACTERIZATION: a 200 response is appended to the bytes already on disk."""
        for module, owner in ((load_upgrade(), "Updater"), (load_launcher(), "LauncherApp")):
            with self.subTest(owner=owner):
                observed = http_200_resume(module, owner)
                self.assertEqual(observed["result"], True)
                self.assertEqual(observed["status"], 200)
                self.assertEqual(observed["range"], f"bytes={len(PARTIAL)}-")
                self.assertEqual(observed["payload"], PARTIAL + BODY)
                self.assertNotEqual(observed["payload"], BODY)

    @unittest.expectedFailure
    def test_acceptance_http_200_replaces_partial_file(self):
        """ACCEPTANCE: a full 200 body replaces a partial file instead of appending.

        Remove expectedFailure only in the change that fixes both downloaders.
        """
        for module, owner in ((load_upgrade(), "Updater"), (load_launcher(), "LauncherApp")):
            with self.subTest(owner=owner):
                observed = http_200_resume(module, owner)
                self.assertEqual(observed["payload"], BODY)

    def test_current_cancel_leaves_the_partial_archive(self):
        """CHARACTERIZATION: cancelling an app update returns without deleting the file."""
        launcher = load_launcher()
        owner = make_downloader(launcher, "LauncherApp", BODY, slide=True)
        original_sleep = launcher.time.sleep
        launcher.time.sleep = lambda _seconds: None
        try:
            with tempfile.TemporaryDirectory(prefix="anbernic-cancel-") as temporary:
                target = Path(temporary) / "app.tar.gz"
                target.write_bytes(PARTIAL)
                owner.cfg.tmp_app_update = str(target)
                owner.update_app("9.9.9", URL, "ignored")
                self.assertTrue(target.exists())
                self.assertEqual(target.read_bytes(), PARTIAL)
        finally:
            launcher.time.sleep = original_sleep

    @unittest.expectedFailure
    def test_acceptance_cancel_does_not_leave_the_archive(self):
        """ACCEPTANCE: cancel must not leave the archive the shell later extracts.

        Remove expectedFailure only in the change that deletes or never creates
        that file on cancel.
        """
        launcher = load_launcher()
        owner = make_downloader(launcher, "LauncherApp", BODY, slide=True)
        original_sleep = launcher.time.sleep
        launcher.time.sleep = lambda _seconds: None
        try:
            with tempfile.TemporaryDirectory(prefix="anbernic-cancel-") as temporary:
                target = Path(temporary) / "app.tar.gz"
                target.write_bytes(PARTIAL)
                owner.cfg.tmp_app_update = str(target)
                owner.update_app("9.9.9", URL, "ignored")
                self.assertFalse(target.exists())
        finally:
            launcher.time.sleep = original_sleep

    def test_current_shell_extracts_app_archive_without_a_checksum(self):
        """CHARACTERIZATION: source lock only. The scripts are not executed."""
        for relative in SHELLS:
            with self.subTest(script=str(relative)):
                branch = app_archive_branch(relative)
                self.assertIn('elif [ -f "$APP_FILE" ]', branch)
                self.assertIn('tar -xf "$APP_FILE"', branch)
                self.assertIn('rm -rf "$APP_FILE"', branch)
                lowered = branch.lower()
                self.assertNotIn("md5", lowered)
                self.assertNotIn("sha256", lowered)
                self.assertNotIn(".ok", lowered)

    @unittest.expectedFailure
    def test_acceptance_shell_checks_the_archive_before_extract(self):
        """ACCEPTANCE: the archive branch should verify integrity before tar.

        This stays a source assertion. It does not run the shell script.
        Remove expectedFailure only when both scripts gain that check.
        """
        for relative in SHELLS:
            with self.subTest(script=str(relative)):
                lowered = app_archive_branch(relative).lower()
                self.assertTrue("md5" in lowered or "sha256" in lowered or ".ok" in lowered)


if __name__ == "__main__":
    unittest.main()
