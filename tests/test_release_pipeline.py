"""CI workflow, download proxy and release metadata endpoint.

Two very different kinds of test live here, and they are marked differently:

* **Product tests** (unmarked) — the download proxy and release-metadata code
  that actually ships and runs. These must always pass.
* **Repo-hygiene tests** (`@pytest.mark.repo_hygiene`) — assertions about
  `.github/workflows/build.yml`, `.vercelignore` and friends. These lint the
  *repository*, not the application.

`build.ps1` deselects the hygiene marker. A release build must not be blocked
because a CI config file is out of date or was never uploaded — that gate would
stop you shipping a perfectly good binary, which is exactly what happened.
Run them explicitly with:  pytest -m repo_hygiene
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"


def _workflow_or_skip() -> str:
    """Return the workflow text, or skip.

    Dotfiles (and `.github/`) are silently dropped by the GitHub web uploader,
    so this file is often absent or stale in a fresh checkout even though the
    application is fine.
    """
    if not WORKFLOW.is_file():
        pytest.skip(
            ".github/workflows/build.yml is missing from this checkout. "
            "The GitHub web uploader drops dot-directories; push with "
            "'git add -f .github' instead.")
    return WORKFLOW.read_text(encoding="utf-8")


def _workflow_yaml():
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(_workflow_or_skip())


def _load(name):
    spec = importlib.util.spec_from_file_location(
        f"pt_api_{name}", ROOT / "api" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ------------------------------------------------------------- workflow

@pytest.mark.repo_hygiene
def test_workflow_exists_and_parses():
    data = _workflow_yaml()
    assert data["jobs"]["build"]["runs-on"] == "windows-latest"


@pytest.mark.repo_hygiene
def test_workflow_builds_on_windows_not_linux():
    """PyInstaller cannot cross-compile; a Windows EXE needs a Windows runner."""
    text = _workflow_or_skip()
    assert "windows-latest" in text
    assert "ubuntu-latest" not in text


@pytest.mark.repo_hygiene
def test_workflow_runs_the_real_build_script():
    text = _workflow_or_skip()
    assert "build.ps1" in text
    # -SkipTests must not be used in CI: a release must never come from a
    # failing tree.
    assert "-SkipTests" not in text


@pytest.mark.repo_hygiene
def test_workflow_smoke_tests_the_exe():
    """A binary that compiles but cannot start is the bug we already shipped."""
    text = _workflow_or_skip()
    assert "PhantomTweeks.exe version" in text or "$exe version" in text
    assert "no known parent package" in text, \
        "CI does not check for the frozen relative-import regression"


@pytest.mark.repo_hygiene
def test_workflow_publishes_all_artifacts_on_a_tag():
    yaml = pytest.importorskip("yaml")
    data = _workflow_yaml()
    steps = data["jobs"]["build"]["steps"]
    release = [s for s in steps if "action-gh-release" in str(s.get("uses", ""))]
    assert release, "no release step"
    files = release[0]["with"]["files"]
    for expected in ("PhantomTweeks.exe", "PhantomTweeks-Portable.exe",
                     "PhantomTweeks-Setup.exe", "SHA256SUMS.txt"):
        assert expected in files


@pytest.mark.repo_hygiene
def test_release_step_only_runs_for_version_tags():
    yaml = pytest.importorskip("yaml")
    data = _workflow_yaml()
    steps = data["jobs"]["build"]["steps"]
    release = [s for s in steps if "action-gh-release" in str(s.get("uses", ""))][0]
    assert "refs/tags/v" in release["if"]


@pytest.mark.repo_hygiene
def test_workflow_requests_write_permission_for_releases():
    yaml = pytest.importorskip("yaml")
    data = _workflow_yaml()
    assert data["permissions"]["contents"] == "write"


@pytest.mark.repo_hygiene
def test_workflow_never_hardcodes_a_token():
    text = _workflow_or_skip()
    assert "ghp_" not in text and "github_pat_" not in text


# ------------------------------------------------------------- download proxy

def test_download_only_serves_allowlisted_files():
    m = _load("download")
    for bad in ("../../etc/passwd", "src/phantom_tweeks/app.py",
                "issuer-private.key", "admin/admin_cli.py", ".env"):
        assert bad not in m.ALLOWED


def test_download_aliases_resolve_to_allowed_files():
    m = _load("download")
    for alias, target in m.ALIASES.items():
        assert target in m.ALLOWED, f"alias {alias} points outside the allowlist"


def test_download_exposes_no_source_or_secrets():
    m = _load("download")
    assert all(f.endswith((".exe", ".txt")) for f in m.ALLOWED)


def test_download_defaults_to_the_configured_repo(monkeypatch):
    m = _load("download")
    monkeypatch.delenv("GITHUB_REPO", raising=False)
    assert m._repo() == "GalaxyFSRP1/PhantomTweeks"


def test_download_reads_token_from_environment_only(monkeypatch):
    """The token must never be a literal in the source."""
    src = (ROOT / "api" / "download.py").read_text()
    assert "ghp_" not in src and "github_pat_" not in src
    m = _load("download")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    assert m._token() == ""


# ------------------------------------------------------------- latest endpoint

def test_latest_reports_clearly_when_unconfigured():
    m = _load("latest")
    code, body = m.build_payload("", "owner/repo")
    assert code == 503 and body["available"] is False


def test_checksum_parser_handles_both_formats():
    m = _load("latest")
    parsed = m._parse_sums(
        "a" * 64 + "  PhantomTweeks-Setup.exe\n"
        + "b" * 64 + " *PhantomTweeks.exe\n"
        "not a checksum line\n")
    assert parsed == {"PhantomTweeks-Setup.exe": "a" * 64,
                      "PhantomTweeks.exe": "b" * 64}


def test_latest_only_reports_public_files():
    m = _load("latest")
    assert "issuer-private.key" not in m.PUBLIC_FILES
    assert all(f.endswith((".exe", ".txt")) for f in m.PUBLIC_FILES)


# ------------------------------------------------------------- vercel config

def test_all_api_functions_are_declared():
    cfg = json.loads((ROOT / "vercel.json").read_text())
    declared = set(cfg["functions"])
    on_disk = {f"api/{p.name}" for p in (ROOT / "api").glob("*.py")}
    assert on_disk <= declared, f"undeclared functions: {on_disk - declared}"


def test_download_function_has_headroom_for_a_large_exe():
    cfg = json.loads((ROOT / "vercel.json").read_text())
    dl = cfg["functions"]["api/download.py"]
    assert dl["maxDuration"] >= 30
    assert dl["memory"] >= 512


def _vercelignore_or_skip() -> str:
    """Dotfiles are dropped by the GitHub web uploader; skip instead of failing."""
    p = ROOT / ".vercelignore"
    if not p.is_file():
        pytest.skip(".vercelignore is missing from this checkout — add it with "
                    "'git add -f .vercelignore'. Deployment still works without "
                    "it, the upload is just larger.")
    return p.read_text()


@pytest.mark.repo_hygiene
def test_vercelignore_keeps_src_available_to_the_api():
    """api/ imports phantom_tweeks from src/; excluding it breaks validation."""
    ignore = _vercelignore_or_skip().splitlines()
    entries = {l.strip().rstrip("/") for l in ignore if l.strip()
               and not l.strip().startswith("#")}
    assert "src" not in entries
    assert "api" not in entries


@pytest.mark.repo_hygiene
def test_vercelignore_excludes_admin_secrets():
    text = _vercelignore_or_skip()
    assert "admin/" in text or "admin" in text


@pytest.mark.repo_hygiene
def test_download_page_links_to_the_real_endpoints():
    html = (ROOT / "website" / "download.html").read_text(encoding="utf-8")
    assert "/api/download?file=setup" in html
    assert "/api/download?file=portable" in html
    assert "/api/latest" in html


@pytest.mark.repo_hygiene
def test_download_page_no_longer_claims_no_release_exists():
    html = (ROOT / "website" / "download.html").read_text(encoding="utf-8")
    assert "intentionally point at the verification section" not in html


@pytest.mark.repo_hygiene
def test_ci_warns_about_missing_dotfiles():
    """A silent skip must not hide a missing .gitignore in CI."""
    text = _workflow_or_skip()
    assert ".gitignore" in text
    assert "::warning::" in text


@pytest.mark.repo_hygiene
def test_ci_refuses_to_build_with_a_committed_private_key():
    text = _workflow_or_skip()
    assert "admin/issuer-private.key" in text
    assert "throw" in text


@pytest.mark.repo_hygiene
def test_push_helper_exists_and_guards_the_private_key():
    """The push helper must refuse to run with an issuer key on disk."""
    p = ROOT / "push-to-github.ps1"
    if not p.is_file():
        pytest.skip("push-to-github.ps1 missing from this checkout")
    text = p.read_text(encoding="utf-8")
    assert "issuer-private.key" in text
    # git calls are routed through Invoke-Git, so match on the arguments
    # rather than a literal "git init" command line.
    assert '"init"' in text, "the script never initialises a repository"
    # Must force-add the dotfiles the web uploader drops.
    assert '"-f"' in text and '".gitignore"' in text
    assert ".github" in text


@pytest.mark.repo_hygiene
def test_push_helper_has_no_multi_argument_die_calls():
    """`Die "a" + "b"` passes 3 args in PowerShell instead of concatenating."""
    p = ROOT / "push-to-github.ps1"
    if not p.is_file():
        pytest.skip("push-to-github.ps1 missing from this checkout")
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if re.match(r'^(Die|Ok|Warn|Step)\s+".*"\s*\+', s):
            pytest.fail(f"line {i}: multi-argument call: {s}")


@pytest.mark.repo_hygiene
def test_push_helper_handles_a_diverged_remote_safely():
    """A rejected push must not silently force-overwrite the remote.

    The script may only force-push when -Force is passed explicitly, and it
    must back the old remote state up to a branch first.
    """
    p = ROOT / "push-to-github.ps1"
    if not p.is_file():
        pytest.skip("push-to-github.ps1 missing from this checkout")
    text = p.read_text(encoding="utf-8-sig")
    assert "[switch]$Force" in text, "no -Force switch"
    assert "--force-with-lease" in text, "must prefer --force-with-lease"
    assert "backup-before-force-" in text, "no backup branch before forcing"
    # The force push must be guarded by the switch.
    guard = text.index("if (-not $Force)")
    forced = text.index("--force-with-lease")
    assert guard < forced, "force push is not gated behind -Force"
    assert "git pull --rebase" in text, "no merge alternative offered"


@pytest.mark.repo_hygiene
def test_push_helper_does_not_trip_on_git_stderr():
    """git writes normal progress to stderr.

    Under $ErrorActionPreference = "Stop", Windows PowerShell 5.1 turns native
    stderr output into a terminating NativeCommandError, killing the script
    even when git succeeded. The script must not combine "Stop" with piping
    git's stderr through the PowerShell error stream.
    """
    p = ROOT / "push-to-github.ps1"
    if not p.is_file():
        pytest.skip("push-to-github.ps1 missing from this checkout")
    text = p.read_text(encoding="utf-8-sig")

    assert '$ErrorActionPreference = "Stop"' not in text, (
        'ErrorActionPreference "Stop" makes git stderr fatal on PS 5.1'
    )
    # No git invocation may pipe its error stream into PowerShell.
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if s.startswith("#"):
            continue
        if "git " in s and "2>&1" in s:
            pytest.fail(f"line {i}: git with 2>&1 can abort the script: {s}")


@pytest.mark.repo_hygiene
def test_every_git_call_goes_through_the_wrapper():
    """Bare `git ...` calls bypass the exit-code checking wrapper."""
    p = ROOT / "push-to-github.ps1"
    if not p.is_file():
        pytest.skip("push-to-github.ps1 missing from this checkout")
    offenders = []
    for i, line in enumerate(p.read_text(encoding="utf-8-sig").splitlines(), 1):
        s = line.strip()
        if s.startswith("#") or "Invoke-Git" in s:
            continue
        if re.match(r'^(\$\w+\s*=\s*)?git\s+\w', s):
            offenders.append(f"line {i}: {s}")
    assert not offenders, (
        "these git calls bypass Invoke-Git:\n" + "\n".join(offenders)
    )


@pytest.mark.repo_hygiene
def test_invoke_git_quotes_arguments_containing_spaces():
    """Start-Process splits its ArgumentList on spaces.

    Without quoting, `git commit -m "Update Phantom Tweeks"` reaches git as
    three separate arguments and fails with
    "pathspec 'Phantom' did not match any file(s)".
    """
    p = ROOT / "push-to-github.ps1"
    if not p.is_file():
        pytest.skip("push-to-github.ps1 missing from this checkout")
    text = p.read_text(encoding="utf-8-sig")
    assert "Start-Process" in text
    # There must be a quoting pass between the args and Start-Process.
    assert "-ArgumentList $quoted" in text, (
        "Start-Process is given raw arguments; multi-word values will split"
    )
    assert "-match '[\\s\"]'" in text or '-match' in text, "no quoting logic found"


@pytest.mark.repo_hygiene
def test_release_is_published_on_a_version_tag():
    """A Release is only created for refs/tags/v*, so a branch push alone
    will never produce one. Verify the trigger and the guard agree."""
    data = _workflow_yaml()
    triggers = data.get("on") or data.get(True)
    assert "v*" in triggers["push"]["tags"], "tags are not a build trigger"

    steps = data["jobs"]["build"]["steps"]
    rel = [s for s in steps if "action-gh-release" in str(s.get("uses", ""))]
    assert rel, "no release step"
    assert "refs/tags/v" in rel[0].get("if", ""), "release step is not tag-gated"
    assert data.get("permissions", {}).get("contents") == "write", (
        "contents: write is required to create a Release"
    )


@pytest.mark.repo_hygiene
def test_release_tolerates_a_missing_msi():
    """The .msi glob matches nothing when WiX is unavailable."""
    data = _workflow_yaml()
    steps = data["jobs"]["build"]["steps"]
    rel = [s for s in steps if "action-gh-release" in str(s.get("uses", ""))][0]
    assert rel["with"].get("fail_on_unmatched_files") is False, (
        "a missing .msi would abort publishing the binaries"
    )


@pytest.mark.repo_hygiene
def test_actions_run_on_a_supported_node_runtime():
    """Node 20 is deprecated on GitHub runners; v4 actions still use it."""
    data = _workflow_yaml()
    minimum = {"actions/checkout": 5,
               "actions/setup-python": 5,
               "actions/upload-artifact": 6}
    for step in data["jobs"]["build"]["steps"]:
        uses = str(step.get("uses", ""))
        if "@" not in uses:
            continue
        name, ver = uses.rsplit("@", 1)
        if name in minimum and ver.startswith("v"):
            major = int(ver[1:].split(".")[0])
            assert major >= minimum[name], (
                f"{name}@{ver} runs on a deprecated Node runtime; "
                f"use v{minimum[name]} or newer"
            )
