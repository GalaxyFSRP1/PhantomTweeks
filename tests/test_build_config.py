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
SPEC = ROOT / "packaging" / "PhantomTweeks.spec"
ISS = ROOT / "packaging" / "installer.iss"


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
    launcher = ROOT / "packaging" / "phantom_launcher.py"
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
    launcher = ROOT / "packaging" / "phantom_launcher.py"
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


# ---------------------------------------------------- website accessibility

def _pages():
    return sorted((ROOT / "website").glob("*.html"))


def test_every_page_has_a_working_skip_link():
    """Keyboard users must be able to bypass the nav on every page."""
    for page in _pages():
        text = page.read_text(encoding="utf-8")
        assert 'class="skip-link"' in text, f"{page.name} has no skip link"
        assert 'id="main"' in text, f"{page.name} has no #main target"


def test_focus_styles_exist():
    """The default focus ring is invisible on this dark theme."""
    css = (ROOT / "website" / "assets" / "style.css").read_text(encoding="utf-8")
    assert ":focus-visible" in css, "no keyboard focus styling"
    assert "outline" in css


def test_reduced_motion_is_respected():
    css = (ROOT / "website" / "assets" / "style.css").read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in css, (
        "animations ignore the OS reduce-motion setting")


def test_stylesheet_braces_are_balanced():
    css = (ROOT / "website" / "assets" / "style.css").read_text(encoding="utf-8")
    assert css.count("{") == css.count("}"), "unbalanced CSS braces"


def test_pages_are_well_formed():
    import html.parser

    class Strict(html.parser.HTMLParser):
        def error(self, message):
            raise ValueError(message)

    for page in _pages():
        Strict().feed(page.read_text(encoding="utf-8"))


# ------------------------------------------------------- version consistency

def _declared_version():
    import re
    text = (ROOT / "src" / "phantom_tweeks" / "branding.py").read_text(encoding="utf-8")
    m = re.search(r'VERSION\s*=\s*"([^"]+)"', text)
    assert m, "branding.py does not declare a VERSION"
    return m.group(1)


def test_version_is_consistent_everywhere():
    """A mismatch silently breaks the updater.

    The app compares its own VERSION against the version the release API
    reports. If the installer, the .exe metadata and branding.py disagree,
    users get told they are out of date forever, or never told at all.
    """
    version = _declared_version()
    checks = {
        "pyproject.toml": f'version = "{version}"',
        "packaging/installer.iss": f'#define AppVersion     "{version}"',
        "docs/EULA.txt": f"Version {version}",
    }
    for rel, needle in checks.items():
        path = ROOT / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        assert needle in text, f"{rel} does not declare version {version}"


def test_windows_version_resource_matches():
    """PyInstaller stamps this into the .exe; Explorer shows it."""
    version = _declared_version()
    text = (ROOT / "version_info.txt").read_text(encoding="utf-8")
    assert f"'{version}.0'" in text, (
        f"version_info.txt does not carry {version} - the .exe would report "
        "the wrong version in its file properties")


def test_changelog_documents_the_current_version():
    path = ROOT / "CHANGELOG.md"
    if not path.is_file():
        pytest.skip("no changelog")
    version = _declared_version()
    assert f"## {version}" in path.read_text(encoding="utf-8"), (
        f"CHANGELOG.md has no entry for {version}")


def test_the_website_does_not_advertise_an_older_version():
    """Static fallback text shown before the API responds."""
    version = _declared_version()
    for name in ("index.html", "download.html"):
        page = ROOT / "website" / name
        if not page.is_file():
            continue
        text = page.read_text(encoding="utf-8")
        if "Version 0." in text or "version 0." in text:
            assert version in text, (
                f"website/{name} advertises a version other than {version}")


# --------------------------------------------- deployment / version drift

def test_vercelignore_does_not_exclude_the_website_stylesheet():
    """A bare 'assets/' also matches website/assets/.

    That removed style.css from the deployment and left the live site
    completely unstyled, while everything looked fine locally.
    """
    path = ROOT / ".vercelignore"
    if not path.is_file():
        pytest.skip("no .vercelignore")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # An unanchored directory pattern matches at every depth.
        assert not (line.rstrip("/") == "assets" and not line.startswith("/")), (
            "'assets/' is unanchored and will also exclude website/assets/. "
            "Use '/assets/' to anchor it to the repository root.")


def test_website_assets_are_deployable():
    """Every stylesheet referenced by a page must survive deployment."""
    import fnmatch
    path = ROOT / ".vercelignore"
    patterns = []
    if path.is_file():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#"):
                patterns.append(line)

    def ignored(rel: str) -> bool:
        for pat in patterns:
            anchored = pat.startswith("/")
            p = pat.lstrip("/").rstrip("/")
            if anchored:
                if rel == p or rel.startswith(p + "/"):
                    return True
            else:
                parts = rel.split("/")
                for i, _ in enumerate(parts):
                    if fnmatch.fnmatch(parts[i], p):
                        return True
                    if "/".join(parts[i:]) == p:
                        return True
        return False

    css = ROOT / "website" / "assets" / "style.css"
    assert css.is_file(), "the stylesheet is missing from the repository"
    assert not ignored("website/assets/style.css"), (
        "website/assets/style.css is excluded from the deployment - the live "
        "site would render with no styling at all")


def test_pages_reference_a_stylesheet_that_exists():
    for page in sorted((ROOT / "website").glob("*.html")):
        text = page.read_text(encoding="utf-8")
        for href in re.findall(r'<link[^>]+href="([^"]+\.css)"', text):
            target = (ROOT / "website" / href.lstrip("/")).resolve()
            assert target.is_file(), f"{page.name} links to missing {href}"


def test_build_script_does_not_hardcode_the_version():
    """build.ps1 hard-coded 0.1.2 and went stale.

    A v0.1.4 release shipped an asset called PhantomTweeks-0.1.2.msi, so users
    downloaded an installer for a version that was three releases old.
    """
    ps1 = (ROOT / "build.ps1").read_text(encoding="utf-8-sig")
    version = _declared_version()
    for line in ps1.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if re.match(r'^\$Version\s*=\s*"[\d.]+"', stripped):
            pytest.fail(
                f"build.ps1 hard-codes a version ({stripped}). It must read "
                "VERSION from branding.py or it will silently go stale.")
    assert "branding.py" in ps1, (
        "build.ps1 never reads branding.py, so the MSI filename cannot track "
        f"the real version ({version})")


def test_nav_download_button_has_readable_text():
    """".nav-links a" is more specific than ".btn-primary".

    That made the nav Download button render muted grey on a teal background -
    the most prominent call to action on the site was nearly illegible.
    """
    css = (ROOT / "website" / "assets" / "style.css").read_text(encoding="utf-8")
    assert ".nav-links a.btn-primary" in css, (
        "no rule restores the button text colour inside the nav")


def test_pages_carry_a_critical_css_fallback():
    """If the stylesheet fails to deploy, pages must still be readable.

    This exact failure happened: .vercelignore excluded website/assets/ and
    the live site served raw unstyled HTML.
    """
    for page in sorted((ROOT / "website").glob("*.html")):
        text = page.read_text(encoding="utf-8")
        if "style.css" not in text:
            continue
        assert "Critical fallback" in text, (
            f"{page.name} has no inline fallback; a missing stylesheet would "
            "leave it completely unstyled")
        inline = text.index("Critical fallback")
        link = text.index('href="assets/style.css"')
        assert inline < link, (
            f"{page.name}: the inline fallback must come before the external "
            "stylesheet so the file wins when it loads")
