"""The Vercel licensing API, tested as pure functions (no server needed)."""
from __future__ import annotations

import base64
import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.setrecursionlimit(10000)
ROOT = Path(__file__).resolve().parents[1]


def _load_api():
    spec = importlib.util.spec_from_file_location(
        "pt_api_validate", ROOT / "api" / "validate.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture()
def api(monkeypatch):
    from phantom_tweeks.licensing import ed25519
    sk = ed25519.generate_private_key()
    pk = ed25519.public_key(sk)
    monkeypatch.setenv("PHANTOM_PUBLIC_KEY", base64.b64encode(pk).decode())
    monkeypatch.delenv("REVOKED_KEYS", raising=False)
    return _load_api(), sk


def _key(sk, **over):
    from phantom_tweeks.licensing import keys
    base = dict(key_id="AAA111", plan="premium", issued="2026-01-01",
                expires="2030-01-01")
    base.update(over)
    return keys.encode_key(keys.LicenseKey(**base), sk)


def test_valid_key_returns_valid(api):
    m, sk = api
    code, body = m.validate_payload({"key": _key(sk)})
    assert code == 200 and body["status"] == "valid"
    assert body["plan"] == "premium" and body["key_id"] == "AAA111"


def test_forged_key_is_invalid(api):
    m, _ = api
    from phantom_tweeks.licensing import ed25519
    other = ed25519.generate_private_key()
    code, body = m.validate_payload({"key": _key(other, key_id="EVIL")})
    assert body["status"] == "invalid"


def test_expired_key_reports_expired_not_invalid(api):
    """Users must know their key lapsed rather than think it is fake."""
    m, sk = api
    code, body = m.validate_payload({"key": _key(sk, expires="2020-01-01")})
    assert body["status"] == "expired"
    assert "2020-01-01" in body["message"]


def test_revoked_key_via_env(api, monkeypatch):
    m, sk = api
    monkeypatch.setenv("REVOKED_KEYS", "AAA111,OTHER")
    code, body = m.validate_payload({"key": _key(sk)})
    assert body["status"] == "revoked"


def test_revocation_is_case_insensitive(api, monkeypatch):
    m, sk = api
    monkeypatch.setenv("REVOKED_KEYS", "aaa111")
    assert m.validate_payload({"key": _key(sk)})[1]["status"] == "revoked"


def test_missing_key_is_a_bad_request(api):
    m, _ = api
    code, body = m.validate_payload({})
    assert code == 400 and body["status"] == "unknown"


def test_garbage_key_is_invalid(api):
    m, _ = api
    assert m.validate_payload({"key": "PT-NOPE"})[1]["status"] == "invalid"


def test_server_without_public_key_fails_loudly(monkeypatch):
    monkeypatch.delenv("PHANTOM_PUBLIC_KEY", raising=False)
    from phantom_tweeks.licensing import keys
    monkeypatch.setattr(keys, "ISSUER_PUBLIC_KEY_B64", "PLACEHOLDER_X")
    m = _load_api()
    code, body = m.validate_payload({"key": "PT-AAAA-BBBB"})
    assert code == 500 and "PHANTOM_PUBLIC_KEY" in body["message"]


def test_api_never_returns_the_private_key_or_raw_email(api):
    m, sk = api
    body = json.dumps(m.validate_payload({"key": _key(sk)})[1])
    assert "private" not in body.lower()
    assert "@" not in body


def test_lifetime_key_has_no_expiry(api):
    m, sk = api
    body = m.validate_payload({"key": _key(sk, plan="lifetime", expires=None)})[1]
    assert body["status"] == "valid" and body["expires"] is None


# ---------------------------------------------------------------- config

def test_vercel_json_is_valid_and_points_at_the_website():
    cfg = json.loads((ROOT / "vercel.json").read_text())
    assert cfg["outputDirectory"] == "website"
    # Functions are declared explicitly per file (they need different memory
    # and duration limits), so just assert the validate endpoint is present.
    assert "api/validate.py" in cfg["functions"]


def test_vercel_sets_security_headers():
    cfg = json.loads((ROOT / "vercel.json").read_text())
    flat = json.dumps(cfg)
    for h in ("X-Content-Type-Options", "X-Frame-Options",
              "Strict-Transport-Security", "Referrer-Policy"):
        assert h in flat, f"missing security header {h}"


def test_api_functions_exist():
    assert (ROOT / "api" / "validate.py").is_file()
    assert (ROOT / "api" / "health.py").is_file()
