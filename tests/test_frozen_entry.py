"""Regressions for two bugs that reached a user's machine.

1. ``ImportError: attempted relative import with no known parent package``
   The frozen executable ran an entry script that used relative imports.
   PyInstaller executes its entry script as a top-level ``__main__`` with no
   parent package, so relative imports are guaranteed to fail there.

2. Console windows flashing on screen.
   A windowed (``console=False``) build that calls ``subprocess.run`` gets a
   new console allocated for each child process. The hardware monitor polls
   on a timer, so this was a black box flashing every few seconds - and it
   can steal focus from a fullscreen game.
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PKG = SRC / "phantom_tweeks"
ENTRIES = [PKG / "__main__.py", ROOT / "build" / "phantom_launcher.py"]


# ------------------------------------------------------- relative imports

@pytest.mark.parametrize("entry", ENTRIES, ids=lambda p: p.name)
def test_entry_points_use_no_relative_imports(entry: Path):
    """Relative imports in an entry script break the frozen build."""
    tree = ast.parse(entry.read_text(encoding="utf-8"))
    bad = [f"line {n.lineno}: level-{n.level} relative import"
           for n in ast.walk(tree)
           if isinstance(n, ast.ImportFrom) and (n.level or 0) > 0]
    assert not bad, (
        f"{entry.name} uses relative imports:\n  " + "\n  ".join(bad) +
        "\nPyInstaller runs the entry script with no parent package, so these "
        "raise ImportError in the packaged app."
    )


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda p: p.name)
def test_entry_point_runs_as_a_bare_script(entry: Path):
    """Executing the file directly must work, with no package context.

    This is the closest reproduction of the frozen environment available
    without building an executable.
    """
    proc = subprocess.run([sys.executable, str(entry), "--help"],
                          capture_output=True, text=True, timeout=120,
                          cwd=str(ROOT))
    combined = proc.stdout + proc.stderr
    assert "attempted relative import" not in combined, (
        f"{entry.name} still fails with a relative-import error:\n{combined}"
    )
    assert proc.returncode == 0, f"{entry.name} exited {proc.returncode}:\n{combined}"


def test_module_invocation_still_works():
    proc = subprocess.run([sys.executable, "-m", "phantom_tweeks", "--help"],
                          capture_output=True, text=True, timeout=120,
                          cwd=str(SRC))
    assert proc.returncode == 0, proc.stderr


def test_spec_builds_the_launcher_not_the_package_main():
    """The spec must point at the standalone launcher."""
    spec = (ROOT / "build" / "PhantomTweeks.spec").read_text(encoding="utf-8")
    assert "phantom_launcher.py" in spec
    assert "phantom_tweeks/__main__.py" not in spec.replace("\\", "/"), (
        "the spec targets the package __main__, which cannot work frozen"
    )


# ------------------------------------------------------- console windows

def _source_files() -> list[Path]:
    return [p for p in PKG.rglob("*.py") if "__pycache__" not in str(p)]


def test_no_module_calls_subprocess_directly():
    """Every external command must go through core.runproc.

    A direct subprocess call in a windowed build flashes a console window.
    """
    offenders = []
    for path in _source_files():
        if path.name == "runproc.py":
            continue                     # the one place allowed to call it
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.search(r"\bsubprocess\.(run|Popen|call|check_output|check_call)\(",
                         stripped):
                offenders.append(f"{path.relative_to(ROOT)}:{i}: {stripped[:70]}")
    assert not offenders, (
        "these call subprocess directly and will flash a console window:\n  "
        + "\n  ".join(offenders)
        + "\nUse core.runproc.run() instead."
    )


def test_runproc_requests_a_hidden_window(monkeypatch):
    """Verify the actual flags, not just that the helper exists."""
    sys.path.insert(0, str(SRC))
    import importlib
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(subprocess, "STARTF_USESHOWWINDOW", 1, raising=False)

    class FakeSI:
        def __init__(self):
            self.dwFlags = 0
            self.wShowWindow = None
    monkeypatch.setattr(subprocess, "STARTUPINFO", FakeSI, raising=False)

    from phantom_tweeks.core import runproc
    importlib.reload(runproc)            # picks up the patched sys.platform
    assert runproc.IS_WINDOWS

    captured = {}

    def spy(cmd, **kw):
        captured.update(kw)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", spy)
    runproc.run(["powercfg", "/getactivescheme"])

    assert captured.get("creationflags") == 0x08000000, "CREATE_NO_WINDOW not set"
    si = captured.get("startupinfo")
    assert si is not None, "no STARTUPINFO supplied"
    assert si.wShowWindow == 0, "child window is not hidden (SW_HIDE)"
    assert si.dwFlags & 1, "STARTF_USESHOWWINDOW not set"

    importlib.reload(runproc)            # restore real module state


def test_runproc_degrades_safely_off_windows():
    """The helper must be a no-op elsewhere, not a crash."""
    sys.path.insert(0, str(SRC))
    from phantom_tweeks.core import runproc
    kw = runproc.hidden_kwargs()
    assert isinstance(kw, dict)
    out = runproc.output([sys.executable, "-c", "print('hello')"], timeout=60)
    assert "hello" in out


def test_runproc_output_swallows_failures():
    """A missing tool means 'information unavailable', never a crash."""
    sys.path.insert(0, str(SRC))
    from phantom_tweeks.core import runproc
    assert runproc.output(["definitely-not-a-real-command-xyz"],
                          default="n/a") == "n/a"


def test_gui_build_is_windowed():
    """console=False is what makes the console-window fix necessary."""
    spec = (ROOT / "build" / "PhantomTweeks.spec").read_text(encoding="utf-8")
    assert re.search(r"console\s*=\s*False", spec), (
        "the GUI build must not open a console window"
    )


# ------------------------------------------------- WMI cost control
#
# `PhantomTweeks.exe hardware` appeared to hang in CI. Cause: every WMI query
# launches a PowerShell process, nothing was cached, and the per-query timeout
# was 20s. Several queries per command, several commands per run.

def _monitor(monkeypatch):
    sys.path.insert(0, str(SRC))
    from phantom_tweeks.hardware import monitor
    monkeypatch.setattr(monitor, "IS_WINDOWS", True)
    monkeypatch.setattr(monitor.shutil, "which", lambda n: "powershell")
    monitor.reset_wmi_cache()
    return monitor


def test_repeated_wmi_queries_launch_powershell_once(monkeypatch):
    """Hardware inventory does not change while the app is open."""
    import types
    monitor = _monitor(monkeypatch)
    calls = []

    def fake(cmd, **kw):
        calls.append(cmd)
        return types.SimpleNamespace(stdout='{"Name":"CPU"}', returncode=0)

    monkeypatch.setattr(monitor.runproc, "run", fake)
    for _ in range(5):
        monitor._wmi_query("root/cimv2", "SELECT Name FROM Win32_Processor",
                           ["Name"])
    assert len(calls) == 1, f"{len(calls)} PowerShell launches for one query"


def test_wmi_has_a_total_time_budget(monkeypatch):
    """A slow provider must not compound across many queries."""
    import time as _time
    import types
    monitor = _monitor(monkeypatch)
    monkeypatch.setattr(monitor, "_WMI_BUDGET_S", 2.0)
    calls = []

    def slow(cmd, **kw):
        calls.append(cmd)
        _time.sleep(0.5)
        return types.SimpleNamespace(stdout="{}", returncode=0)

    monkeypatch.setattr(monitor.runproc, "run", slow)
    started = _time.monotonic()
    for i in range(30):
        monitor._wmi_query("root/cimv2", f"SELECT C{i} FROM T", ["C"])
    elapsed = _time.monotonic() - started
    assert elapsed < 6, f"the budget did not cap WMI cost ({elapsed:.1f}s)"
    assert len(calls) < 30, "every query ran despite the budget"


def test_a_failed_wmi_query_is_not_retried(monkeypatch):
    """Retrying a broken provider is what turns slow into 'hung'."""
    import subprocess as sp
    monitor = _monitor(monkeypatch)
    calls = []

    def boom(cmd, **kw):
        calls.append(cmd)
        raise sp.TimeoutExpired(cmd, 5)

    monkeypatch.setattr(monitor.runproc, "run", boom)
    for _ in range(10):
        assert monitor._wmi_query("root/cimv2", "SELECT A FROM B", ["A"]) == []
    assert len(calls) == 1, "a failing query was retried"


def test_wmi_timeout_is_short_enough_to_stay_responsive():
    sys.path.insert(0, str(SRC))
    from phantom_tweeks.hardware import monitor
    assert monitor._WMI_TIMEOUT_S <= 10, (
        "a single WMI query may stall a command for too long")


@pytest.mark.repo_hygiene
def test_ci_smoke_test_cannot_hang():
    """A hanging smoke test burns the job timeout and reports nothing."""
    wf = ROOT / ".github" / "workflows" / "build.yml"
    if not wf.is_file():
        pytest.skip("workflow missing from this checkout")
    text = wf.read_text(encoding="utf-8")
    assert "Wait-Job" in text and "-Timeout" in text, (
        "the exe smoke test has no per-command time limit")
    assert "PHANTOM_WMI_BUDGET" in text, "CI does not cap WMI cost"
