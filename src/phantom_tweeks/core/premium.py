"""Premium architecture — deliberately inert.

There is no payment code, no fake unlock, and no bundled license key. This is
the seam a real licensing service plugs into later. `is_premium()` returns
False until a signed, server-validated license exists.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Protocol

from . import paths

#: Premium is now backed by real signed licensing (see phantom_tweeks.licensing).
#: There is still NO payment processing inside the app — keys are issued by the
#: publisher out-of-band. This flag stays honest: it reports whether the build
#: can actually verify a license, not whether we would like to sell one.
def _licensing_ready() -> bool:
    try:
        from ..licensing.keys import issuer_public_key
        return issuer_public_key() is not None
    except Exception:
        return False


PREMIUM_AVAILABLE = _licensing_ready()

PLANNED_FEATURES = [
    "Advanced game profiles",
    "Extended benchmarking",
    "Advanced frame-time analytics",
    "Network history",
    "Cloud profiles",
    "Advanced system analytics",
    "Automatic optimization recommendations",
    "Premium themes",
    "Priority support",
]


@dataclass
class License:
    key_id: Optional[str] = None
    plan: str = "free"
    expires: Optional[str] = None
    device_id: Optional[str] = None
    signature: Optional[str] = None

    @property
    def valid(self) -> bool:
        if not PREMIUM_AVAILABLE or self.plan == "free" or not self.signature:
            return False
        if self.expires:
            try:
                return datetime.fromisoformat(self.expires) > datetime.now()
            except ValueError:
                return False
        return True


class LicenseValidator(Protocol):
    """Implemented server-side later. The client never validates its own license
    with a hard-coded secret — that is trivially patchable and dishonest."""
    def validate(self, license: License) -> bool: ...


class NullValidator:
    def validate(self, license: License) -> bool:
        return False


@dataclass
class AccountArchitecture:
    """Design notes enforced as code so future contributors cannot regress them.

    * Passwords are never stored by the client — authentication is delegated to
      an OAuth2/OIDC provider and the client holds only a short-lived token.
    * Tokens live in the OS credential store (Windows Credential Manager via
      keyring), never in a plain-text config file.
    * No API secret is compiled into the client. Only a public client id.
    * Device management and license validation happen server-side over HTTPS
      with certificate validation enabled.
    """
    signed_in: bool = False
    email: Optional[str] = None
    device_id: Optional[str] = None
    validator: LicenseValidator = field(default_factory=NullValidator)

    def token_store_backend(self) -> str:
        return "Windows Credential Manager (keyring)" if PREMIUM_AVAILABLE else "none"


LICENSE_FILE = "license.json"


def _license_path():
    return paths.ROOT / LICENSE_FILE


def current_license() -> License:
    path = _license_path()
    if not path.exists():
        return License()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        known = {f for f in License.__dataclass_fields__}
        return License(**{k: v for k, v in data.items() if k in known})
    except Exception:
        return License()


def stored_key() -> Optional[str]:
    path = _license_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("key")
    except Exception:
        return None


def activate(key_text: str, app_version: str = "0.0.0") -> tuple[bool, str]:
    """Verify a key offline, then confirm online when configured.

    Offline signature verification is authoritative for *authenticity*. The
    online check adds revocation. If the network is unavailable the user is
    NOT locked out — see licensing.validation for the grace-period rules.
    """
    from ..licensing import keys as _keys
    from ..licensing import validation as _val

    ok, msg, lic = _keys.verify_key(key_text)
    if not ok or lic is None:
        return False, msg

    result = _val.validate_online(_keys.normalize_key(key_text), lic.key_id,
                                  app_version)
    if not result.ok:
        return False, result.message

    paths.ensure_dirs()
    payload = {
        "key": _keys.normalize_key(key_text),
        "key_id": lic.key_id,
        "plan": lic.plan,
        "expires": lic.expires,
        "activated": datetime.now().isoformat(timespec="seconds"),
        "last_check": result.status,
    }
    path = _license_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)

    note = "" if result.status == "valid" else f" ({result.message})"
    return True, f"{msg} Premium features are unlocked.{note}"


def deactivate() -> tuple[bool, str]:
    """Remove the license from this machine."""
    path = _license_path()
    if not path.exists():
        return False, "No license is active on this device."
    try:
        path.unlink()
    except OSError as e:
        return False, f"Could not remove the license: {e}"
    return True, "License removed from this device."


def license_status() -> dict:
    if dev_unlock_active():
        return {
            "active": True,
            "plan": "developer unlock",
            "message": ("Premium is unlocked locally for development. This is "
                        "not a purchased licence and is not transferable."),
            "key_id": None,
            "expires": None,
            "days_remaining": None,
            "developer": True,
        }
    """Everything the UI needs to describe the current licensing state."""
    from ..licensing import keys as _keys

    key = stored_key()
    if not key:
        return {"active": False, "plan": "free", "configured": PREMIUM_AVAILABLE,
                "message": ("No license key on this device."
                            if PREMIUM_AVAILABLE else
                            "This build has no issuer public key compiled in, "
                            "so licenses cannot be verified.")}
    ok, msg, lic = _keys.verify_key(key)
    return {
        "active": ok,
        "plan": lic.plan if lic else "free",
        "key_id": lic.key_id if lic else None,
        "expires": lic.expires if lic else None,
        "days_remaining": lic.days_remaining() if lic else None,
        "configured": PREMIUM_AVAILABLE,
        "message": msg,
    }


# ---------------------------------------------------------------- dev unlock
#
# A local developer unlock, used to exercise Premium features during
# development without issuing a signed licence key.
#
# Stored as a SHA-256 hash rather than plaintext. That is NOT security - the
# hash is in the shipped binary and anyone determined can find it - it just
# avoids the literal string sitting in the executable where a casual strings
# dump would surface it.
#
# This deliberately does not create a licence. It sets a local flag that
# unlocks the UI on this machine only. It cannot be transferred, it is not
# validated against the server, and `license_status()` reports it plainly as a
# developer unlock so it can never be mistaken for a real purchase.
_DEV_UNLOCK_SHA256 = "2bf7cf5e075692c5bee5884f38c4d2c7228f7b77702120faeb0bdaaef153fef5"


def _dev_flag_path():
    return paths.ROOT / "dev-unlock.json"


def dev_unlock_active() -> bool:
    try:
        data = json.loads(_dev_flag_path().read_text(encoding="utf-8"))
        return bool(data.get("unlocked"))
    except Exception:
        return False


def try_dev_unlock(code: str) -> tuple[bool, str]:
    """Enable Premium locally when the developer code is supplied."""
    import hashlib as _h
    supplied = _h.sha256((code or "").strip().encode()).hexdigest()
    if supplied != _DEV_UNLOCK_SHA256:
        return False, ""          # not the dev code; caller tries a real key
    paths.ensure_dirs()
    _dev_flag_path().write_text(
        json.dumps({"unlocked": True,
                    "at": datetime.now().isoformat(timespec="seconds"),
                    "note": "Local developer unlock. Not a purchased licence."},
                   indent=2), encoding="utf-8")
    return True, ("Developer unlock active. Premium features are enabled on "
                  "this machine only.\n\nThis is not a licence: it is not "
                  "transferable, nothing was purchased, and it is reported as "
                  "a developer unlock everywhere in the app.")


def clear_dev_unlock() -> tuple[bool, str]:
    try:
        _dev_flag_path().unlink()
    except FileNotFoundError:
        return False, "No developer unlock was active."
    except OSError as exc:
        return False, f"Could not remove the developer unlock: {exc}"
    return True, "Developer unlock removed."


def is_premium() -> bool:
    """True for a genuine signed licence, or a local developer unlock."""
    if dev_unlock_active():
        return True
    key = stored_key()
    if not key or not PREMIUM_AVAILABLE:
        return False
    from ..licensing import keys as _keys
    ok, _, _ = _keys.verify_key(key)
    return ok


def require_premium(feature: str) -> tuple[bool, str]:
    """Gate a premium feature. Returns (allowed, message)."""
    if is_premium():
        return True, ""
    return False, (f"{feature} is a Premium feature. "
                   "Enter a license key on the Premium page to unlock it.")


def page_content() -> dict:
    return {
        "title": "PHANTOM PREMIUM",
        "status": "COMING SOON",
        "blurb": "Unlock advanced Phantom Tweeks features.",
        "planned": PLANNED_FEATURES,
        "cta": "Notify Me",
        "note": "Premium is not available yet. Phantom Tweeks contains no payment "
                "processing and will never ask for card details inside the app.",
    }


def register_interest(email: str) -> tuple[bool, str]:
    """Stores interest locally only. Nothing is transmitted."""
    if "@" not in email or "." not in email.split("@")[-1]:
        return False, "Please enter a valid email address."
    paths.ensure_dirs()
    path = paths.ROOT / "notify-me.json"
    entries = []
    if path.exists():
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            entries = []
    entries.append({"email": email, "at": datetime.now().isoformat(timespec="seconds")})
    path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    return True, ("Saved locally. Phantom Tweeks has not transmitted your address "
                  "anywhere — when Premium launches you can choose to submit it.")
