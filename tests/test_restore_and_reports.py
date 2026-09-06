"""Tests for Windows restore points and diagnostic report export."""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from phantom_tweeks.engine import reports, restorepoint  # noqa: E402


def _fake_run(stdout="", stderr="", rc=0):
    return lambda cmd, **kw: types.SimpleNamespace(
        stdout=stdout, stderr=stderr, returncode=rc)


# --------------------------------------------------------- restore points

def test_reports_unavailable_off_windows():
    ok, msg = restorepoint.create()
    if not restorepoint.IS_WINDOWS:
        assert not ok
        assert "Windows" in msg


def test_disabled_protection_explains_how_to_enable(monkeypatch):
    """Many OEM Windows 11 installs ship with System Protection off."""
    monkeypatch.setattr(restorepoint, "IS_WINDOWS", True)
    monkeypatch.setattr(restorepoint.runproc, "run", _fake_run("no shadow copies"))
    monkeypatch.setattr(restorepoint, "is_admin", lambda: True)
    st = restorepoint.status()
    assert not st.enabled
    text = st.render()
    assert "Enable-ComputerRestore" in text, "no instructions given"
    assert "will not turn it on for you" in text, (
        "must not silently change system configuration")


def test_we_never_enable_protection_ourselves():
    src = Path(restorepoint.__file__).read_text(encoding="utf-8")
    for line in src.splitlines():
        if "Enable-ComputerRestore" in line:
            # Only ever quoted as advice, never executed.
            assert "_ps(" not in line and "run(" not in line, (
                "Phantom Tweeks executes Enable-ComputerRestore")


def test_rate_limit_gets_a_specific_explanation(monkeypatch):
    """Windows allows one point per 24h; a generic error would confuse."""
    monkeypatch.setattr(restorepoint, "IS_WINDOWS", True)
    monkeypatch.setattr(restorepoint, "is_admin", lambda: True)

    def run(cmd, **kw):
        if "Checkpoint-Computer" in " ".join(cmd):
            return types.SimpleNamespace(
                stdout="", returncode=1,
                stderr="cannot be created because one has already been "
                       "created within the past 1440 minutes.")
        return types.SimpleNamespace(stdout="For volume: (C:)", stderr="",
                                     returncode=0)

    monkeypatch.setattr(restorepoint.runproc, "run", run)
    ok, msg = restorepoint.create()
    assert not ok
    assert "24 hours" in msg
    assert "still" in msg.lower(), "does not reassure that backups still work"


def test_needs_admin_and_says_so(monkeypatch):
    monkeypatch.setattr(restorepoint, "IS_WINDOWS", True)
    monkeypatch.setattr(restorepoint, "is_admin", lambda: False)
    monkeypatch.setattr(restorepoint.runproc, "run",
                        _fake_run("For volume: (C:)"))
    ok, msg = restorepoint.create()
    assert not ok
    assert "administrator" in msg.lower()


def test_successful_creation(monkeypatch):
    monkeypatch.setattr(restorepoint, "IS_WINDOWS", True)
    monkeypatch.setattr(restorepoint, "is_admin", lambda: True)
    monkeypatch.setattr(restorepoint.runproc, "run",
                        _fake_run("For volume: (C:)"))
    ok, msg = restorepoint.create("Before Phantom Tweeks changes")
    assert ok
    assert "Before Phantom Tweeks changes" in msg


def test_list_points_never_raises(monkeypatch):
    monkeypatch.setattr(restorepoint, "IS_WINDOWS", True)
    monkeypatch.setattr(restorepoint.runproc, "run", _fake_run("not json at all"))
    assert restorepoint.list_points() == []


# ---------------------------------------------------------------- reports

def test_every_format_produces_output():
    report = reports.build()
    for fmt in reports.FORMATS:
        text = report.render(fmt)
        assert text and len(text) > 100, f"{fmt} export is empty"


def test_html_is_self_contained():
    """No external CSS: the file must render correctly when emailed."""
    html_out = reports.build().to_html()
    assert "<style>" in html_out, "styling is not inlined"
    assert "http://" not in html_out and "https://" not in html_out, (
        "the report references an external resource")


def test_html_is_well_formed():
    import html.parser

    class Strict(html.parser.HTMLParser):
        def error(self, message):
            raise ValueError(message)

    Strict().feed(reports.build().to_html())


def test_json_is_valid_and_structured():
    data = json.loads(reports.build().to_json())
    assert data["sections"], "no sections in the JSON export"
    assert "version" in data


def test_username_is_scrubbed():
    """A screenshot of a report is the easiest way to leak your own name."""
    import getpass
    try:
        user = getpass.getuser()
    except Exception:
        pytest.skip("no username available")
    if len(user) <= 2:
        pytest.skip("username too short to scrub safely")
    text = f"C:\\Users\\{user}\\AppData\\Local\\PhantomTweeks"
    scrubbed = reports._scrub(text)
    assert "<user>" in scrubbed, "the username was not replaced"
    # The account name must be gone as a standalone path segment. It may
    # legitimately survive inside another word - "Users" contains "user" when
    # the account is named "user", and mangling that would corrupt the path.
    assert f"\\{user}\\" not in scrubbed, "the username survived as a path part"
    assert "Users" in scrubbed, "scrubbing corrupted an unrelated word"


def test_scrub_does_not_mangle_similar_words():
    """A plain string replace turned C:\\Users\\user into C:\\<user>s\\<user>."""
    assert reports._scrub("Users and groups") == "Users and groups"
    assert reports._scrub("username") == "username"


def test_unsupported_format_is_rejected(tmp_path):
    ok, msg = reports.save(tmp_path / "x.docx")
    assert not ok
    assert "Unsupported" in msg


def test_save_writes_the_file(tmp_path):
    target = tmp_path / "sub" / "report.md"
    ok, msg = reports.save(target)
    assert ok, msg
    assert target.is_file()
    assert "not uploaded" in msg.lower()


def test_reports_never_upload_anything():
    src = Path(reports.__file__).read_text(encoding="utf-8")
    for banned in ("urlopen", "requests.", "socket.", "http.client"):
        assert banned not in src, f"reports module references {banned}"


def test_export_feature_points_at_a_real_page():
    from phantom_tweeks.core import features
    from phantom_tweeks.gui import app_window
    f = features.get("export_reports")
    assert f is not None
    assert f.page in dict(app_window.NAV), (
        f"export_reports links to '{f.page}', which is not a real page")
