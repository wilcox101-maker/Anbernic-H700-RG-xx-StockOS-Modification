"""Failed install.sh handling.

The test builds a zip with an install.sh that would only write a canary file,
then calls the real Updater.start_update. subprocess.run is replaced so bash
is not started. The canary must stay absent.
"""

import hashlib
import io
import socket
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from tests.harness import (
    INSTALL_CANARY,
    install_script_bytes,
    load_upgrade,
    zip_with_install_script,
)


class _Redirect:
    def __init__(self, inner, dest: Path):
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_dest", str(dest))
        object.__setattr__(self, "chosen", None)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_inner"), name)

    @property
    def target_path(self):
        chosen = object.__getattribute__(self, "chosen")
        if chosen is None:
            return ""
        return object.__getattribute__(self, "_dest")

    @target_path.setter
    def target_path(self, value):
        object.__setattr__(self, "chosen", value)


def run_install(mode):
    if mode not in ("fail", "raise", "ok"):
        raise AssertionError(mode)
    upgrade = load_upgrade()
    if INSTALL_CANARY.exists():
        INSTALL_CANARY.unlink()
    device_path = Path("/mnt/mmc/update/mod/patch")
    if device_path.exists():
        raise AssertionError(f"refusing to run while {device_path} exists")

    zip_bytes = zip_with_install_script()
    digest = hashlib.md5(zip_bytes).hexdigest()
    calls = []
    messages = []
    reboots = []
    sleeps = []

    def fake_run(args, cwd=None, **kwargs):
        script = Path(cwd) / "install.sh"
        calls.append(
            {
                "args": list(args),
                "cwd": cwd,
                "script": script.read_bytes(),
            }
        )
        if mode == "raise":
            raise subprocess.TimeoutExpired(args, 300)
        code = 0 if mode == "ok" else 1
        stderr = "" if mode == "ok" else "install failed"
        return subprocess.CompletedProcess(args, code, stdout="", stderr=stderr)

    def refuse(command, *args, **kwargs):
        raise AssertionError(f"refusing process execution: {command}")

    def draw(title, subtitle=None, icon=None, status="info"):
        messages.append(
            {"title": title, "subtitle": subtitle, "icon": icon, "status": status}
        )

    def reboot(ui, cfg, auto=False):
        reboots.append(auto)

    def exit_cleanup(code, ui, cfg):
        raise AssertionError(f"exit_cleanup {code} during failed-install scenario")

    updater = upgrade.Updater.__new__(upgrade.Updater)
    with tempfile.TemporaryDirectory(prefix="anbernic-install-") as temporary:
        dest = Path(temporary) / "patch"
        updater.cfg = _Redirect(upgrade.Config(), dest)
        updater.ui = type(
            "UI",
            (),
            {
                "x_size": 640,
                "y_size": 480,
                "cfg": updater.cfg,
                "clear": lambda self: None,
                "paint": lambda self: None,
                "text": lambda self, *args, **kwargs: None,
                "info_header": lambda self, *args, **kwargs: None,
                "progress_bar": lambda self, *args, **kwargs: None,
            },
        )()
        updater.t = type("T", (), {"t": staticmethod(lambda message, **kwargs: message)})()
        updater.draw_message_center = draw

        def fake_download(url, local_path, progress_hook=None, num_file=None):
            Path(local_path).write_bytes(zip_bytes)
            return True

        updater._download_file = fake_download

        def fake_disk(path):
            free = {"/tmp": 2 << 30, "/mnt/mmc": 4 << 30, "/mnt/sdcard": 3 << 30}[str(path)]
            return type("Usage", (), {"total": 8 << 30, "used": 1 << 30, "free": free})()

        original_run = upgrade.subprocess.run
        original_system = upgrade.os.system
        original_sleep = upgrade.time.sleep
        original_disk = upgrade.shutil.disk_usage
        original_reboot = upgrade.MainApp.reboot
        original_cleanup = upgrade.MainApp.exit_cleanup
        upgrade.subprocess.run = fake_run
        upgrade.os.system = refuse
        upgrade.time.sleep = lambda seconds: sleeps.append(seconds)
        upgrade.shutil.disk_usage = fake_disk
        upgrade.MainApp.reboot = staticmethod(reboot)
        upgrade.MainApp.exit_cleanup = staticmethod(exit_cleanup)
        try:
            updater.start_update(
                [{"filename": "patch.zip", "md5": digest}],
                install_active=True,
            )
        finally:
            upgrade.subprocess.run = original_run
            upgrade.os.system = original_system
            upgrade.time.sleep = original_sleep
            upgrade.shutil.disk_usage = original_disk
            upgrade.MainApp.reboot = original_reboot
            upgrade.MainApp.exit_cleanup = original_cleanup

    if INSTALL_CANARY.exists():
        INSTALL_CANARY.unlink()
        raise AssertionError("install.sh was executed; the canary file was created")
    if device_path.exists():
        raise AssertionError(f"start_update wrote {device_path}")
    if len(calls) != 1:
        raise AssertionError(f"expected one intercepted install.sh call, got {calls}")
    if calls[0]["args"] != ["/bin/bash", "install.sh"]:
        raise AssertionError(calls[0]["args"])
    if calls[0]["script"] != install_script_bytes():
        raise AssertionError("extracted install.sh was not the fixture script")
    if updater.cfg.chosen != "/mnt/mmc/update/mod/patch":
        raise AssertionError(f"unexpected install target {updater.cfg.chosen}")
    return {"messages": messages, "reboots": reboots, "sleeps": sleeps}


