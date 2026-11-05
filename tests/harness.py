"""Import the updater and launcher without network, device nodes, or package extraction.

The production modules import PIL, open a log file, and probe download mirrors
while the class body is executing. They also unpack bundled dependencies onto
``/`` when those imports fail. Tests install stubs first, then call the real
functions.
"""

from __future__ import annotations

import ast
import io
import json
import logging
import os
import socket
import subprocess
import sys
import types
import zipfile
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
UPGRADE_DIR = ROOT / "Modified_System_Online_Upgrade" / "upgrade"
VERSION_INI = Path("/mnt/vendor/oem/version.ini")
INSTALL_CANARY = Path("/tmp/anbernic-regression-install-canary")

_upgrade = None
_launcher = None
_stubs_ready = False


class DiscardHandler(logging.Handler):
    """Stand-in for FileHandler that does not create update.log or launcher.log."""

    def __init__(self, *args, **kwargs):
        super().__init__()

    def emit(self, record):
        return None


class _Response:
    def __init__(self, body: bytes, status: int = 200):
        self.status_code = status
        self.headers = {"content-length": str(len(body))}
        self._body = body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise OSError(f"HTTP {self.status_code}")

    def iter_content(self, block_size):
        yield self._body

    def close(self):
        return None


class RecordingSession:
    def __init__(self, response: _Response):
        self.response = response
        self.calls = []

    def get(self, url, stream=True, timeout=None, headers=None):
        self.calls.append({"url": url, "headers": dict(headers or {})})
        return self.response


def _block_network():
    def blocked(*_args, **_kwargs):
        raise RuntimeError("network is disabled in device-free tests")

    socket.create_connection = blocked

    def connect(self, address):
        raise RuntimeError(f"socket connect blocked: {address}")

    socket.socket.connect = connect


def _guard_extractall():
    real = zipfile.ZipFile.extractall

    def guarded(self, path=None, members=None, pwd=None):
        target = os.getcwd() if path is None else path
        if os.path.abspath(target) == os.path.abspath("/"):
            raise RuntimeError("refusing ZipFile.extractall('/')")
        return real(self, path, members, pwd)

    zipfile.ZipFile.extractall = guarded


def _install_stubs():
    global _stubs_ready
    if _stubs_ready:
        return
    if "upgrade" in sys.modules or "launcher" in sys.modules:
        raise RuntimeError("upgrade or launcher was imported before test stubs")

    _block_network()
    _guard_extractall()
    logging.FileHandler = DiscardHandler

    class _Any:
        """Attribute stub for annotations such as Image.Image. It is never called to draw."""

        def __call__(self, *args, **kwargs):
            return self

        def __getattr__(self, name):
            return self

    pil = types.ModuleType("PIL")
    pil.Image = _Any()
    pil.ImageDraw = _Any()
    pil.ImageFont = _Any()
    sys.modules["PIL"] = pil

    sdl2 = types.ModuleType("sdl2")
    sdl2.__getattr__ = lambda name: 0
    sys.modules["sdl2"] = sdl2

    requests = types.ModuleType("requests")

    def requests_get(*_args, **_kwargs):
        raise OSError("network disabled")

    requests.get = requests_get
    exceptions = types.ModuleType("requests.exceptions")
    for name in (
        "RequestException",
        "Timeout",
        "HTTPError",
        "ChunkedEncodingError",
        "ConnectionError",
    ):
        setattr(exceptions, name, type(name, (Exception,), {}))
    requests.exceptions = exceptions
    adapters = types.ModuleType("requests.adapters")
    adapters.HTTPAdapter = type("HTTPAdapter", (), {"__init__": lambda self, *a, **k: None})
    sys.modules["requests"] = requests
    sys.modules["requests.exceptions"] = exceptions
    sys.modules["requests.adapters"] = adapters

    urllib3 = types.ModuleType("urllib3")
    util = types.ModuleType("urllib3.util")
    retry_mod = types.ModuleType("urllib3.util.retry")
    retry = type("Retry", (), {"__init__": lambda self, *a, **k: None})
    util.Retry = retry
    retry_mod.Retry = retry
    urllib3.util = util
    sys.modules["urllib3"] = urllib3
    sys.modules["urllib3.util"] = util
    sys.modules["urllib3.util.retry"] = retry_mod
    _stubs_ready = True


