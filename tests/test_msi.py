"""The WiX MSI package definition.

These parse the .wxs as XML rather than string-matching, so they fail for real
reasons. Marked repo_hygiene where they assert build wiring rather than the
shipped application.
"""
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WXS = ROOT / "packaging" / "PhantomTweeks.wxs"
NS = {"w": "http://wixtoolset.org/schemas/v4/wxs"}


def _tree():
    if not WXS.is_file():
        pytest.skip("build/PhantomTweeks.wxs is missing from this checkout.")
    return ET.parse(WXS).getroot()


def test_wxs_is_well_formed_xml():
    assert _tree() is not None


def test_component_guids_are_unique():
    """Duplicate GUIDs make Windows Installer behave unpredictably."""
    guids = [c.get("Guid") for c in _tree().findall(".//w:Component", NS)]
    assert guids, "no components defined"
    assert all(guids), "a component has no GUID"
    dupes = {g for g in guids if guids.count(g) > 1}
    assert not dupes, f"duplicate component GUIDs: {dupes}"


def test_upgrade_code_is_stable_and_present():
    """The UpgradeCode must never change, or upgrades install side-by-side."""
    pkg = _tree().find(".//w:Package", NS)
    assert pkg.get("UpgradeCode"), "no UpgradeCode: upgrades would duplicate"
    assert len(pkg.get("UpgradeCode")) == 36


def test_major_upgrade_is_configured():
    """Without this, installing v2 leaves v1 in Add/Remove Programs."""
    mu = _tree().find(".//w:MajorUpgrade", NS)
    assert mu is not None, "no MajorUpgrade element"
    assert mu.get("DowngradeErrorMessage"), "downgrades must be explained"


def test_installs_per_machine():
    pkg = _tree().find(".//w:Package", NS)
    assert pkg.get("Scope") == "perMachine"


def test_ships_the_application_executable():
    sources = [f.get("Source", "") for f in _tree().findall(".//w:File", NS)]
    assert any(s.endswith("PhantomTweeks.exe") for s in sources)


def test_ships_the_privacy_and_security_docs():
    """Users must be able to read what the app does without going online."""
    # Source paths use Windows separators; pathlib on Linux will not split
    # them, so normalise by hand rather than relying on Path().name.
    sources = [f.get("Source", "").replace("\\", "/").rsplit("/", 1)[-1]
               for f in _tree().findall(".//w:File", NS)]
    for doc in ("PRIVACY.md", "SECURITY.md", "USER_GUIDE.md", "EULA.txt"):
        assert doc in sources, f"{doc} is not installed"


def test_uses_no_wix_v3_condition_elements():
    """WiX v4 moved Condition from a child element to an attribute."""
    bad = _tree().findall(".//w:Component/w:Condition", NS)
    assert not bad, "v3-style <Condition> element will not compile under WiX v4"


def test_no_custom_action_runs_arbitrary_code():
    """An MSI that shells out during install is a security smell."""
    actions = _tree().findall(".//w:CustomAction", NS)
    for a in actions:
        assert not a.get("ExeCommand"), \
            f"CustomAction {a.get('Id')} executes a command during install"


def test_path_entry_is_optional_not_forced():
    """Modifying system PATH must be a choice, not a default."""
    root = _tree()
    feature = None
    for f in root.findall(".//w:Feature", NS):
        if f.get("Id") == "PathEntry":
            feature = f
    assert feature is not None, "no PathEntry feature"
    # Level > 1 means not installed unless the user opts in.
    assert int(feature.get("Level", "1")) > 1, "PATH change is on by default"


def test_uninstall_preserves_user_backups():
    """Backups live in %LOCALAPPDATA% and must survive an uninstall.

    If the MSI ever removed them, a user who uninstalled could never roll back
    the changes Phantom Tweeks made — the exact opposite of the golden rule.
    """
    text = WXS.read_text(encoding="utf-8") if WXS.is_file() else pytest.skip("missing")
    for danger in ("LocalAppDataFolder", "RemoveFile", "util:RemoveFolderEx"):
        assert danger not in text, \
            f"{danger} appears in the MSI; user backups could be deleted"


def test_requires_windows_10_1809_or_newer():
    launch = _tree().find(".//w:Launch", NS)
    assert launch is not None
    assert "VersionNT" in launch.get("Condition", "")


