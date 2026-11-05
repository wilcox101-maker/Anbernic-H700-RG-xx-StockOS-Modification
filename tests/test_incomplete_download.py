"""Partial downloads and the shell archive branch.

Download tests call the real ``_download_file`` methods. The HTTP response is
an in-memory stub, so nothing is contacted. The shell assertions read the
update scripts and do not execute them.
"""

import sys
import tempfile
import unittest
from pathlib import Path

from tests.harness import (
    ROOT,
    _Response,
    app_archive_branch,
    load_launcher,
    load_upgrade,
    make_downloader,
)
from tests.harness import RecordingSession

PARTIAL = b"PARTIAL-BYTES"
BODY = b"FULL-BODY-CONTENTS"
REMAINDER = b"-REMAINDER"
URL = "http://example.invalid/package.bin"

SHELLS = (
    ROOT / "Modified_System_Online_Upgrade/upgrade/update.sh",
    ROOT / "Modified_System_Online_Upgrade/Modified_System_Online_Upgrade.sh",
)

OWNERS = (("Updater", load_upgrade), ("LauncherApp", load_launcher))


def run_download(module, owner_name, partial, responses):
    owner = make_downloader(module, owner_name, b"", slide=False)
    owner.session = RecordingSession(responses)
    with tempfile.TemporaryDirectory(prefix="anbernic-download-") as temporary:
        target = Path(temporary) / "package.bin"
        if partial is not None:
            target.write_bytes(partial)
        result = owner._download_file(URL, str(target), None, None)
        return {
            "result": result,
            "payload": target.read_bytes() if target.exists() else None,
            "exists": target.exists(),
            "calls": owner.session.calls,
        }


def response(body, status=200, **headers):
    return _Response(body, status=status, headers=headers or None)


def without_download_sleep(run):
    modules = [load_upgrade(), load_launcher()]
    original = [module.time.sleep for module in modules]
    for module in modules:
        module.time.sleep = lambda *_args, **_kwargs: None
    try:
        run()
    finally:
        for module, sleep in zip(modules, original):
            module.time.sleep = sleep


class _DroppingResponse(_Response):
    def iter_content(self, block_size):
        requests = sys.modules["requests"]
        raise requests.exceptions.ConnectionError("dropped")


