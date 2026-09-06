"""License key format, encoding and offline verification.

Design
------
A key is a compact, self-contained, Ed25519-signed payload:

    PT-<base32 payload>-<base32 signature>

The client verifies the signature with an embedded PUBLIC key. It therefore
works fully offline and cannot be forged without the issuer's private key.
The private key never ships with the client.

What this does and does not achieve — stated plainly:

* It DOES stop a user inventing their own key, and lets a key encode a plan,
  an expiry and an optional device binding that the client can trust.
* It does NOT stop a determined attacker patching the binary to skip the
  check. No client-side scheme can. Online revocation (see validation.py)
  limits sharing of *genuine* keys, which is the realistic threat.
"""
from __future__ import annotations

import base64
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Optional

from . import ed25519

PREFIX = "PT"
KEY_VERSION = 1

#: Issuer public key (base64). Replace with your own from `admin_cli.py genkey`.
#: A public key is safe to embed; only the matching private key can sign.
ISSUER_PUBLIC_KEY_B64 = "PLACEHOLDER_REPLACE_WITH_YOUR_PUBLIC_KEY"

_B32_STRIP = re.compile(r"[^A-Z2-7]")


class KeyError_(Exception):
    """Raised for malformed keys. Named to avoid shadowing builtins.KeyError."""


@dataclass
class LicenseKey:
    key_id: str
    plan: str                       # e.g. "premium", "lifetime", "trial"
    issued: str                     # ISO date
    expires: Optional[str] = None   # ISO date, None = perpetual
    device_id: Optional[str] = None # bind to one machine, None = portable
    seats: int = 1
    email_hash: Optional[str] = None  # sha256 of email; never the address
    version: int = KEY_VERSION
    note: str = ""

    def payload_bytes(self) -> bytes:
        """Deterministic serialization — signature depends on exact bytes."""
        return json.dumps(asdict(self), sort_keys=True,
                          separators=(",", ":")).encode("utf-8")

    @property
    def expired(self) -> bool:
        if not self.expires:
            return False
        try:
            return date.fromisoformat(self.expires) < date.today()
        except ValueError:
            return True          # unparseable expiry is treated as expired

    def days_remaining(self) -> Optional[int]:
        if not self.expires:
            return None
        try:
            return (date.fromisoformat(self.expires) - date.today()).days
        except ValueError:
            return 0


def _b32(data: bytes) -> str:
    return base64.b32encode(data).decode("ascii").rstrip("=")


def _unb32(text: str) -> bytes:
    pad = "=" * (-len(text) % 8)
    return base64.b32decode(text + pad)


def encode_key(lic: LicenseKey, private_key: bytes) -> str:
    """Sign and encode a license. Issuer-side only."""
    payload = lic.payload_bytes()
    sig = ed25519.sign(private_key, payload)
    return f"{PREFIX}-{_b32(payload)}-{_b32(sig)}"


def normalize_key(text: str) -> str:
    """Accept user input with spaces, lowercase, or missing dashes."""
    return (text or "").strip().upper().replace(" ", "")


def format_key(key: str, group: int = 6) -> str:
    """Group the payload for readability when displaying a key."""
    key = normalize_key(key)
    parts = key.split("-")
    if len(parts) != 3:
        return key
    body = parts[1]
    grouped = "-".join(body[i:i + group] for i in range(0, len(body), group))
    return f"{parts[0]}-{grouped}-{parts[2]}"


def decode_key(text: str) -> tuple[LicenseKey, bytes, bytes]:
    """Parse a key into (license, payload_bytes, signature). No verification."""
    key = normalize_key(text)
    if not key.startswith(PREFIX + "-"):
        raise KeyError_("That does not look like a Phantom Tweeks key "
                        "(it should start with 'PT-').")
    parts = key.split("-")
    if len(parts) < 3:
        raise KeyError_("Key is incomplete — it should have three sections "
                        "separated by dashes.")
    # Middle sections may be dash-grouped for readability; rejoin them.
    payload_b32 = _B32_STRIP.sub("", "".join(parts[1:-1]))
    sig_b32 = _B32_STRIP.sub("", parts[-1])
    try:
        payload = _unb32(payload_b32)
        sig = _unb32(sig_b32)
    except Exception as e:
        raise KeyError_(f"Key contains invalid characters: {e}") from e
    try:
        data = json.loads(payload.decode("utf-8"))
    except Exception as e:
        raise KeyError_("Key payload is corrupt or truncated.") from e
    if not isinstance(data, dict):
        raise KeyError_("Key payload is not a license record.")
    known = {f for f in LicenseKey.__dataclass_fields__}
    unknown = set(data) - known
    if unknown:
        # Forward compatibility: a newer issuer may add fields. Do not reject,
        # but the signature still covers them, so tampering is caught.
        for u in unknown:
            data.pop(u)
    missing = {"key_id", "plan", "issued"} - set(data)
    if missing:
        raise KeyError_(f"Key is missing required fields: {', '.join(sorted(missing))}")
    return LicenseKey(**data), payload, sig


def issuer_public_key() -> Optional[bytes]:
    if (not ISSUER_PUBLIC_KEY_B64
            or ISSUER_PUBLIC_KEY_B64.startswith("PLACEHOLDER")):
        return None
    try:
        return base64.b64decode(ISSUER_PUBLIC_KEY_B64)
    except Exception:
        return None


def verify_key(text: str, public_key: Optional[bytes] = None
               ) -> tuple[bool, str, Optional[LicenseKey]]:
    """Offline-verify a key. Returns (ok, human message, license or None)."""
    try:
        lic, payload, sig = decode_key(text)
    except KeyError_ as e:
        return False, str(e), None

    pub = public_key if public_key is not None else issuer_public_key()
    if pub is None:
        return False, ("This build has no issuer public key compiled in, so it "
                       "cannot verify licenses. This is a build configuration "
                       "problem, not a problem with your key."), lic

    if not ed25519.verify(pub, payload, sig):
        return False, ("Signature check failed. This key was not issued by "
                       "Phantom Tweeks, or it has been altered."), lic

    if lic.expired:
        return False, f"This key expired on {lic.expires}.", lic

    return True, f"Valid {lic.plan} license.", lic
