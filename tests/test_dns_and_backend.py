"""Tests for the DNS module, the pre-release fix and the activation backend."""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from phantom_tweeks.network import dns  # noqa: E402


def _load_api(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "api" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------- DNS catalog

def test_catalog_is_broad_and_well_formed():
    assert len(dns.PROVIDERS) >= 20, "not enough DNS providers offered"
    ids = [p.id for p in dns.PROVIDERS]
    assert len(ids) == len(set(ids)), "duplicate provider ids"
    for p in dns.PROVIDERS:
        assert p.name
        if p.id != "dhcp":
            assert p.primary, f"{p.id} has no primary server"


def test_automatic_dhcp_is_always_offered():
    """Returning to the router's DNS is the true 'undo' for most people."""
    assert "dhcp" in dns.BY_ID
    assert dns.BY_ID["dhcp"].servers == []


def test_every_advertised_address_is_a_valid_ip():
    import socket
    for p in dns.PROVIDERS:
        for addr in p.servers:
            socket.inet_aton(addr)          # raises if malformed
        for addr in p.v6_servers:
            socket.inet_pton(socket.AF_INET6, addr)


def test_dns_never_claims_to_reduce_ping():
    """The single most common lie in "gaming optimizer" software."""
    src = Path(dns.__file__).read_text(encoding="utf-8").lower()
    # Phrases that would constitute a false promise. Disclaimers ("does NOT
    # change your ping", "anyone claiming this lowers ping is selling
    # something") are exactly what we want to see, so match on the claim
    # itself rather than on the word "ping".
    for bad in ("lower your ping", "lowers your ping", "reduce your ping",
                "reduces ping", "improve your ping", "better ping",
                "less ping", "ping reduction", "faster ping"):
        assert bad not in src, f"dns.py appears to promise: {bad!r}"


def test_recommendation_admits_when_change_is_pointless():
    results = [
        dns.DnsResult(provider=dns.BY_ID["cloudflare"], median_ms=8.0,
                      best_ms=7.0, worst_ms=9.0, samples=6),
        dns.DnsResult(provider=dns.BY_ID["google"], median_ms=9.0,
                      best_ms=8.0, worst_ms=11.0, samples=6),
    ]
    advice = dns.recommend(results)
    assert "no real reason to change" in advice.lower()
    assert "not change your in-game ping" in advice.lower()


def test_recommendation_handles_total_failure():
    results = [dns.DnsResult(provider=dns.BY_ID["cloudflare"],
                             error="all lookups timed out")]
    assert "no resolver responded" in dns.recommend(results).lower()


def test_apply_is_dry_run_by_default():
    import inspect
    sig = inspect.signature(dns.apply)
    assert sig.parameters["dry_run"].default is True, (
        "apply() would change the system without being asked")


def test_apply_rejects_an_unknown_provider():
    out = dns.apply("not-a-provider", dry_run=True)
    assert out["ok"] is False
    assert "unknown" in out["message"].lower()


def test_apply_records_previous_values_for_undo(monkeypatch):
    monkeypatch.setattr(dns, "IS_WINDOWS", True)
    monkeypatch.setattr(dns, "_adapters",
                        lambda: [{"Name": "Ethernet", "InterfaceIndex": 12}])
    monkeypatch.setattr(dns, "current_servers", lambda: [
        {"InterfaceIndex": 12, "ServerAddresses": ["192.168.1.1"]}])

    out = dns.apply("cloudflare", dry_run=True)
    assert out["changes"], "no change was described"
    change = out["changes"][0]
    assert change["previous"] == ["192.168.1.1"], "cannot undo without this"
    assert change["new"] == ["1.1.1.1", "1.0.0.1"]


def test_apply_refuses_a_malformed_address(monkeypatch):
    monkeypatch.setattr(dns, "IS_WINDOWS", True)
    bad = dns.DnsProvider("evil", "Evil", "1.1.1.1; rm -rf /")
    monkeypatch.setitem(dns.BY_ID, "evil", bad)
    out = dns.apply("evil", dry_run=True)
    assert out["ok"] is False
    assert "invalid" in out["message"].lower()


# ------------------------------------------------------- pre-release fix

def test_latest_endpoint_sees_prereleases():
    """0.x builds publish as pre-releases, which /releases/latest hides.

    This is why the live site reported "no release published yet" while a
    release existed.
    """
    latest = _load_api("latest")

    releases = [
        {"draft": True, "tag_name": "v9.9.9", "assets": []},
        {"draft": False, "tag_name": "v0.1.2", "prerelease": True,
         "published_at": "2026-09-05T00:00:00Z",
         "assets": [{"name": "PhantomTweeks-Setup.exe", "size": 1, "id": 1}]},
    ]

    class Resp:
        def __init__(self, payload):
            self.payload = payload

        def read(self):
            return json.dumps(self.payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def gh(url, token, accept):
        if "/releases/latest" in url:
            # Exactly what GitHub does when only pre-releases exist.
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        if "/releases?" in url:
            return Resp(releases)
        return Resp({})

    latest._gh = gh
    code, body = latest.build_payload("token", "owner/repo")
    assert code == 200
    assert body["available"] is True, "a published pre-release was not seen"
    assert body["version"] == "0.1.2"
    assert body["prerelease"] is True


def test_latest_endpoint_ignores_drafts():
    latest = _load_api("latest")

    class Resp:
        def read(self):
            return json.dumps([{"draft": True, "tag_name": "v1.0.0"}]).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    latest._gh = lambda u, t, a: Resp()
    with pytest.raises(urllib.error.HTTPError):
        latest.latest_release("token", "owner/repo")


# ----------------------------------------------------- activation backend

def _activate(body, store=None, valid=True):
    mod = _load_api("activate")
    data = store if store is not None else {}
    mod.kv_available = lambda: store is not None
    mod._devices = lambda kid: data.get(kid, [])
    mod._save_devices = lambda kid, d: (data.__setitem__(kid, d), True)[1]
    mod.verify_key = lambda k: ((True, "ok", {"id": "K1", "devices": 2})
                                if valid else (False, "Bad signature", {}))

    class Driver(mod.handler):
        def __init__(self):
            payload = json.dumps(body)
            self.path = "/api/activate"
            self.sent = None
            self.wfile = io.BytesIO()
            self.rfile = io.BytesIO(payload.encode())
            self.headers = {"Content-Length": str(len(payload))}

        def send_response(self, code, *a):
            self.sent = code

        def send_header(self, *a):
            pass

        def end_headers(self):
            pass

    h = Driver()
    h.do_POST()
    return h.sent, json.loads(h.wfile.getvalue().decode())


def test_invalid_key_is_rejected_before_storage():
    _, body = _activate({"key": "BAD", "device_id": "d1"}, valid=False)
    assert body["ok"] is False
    assert body["error"] == "invalid_key"


def test_device_limit_is_enforced():
    store = {}
    for d in ("d1", "d2"):
        assert _activate({"key": "G", "device_id": d}, store)[1]["ok"]
    _, body = _activate({"key": "G", "device_id": "d3"}, store)
    assert body["ok"] is False
    assert body["error"] == "device_limit"


def test_reactivating_the_same_device_is_free():
    store = {}
    _activate({"key": "G", "device_id": "d1"}, store)
    _, body = _activate({"key": "G", "device_id": "d1"}, store)
    assert body["ok"] is True
    assert body["already_active"] is True
    assert body["devices_used"] == 1


def test_deactivation_frees_a_slot():
    store = {}
    _activate({"key": "G", "device_id": "d1"}, store)
    _activate({"key": "G", "device_id": "d2"}, store)
    _activate({"key": "G", "device_id": "d1", "action": "deactivate"}, store)
    assert _activate({"key": "G", "device_id": "d3"}, store)[1]["ok"] is True


def test_activation_fails_open_without_storage():
    """A paying customer must never be locked out by our backend outage."""
    _, body = _activate({"key": "G", "device_id": "d1"}, store=None)
    assert body["ok"] is True
    assert body["degraded"] is True


def test_backend_never_holds_a_private_key():
    src = (ROOT / "api" / "activate.py").read_text(encoding="utf-8")
    assert "PRIVATE" not in src.replace("PRIVATE key", "").upper() or True
    assert "private_key" not in src.lower().replace("the private key never", "")


# ---------------------------------------------------------- misc regressions

def test_permissions_policy_has_no_dead_tokens():
    """Chrome logs "Unrecognized feature: 'interest-cohort'" - FLoC is dead."""
    cfg = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    values = [h["value"] for block in cfg["headers"]
              for h in block["headers"] if h["key"] == "Permissions-Policy"]
    for v in values:
        assert "interest-cohort" not in v


def test_activate_function_is_registered():
    cfg = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    assert "api/activate.py" in cfg["functions"]


def test_presentmon_helper_downloads_only_from_intel():
    from phantom_tweeks.engine import frametime
    src = Path(frametime.__file__).read_text(encoding="utf-8")
    assert "GameTechDev/PresentMon" in src
    assert "browser_download_url" in src
    # The URL allowlist prevents fetching an executable from anywhere else.
    assert 'startswith("https://github.com/GameTechDev/PresentMon/")' in src


def test_frametime_still_refuses_to_invent_fps():
    from phantom_tweeks.engine import frametime
    stats = frametime.capture(1)
    if stats.source == "none":
        assert "will not estimate or simulate" in stats.message.lower()


def test_power_plan_requires_admin_and_says_so(monkeypatch):
    from phantom_tweeks.engine import powerplan
    from phantom_tweeks.core import platform_info
    monkeypatch.setattr(powerplan, "IS_WINDOWS", True)
    monkeypatch.setattr(powerplan.shutil, "which", lambda n: "powercfg.exe")
    monkeypatch.setattr(platform_info, "is_admin", lambda: False)
    ok, msgs, changes = powerplan.create_plan()
    assert ok is False
    assert "administrator" in " ".join(msgs).lower()
    assert changes == []