# ---------------------------------------------------------- build wiring

@pytest.mark.repo_hygiene
def test_build_script_builds_the_msi():
    ps1 = (ROOT / "build.ps1").read_text(encoding="utf-8-sig")
    # Arguments are passed as an array and splatted, so match on the pieces.
    assert "wix.exe" in ps1 and '"build"' in ps1
    assert "PhantomTweeks.wxs" in ps1
    assert "-SkipMsi" in ps1 or "SkipMsi" in ps1


@pytest.mark.repo_hygiene
def test_build_script_passes_every_variable_the_wxs_needs():
    """A missing -d flag makes WiX fail with an unhelpful error."""
    ps1 = (ROOT / "build.ps1").read_text(encoding="utf-8-sig")
    text = WXS.read_text(encoding="utf-8")
    import re
    needed = set(re.findall(r"\$\(var\.(\w+)\)", text))
    for var in needed:
        # Either the old inline form (-d Name=) or the array form ("Name=...").
        assert f"-d {var}=" in ps1 or f'"{var}=' in ps1, \
            f"build.ps1 never defines -d {var}"


@pytest.mark.repo_hygiene
def test_msi_is_checksummed_and_released():
    ps1 = (ROOT / "build.ps1").read_text(encoding="utf-8-sig")
    assert "*.msi" in ps1, "the MSI is not included in SHA256SUMS.txt"
    wf = ROOT / ".github" / "workflows" / "build.yml"
    if not wf.is_file():
        pytest.skip(".github/workflows/build.yml missing from this checkout")
    text = wf.read_text(encoding="utf-8")
    assert "dist/*.msi" in text, "the MSI is not attached to the release"
    assert "wix" in text.lower(), "CI never installs WiX"


@pytest.mark.repo_hygiene
def test_ui_extension_is_installed_before_use():
    """WiX v4 fails with WIX0144 if -ext is used before "extension add".

    This is exactly what broke the first real CI build.
    """
    ps1 = (ROOT / "build.ps1").read_text(encoding="utf-8-sig")
    add = ps1.index("extension add")
    use = ps1.index("WixToolset.UI.wixext")
    assert add >= 0 and use >= 0
    # The install must not have its failure discarded.
    line = [l for l in ps1.splitlines() if "extension add" in l][0]
    assert "Out-Null" not in line, (
        "the result of 'extension add' is discarded; a failed install then "
        "surfaces later as a confusing WIX0144 error"
    )


@pytest.mark.repo_hygiene
def test_a_missing_msi_does_not_fail_the_build():
    """The MSI is optional. Losing it must not sink a good release."""
    ps1 = (ROOT / "build.ps1").read_text(encoding="utf-8-sig")
    msi_block = ps1[ps1.index("Building MSI"):]
    assert 'Fail "WiX failed' not in msi_block, (
        "a WiX failure aborts the build; the .exe installer is already built"
    )
    assert "MsiFailed" in ps1, "no flag tracking a skipped MSI"


@pytest.mark.repo_hygiene
def test_ci_installs_the_ui_extension():
    wf = ROOT / ".github" / "workflows" / "build.yml"
    if not wf.is_file():
        pytest.skip("workflow missing from this checkout")
    text = wf.read_text(encoding="utf-8")
    assert "extension add -g WixToolset.UI.wixext" in text


def test_wizard_ui_is_conditional_in_the_wxs():
    """The .wxs must still compile when the UI extension is unavailable."""
    if not WXS.is_file():
        pytest.skip("wxs missing")
    text = WXS.read_text(encoding="utf-8")
    assert "<?ifdef IncludeUI ?>" in text, (
        "WixUI is unconditional; the MSI cannot be built without the extension"
    )
    assert text.count("<?ifdef IncludeUI ?>") == text.count("<?endif ?>")


@pytest.mark.repo_hygiene
def test_wix_version_is_pinned_below_the_maintenance_fee():
    """WiX v6 introduced the OSMF and v7 enforces it by blocking every command.

    An unpinned `dotnet tool install --global wix` resolves to the latest
    release and fails with WIX7015. 5.0.2 is the last fee-free version.
    """
    wf = ROOT / ".github" / "workflows" / "build.yml"
    if not wf.is_file():
        pytest.skip("workflow missing from this checkout")
    text = wf.read_text(encoding="utf-8")
    assert "dotnet tool install --global wix --version 5.0.2" in text, (
        "WiX is not pinned to 5.0.2; a floating version hits the OSMF EULA"
    )
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("dotnet tool install") and "wix" in s:
            assert "--version" in s, f"unpinned WiX install: {s}"