def _patch_version_ini(text: Optional[str]):
    real_exists = Path.exists
    real_read = Path.read_text

    def exists(self):
        if Path(self) == VERSION_INI:
            return text is not None
        return real_exists(self)

    def read_text(self, *args, **kwargs):
        if Path(self) == VERSION_INI:
            if text is None:
                raise FileNotFoundError(str(VERSION_INI))
            return text
        return real_read(self, *args, **kwargs)

    Path.exists = exists
    Path.read_text = read_text


def _quiet(logger_name: str):
    logging.getLogger(logger_name).setLevel(logging.ERROR)


def _require_safe_import(module):
    if getattr(module.requests.get, "__name__", "") != "requests_get":
        raise RuntimeError(f"{module.__name__} imported a live requests.get")
    if zipfile.ZipFile.extractall.__name__ != "guarded":
        raise RuntimeError("ZipFile.extractall guard is not installed")


def load_upgrade(version_text: Optional[str] = None, patch_version: bool = False):
    """Import the real upgrade module.

    ``patch_version`` is only for a fresh process. Reusing one import would keep
    the channel chosen by the first version.ini read.
    """
    global _upgrade
    if _upgrade is not None:
        if patch_version:
            raise RuntimeError("refusing to reuse an upgrade import for another version.ini")
        return _upgrade
    _install_stubs()
    if patch_version:
        _patch_version_ini(version_text)
    if str(UPGRADE_DIR) not in sys.path:
        sys.path.insert(0, str(UPGRADE_DIR))
    import upgrade

    upgrade._device_free_stub = True
    _require_safe_import(upgrade)
    _quiet("upgrade")
    _upgrade = upgrade
    return upgrade


def load_launcher():
    global _launcher
    if _launcher is not None:
        return _launcher
    _install_stubs()
    if str(UPGRADE_DIR) not in sys.path:
        sys.path.insert(0, str(UPGRADE_DIR))
    import launcher

    launcher._device_free_stub = True
    _require_safe_import(launcher)
    _quiet("launcher")
    _launcher = launcher
    return launcher


def _gate_node(upgrade_path: Path, target: str) -> ast.If:
    """Return the real ``if`` that assigns ``target`` in upgrade.py."""
    source = upgrade_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        for stmt in node.body:
            targets = getattr(stmt, "targets", ())
            if any(isinstance(item, ast.Name) and item.id == target for item in targets):
                found.append(node)
                break
    if len(found) != 1:
        raise AssertionError(f"expected one {target} gate in {upgrade_path}, found {len(found)}")
    segment = ast.get_source_segment(source, found[0]) or ""
    if 'cur_ver == "Unknown"' not in segment or "os_cur_ver >= base_date" not in segment:
        raise AssertionError(f"extracted {target} gate is not the audited condition:\n" + segment)
    return found[0]


def _exec_gate(module, gate: ast.If, namespace: dict):
    globals_ = {"bool": bool}
    qualifier = getattr(module, "is_os_date", None)
    if qualifier is not None:
        globals_["is_os_date"] = qualifier
    module_node = ast.Module(body=[gate], type_ignores=[])
    ast.fix_missing_locations(module_node)
    exec(compile(module_node, str(module.__file__), "exec"), globals_, namespace)


def append_offered(module, cur_ver: str, data_ver: str, data_url: str) -> bool:
    """Execute the real append gate against this import's channel globals."""
    gate = _gate_node(Path(module.__file__), "append_active")
    namespace = {
        "cur_ver": cur_ver,
        "data_ver": data_ver,
        "data_update_url": data_url,
        "base_ver": module.base_ver,
        "base_date": module.base_date,
        "os_cur_ver": module.os_cur_ver,
        "append_active": False,
    }
    _exec_gate(module, gate, namespace)
    return bool(namespace["append_active"])


def update_offered(module) -> bool:
    """Execute the real update gate for an unknown mod version and a real manifest."""
    gate = _gate_node(Path(module.__file__), "update_active")
    namespace = {
        "cur_ver": "Unknown",
        "update_ver": "4.0.4",
        "data_ver": "4.0.0",
        "update_file_list": ["patch.zip"],
        "base_ver": module.base_ver,
        "base_date": module.base_date,
        "os_cur_ver": module.os_cur_ver,
        "update_active": False,
        "new_ver": None,
    }
    _exec_gate(module, gate, namespace)
    return bool(namespace["update_active"])


