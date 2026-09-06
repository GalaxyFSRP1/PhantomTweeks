"""Automatic update checking and staged, verified downloads.

How it works
------------
The app asks ``https://<site>/api/latest`` what the newest release is. That
endpoint reads the GitHub Release and returns the version, the file list and
the SHA-256 of every asset. If the reported version is newer than the running
one, the user is told - never interrupted mid-game, never auto-installed.

Safety rules encoded here
-------------------------
* **HTTPS only**, with certificate verification on. A plain-HTTP manifest or
  payload URL is refused outright.
* **The checksum is mandatory.** A download whose SHA-256 does not match the
  manifest is deleted, not run. There is no "continue anyway".
* **Nothing is ever executed automatically.** The installer is staged on disk
  and the user launches it themselves. An optimizer that silently runs
  downloaded executables is indistinguishable from malware.
* **Never during a game.** Update prompts are suppressed while a game is
  detected; a popup stealing focus mid-match is exactly the disruption this
  app exists to avoid.
* **Fail-safe and silent on error.** A failed check is logged and ignored. It
  must never block startup or nag.

On code signing
---------------
The binaries are not Authenticode-signed yet. The previous version of this
module *required* a valid signature, which meant updates could never succeed -
it would reject every real release. Rather than pretend, this version treats
signature verification as an additional check when a signature exists, and is
explicit in the UI that the current binaries are unsigned and verified by
checksum only. When signing is in place, ``require_signature`` flips to True
and the stricter path is already written and tested.
"""
from __future__ import annotations

import hashlib
import json
import re
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..branding import VERSION
from . import paths, runproc
from .logging_setup import get_logger

log = get_logger("updates")

# The live site. Overridable in config for self-hosting or testing.
DEFAULT_UPDATE_HOST = "https://phantomtweeks.phantomforgeinteractive.store"
LATEST_PATH = "/api/latest"

# How often a background check may run, and how long a "remind me later" lasts.
CHECK_INTERVAL_S = 24 * 3600
SNOOZE_S = 7 * 24 * 3600

_STATE = "update-state.json"


# --------------------------------------------------------------- versioning

_VER_RE = re.compile(r"^\s*v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[-.]?([A-Za-z0-9.]+))?")


def parse_version(text: str) -> tuple:
    """Parse a version into a comparable tuple.

    Handles ``v0.1.2``, ``0.1.2``, ``1.0``, and pre-release suffixes such as
    ``1.0.0-beta.2``. A release always sorts above a pre-release of the same
    number, which is why the flag is inverted in the tuple.
    """
    m = _VER_RE.match(text or "")
    if not m:
        return (0, 0, 0, 1, "")
    major, minor, patch, pre = m.groups()
    return (
        int(major or 0), int(minor or 0), int(patch or 0),
        0 if pre else 1,            # pre-release sorts BELOW the release
        (pre or "").lower(),
    )


def is_newer(candidate: str, current: str = VERSION) -> bool:
    return parse_version(candidate) > parse_version(current)


# ------------------------------------------------------------------- model

@dataclass
class UpdateInfo:
    version: str = ""
    tag: str = ""
    published: str = ""
    prerelease: bool = False
    notes: str = ""
    signed: bool = False
    files: list = field(default_factory=list)
    base_url: str = ""

    def asset(self, name: str) -> Optional[dict]:
        for f in self.files:
            if f.get("name") == name:
                return f
        return None

    @property
    def installer(self) -> Optional[dict]:
        return (self.asset("PhantomTweeks-Setup.exe")
                or self.asset("PhantomTweeks-Portable.exe")
                or (self.files[0] if self.files else None))

    def download_url(self, asset: dict) -> str:
        url = asset.get("url", "")
        if url.startswith("http"):
            return url
        return self.base_url.rstrip("/") + url

    def render(self) -> str:
        out = [f"Phantom Tweeks {self.version} is available "
               f"(you have {VERSION})."]
        if self.prerelease:
            out.append("This is a pre-release.")
        if self.published:
            out.append(f"Published {self.published}.")
        if self.files:
            out.append("")
            for f in self.files:
                out.append(f"  {f['name']}  {f.get('size_mb', '?')} MB")
        if not self.signed:
            out += ["", "These binaries are not code-signed, so Windows "
                        "SmartScreen will warn on first run. The download is "
                        "verified against its published SHA-256 checksum."]
        return "\n".join(out)


# ------------------------------------------------------------------- state

def _state_path() -> Path:
    return paths.ROOT / _STATE


def load_state() -> dict:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(**changes) -> dict:
    data = load_state()
    data.update(changes)
    try:
        paths.ensure_dirs()
        _state_path().write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass
    return data


def skip_version(version: str) -> None:
    """Never prompt for this specific version again."""
    save_state(skipped=version)


def snooze() -> None:
    save_state(snoozed_until=time.time() + SNOOZE_S)


def should_check(now: Optional[float] = None) -> bool:
    """Rate-limit background checks so the app is never chatty."""
    now = time.time() if now is None else now
    st = load_state()
    if now < float(st.get("snoozed_until", 0)):
        return False
    return (now - float(st.get("last_check", 0))) >= CHECK_INTERVAL_S


