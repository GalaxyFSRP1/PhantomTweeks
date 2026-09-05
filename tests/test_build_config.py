"""Guards on the Windows build configuration.

These are cheap static checks. They exist because a broken build.ps1 costs a
full Windows build cycle to discover, and one real failure already shipped:
`--onefile` was passed alongside a .spec file, which PyInstaller rejects.
"""
from __future__ import annotations

import os
import pathlib
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILD_PS1 = ROOT / "build.ps1"
SPEC = ROOT / "build" / "PhantomTweeks.spec"
ISS = ROOT / "build" / "installer.iss"


def _ps1() -> str:
    return BUILD_PS1.read_text(encoding="utf-8", errors="replace")


def test_build_script_exists():
    assert BUILD_PS1.is_file()
    assert SPEC.is_file()


@pytest.mark.parametrize("flag", ["--onefile", "--onedir", "--name", "--icon",
                                  "--windowed", "--noconsole", "--add-data"])
def test_no_makespec_flags_passed_with_spec_file(flag):
    """PyInstaller errors out if makespec options accompany a .spec file.

    'ERROR: option(s) not allowed: --onedir/--onefile
     makespec options not valid when a .spec file is given'
    """
    for line in _ps1().splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue          # comments may legitimately mention the flags
        if flag in stripped:
            pytest.fail(f"build.ps1 passes {flag} alongside a .spec file: {stripped}")


def test_spec_builds_a_single_file_exe():
    """No COLLECT step means binaries+datas are folded into the EXE itself."""
    src = SPEC.read_text(encoding="utf-8")
    assert "COLLECT(" not in src, "spec has a COLLECT step; it is no longer one-file"
    exe_call = src[src.index("exe = EXE("):]
    for part in ("a.scripts", "a.binaries", "a.datas"):
        assert part in exe_call, f"{part} missing from EXE(); output would not be one-file"


def test_both_builds_use_separate_workpaths():
    """Shared workpaths let one build reuse the other's cached analysis."""
    paths = re.findall(r"--workpath\s+(\([^)]*\)|\S+)", _ps1())
    assert len(paths) >= 2, f"expected two builds, found {paths}"
    assert len(set(paths)) == len(paths), f"workpaths collide: {paths}"


def test_build_verifies_artifacts_exist():
    """A zero exit code is not proof the EXE was written."""
    s = _ps1()
    for exe in ("PhantomTweeks.exe", "PhantomTweeks-Portable.exe"):
        assert f'Test-Path (Join-Path $Dist "{exe}")' in s, \
            f"build.ps1 never confirms {exe} was actually produced"


def test_portable_flag_is_detectable_at_runtime():
    """A build-time env var does not survive into the running EXE.

    If the portable build cannot tell it is portable, it writes to
    %LOCALAPPDATA% exactly like the installed build and is not portable.
    """
    spec = SPEC.read_text(encoding="utf-8")
    assert "portable.flag" in spec, "spec bakes no runtime portable marker"

    from phantom_tweeks.core import paths
    assert hasattr(paths, "is_portable")
    assert "portable.flag" in paths.is_portable.__doc__ or \
           "portable.flag" in Path(paths.__file__).read_text(encoding="utf-8")


def test_portable_build_stores_data_beside_executable(tmp_path, monkeypatch):
    import importlib
    import sys

    mei = tmp_path / "mei"
    mei.mkdir()
    (mei / "portable.flag").write_text("x")
    exedir = tmp_path / "usbstick"
    exedir.mkdir()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(mei), raising=False)
    monkeypatch.setattr(sys, "executable",
                        str(exedir / "PhantomTweeks-Portable.exe"))

    from phantom_tweeks.core import paths
    importlib.reload(paths)
    try:
        assert paths.is_portable() is True
        assert paths.ROOT.parent == exedir, paths.ROOT
        # Assert the real intent: data lives beside the EXE, not in the
        # per-user install location.
        #
        # Two earlier attempts were wrong, for instructive reasons:
        #   * `"AppData" not in str(ROOT)` — a GitHub Windows runner puts
        #     tmp_path under C:\Users\runneradmin\AppData\Local\Temp, so the
        #     correct behaviour tripped the assertion.
        #   * `not startswith(LOCALAPPDATA)` — same problem: the temp dir is
        #     itself *inside* %LOCALAPPDATA%.
        # What actually matters is that the path is the portable one, so
        # compare against what the non-portable branch would have produced.
        assert paths.ROOT == exedir / "PhantomTweeksData"
        local = os.environ.get("LOCALAPPDATA")
        if local:
            installed = pathlib.Path(local) / "PhantomTweeks"
            assert paths.ROOT != installed
    finally:
        monkeypatch.undo()
        importlib.reload(paths)


