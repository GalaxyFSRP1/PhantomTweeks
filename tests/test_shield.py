"""Phantom Shield is the safety guarantee. These tests are non-negotiable."""
import pytest

from phantom_tweeks.core.shield import (ANTI_CHEAT, LAUNCHERS, PhantomShield,
                                        PROTECTED_SERVICES)


@pytest.fixture
def shield():
    return PhantomShield()


@pytest.mark.parametrize("name", [
    "steam.exe", "discord.exe", "EpicGamesLauncher.exe", "gamingservices.exe",
    "Battle.net.exe", "RiotClientServices.exe", "EADesktop.exe", "upc.exe",
    "obs64.exe", "EasyAntiCheat.exe", "BEService.exe", "vgc.exe",
    "nvcontainer.exe", "RadeonSoftware.exe", "lghub.exe",
    "csrss.exe", "lsass.exe", "MsMpEng.exe", "SecurityHealthService.exe",
])
def test_core_processes_are_protected(shield, name):
    assert shield.is_protected(name), f"{name} must be protected"


@pytest.mark.parametrize("action", [
    "terminate", "suspend", "set_priority", "set_affinity", "inject",
    "modify_files", "stop_service",
])
def test_every_dangerous_action_is_blocked(shield, action):
    for name in ("steam.exe", "discord.exe", "vgc.exe", "obs64.exe"):
        decision = shield.guard(name, action)
        assert not decision.allowed
        assert "Phantom Shield blocked" in decision.reason


def test_case_insensitive(shield):
    assert shield.is_protected("STEAM.EXE")
    assert shield.is_protected("Discord.exe")


def test_wildcard_patterns(shield):
    assert shield.is_protected("mhyprot3.exe")


def test_current_game_is_protected(shield):
    assert not shield.is_protected("mygame.exe")
    shield.set_game_processes({"mygame.exe"})
    assert shield.is_protected("mygame.exe")
    assert shield.classify("mygame.exe")[0] == "Current Game"
    assert not shield.guard("mygame.exe", "terminate").allowed


def test_user_protected_apps(shield):
    shield.add_user_protected("MyTool.exe")
    assert shield.is_protected("mytool.exe")
    shield.remove_user_protected("MyTool.exe")
    assert not shield.is_protected("mytool.exe")


def test_unknown_process_fails_closed(shield):
    """An unidentifiable process must never be actioned."""
    assert not shield.guard(None, "terminate").allowed
    assert not shield.guard("", "terminate").allowed


def test_unprotected_process_is_allowed(shield):
    assert shield.guard("notepad.exe", "inspect").allowed


@pytest.mark.parametrize("service", sorted(PROTECTED_SERVICES))
def test_protected_services_cannot_be_stopped(shield, service):
    assert not shield.guard_service(service, "stop").allowed
    assert not shield.guard_service(service.upper(), "disable").allowed


def test_dashboard_shape(shield):
    d = shield.dashboard()
    assert d["status"] == "ACTIVE"
    assert isinstance(d["protected_count"], int)
    assert isinstance(d["groups"], dict)


def test_all_launchers_and_anticheat_classify():
    s = PhantomShield()
    for name in list(LAUNCHERS) + list(ANTI_CHEAT):
        if "*" in name:
            continue
        assert s.classify(name) is not None, name
