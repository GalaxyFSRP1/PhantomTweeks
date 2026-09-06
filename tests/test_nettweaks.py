"""Tests for the network tweak toggles and the developer unlock."""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from phantom_tweeks.engine import nettweaks  # noqa: E402


def test_there_are_at_least_ten_network_tweaks():
    assert len(nettweaks.TWEAKS) >= 10


def test_ids_are_unique_and_every_tweak_is_complete():
    ids = [t.id for t in nettweaks.TWEAKS]
    assert len(ids) == len(set(ids))
    for t in nettweaks.TWEAKS:
        assert t.name and t.effect
        assert len(t.detail) > 60, f"{t.id} does not explain itself"
        assert t.apply is not None, f"{t.id} does nothing"


def test_no_tweak_claims_to_lower_ping():
    """The single most common false promise in this category.

    These reduce PC-side delay. None of them change the distance to a game
    server, and saying otherwise would be a lie.
    """
    src = Path(nettweaks.__file__).read_text(encoding="utf-8").lower()
    for claim in ("lower your ping", "lowers ping", "reduce your ping",
                  "reduces ping", "better ping", "less ping",
                  "improve your ping", "faster ping", "ping reduction"):
        assert claim not in src, f"nettweaks promises: {claim!r}"


def test_the_module_says_plainly_what_it_does_not_do():
    # The disclaimer wraps across lines, so compare on collapsed whitespace.
    text = " ".join(nettweaks.summary().lower().split())
    assert "do not change the distance to a game server" in text


def test_risky_tweaks_carry_a_warning():
    """Toggles with no analysis step still have to flag what can backfire."""
    for tid in ("interrupt_moderation", "nic_power_saving"):
        t = nettweaks.BY_ID[tid]
        assert t.warning, f"{tid} can backfire but carries no warning"


def test_toggling_off_restores_the_windows_default(monkeypatch):
    """Off must undo, not merely stop applying."""
    writes = []
    monkeypatch.setattr(nettweaks, "IS_WINDOWS", True)
    monkeypatch.setattr(nettweaks, "is_admin", lambda: True)
    monkeypatch.setattr(nettweaks, "_adapter_guids",
                        lambda: ["{00000000-0000-0000-0000-000000000000}"])
    monkeypatch.setattr(nettweaks.ws, "write_registry",
                        lambda h, k, n, v, **kw: writes.append((n, v)))

    nettweaks.set_tweak("nagle", True)
    on = dict(writes)
    writes.clear()
    nettweaks.set_tweak("nagle", False)
    off = dict(writes)

    assert on["TCPNoDelay"] == 1 and off["TCPNoDelay"] == 0
    assert on["TcpAckFrequency"] == 1 and off["TcpAckFrequency"] == 2


def test_admin_is_required_and_reported(monkeypatch):
    monkeypatch.setattr(nettweaks, "IS_WINDOWS", True)
    monkeypatch.setattr(nettweaks, "is_admin", lambda: False)
    ok, message, changes = nettweaks.set_tweak("nagle", True)
    assert not ok
    assert "administrator" in message.lower()
    assert changes == []


def test_unknown_tweak_is_rejected():
    ok, message, _ = nettweaks.set_tweak("not-a-tweak", True)
    assert not ok
    assert "Unknown" in message


def test_states_never_raises(monkeypatch):
    def boom():
        raise RuntimeError("registry unavailable")
    monkeypatch.setattr(nettweaks.BY_ID["nagle"], "is_on", boom)
    assert nettweaks.states()["nagle"] is False


def test_nothing_touches_security_settings():
    src = Path(nettweaks.__file__).read_text(encoding="utf-8")
    for i, line in enumerate(src.splitlines(), 1):
        stripped = line.strip()
        # Skip comments and docstring prose: the module explicitly promises
        # NOT to touch these, and that sentence must not trip the check.
        if stripped.startswith(("#", "*", '"""', "'")):
            continue
        low = stripped.lower()
        for banned in ("defender", "firewall", "wuauserv",
                       "disableantispyware", "tamperprotection"):
            assert banned not in low, (
                f"line {i} touches {banned}: {stripped[:70]}")


def test_a_broken_adapter_does_not_abort_the_rest(monkeypatch):
    monkeypatch.setattr(nettweaks, "_adapter_guids", lambda: ["{A}", "{B}"])
    calls = []

    def flaky(hive, key, name, value, **kw):
        calls.append(key)
        if "{A}" in key:
            raise OSError("access denied on this adapter")
        return object()

    monkeypatch.setattr(nettweaks.ws, "write_registry", flaky)
    changes = nettweaks._set_on_all_adapters("X", 1, "test")
    assert len(calls) == 2, "stopped after the first failure"
    assert len(changes) == 1, "the working adapter was not configured"


# ----------------------------------------------------------- dev unlock

@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    from phantom_tweeks.core import paths
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    monkeypatch.setattr(paths, "ensure_dirs", lambda: None)
    return tmp_path


def test_wrong_code_does_not_unlock(data_dir):
    from phantom_tweeks.core import premium
    ok, _ = premium.try_dev_unlock("hunter2")
    assert not ok
    assert not premium.dev_unlock_active()


def test_developer_code_unlocks_premium_locally(data_dir):
    from phantom_tweeks.core import premium, features
    ok, message = premium.try_dev_unlock("adminsaregood25")
    assert ok
    assert premium.is_premium()
    assert features.check("history_trends").allowed
    assert "not a licence" in message.lower(), (
        "the unlock must not present itself as a purchase")


def test_dev_unlock_is_reported_honestly(data_dir):
    from phantom_tweeks.core import premium
    premium.try_dev_unlock("adminsaregood25")
    st = premium.license_status()
    assert st["developer"] is True
    assert "developer" in st["plan"].lower()
    assert "not a purchased licence" in st["message"].lower()


def test_dev_unlock_can_be_removed(data_dir):
    from phantom_tweeks.core import premium
    premium.try_dev_unlock("adminsaregood25")
    ok, _ = premium.clear_dev_unlock()
    assert ok
    assert not premium.is_premium()


def test_the_code_is_not_stored_in_plaintext():
    src = (ROOT / "src" / "phantom_tweeks" / "core"
           / "premium.py").read_text(encoding="utf-8")
    assert "adminsaregood25" not in src, (
        "the developer code is a literal string in the shipped source")
