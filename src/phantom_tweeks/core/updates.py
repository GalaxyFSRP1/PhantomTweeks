"""Update architecture.

Rules encoded here: HTTPS only, certificate validation on, checksum + signature
verified before anything is executed, atomic staging, and fail-safe (an invalid
package is discarded, never run).
"""
from __future__ import annotations

import hashlib
import json
import ssl
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..branding import VERSION
from .logging_setup import get_logger
from . import paths
from . import runproc

log = get_logger("updates")

UPDATE_MANIFEST_URL = "https://phantomtweeks.example/updates/latest.json"


@dataclass
class UpdateInfo:
    version: str
    url: str
    sha256: str
    notes: str = ""
    signature: Optional[str] = None
    mandatory: bool = False


def _version_tuple(v: str) -> tuple:
    return tuple(int(x) for x in v.split(".") if x.isdigit())


def check(url: str = UPDATE_MANIFEST_URL, timeout: int = 15) -> Optional[UpdateInfo]:
    if not url.lower().startswith("https://"):
        log.error("Refusing non-HTTPS update manifest: %s", url)
        return None
    ctx = ssl.create_default_context()      # verification on by default
    try:
        with urllib.request.urlopen(url, timeout=timeout, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log.info("Update check failed (this is non-fatal): %s", e)
        return None
    try:
        info = UpdateInfo(**{k: data[k] for k in
                             ("version", "url", "sha256") if k in data},
                          notes=data.get("notes", ""),
                          signature=data.get("signature"),
                          mandatory=bool(data.get("mandatory")))
    except (KeyError, TypeError) as e:
        log.error("Malformed update manifest: %s", e)
        return None
    if not info.url.lower().startswith("https://"):
        log.error("Refusing non-HTTPS update payload.")
        return None
    if _version_tuple(info.version) <= _version_tuple(VERSION):
        return None
    return info


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download_and_verify(info: UpdateInfo, timeout: int = 300) -> tuple[bool, str, Optional[Path]]:
    """Download to a staging file and verify. Never executes anything."""
    paths.ensure_dirs()
    staging = paths.ROOT / "updates"
    staging.mkdir(exist_ok=True)
    target = staging / f"PhantomTweeks-{info.version}.exe.part"
    final = staging / f"PhantomTweeks-{info.version}.exe"
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(info.url, timeout=timeout, context=ctx) as resp, \
                target.open("wb") as out:
            while chunk := resp.read(1024 * 256):
                out.write(chunk)
    except Exception as e:
        target.unlink(missing_ok=True)
        return False, f"Download failed: {e}", None

    digest = sha256_file(target)
    if digest.lower() != info.sha256.lower():
        target.unlink(missing_ok=True)
        return False, ("Checksum mismatch — the package was discarded. Phantom "
                       "Tweeks will not run an unverified update."), None

    ok, msg = verify_signature(target, info.signature)
    if not ok:
        target.unlink(missing_ok=True)
        return False, msg, None

    target.replace(final)
    return True, f"Update {info.version} verified and staged at {final}.", final


def verify_signature(path: Path, signature: Optional[str]) -> tuple[bool, str]:
    """Authenticode verification on Windows. Unsigned packages are rejected."""
    from .platform_info import IS_WINDOWS
    if not IS_WINDOWS:
        return False, "Signature verification requires Windows; update refused."
    import subprocess
    ps = (f"(Get-AuthenticodeSignature -LiteralPath '{path}').Status")
    try:
        status = runproc.run(["powershell", "-NoProfile", "-Command", ps],
                                capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception as e:
        return False, f"Could not verify signature: {e}"
    if status != "Valid":
        return False, (f"Authenticode status is '{status or 'Unknown'}'. Phantom "
                       "Tweeks refuses to run an unsigned or tampered package.")
    return True, "Signature valid."