_PROBE = r"""
import json, os, sys
sys.path.insert(0, os.environ["REPO_ROOT"])
from tests.harness import append_offered, load_upgrade, update_offered
missing = os.environ.get("VERSION_MISSING") == "1"
text = None if missing else os.environ["VERSION_TEXT"]
mod = load_upgrade(text, patch_version=True)
log_path = os.path.join(os.path.dirname(mod.__file__), "update.log")
payload = {
    "os_cur_ver": mod.os_cur_ver,
    "source": mod.source,
    "base_ver": mod.base_ver,
    "base_date": mod.base_date,
    "append_when_mod_unknown": append_offered(
        mod, "Unknown", "4.0.4", "https://example.invalid/append.zip"
    ),
    "update_when_mod_unknown": update_offered(mod),
    "update_log_exists": os.path.exists(log_path),
}
print("PROBE " + json.dumps(payload))
"""


def probe_channel(version_text: Optional[str]) -> dict:
    """Import upgrade.py in a child process with one version.ini value.

    Channel selection runs at import time, so each OS version needs its own
    interpreter. The child has the same network and extractall guards.
    """
    env = os.environ.copy()
    env["REPO_ROOT"] = str(ROOT)
    env["PYTHONPATH"] = str(ROOT)
    env["VERSION_MISSING"] = "1" if version_text is None else "0"
    if version_text is not None:
        env["VERSION_TEXT"] = version_text
    completed = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(
            "version probe failed\n"
            + completed.stdout
            + "\n"
            + completed.stderr
        )
    lines = [line[6:] for line in completed.stdout.splitlines() if line.startswith("PROBE ")]
    if len(lines) != 1:
        raise AssertionError("version probe did not report one result\n" + completed.stdout)
    return json.loads(lines[0])


def app_archive_branch(path: Path) -> str:
    """Return the ``elif APP_FILE`` branch. This reads source; it does not run it."""
    lines = path.read_text(encoding="utf-8").splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip().startswith("elif") and "APP_FILE" in line:
            start = index
            break
    if start is None:
        raise AssertionError(f"APP_FILE branch not found in {path}")
    chunk = []
    for line in lines[start:]:
        if chunk and line.strip() == "else:":
            break
        chunk.append(line)
    branch = "\n".join(chunk)
    if "tar" not in branch:
        raise AssertionError(f"APP_FILE branch in {path} has no tar command:\n{branch}")
    return branch


def make_downloader(module, owner_name: str, body: bytes, slide: bool):
    if owner_name == "Updater":
        owner = module.Updater.__new__(module.Updater)
    elif owner_name == "LauncherApp":
        owner = module.LauncherApp.__new__(module.LauncherApp)
    else:
        raise AssertionError(owner_name)
    owner.cfg = module.Config()
    owner.input = types.SimpleNamespace(
        slide_key=lambda: slide,
        poll=lambda: None,
        reset=lambda: None,
        is_key=lambda _name: False,
    )
    owner.session = RecordingSession(_Response(body))
    owner._active_threads = []
    owner._shutdown_flag = False
    owner.ui = types.SimpleNamespace(
        x_size=640,
        y_size=480,
        cfg=owner.cfg,
        clear=lambda: None,
        paint=lambda: None,
        text=lambda *a, **k: None,
        panel=lambda *a, **k: None,
        circle=lambda *a, **k: None,
        button=lambda *a, **k: None,
        wrap_text=lambda *a, **k: ["line"],
        info_header=lambda *a, **k: None,
        progress_bar=lambda *a, **k: None,
        show_info=lambda *a, **k: None,
        draw_end=lambda: None,
    )
    owner.t = types.SimpleNamespace(t=lambda message, **kwargs: message)
    owner.skip_first_input = False
    return owner


def install_script_bytes() -> bytes:
    return (
        b"#!/bin/bash\n"
        b"echo ran > /tmp/anbernic-regression-install-canary\n"
        b"exit 1\n"
    )


def zip_with_install_script() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("install.sh", install_script_bytes())
    return buffer.getvalue()