def _titles(result):
    return [message["title"] for message in result["messages"]]


def _failed_message(result):
    failed = [message for message in result["messages"] if "Installation Failed" in message["title"]]
    if len(failed) != 1:
        raise AssertionError(result["messages"])
    return failed[0]


class FailedInstallTests(unittest.TestCase):
    def test_nonzero_install_reports_failure_and_does_not_reboot(self):
        """A nonzero install.sh stops before the success message and reboot."""
        result = run_install("fail")
        failed = _failed_message(result)
        self.assertIn("exit 1", failed["subtitle"])
        self.assertIn("install failed", failed["subtitle"])
        self.assertEqual(failed["status"], "error")
        self.assertFalse(any("Installation Complete" in title for title in _titles(result)))
        self.assertFalse(any("Ready, start upgrading" in (message["subtitle"] or "") for message in result["messages"]))
        self.assertEqual(result["reboots"], [])
        self.assertNotIn(3, result["sleeps"])

    def test_acceptance_failed_install_does_not_reboot_or_report_complete(self):
        """Promoted acceptance: return code 1 is a failure, not a reboot."""
        result = run_install("fail")
        self.assertEqual(result["reboots"], [])
        self.assertFalse(any("Installation Complete" in title for title in _titles(result)))
        self.assertIn("exit 1", _failed_message(result)["subtitle"])

    def test_install_launch_error_reports_failure_and_does_not_reboot(self):
        """A launch error such as a timeout is shown and does not reboot."""
        result = run_install("raise")
        failed = _failed_message(result)
        self.assertIn("timed out", failed["subtitle"])
        self.assertEqual(failed["status"], "error")
        self.assertFalse(any("Installation Complete" in title for title in _titles(result)))
        self.assertEqual(result["reboots"], [])

    def test_successful_install_reports_complete_and_reboots(self):
        """Return code 0 still announces completion and reboots."""
        result = run_install("ok")
        self.assertTrue(any("Installation Complete" in title for title in _titles(result)))
        self.assertFalse(any("Installation Failed" in title for title in _titles(result)))
        self.assertTrue(any("Ready, start upgrading" in (message["subtitle"] or "") for message in result["messages"]))
        self.assertEqual(result["reboots"], [False])
        self.assertIn(3, result["sleeps"])

    def test_extractall_onto_root_and_network_are_refused(self):
        load_upgrade()
        sock = socket.socket()
        try:
            with self.assertRaises(RuntimeError) as blocked:
                sock.connect(("127.0.0.1", 9))
            self.assertIn("socket connect blocked", str(blocked.exception))
        finally:
            sock.close()
        sentinel = Path("/anbernic-regression-should-not-exist")
        self.assertFalse(sentinel.exists())
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("anbernic-regression-should-not-exist", b"no")
        buffer.seek(0)
        with zipfile.ZipFile(buffer, "r") as archive:
            with self.assertRaises(RuntimeError) as caught:
                archive.extractall("/")
        self.assertIn("refusing", str(caught.exception))
        self.assertFalse(sentinel.exists())


if __name__ == "__main__":
    unittest.main()
