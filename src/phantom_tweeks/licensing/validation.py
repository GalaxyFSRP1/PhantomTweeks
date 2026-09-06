"""Optional online license validation and revocation.

Offline signature checking (keys.py) proves a key is *genuine*. It cannot tell
you a key was refunded, charged back, or is being shared by 200 people. That
requires a server, so this module defines the client half of that conversation.

Standing rules this module obeys:
  * HTTPS only, with certificate verification ON. Never plain HTTP.
  * No secret API key is compiled into the client. The license key itself is
    the bearer credential, sent over TLS.
  * Fail SAFE, not open and not closed: if the server is unreachable, a
    previously valid key keeps working within a grace period. Users must not
    lose access because our server had an outage.
  * Nothing is uploaded without a reason. The request carries the key id, a
    device fingerprint and the app version — no personal files, no game list,
    no hardware inventory.
"""
from __future__ import annotations

import hashlib
import json
import platform
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from ..core import paths
from ..core.logging_setup import get_logger

log = get_logger("licensing")

#: Set to your deployed endpoint, e.g. https://phantomtweeks.vercel.app/api
VALIDATION_ENDPOINT = ""

#: How long a cached "valid" answer is trusted when the server is unreachable.
OFFLINE_GRACE = timedelta(days=14)

TIMEOUT_SECONDS = 8


@dataclass
class ValidationResult:
    ok: bool
    status: str            # valid | revoked | expired | unknown | offline | disabled
    message: str
    checked_at: Optional[str] = None
    cached: bool = False

    @property
    def should_grant_access(self) -> bool:
        return self.ok


def device_fingerprint() -> str:
    """A stable, non-identifying machine id.

    Deliberately coarse: a hash of machine name + platform. It is not a
    hardware inventory, cannot be reversed into a serial number, and is only
    used to spot one key being used on many machines at once.
    """
    raw = "|".join([
        platform.node() or "unknown",
        platform.machine() or "unknown",
        platform.system() or "unknown",
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _cache_path():
    return paths.ROOT / "license-cache.json"


def _read_cache() -> dict:
    p = _cache_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_cache(key_id: str, status: str, message: str) -> None:
    try:
        paths.ensure_dirs()
        cache = _read_cache()
        cache[key_id] = {
            "status": status,
            "message": message,
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }
        p = _cache_path()
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, indent=2), encoding="utf-8")
        tmp.replace(p)
    except OSError as e:
        log.warning("Could not cache license status: %s", e)


def _cached_result(key_id: str) -> Optional[ValidationResult]:
    entry = _read_cache().get(key_id)
    if not entry:
        return None
    try:
        when = datetime.fromisoformat(entry["checked_at"])
    except Exception:
        return None
    age = datetime.now() - when
    if entry.get("status") == "revoked":
        # A revocation is remembered permanently; it never expires into "valid".
        return ValidationResult(False, "revoked",
                                "This license has been revoked.",
                                entry["checked_at"], cached=True)
    if entry.get("status") == "valid" and age <= OFFLINE_GRACE:
        left = OFFLINE_GRACE - age
        return ValidationResult(
            True, "offline",
            f"Could not reach the licensing server; using your last verified "
            f"status. This works for another {left.days} day(s).",
            entry["checked_at"], cached=True)
    return None


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


def validate_online(key_text: str, key_id: str, app_version: str,
                    endpoint: Optional[str] = None) -> ValidationResult:
    """Ask the licensing server about this key. Never raises."""
    url = (endpoint if endpoint is not None else VALIDATION_ENDPOINT) or ""
    if not url:
        return ValidationResult(
            True, "disabled",
            "Online validation is not configured in this build; the key was "
            "verified offline by signature only.")

    if not url.lower().startswith("https://"):
        # Refuse to send a credential over plaintext, even if misconfigured.
        return ValidationResult(
            False, "unknown",
            "Refusing to contact the licensing server over an insecure "
            "connection. This is a build configuration problem.")

    body = json.dumps({
        "key": key_text,
        "key_id": key_id,
        "device": device_fingerprint(),
        "version": app_version,
    }).encode("utf-8")

    req = urllib.request.Request(
        url.rstrip("/") + "/validate",
        data=body,
        headers={"Content-Type": "application/json",
                 "User-Agent": f"PhantomTweeks/{app_version}"},
        method="POST")

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS,
                                    context=_ssl_context()) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            _write_cache(key_id, "revoked", "Key rejected by the server.")
            return ValidationResult(False, "revoked",
                                    "The licensing server does not recognise "
                                    "this key, or it has been revoked.")
        log.warning("License check HTTP %s", e.code)
        cached = _cached_result(key_id)
        return cached or ValidationResult(
            True, "offline",
            "The licensing server returned an error. Your key was verified "
            "offline by signature, so Premium stays enabled.")
    except (urllib.error.URLError, ssl.SSLError, TimeoutError, OSError,
            json.JSONDecodeError) as e:
        log.info("License check unavailable: %s", e)
        cached = _cached_result(key_id)
        return cached or ValidationResult(
            True, "offline",
            "Could not reach the licensing server. Your key was verified "
            "offline by signature, so Premium stays enabled.")

    status = str(payload.get("status", "unknown")).lower()
    message = str(payload.get("message", ""))
    if status == "valid":
        _write_cache(key_id, "valid", message or "Valid.")
        return ValidationResult(True, "valid", message or "License is valid.",
                                datetime.now().isoformat(timespec="seconds"))
    if status in ("revoked", "expired"):
        _write_cache(key_id, status, message or status)
        return ValidationResult(False, status,
                                message or f"This license is {status}.")
    return ValidationResult(False, "unknown",
                            message or "The server could not confirm this license.")
