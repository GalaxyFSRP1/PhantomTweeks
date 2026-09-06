"""Tests for automatic update checking.

The update path is the highest-risk code in the product: it downloads an
executable from the internet. These tests exist to guarantee the safety rules
hold - HTTPS only, checksum mandatory, nothing executed automatically, and
never interrupting a game.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from phantom_tweeks.core import updates  # noqa: E402


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    from phantom_tweeks.core import paths
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    monkeypatch.setattr(paths, "ensure_dirs", lambda: None)
    return tmp_path


# ---------------------------------------------------------- version compare

@pytest.mark.parametrize("newer,current,expected", [
    ("0.1.3", "0.1.2", True),
    ("0.1.2", "0.1.2", False),
    ("0.1.1", "0.1.2", False),
    ("1.0.0", "0.9.9", True),
    ("v0.2.0", "0.1.2", True),          # tolerates a leading v
    ("0.2", "0.1.9", True),             # two-part versions
    ("0.10.0", "0.9.0", True),          # numeric, not lexicographic
    ("1.0.0", "1.0.0-beta.1", True),    # release beats its own pre-release
    ("1.0.0-beta.1", "1.0.0", False),
    ("", "0.1.2", False),               # junk never counts as newer
    ("garbage", "0.1.2", False),
])
def test_version_comparison(newer, current, expected):
    assert updates.is_newer(newer, current) is expected


# ------------------------------------------------------------- check logic

def _manifest(version="9.9.9", **extra):
    d = {
        "available": True,
        "version": version,
        "tag": f"v{version}",
        "published": "2026-09-05",
        "prerelease": False,
        "signed": False,
        "files": [{"name": "PhantomTweeks-Setup.exe", "size": 100,
                   "size_mb": 0.1, "sha256": "ab" * 32,
                   "url": "/api/download?file=setup"}],
    }
    d.update(extra)
    return d


def _fake_urlopen(payload, monkeypatch):
    class Resp:
        def read(self):
            return json.dumps(payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(updates.urllib.request, "urlopen",
                        lambda *a, **k: Resp())


def test_check_refuses_plain_http(data_dir):
    assert updates.check("http://example.com") is None


def test_check_finds_a_newer_version(data_dir, monkeypatch):
    _fake_urlopen(_manifest("9.9.9"), monkeypatch)
    info = updates.check("https://example.com")
    assert info is not None
    assert info.version == "9.9.9"
    assert info.installer["name"] == "PhantomTweeks-Setup.exe"


def test_check_ignores_an_older_or_equal_version(data_dir, monkeypatch):
    from phantom_tweeks.branding import VERSION
    _fake_urlopen(_manifest(VERSION), monkeypatch)
    assert updates.check("https://example.com") is None


def test_check_handles_no_release_published(data_dir, monkeypatch):
    _fake_urlopen({"available": False, "message": "none yet"}, monkeypatch)
    assert updates.check("https://example.com") is None


def test_check_never_raises_on_a_network_failure(data_dir, monkeypatch):
    def boom(*a, **k):
        raise OSError("network down")
    monkeypatch.setattr(updates.urllib.request, "urlopen", boom)
    assert updates.check("https://example.com") is None


def test_check_survives_malformed_json(data_dir, monkeypatch):
    class Resp:
        def read(self):
            return b"<html>not json</html>"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(updates.urllib.request, "urlopen", lambda *a, **k: Resp())
    assert updates.check("https://example.com") is None


def test_a_skipped_version_is_never_offered_again(data_dir, monkeypatch):
    _fake_urlopen(_manifest("9.9.9"), monkeypatch)
    assert updates.check("https://example.com") is not None
    updates.skip_version("9.9.9")
    assert updates.check("https://example.com") is None


def test_snooze_suppresses_background_checks(data_dir):
    updates.save_state(last_check=0)
    assert updates.should_check() is True
    updates.snooze()
    assert updates.should_check() is False


def test_background_checks_are_rate_limited(data_dir):
    updates.save_state(last_check=time.time())
    assert updates.should_check() is False
    updates.save_state(last_check=time.time() - updates.CHECK_INTERVAL_S - 10)
    assert updates.should_check() is True


def test_no_update_prompt_while_a_game_is_running(data_dir, monkeypatch):
    """An update popup must never steal focus mid-match."""
    updates.save_state(last_check=0)
    _fake_urlopen(_manifest("9.9.9"), monkeypatch)

    from phantom_tweeks.core import games

    class FakeGame:
        name = "Counter-Strike"
    monkeypatch.setattr(games, "detect_running_game", lambda *a, **k: FakeGame())
    assert updates.check_if_due("https://example.com") is None


# ------------------------------------------------------------- downloading

def test_download_requires_a_published_checksum(data_dir):
    info = updates.UpdateInfo(
        version="9.9.9", base_url="https://example.com",
        files=[{"name": "x.exe", "url": "/dl", "sha256": ""}])
    ok, msg, path = updates.download_and_verify(info)
    assert not ok
    assert "checksum" in msg.lower()
    assert path is None


def test_download_refuses_plain_http(data_dir):
    info = updates.UpdateInfo(
        version="9.9.9", base_url="http://example.com",
        files=[{"name": "x.exe", "url": "http://example.com/dl",
                "sha256": "ab" * 32}])
    ok, msg, _ = updates.download_and_verify(info)
    assert not ok
    assert "https" in msg.lower()


def test_a_tampered_download_is_rejected_and_deleted(data_dir, monkeypatch):
    """The single most important guarantee in this module."""
    payload = b"malicious replacement binary"
    honest = hashlib.sha256(b"the real installer").hexdigest()

    class Resp:
        headers = {"Content-Length": str(len(payload))}

        def __init__(self):
            self._sent = False

        def read(self, n=-1):
            if self._sent:
                return b""
            self._sent = True
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(updates.urllib.request, "urlopen", lambda *a, **k: Resp())
    info = updates.UpdateInfo(
        version="9.9.9", base_url="https://example.com",
        files=[{"name": "PhantomTweeks-Setup.exe", "url": "/dl",
                "sha256": honest, "size": len(payload)}])

    ok, msg, path = updates.download_and_verify(info)
    assert not ok, "a tampered package was accepted"
    assert "checksum mismatch" in msg.lower()
    assert path is None
    leftovers = list((data_dir / "updates").glob("*"))
    assert not leftovers, f"partial download left on disk: {leftovers}"


def test_a_valid_download_is_staged_but_not_executed(data_dir, monkeypatch):
    payload = b"a legitimate installer"
    digest = hashlib.sha256(payload).hexdigest()

    class Resp:
        headers = {"Content-Length": str(len(payload))}

        def __init__(self):
            self._sent = False

        def read(self, n=-1):
            if self._sent:
                return b""
            self._sent = True
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(updates.urllib.request, "urlopen", lambda *a, **k: Resp())
    info = updates.UpdateInfo(
        version="9.9.9", base_url="https://example.com",
        files=[{"name": "PhantomTweeks-Setup.exe", "url": "/dl",
                "sha256": digest, "size": len(payload)}])

    ok, msg, path = updates.download_and_verify(info)
    assert ok, msg
    assert path.exists()
    assert path.read_bytes() == payload
    assert "run that file" in msg.lower(), "user is not told to install it"


def test_the_updater_never_launches_anything():
    """Downloading and then executing would be indistinguishable from malware."""
    src = Path(updates.__file__).read_text(encoding="utf-8")
    for banned in ("os.startfile", "Popen", "os.system", "os.execv",
                   "ShellExecute"):
        for line in src.splitlines():
            if banned in line and not line.strip().startswith("#"):
                pytest.fail(f"updates.py may execute a payload: {line.strip()}")


def test_progress_callback_is_reported(data_dir, monkeypatch):
    payload = b"x" * 1000
    digest = hashlib.sha256(payload).hexdigest()

    class Resp:
        headers = {"Content-Length": "1000"}

        def __init__(self):
            self._n = 0

        def read(self, n=-1):
            if self._n:
                return b""
            self._n = 1
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(updates.urllib.request, "urlopen", lambda *a, **k: Resp())
    seen = []
    info = updates.UpdateInfo(
        version="9.9.9", base_url="https://example.com",
        files=[{"name": "a.exe", "url": "/dl", "sha256": digest,
                "size": 1000}])
    ok, _, _ = updates.download_and_verify(info, progress=lambda d, t: seen.append(d))
    assert ok and seen, "no progress was reported"


def test_a_broken_progress_callback_does_not_abort_the_download(data_dir, monkeypatch):
    payload = b"y" * 500
    digest = hashlib.sha256(payload).hexdigest()

    class Resp:
        headers = {"Content-Length": "500"}

        def __init__(self):
            self._n = 0

        def read(self, n=-1):
            if self._n:
                return b""
            self._n = 1
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(updates.urllib.request, "urlopen", lambda *a, **k: Resp())

    def bad(d, t):
        raise ValueError("ui bug")

    info = updates.UpdateInfo(
        version="9.9.9", base_url="https://example.com",
        files=[{"name": "b.exe", "url": "/dl", "sha256": digest, "size": 500}])
    ok, msg, _ = updates.download_and_verify(info, progress=bad)
    assert ok, msg