class IncompleteDownloadTests(unittest.TestCase):
    def _each(self, partial, responses, check):
        for owner_name, loader in OWNERS:
            with self.subTest(owner=owner_name):
                check(run_download(loader(), owner_name, partial, responses))

    def test_fresh_http_200_writes_the_body(self):
        def check(observed):
            self.assertEqual(observed["result"], True)
            self.assertEqual(observed["payload"], BODY)
            self.assertNotIn("Range", observed["calls"][0]["headers"])

        self._each(None, response(BODY), check)

    def test_http_200_restarts_a_partial_file(self):
        """A full 200 body replaces a partial file instead of appending to it."""
        def check(observed):
            self.assertEqual(observed["result"], True)
            self.assertEqual(observed["calls"][0]["headers"].get("Range"), f"bytes={len(PARTIAL)}-")
            self.assertEqual(observed["payload"], BODY)

        self._each(PARTIAL, response(BODY), check)

    def test_acceptance_http_200_replaces_partial_file(self):
        """Promoted acceptance: HTTP 200 must not append onto a partial file."""
        self._each(PARTIAL, response(BODY), lambda observed: self.assertEqual(observed["payload"], BODY))

    def test_http_206_appends_a_matching_range(self):
        start = len(PARTIAL)
        end = start + len(REMAINDER) - 1
        total = end + 1
        ranged = response(
            REMAINDER,
            status=206,
            **{
                "content-range": f"bytes {start}-{end}/{total}",
                "content-length": str(len(REMAINDER)),
            },
        )

        def check(observed):
            self.assertEqual(observed["result"], True)
            self.assertEqual(observed["calls"][0]["headers"].get("Range"), f"bytes={start}-")
            self.assertEqual(observed["payload"], PARTIAL + REMAINDER)

        self._each(PARTIAL, ranged, check)

    def test_http_206_full_range_restarts_instead_of_appending(self):
        end = len(BODY) - 1
        ranged = response(
            BODY,
            status=206,
            **{"content-range": f"bytes 0-{end}/{len(BODY)}", "content-length": str(len(BODY))},
        )
        self._each(PARTIAL, ranged, lambda observed: self.assertEqual(observed["payload"], BODY))

    def test_http_206_wrong_start_does_not_append(self):
        ranged = response(
            b"ABCD",
            status=206,
            **{"content-range": "bytes 0-3/100", "content-length": "4"},
        )

        def check(observed):
            self.assertEqual(observed["result"], False)
            self.assertEqual(observed["payload"], PARTIAL)

        self._each(PARTIAL, ranged, check)

    def test_http_206_length_mismatch_does_not_append(self):
        ranged = response(
            b"ABCD",
            status=206,
            **{"content-range": "bytes 13-16/100", "content-length": "999"},
        )

        def check(observed):
            self.assertEqual(observed["result"], False)
            self.assertEqual(observed["payload"], PARTIAL)

        self._each(PARTIAL, ranged, check)

    def test_http_206_unparseable_range_does_not_append(self):
        ranged = response(
            REMAINDER,
            status=206,
            **{"content-range": "units 13-22/23", "content-length": str(len(REMAINDER))},
        )

        def check(observed):
            self.assertEqual(observed["result"], False)
            self.assertEqual(observed["payload"], PARTIAL)

        self._each(PARTIAL, ranged, check)

    def _ranged_206(self, body):
        start = len(PARTIAL)
        end = start + len(body) - 1
        total = end + 1
        headers = {
            "content-range": f"bytes {start}-{end}/{total}",
            "content-length": str(len(body)),
        }
        return start, headers

    def test_interrupted_206_does_not_append_a_following_http_200(self):
        """A dropped resume must not append a later full HTTP 200 body."""
        load_upgrade()
        start, headers = self._ranged_206(REMAINDER)
        first = _DroppingResponse(b"", status=206, headers=headers)

        def check(observed):
            self.assertEqual(observed["result"], False)
            self.assertEqual(observed["payload"], PARTIAL)
            self.assertEqual(observed["calls"][1]["headers"].get("Range"), f"bytes={start}-")

        without_download_sleep(lambda: self._each(PARTIAL, [first, response(BODY)], check))

    def test_interrupted_206_appends_a_matching_retry(self):
        """A dropped resume still appends when the retry is the same 206 range."""
        load_upgrade()
        _start, headers = self._ranged_206(REMAINDER)
        first = _DroppingResponse(b"", status=206, headers=headers)
        second = response(REMAINDER, status=206, **headers)

        def check(observed):
            self.assertEqual(observed["result"], True)
            self.assertEqual(observed["payload"], PARTIAL + REMAINDER)

        without_download_sleep(lambda: self._each(PARTIAL, [first, second], check))

    def test_http_error_leaves_the_partial_file(self):
        def check(observed):
            self.assertEqual(observed["result"], False)
            self.assertEqual(observed["payload"], PARTIAL)
            self.assertEqual(len(observed["calls"]), 1)

        self._each(PARTIAL, response(b"nope", status=500), check)

    def test_http_416_complete_file_is_kept(self):
        ranged = response(
            b"",
            status=416,
            **{"content-range": f"bytes */{len(PARTIAL)}", "content-length": "0"},
        )

        def check(observed):
            self.assertEqual(observed["result"], True)
            self.assertEqual(observed["payload"], PARTIAL)
            self.assertEqual(len(observed["calls"]), 1)

        self._each(PARTIAL, ranged, check)

    def test_http_416_restarts_when_the_range_is_not_complete(self):
        ranged = [
            response(b"", status=416, **{"content-range": "bytes */100", "content-length": "0"}),
            response(BODY, status=200),
        ]

        def check(observed):
            self.assertEqual(observed["result"], True)
            self.assertEqual(observed["payload"], BODY)
            self.assertNotIn("Range", observed["calls"][1]["headers"])

        self._each(PARTIAL, ranged, check)

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
