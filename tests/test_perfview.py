"""Tests for the consolidated performance view and the packaging layout."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from phantom_tweeks.engine import perfview  # noqa: E402


def test_report_builds_without_raising():
    """Every section must degrade to a note rather than propagate."""
    report = perfview.build()
    assert report.sections
    assert report.render()


def test_every_expected_section_is_present():
    titles = {s.title for s in perfview.build().sections}
    for expected in ("PROCESSOR", "GRAPHICS", "MEMORY", "STORAGE", "NETWORK",
                     "HEAVIEST PROCESSES"):
        assert expected in titles, f"{expected} missing from the report"


def test_unmeasurable_values_say_so_rather_than_guessing():
    r = perfview.Reading("Temperature", None, " C")
    assert "not measured" in r.render()


def test_storage_lists_every_drive(monkeypatch):
    """The whole point: secondary drives must appear, not just C:."""
    class Disk:
        def __init__(self, mp, total, free, media):
            self.mountpoint, self.device = mp, mp
            self.total_gb, self.free_gb = total, free
            self.percent_used = (1 - free / total) * 100
            self.media_type, self.health = media, "Healthy"
            self.read_mb_s = self.write_mb_s = self.temperature_c = None

    class Report:
        disks = [Disk("C:", 500, 100, "SSD"), Disk("D:", 2000, 900, "HDD"),
                 Disk("E:", 1000, 50, "SSD")]
        physical = [{"media_type": "HDD", "name": "ST2000"}]

    from phantom_tweeks.engine import storage
    monkeypatch.setattr(storage, "scan", lambda: Report())
    text = perfview.storage_section().render()
    for drive in ("C:", "D:", "E:"):
        assert drive in text, f"{drive} is missing from the storage view"


def test_a_nearly_full_drive_is_flagged(monkeypatch):
    class Disk:
        mountpoint = device = "E:"
        total_gb, free_gb = 1000.0, 20.0
        percent_used = 98.0
        media_type, health = "SSD", "Healthy"
        read_mb_s = write_mb_s = temperature_c = None

    class Report:
        disks = [Disk()]
        physical = []

    from phantom_tweeks.engine import storage
    monkeypatch.setattr(storage, "scan", lambda: Report())
    section = perfview.storage_section()
    assert section.worst in ("warn", "bad"), "a 98%-full drive was not flagged"


def test_failing_smart_status_is_reported_as_hardware(monkeypatch):
    class Disk:
        mountpoint = device = "D:"
        total_gb, free_gb, percent_used = 1000.0, 500.0, 50.0
        media_type = "HDD"
        health = "Warning"
        read_mb_s = write_mb_s = temperature_c = None

    class Report:
        disks = [Disk()]
        physical = []

    from phantom_tweeks.engine import storage
    monkeypatch.setattr(storage, "scan", lambda: Report())
    text = perfview.storage_section().render().lower()
    assert "back up" in text, "a failing drive does not tell the user to back up"
    assert "hardware" in text


def test_process_section_never_kills_anything():
    src = Path(perfview.__file__).read_text(encoding="utf-8")
    for banned in ("terminate(", ".kill(", "suspend(", "nice("):
        assert banned not in src, f"perfview calls {banned}"


def test_report_states_when_nothing_is_wrong():
    """"Everything is fine" must be a real, stated outcome."""
    report = perfview.PerfReport(sections=[perfview.Section("X")])
    assert "Nothing needs attention" in report.render()


# ------------------------------------------------------------- packaging

@pytest.mark.repo_hygiene
def test_packaging_directory_is_used_not_build():
    """A directory literally named 'build' is excluded from workspace
    snapshots, so the installer and spec files kept vanishing. They live in
    packaging/ now."""
    assert (ROOT / "packaging").is_dir(), "packaging/ is missing"
    for name in ("installer.iss", "PhantomTweeks.spec", "PhantomTweeks.wxs",
                 "phantom_launcher.py", "updater_launcher.py", "Updater.spec"):
        assert (ROOT / "packaging" / name).is_file(), f"packaging/{name} missing"


@pytest.mark.repo_hygiene
def test_build_script_points_at_packaging():
    ps1 = (ROOT / "build.ps1").read_text(encoding="utf-8-sig")
    for needle in ("packaging\\PhantomTweeks.spec", "packaging\\installer.iss",
                   "packaging\\phantom_launcher.py", "packaging\\Updater.spec"):
        assert needle in ps1, f"build.ps1 does not reference {needle}"


@pytest.mark.repo_hygiene
def test_installer_ships_the_updater_and_an_uninstall_shortcut():
    iss = (ROOT / "packaging" / "installer.iss").read_text(encoding="utf-8")
    assert "Update.exe" in iss, "Update.exe is never installed"
    assert iss.count("{uninstallexe}") >= 1, "no uninstaller shortcut"
    # Inno rejects duplicate [Icons] entries.
    assert iss.count('Name: "{group}\\Uninstall') == 1, (
        "duplicate uninstall shortcut - Inno Setup will refuse to compile")


@pytest.mark.repo_hygiene
def test_updater_uses_absolute_imports():
    """PyInstaller runs an entry script with no parent package."""
    import ast
    tree = ast.parse((ROOT / "packaging" / "updater_launcher.py")
                     .read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.level or 0), (
                f"relative import at line {node.lineno} breaks the frozen build")


@pytest.mark.repo_hygiene
def test_updater_never_executes_what_it_downloads():
    src = (ROOT / "packaging" / "updater_launcher.py").read_text(encoding="utf-8")
    for banned in ("os.startfile", "Popen", "os.system", "os.execv"):
        assert banned not in src, f"the updater may run a payload: {banned}"
