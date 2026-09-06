"""Vercel function: POST /api/activate  and  POST /api/deactivate

Device activation for Phantom Tweeks Premium.

What this is for
----------------
Offline signature verification already proves a key is genuine. This endpoint
adds the thing signatures cannot do on their own: limiting how many machines
one key runs on, and letting a user move their key to a new PC.

Security posture
----------------
* Only the ISSUER PUBLIC key is ever deployed here. Signing happens offline
  with ``admin/admin_cli.py``; the private key never touches the server.
* The device id is an opaque hash produced by the client. We compare it and
  store it; we never decode it and it contains nothing identifying.
* A key that fails signature verification is rejected before any storage is
  touched.
* **Fail-open by design.** If storage is unavailable the endpoint reports
  success with ``degraded: true``. A paying customer must never be locked out
  of software they bought because our backend had a bad day. Offline
  verification remains the authority.

Storage
-------
Uses Vercel KV / Upstash Redis over HTTPS when ``KV_REST_API_URL`` and
``KV_REST_API_TOKEN`` are set. With no storage configured the endpoint still
validates keys and simply cannot enforce a device limit - which is the
correct default for a product that is not selling licences yet.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.setrecursionlimit(10000)

_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT / "src", _ROOT / "api" / "_lib"):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

DEFAULT_DEVICE_LIMIT = int(os.environ.get("PHANTOM_DEVICE_LIMIT", "3"))
_TIMEOUT = 8


# ------------------------------------------------------------- storage

def _kv_config() -> tuple[str, str]:
    url = (os.environ.get("KV_REST_API_URL")
           or os.environ.get("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
    token = (os.environ.get("KV_REST_API_TOKEN")
             or os.environ.get("UPSTASH_REDIS_REST_TOKEN") or "")
    return url, token


def kv_available() -> bool:
    url, token = _kv_config()
    return bool(url and token)


def _kv(path: str, body=None):
    """Call the KV REST API. Returns the decoded result, or None on failure."""
    url, token = _kv_config()
    if not (url and token):
        return None
    req = urllib.request.Request(
        f"{url}/{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
        method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8")).get("result")
    except Exception:
        # Never propagate: storage problems must not deny a valid customer.
        return None


def _devices(key_id: str) -> list[dict]:
    raw = _kv(f"get/phantom:devices:{key_id}")
    if not raw:
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return data if isinstance(data, list) else []
    except ValueError:
        return []


def _save_devices(key_id: str, devices: list[dict]) -> bool:
    return _kv(f"set/phantom:devices:{key_id}",
               json.dumps(devices)) is not None


# ------------------------------------------------------------ key checks

def verify_key(key_text: str) -> tuple[bool, str, dict]:
    """Offline signature verification, reusing the shipped licensing code."""
    try:
        from phantom_tweeks.licensing import keys as _keys
    except Exception as exc:                                # pragma: no cover
        return False, f"Licensing module unavailable: {exc}", {}

    pub = os.environ.get("PHANTOM_PUBLIC_KEY", "").strip()
    if pub:
        try:
            _keys.ISSUER_PUBLIC_KEY_B64 = pub
        except Exception:
            pass
    try:
        ok, message, payload = _keys.verify_key(key_text)
        return bool(ok), str(message), (payload or {})
    except Exception as exc:
        return False, f"Key could not be verified: {exc}", {}


def _revoked(key_id: str) -> bool:
    env = os.environ.get("REVOKED_KEYS", "")
    if key_id and key_id in {k.strip() for k in env.split(",") if k.strip()}:
        return True
    path = _ROOT / "api" / "revoked.json"
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            ids = data if isinstance(data, list) else data.get("revoked", [])
            return key_id in set(ids)
        except (ValueError, OSError):
            return False
    return False


# --------------------------------------------------------------- handler

class handler(BaseHTTPRequestHandler):
    def _json(self, code: int, body: dict) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):                                       # noqa: N802
        self._json(200, {
            "service": "phantom-tweeks-activation",
            "storage_configured": kv_available(),
            "device_limit": DEFAULT_DEVICE_LIMIT,
            "note": ("POST a JSON body of {key, device_id, action} where "
                     "action is 'activate', 'deactivate' or 'check'."),
        })

    def do_POST(self):                                      # noqa: N802
        try:
            self._handle()
        except Exception as exc:                            # pragma: no cover
            # An uncaught exception becomes an opaque platform 502.
            self._json(500, {"ok": False, "error": "unexpected",
                             "message": "The activation service failed.",
                             "detail": type(exc).__name__})

    def _handle(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except (ValueError, TypeError):
            self._json(400, {"ok": False, "error": "bad_request",
                             "message": "Send a JSON body."})
            return

        key_text = str(body.get("key") or "").strip()
        device_id = str(body.get("device_id") or "").strip()[:128]
        action = str(body.get("action") or "activate").strip().lower()

        if not key_text:
            self._json(400, {"ok": False, "error": "missing_key",
                             "message": "No license key supplied."})
            return

        ok, message, payload = verify_key(key_text)
        if not ok:
            self._json(200, {"ok": False, "error": "invalid_key",
                             "message": message})
            return

        key_id = str(payload.get("id") or payload.get("key_id") or "")
        if _revoked(key_id):
            self._json(200, {"ok": False, "error": "revoked",
                             "message": ("This key has been revoked. Contact "
                                         "support if you believe that is "
                                         "wrong.")})
            return

        limit = int(payload.get("devices") or DEFAULT_DEVICE_LIMIT)

        if not kv_available():
            # No storage: verification still succeeded, so allow it and say so.
            self._json(200, {
                "ok": True, "degraded": True, "key_id": key_id,
                "device_limit": limit, "devices_used": 0,
                "message": ("Key is valid. Device tracking is not configured "
                            "on this server, so no device limit is enforced."),
            })
            return

        devices = _devices(key_id)
        now = int(time.time())

        if action == "deactivate":
            remaining = [d for d in devices if d.get("id") != device_id]
            saved = _save_devices(key_id, remaining)
            self._json(200, {
                "ok": True, "key_id": key_id,
                "devices_used": len(remaining), "device_limit": limit,
                "degraded": not saved,
                "message": ("This device has been released. You can activate "
                            "on another PC."),
            })
            return

        known = next((d for d in devices if d.get("id") == device_id), None)

        if action == "check":
            self._json(200, {
                "ok": bool(known) or len(devices) < limit,
                "key_id": key_id, "activated": bool(known),
                "devices_used": len(devices), "device_limit": limit,
                "message": "Active on this device." if known else
                           "Not yet activated on this device.",
            })
            return

        # activate
        if known:
            known["last_seen"] = now
            _save_devices(key_id, devices)
            self._json(200, {
                "ok": True, "key_id": key_id, "already_active": True,
                "devices_used": len(devices), "device_limit": limit,
                "message": "Already activated on this device.",
            })
            return

        if len(devices) >= limit:
            self._json(200, {
                "ok": False, "error": "device_limit",
                "key_id": key_id,
                "devices_used": len(devices), "device_limit": limit,
                "message": (f"This key is already active on {len(devices)} "
                            f"of {limit} devices. Deactivate one first - you "
                            "can do that from the Premium page on that PC."),
            })
            return

        devices.append({"id": device_id, "first_seen": now, "last_seen": now})
        saved = _save_devices(key_id, devices)
        self._json(200, {
            "ok": True, "key_id": key_id,
            "devices_used": len(devices), "device_limit": limit,
            "degraded": not saved,
            "message": (f"Activated. This key is now used on "
                        f"{len(devices)} of {limit} devices."),
        })