def test_installed_build_is_not_portable(tmp_path, monkeypatch):
    import importlib
    import sys

    mei = tmp_path / "mei"
    mei.mkdir()                       # no portable.flag
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(mei), raising=False)
    monkeypatch.delenv("PHANTOM_TWEEKS_PORTABLE", raising=False)

    from phantom_tweeks.core import paths
    importlib.reload(paths)
    try:
        assert paths.is_portable() is False
    finally:
        monkeypatch.undo()
        importlib.reload(paths)


def test_build_refuses_to_ship_failing_tests():
    s = _ps1()
    assert "Refusing to build a release from a failing tree" in s


def test_installer_version_matches_app_version():
    from phantom_tweeks import branding
    iss = ISS.read_text(encoding="utf-8")
    m = re.search(r'#define\s+AppVersion\s+"([^"]+)"', iss)
    assert m, "installer.iss defines no AppVersion"
    assert m.group(1) == branding.VERSION, (
        f"installer.iss says {m.group(1)}, package says {branding.VERSION}")


def test_installer_consumes_the_built_exe():
    iss = ISS.read_text(encoding="utf-8")
    assert r"..\dist\PhantomTweeks.exe" in iss
    assert r"OutputDir=..\dist" in iss


# ------------------------------------------------------- frozen entry point

def test_spec_entry_script_is_not_inside_the_package():
    """PyInstaller runs the entry script with no parent package.

    Pointing it at src/phantom_tweeks/__main__.py makes every relative import
    inside that file raise at startup:
        ImportError: attempted relative import with no known parent package
    This shipped once and broke the compiled EXE for every user.
    """
    src = SPEC.read_text(encoding="utf-8")
    m = re.search(r"Analysis\(\s*\[([^\]]+)\]", src, re.S)
    assert m, "could not find the Analysis entry script list"
    entry = m.group(1)
    assert "__main__.py" not in entry, (
        "spec uses the package __main__.py as its entry script; relative "
        "imports will fail in the frozen build")
    assert "phantom_launcher" in entry


def test_launcher_exists_and_uses_absolute_imports_only():
    launcher = ROOT / "build" / "phantom_launcher.py"
    assert launcher.is_file(), "frozen entry point is missing"
    text = launcher.read_text(encoding="utf-8")
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("from .") or s.startswith("import ."):
            pytest.fail(f"launcher uses a relative import: {s}")
    assert "phantom_tweeks" in text


def test_launcher_runs_as_a_bare_script(tmp_path):
    """Exactly how PyInstaller invokes it: as a top-level script."""
    import subprocess
    launcher = ROOT / "build" / "phantom_launcher.py"
    r = subprocess.run([sys.executable, str(launcher), "version"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert "Phantom Tweeks" in r.stdout
    assert "no known parent package" not in r.stderr


def test_package_main_also_survives_being_run_directly():
    import subprocess
    main = ROOT / "src" / "phantom_tweeks" / "__main__.py"
    r = subprocess.run([sys.executable, str(main), "version"],
                       capture_output=True, text=True, timeout=120)
    assert "no known parent package" not in r.stderr, r.stderr
    assert r.returncode == 0, r.stderr


def test_spec_collects_the_whole_package():
    """With the entry script outside the package, submodules need collecting."""
    src = SPEC.read_text(encoding="utf-8")
    assert "collect_submodules" in src