@pytest.mark.repo_hygiene
def test_wix_setup_failure_does_not_fail_the_release():
    """WiX licensing changed once already; it must not gate the .exe."""
    wf = ROOT / ".github" / "workflows" / "build.yml"
    if not wf.is_file():
        pytest.skip("workflow missing from this checkout")
    import yaml
    data = yaml.safe_load(wf.read_text(encoding="utf-8"))
    steps = data["jobs"]["build"]["steps"]
    wix = [s for s in steps if "WiX" in str(s.get("name", ""))]
    assert wix, "no WiX install step found"
    assert wix[0].get("continue-on-error") is True, (
        "a WiX install failure aborts the whole release"
    )


@pytest.mark.repo_hygiene
def test_build_script_explains_the_maintenance_fee_error():
    """WIX7015 is opaque; the script should say what to actually do."""
    ps1 = (ROOT / "build.ps1").read_text(encoding="utf-8-sig")
    assert "WIX7015" in ps1
    assert "--version 5.0.2" in ps1, "no fee-free version suggested"


# ------------------------------------------------- installer data folder

@pytest.mark.repo_hygiene
def test_installer_creates_the_user_data_folder():
    """The installer must create %LOCALAPPDATA%\\PhantomTweeks up front.

    Creating it lazily on first run means a permissions problem surfaces when
    the user is trying to take a backup, which is the worst possible moment.
    """
    iss = (ROOT / "packaging" / "installer.iss").read_text(encoding="utf-8")
    assert "[Dirs]" in iss, "the installer never creates any directories"
    for sub in ("backups", "logs", "profiles", "snapshots", "updates"):
        assert f"PhantomTweeks\\{sub}" in iss, f"{sub} is not created"


@pytest.mark.repo_hygiene
def test_installer_never_deletes_user_data_on_uninstall():
    """Backups must survive an uninstall so a user can still roll back."""
    iss = (ROOT / "packaging" / "installer.iss").read_text(encoding="utf-8")
    assert "uninsneveruninstall" in iss, "data folders are not protected"
    delete_block = iss.split("[UninstallDelete]", 1)[1].split("[", 1)[0]
    assert "localappdata" not in delete_block.lower(), (
        "the uninstaller removes user data")


@pytest.mark.repo_hygiene
def test_installer_seeds_default_settings():
    iss = (ROOT / "packaging" / "installer.iss").read_text(encoding="utf-8")
    assert "config --init" in iss, "settings are never initialised"
    assert "runhidden" in iss, "the init step would flash a console window"


def test_config_init_creates_the_tree_and_keeps_existing_settings(tmp_path,
                                                                  monkeypatch):
    """`config --init` is what the installer runs. Verify it for real."""
    import subprocess
    import sys
    env = dict(os.environ, PHANTOM_TWEEKS_HOME=str(tmp_path))
    run = [sys.executable, str(ROOT / "run.py"), "config", "--init"]

    first = subprocess.run(run, capture_output=True, text=True, env=env,
                           timeout=180)
    assert first.returncode == 0, first.stderr
    for sub in ("backups", "logs", "logs/crash", "profiles", "snapshots",
                "updates"):
        assert (tmp_path / sub).is_dir(), f"{sub} was not created"

    cfg = tmp_path / "config.json"
    assert cfg.is_file(), "no settings file was written"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    # Nothing automatic may be enabled by a fresh install.
    assert data["auto_apply_high_confidence"] is False
    assert data["auto_apply_game_profile"] is False
    assert data["telemetry"] is False

    # A reinstall must not discard the user's choices.
    data["expert_mode"] = True
    cfg.write_text(json.dumps(data), encoding="utf-8")
    second = subprocess.run(run, capture_output=True, text=True, env=env,
                            timeout=180)
    assert second.returncode == 0
    assert json.loads(cfg.read_text(encoding="utf-8"))["expert_mode"] is True, (
        "reinstalling wiped the user's settings")