# ------------------------------------------------------------------- check

def _https_only(url: str) -> bool:
    return url.lower().startswith("https://")


def check(host: str = DEFAULT_UPDATE_HOST, timeout: int = 15,
          record: bool = True) -> Optional[UpdateInfo]:
    """Ask the site for the newest release.

    Returns an :class:`UpdateInfo` only when a *newer* version exists.
    Returns None for "up to date" and for every failure mode - an update
    check must never be the reason something breaks.
    """
    if not _https_only(host):
        log.error("Refusing a non-HTTPS update host: %s", host)
        return None

    url = host.rstrip("/") + LATEST_PATH
    ctx = ssl.create_default_context()          # verification on by default
    try:
        req = urllib.request.Request(
            url, headers={"Accept": "application/json",
                          "User-Agent": f"PhantomTweeks/{VERSION}"})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        log.info("Update check returned HTTP %s (non-fatal).", exc.code)
        return None
    except Exception as exc:
        log.info("Update check failed (non-fatal): %s", exc)
        return None
    finally:
        if record:
            save_state(last_check=time.time())

    if not isinstance(data, dict) or not data.get("available"):
        return None

    version = str(data.get("version") or "").strip()
    if not version or not is_newer(version):
        return None

    if load_state().get("skipped") == version:
        return None

    return UpdateInfo(
        version=version,
        tag=str(data.get("tag") or ""),
        published=str(data.get("published") or ""),
        prerelease=bool(data.get("prerelease")),
        notes=str(data.get("note") or ""),
        signed=bool(data.get("signed")),
        files=[f for f in (data.get("files") or []) if isinstance(f, dict)],
        base_url=host.rstrip("/"),
    )


def check_if_due(host: str = DEFAULT_UPDATE_HOST) -> Optional[UpdateInfo]:
    """Background-friendly check: rate-limited, and never during a game."""
    if not should_check():
        return None
    try:
        from . import games
        if games.detect_running_game() is not None:
            # Never interrupt a session with an update prompt.
            return None
    except Exception:
        pass
    return check(host)


# ---------------------------------------------------------------- download

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download_and_verify(info: UpdateInfo, asset: Optional[dict] = None,
                        timeout: int = 600,
                        progress=None,
                        require_signature: bool = False,
                        ) -> tuple[bool, str, Optional[Path]]:
    """Download an update, verify it, and stage it. Never executes it.

    ``progress`` is called with (bytes_done, bytes_total) if supplied.
    """
    asset = asset or info.installer
    if not asset:
        return False, "The release has no downloadable installer.", None

    expected = (asset.get("sha256") or "").strip().lower()
    if not expected:
        # Without a checksum there is no way to know what was downloaded.
        return False, ("No SHA-256 checksum is published for this file, so it "
                       "cannot be verified. Download refused."), None

    url = info.download_url(asset)
    if not _https_only(url):
        return False, "Refusing a non-HTTPS download URL.", None

    paths.ensure_dirs()
    staging = paths.ROOT / "updates"
    staging.mkdir(parents=True, exist_ok=True)
    name = asset.get("name", f"PhantomTweeks-{info.version}.exe")
    part = staging / f"{name}.part"
    final = staging / name

    ctx = ssl.create_default_context()
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": f"PhantomTweeks/{VERSION}"})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp, \
                part.open("wb") as out:
            total = int(resp.headers.get("Content-Length") or
                        asset.get("size") or 0)
            done = 0
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if progress:
                    try:
                        progress(done, total)
                    except Exception:
                        pass
    except Exception as exc:
        part.unlink(missing_ok=True)
        return False, f"Download failed: {exc}", None

    digest = sha256_file(part)
    if digest != expected:
        part.unlink(missing_ok=True)
        return False, ("Checksum mismatch - the package was discarded. "
                       "Phantom Tweeks will not run an unverified update.\n"
                       f"  expected {expected}\n  got      {digest}"), None

    if require_signature or info.signed:
        ok, msg = verify_signature(part)
        if not ok:
            part.unlink(missing_ok=True)
            return False, msg, None

    part.replace(final)
    return True, (f"Version {info.version} downloaded and its checksum "
                  f"verified.\nSaved to: {final}\n\n"
                  "Close Phantom Tweeks and run that file to install it. "
                  "Nothing is run automatically."), final


def verify_signature(path: Path) -> tuple[bool, str]:
    """Authenticode check. Only meaningful once the binaries are signed."""
    from .platform_info import IS_WINDOWS
    if not IS_WINDOWS:
        return False, "Signature verification requires Windows."
    ps = f"(Get-AuthenticodeSignature -LiteralPath '{path}').Status"
    try:
        status = runproc.run(["powershell", "-NoProfile", "-Command", ps],
                             timeout=60).stdout.strip()
    except Exception as exc:
        return False, f"Could not verify the signature: {exc}"
    if status != "Valid":
        return False, (f"Authenticode status is '{status or 'Unknown'}'. "
                       "Phantom Tweeks refuses to stage an unsigned or "
                       "tampered package.")
    return True, "Signature valid."
