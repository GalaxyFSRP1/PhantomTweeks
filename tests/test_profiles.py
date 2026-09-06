"""Profiles and snapshots may only reference settings we actually manage."""
import pytest

from phantom_tweeks.engine import profiles
from phantom_tweeks.engine.catalog import BY_ID


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    from phantom_tweeks.core import paths
    monkeypatch.setattr(paths, "PROFILES", tmp_path / "profiles")
    monkeypatch.setattr(paths, "SNAPSHOTS", tmp_path / "snapshots")
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    for p in (paths.PROFILES, paths.SNAPSHOTS):
        p.mkdir(parents=True, exist_ok=True)


def test_builtin_profiles_reference_real_optimizations():
    for prof in profiles.BUILTIN_PRESETS:
        for oid in prof.optimization_ids:
            assert oid in BY_ID, f"{prof.name} references unknown id {oid}"


def test_profile_sanitize_strips_unmanaged_ids():
    p = profiles.GameProfile(name="Test", optimization_ids=["win.game_mode", "evil.hack"])
    p.sanitize()
    assert p.optimization_ids == ["win.game_mode"]


def test_profiles_do_not_auto_apply_by_default():
    for prof in profiles.BUILTIN_PRESETS:
        assert prof.auto_apply is False


def test_save_and_load_roundtrip():
    p = profiles.GameProfile(name="My Game", game="My Game", fps_target=144)
    profiles.save(p)
    loaded = profiles.load("My Game")
    assert loaded is not None
    assert loaded.fps_target == 144


def test_esports_titles_get_competitive_profile():
    assert profiles.profile_for_game("Counter-Strike 2").name == "Competitive"
    assert profiles.profile_for_game("VALORANT").name == "Competitive"
    assert profiles.profile_for_game("Some Story RPG").name == "Balanced"


def test_snapshot_only_contains_managed_settings():
    snap = profiles.create_snapshot("Everyday")
    assert set(snap.values).issubset(set(BY_ID) | {"power.high_performance"})
    for key in snap.values:
        assert key in BY_ID


def test_streaming_profile_protects_capture_tools():
    streaming = next(p for p in profiles.BUILTIN_PRESETS if p.name == "Streaming")
    notes = " ".join(streaming.background_notes).lower()
    assert "obs" in notes and "protected" in notes
