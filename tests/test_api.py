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


# ---------------------------------------------------------------------------
# Regressions for the live site returning "502 Bad Gateway" on the download
# button, and a red 404 in the browser console for /api/latest.
#
# Root cause in both: no GitHub Release had been published yet. That is a
# completely normal state for a new site, but the API treated it as a hard
# error, and the visitor saw an opaque Cloudflare 502.
# ---------------------------------------------------------------------------

import io
import urllib.error


def _load(name):
    import importlib.util
    path = ROOT / "api" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(handler_cls, path):
    """Drive a Vercel handler without a socket.

    BaseHTTPRequestHandler.__init__ wants a real connection, so subclass it
    and bypass the constructor entirely.
    """
    class Driver(handler_cls):
        def __init__(self):                      # noqa: D107
            self.path = path
            self.sent = None
            self.wfile = io.BytesIO()

        def send_response(self, code, *a):
            self.sent = code

        def send_header(self, *a):
            pass

        def end_headers(self):
            pass

        def payload(self):
            return json.loads(self.wfile.getvalue().decode())

    h = Driver()
    h.do_GET()
    return h


def test_latest_returns_200_when_no_release_exists():
    """A site live before its first release is normal, not an error.

    Returning 404 put a red error in every visitor's browser console.
    """
    latest = _load("latest")

    def not_found(url, token, accept):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    latest._gh = not_found
    code, body = latest.build_payload("token", "owner/repo")
    assert code == 200, "no-release must not be reported as a 404"
    assert body["available"] is False
    assert "release" in body["message"].lower()


def test_download_explains_a_missing_release_instead_of_502(monkeypatch):
    """The exact failure a user hit: 502 Bad Gateway with no explanation."""
    dl = _load("download")
    monkeypatch.setenv("GITHUB_TOKEN", "token")

    def not_found(url, token, accept):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    dl._gh = not_found
    h = _run(dl.handler, "/api/download?file=setup")
    assert h.sent == 404, f"expected an explained 404, got {h.sent}"
    body = h.payload()
    assert body["error"] == "no_release"
    assert "published" in body["message"].lower()


def test_download_reports_an_invalid_token_clearly(monkeypatch):
    dl = _load("download")
    monkeypatch.setenv("GITHUB_TOKEN", "token")

    def denied(url, token, accept):
        raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)

    dl._gh = denied
    h = _run(dl.handler, "/api/download?file=setup")
    assert h.sent == 503
    assert h.payload()["error"] == "token_invalid"


def test_download_never_lets_an_exception_become_a_bare_502(monkeypatch):
    """An unhandled exception is killed by the platform as a raw 502."""
    dl = _load("download")
    monkeypatch.setenv("GITHUB_TOKEN", "token")

    def explode(url, token, accept):
        raise RuntimeError("kaboom")

    dl._gh = explode
    h = _run(dl.handler, "/api/download?file=setup")
    assert h.sent is not None, "the handler crashed instead of responding"
    assert h.payload().get("message"), "no explanation returned"


def test_download_rejects_path_traversal(monkeypatch):
    dl = _load("download")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    h = _run(dl.handler, "/api/download?file=../../etc/passwd")
    assert h.sent == 400
    assert h.payload()["error"] == "unknown_file"


def test_download_page_disables_buttons_until_a_release_exists():
    """Live buttons pointing at an unservable endpoint produced the 502."""
    html = (ROOT / "website" / "download.html").read_text(encoding="utf-8")
    assert "disableDownloads" in html, "buttons are never disabled"
    # Must start disabled, so a slow or failed request cannot leave a dead
    # link clickable.
    pre = html.index("disableDownloads('Checking availability")
    fetch_at = html.index("fetch('/api/latest'")
    assert pre < fetch_at, "buttons are clickable before availability is known"
    assert "enableDownloads()" in html, "buttons are never re-enabled"
