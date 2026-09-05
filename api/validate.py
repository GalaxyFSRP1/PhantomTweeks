"""Vercel serverless function: POST /api/validate

Verifies a Phantom Tweeks license key and reports revocation status.

Security posture
----------------
* The ISSUER PUBLIC key lives here (env var PHANTOM_PUBLIC_KEY). Public keys
  are safe to deploy. The PRIVATE key must never be on the server — signing
  happens offline with admin/admin_cli.py.
* Revoked key ids come from the REVOKED_KEYS env var (comma separated) or
  api/revoked.json. No database required to start.
* We log nothing that identifies a person. The device fingerprint is an opaque
  hash the client generates and we only compare it, never decode it.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.setrecursionlimit(10000)

# Vendored so the function has no build step or dependency install.
_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT / "src", _ROOT / "api" / "_lib"):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

try:
    from phantom_tweeks.licensing import ed25519, keys
except Exception:                                    # pragma: no cover
    ed25519 = None
    keys = None

MAX_BODY = 8192


def _revoked_ids() -> set:
    ids = set()
    env = os.environ.get("REVOKED_KEYS", "")
    for part in env.replace(";", ",").split(","):
        if part.strip():
            ids.add(part.strip().upper())
    f = _ROOT / "api" / "revoked.json"
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                ids.update(k.upper() for k in data)
            elif isinstance(data, list):
                ids.update(str(k).upper() for k in data)
        except Exception:
            pass
    return ids


def _public_key():
    import base64
    b64 = os.environ.get("PHANTOM_PUBLIC_KEY", "").strip()
    if not b64 and keys is not None:
        b64 = getattr(keys, "ISSUER_PUBLIC_KEY_B64", "")
    if not b64 or b64.startswith("PLACEHOLDER"):
        return None
    try:
        return base64.b64decode(b64)
    except Exception:
        return None


def validate_payload(payload: dict) -> tuple[int, dict]:
    """Pure function so it can be unit tested without a server."""
    if keys is None:
        return 500, {"status": "unknown",
                     "message": "Licensing library unavailable on the server."}

    key_text = str(payload.get("key", "")).strip()
    if not key_text:
        return 400, {"status": "unknown", "message": "No key supplied."}

    pub = _public_key()
    if pub is None:
        return 500, {"status": "unknown",
                     "message": "Server is missing PHANTOM_PUBLIC_KEY."}

    ok, message, lic = keys.verify_key(key_text, pub)
    if lic is None:
        return 200, {"status": "invalid", "message": message}
    if not ok:
        # verify_key folds expiry into its failure result. Report an expired
        # key as 'expired', not 'invalid' — the user needs to know it was a
        # real key that lapsed, not a forgery.
        status = "expired" if lic.expired else "invalid"
        return 200, {"status": status, "message": message}

    if lic.key_id.upper() in _revoked_ids():
        return 200, {"status": "revoked",
                     "message": "This license has been revoked. If you believe "
                                "this is a mistake, contact support."}

    if lic.expires:
        try:
            if date.fromisoformat(lic.expires) < date.today():
                return 200, {"status": "expired",
                             "message": f"This license expired on {lic.expires}."}
        except ValueError:
            return 200, {"status": "invalid",
                         "message": "License expiry date is malformed."}

    return 200, {
        "status": "valid",
        "message": f"Valid {lic.plan} license.",
        "plan": lic.plan,
        "expires": lic.expires,
        "key_id": lic.key_id,
    }


class handler(BaseHTTPRequestHandler):          # Vercel entry point
    def _send(self, code: int, body: dict) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):                        # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):                            # noqa: N802
        self._send(200, {"status": "ok",
                         "message": "Phantom Tweeks licensing API. POST a key "
                                    "to /api/validate."})

    def do_POST(self):                           # noqa: N802
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            self._send(400, {"status": "unknown", "message": "Bad request body."})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError
        except Exception:
            self._send(400, {"status": "unknown", "message": "Malformed JSON."})
            return
        code, body = validate_payload(payload)
        self._send(code, body)
