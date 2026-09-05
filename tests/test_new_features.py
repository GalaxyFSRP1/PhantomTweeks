"""Tests for game auto-detection, Maintenance Mode, history and Premium gating.

These focus on the promises the product makes, not on implementation detail:
nothing runs while a game is playing, nothing personal is deleted, safety
features are never paywalled, and no locked feature fabricates results.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from phantom_tweeks.core import features, gamewatch          # noqa: E402
from phantom_tweeks.engine import history, maintenance       # noqa: E402


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Point the app's data directory at a temp folder."""
    from phantom_tweeks.core import paths
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    monkeypatch.setattr(paths, "ensure_dirs", lambda: None)
    return tmp_path


# ------------------------------------------------------------- game watcher

class _FakeGame:
    def __init__(self, name="Test Game", pid=1234, anti_cheat=None):
        self.name = name
        self.pid = pid
        self.executable = "game.exe"
        self.executable_path = None
        self.launcher = "Steam"
        self.anti_cheat = anti_cheat
        self.process_tree = [pid]
        self.install_dir = None


def test_watcher_requires_repeated_sightings_before_declaring_a_start(monkeypatch):
    """Launchers spawn helper processes; a single sighting must not count.

    Without this the UI flaps between "game running" and "no game" during
    startup.
    """
    game = _FakeGame()
    monkeypatch.setattr(gamewatch.games, "detect_running_game",
                        lambda lib=None: game)
    monkeypatch.setattr(gamewatch.games, "scan_library", lambda: [])

    started = []
    w = gamewatch.GameWatcher(confirm_polls=2,
                              on_start=lambda g: started.append(g))
    w.poll_once()
    assert started == [], "declared a start after a single sighting"
    w.poll_once()
    assert len(started) == 1, "never confirmed the start"
    w.poll_once()
    assert len(started) == 1, "fired on_start more than once"


def test_watcher_detects_a_game_that_was_already_running(monkeypatch):
    """The app must notice a game launched before it opened."""
    monkeypatch.setattr(gamewatch.games, "detect_running_game",
                        lambda lib=None: _FakeGame())
    monkeypatch.setattr(gamewatch.games, "scan_library", lambda: [])
    w = gamewatch.GameWatcher(confirm_polls=1)
    w.poll_once()
    assert w.state.running
    assert w.state.game.name == "Test Game"


def test_watcher_fires_stop_when_the_game_exits(monkeypatch):
    seq = [_FakeGame(), _FakeGame(), None]
    monkeypatch.setattr(gamewatch.games, "scan_library", lambda: [])
    monkeypatch.setattr(gamewatch.games, "detect_running_game",
                        lambda lib=None: seq.pop(0) if seq else None)
    stopped = []
    w = gamewatch.GameWatcher(confirm_polls=1, on_stop=lambda g: stopped.append(g))
    w.poll_once()
    w.poll_once()
    w.poll_once()
    assert len(stopped) == 1
    assert not w.state.running


def test_watcher_survives_a_detection_error(monkeypatch):
    """A failure in detection must not kill the watcher thread."""
    def boom(lib=None):
        raise RuntimeError("wmi exploded")
    monkeypatch.setattr(gamewatch.games, "detect_running_game", boom)
    monkeypatch.setattr(gamewatch.games, "scan_library", lambda: [])
    w = gamewatch.GameWatcher()
    state = w.poll_once()
    assert not state.running
    assert "wmi exploded" in state.last_error


def test_watcher_survives_a_broken_callback(monkeypatch):
    monkeypatch.setattr(gamewatch.games, "detect_running_game",
                        lambda lib=None: _FakeGame())
    monkeypatch.setattr(gamewatch.games, "scan_library", lambda: [])

    def bad(_g):
        raise ValueError("callback bug")

    w = gamewatch.GameWatcher(confirm_polls=1, on_start=bad)
    w.poll_once()          # must not raise
    assert w.state.running


def test_watcher_never_modifies_the_game_process():
    """Detection is observation only.

    Guards the golden rule: Phantom Tweeks must never reprioritise, suspend,
    or kill a running game.
    """
    src = Path(gamewatch.__file__).read_text(encoding="utf-8")
    for banned in ("terminate(", "kill(", "suspend(", "nice(",
                   "cpu_affinity(", "set_priority", "TerminateProcess"):
        assert banned not in src, f"gamewatch calls {banned}"


def test_watcher_thread_starts_and_stops_cleanly(monkeypatch):
    monkeypatch.setattr(gamewatch.games, "detect_running_game", lambda lib=None: None)
    monkeypatch.setattr(gamewatch.games, "scan_library", lambda: [])
    w = gamewatch.GameWatcher(interval=0.05)
    w.start()
    time.sleep(0.15)
    assert w.alive
    w.stop()
    assert not w.alive


# -------------------------------------------------------------- maintenance

def test_maintenance_refuses_to_run_while_a_game_is_playing(monkeypatch):
    """The single most important rule in this module.

    Competing for CPU and disk mid-match is exactly the sort of "help" that
    loses someone a game.
    """
    monkeypatch.setattr(maintenance, "game_is_running", lambda: "Counter-Strike")
    report = maintenance.run()
    assert not report.ran
    assert "Counter-Strike" in report.skipped_reason
    assert report.results == []


def test_maintenance_apply_also_refuses_during_a_game(monkeypatch):
    monkeypatch.setattr(maintenance, "game_is_running", lambda: "Valorant")
    out = maintenance.apply(["temp"], dry_run=False)
    assert out["applied"] == []
    assert any("Valorant" in s for s in out["skipped"])


def test_maintenance_runs_when_no_game_is_present(monkeypatch):
    monkeypatch.setattr(maintenance, "game_is_running", lambda: None)
    report = maintenance.run()
    assert report.ran
    assert len(report.results) == len(maintenance.TASKS)


def test_every_task_explains_why_it_matters(monkeypatch):
    """No cargo-culted advice: each task justifies itself."""
    monkeypatch.setattr(maintenance, "game_is_running", lambda: None)
    for result in maintenance.run().results:
        if result.error:
            continue
        assert result.why or result.summary, f"{result.task_id} explains nothing"


def test_maintenance_apply_defaults_to_a_dry_run(monkeypatch):
    monkeypatch.setattr(maintenance, "game_is_running", lambda: None)
    out = maintenance.apply(["temp"])
    assert out["dry_run"] is True, "apply() must not delete unless asked"


def test_maintenance_never_targets_personal_folders():
    """Documents, Downloads, Pictures and saves must never be cleanup targets."""
    src = Path(maintenance.__file__).read_text(encoding="utf-8")
    lowered = src.lower()
    for personal in ("documents", "downloads", "pictures", "desktop",
                     "videos", "onedrive", "recycle", "savegames"):
        # Allowed only in prose that promises NOT to touch them.
        for line in lowered.splitlines():
            if personal in line:
                assert ("never" in line or "not " in line or "#" in line
                        or "untouched" in line or "no " in line), (
                    f"{personal!r} appears in a non-disclaiming line: {line}")


def test_dry_run_does_not_delete_anything(tmp_path, monkeypatch):
    victim = tmp_path / "junk.tmp"
    victim.write_text("x" * 2_000_000)      # 2 MB, so the rounded MB is visible
    monkeypatch.setenv("TEMP", str(tmp_path))
    monkeypatch.setenv("TMP", str(tmp_path))
    monkeypatch.setattr(maintenance, "game_is_running", lambda: None)

    out = maintenance.apply(["temp"], dry_run=True)
    assert victim.exists(), "dry run deleted a file"
    assert out["freed_mb"] > 0, "dry run reported nothing"


def test_real_run_deletes_only_the_targeted_cache(tmp_path, monkeypatch):
    temp = tmp_path / "temp"
    temp.mkdir()
    (temp / "a.tmp").write_text("x" * 2048)
    keep = tmp_path / "Documents"
    keep.mkdir()
    (keep / "important.docx").write_text("do not delete")

    monkeypatch.setenv("TEMP", str(temp))
    monkeypatch.setenv("TMP", str(temp))
    monkeypatch.setattr(maintenance, "game_is_running", lambda: None)

    maintenance.apply(["temp"], dry_run=False)
    assert not (temp / "a.tmp").exists(), "temp file was not removed"
    assert (keep / "important.docx").exists(), "a personal file was deleted"


def test_schedule_round_trips(data_dir):
    maintenance.save_schedule(maintenance.SCHEDULE_WEEKLY)
    assert maintenance.load_schedule()["schedule"] == "weekly"


def test_unknown_schedule_is_rejected(data_dir):
    with pytest.raises(ValueError):
        maintenance.save_schedule("hourly")


def test_scheduled_run_is_never_due_during_a_game(data_dir, monkeypatch):
    maintenance.save_schedule(maintenance.SCHEDULE_WEEKLY, last_run=0.0)
    monkeypatch.setattr(maintenance, "game_is_running", lambda: "Apex Legends")
    assert maintenance.is_due() is False


def test_schedule_off_is_never_due(data_dir, monkeypatch):
    maintenance.save_schedule(maintenance.SCHEDULE_OFF, last_run=0.0)
    monkeypatch.setattr(maintenance, "game_is_running", lambda: None)
    assert maintenance.is_due() is False


def test_disk_check_flags_low_space(monkeypatch):
    class Usage:
        total = 500 * 1024 ** 3
        free = 10 * 1024 ** 3      # 2%
        used = total - free
    monkeypatch.setattr(maintenance.shutil, "disk_usage", lambda p: Usage())
    r = maintenance.task_disk_space()
    assert r.severity == maintenance.SEVERITY_ATTENTION


# ----------------------------------------------------------------- history

def test_history_records_and_reads_back(data_dir):
    history.record("avg_fps", 120.0, "fps")
    history.record("avg_fps", 118.0, "fps")
    entries = history.load("avg_fps")
    assert len(entries) == 2
    assert entries[-1].value == 118.0


def test_history_ignores_corrupt_lines(data_dir):
    history.record("avg_fps", 100.0, "fps")
    with (data_dir / "history.jsonl").open("a", encoding="utf-8") as fh:
        fh.write("this is not json\n")
    assert len(history.load()) == 1, "a corrupt line broke the whole file"


def test_small_changes_are_reported_as_noise_not_improvement(data_dir):
    """Never dress measurement noise up as a win."""
    for v in (120.0, 121.0, 119.0, 120.5):
        history.record("avg_fps", v, "fps")
    t = history.trend("avg_fps")
    assert t.improved is None
    assert "variation" in t.verdict.lower()


def test_a_real_regression_is_detected(data_dir):
    for v in (120.0, 121.0, 119.0, 85.0):
        history.record("avg_fps", v, "fps")
    t = history.trend("avg_fps")
    assert t.improved is False
    assert t.change_pct < -20


def test_lower_is_better_metrics_invert_correctly(data_dir):
    history.record("p1_low_ms", 20.0, "ms")
    history.record("p1_low_ms", 10.0, "ms")
    t = history.trend("p1_low_ms")
    assert t.improved is True, "a lower frame time must count as better"
    assert t.best == 10.0


def test_single_measurement_makes_no_claim(data_dir):
    history.record("avg_fps", 100.0, "fps")
    t = history.trend("avg_fps")
    assert t.improved is None
    assert "first" in t.verdict.lower()


def test_free_tier_keeps_the_data_it_does_not_chart(data_dir):
    """Free users' data is retained, not deleted."""
    for i in range(25):
        history.record("avg_fps", 100.0 + i, "fps")
    data = history.summary(premium=False)
    assert data["total_entries"] == 25
    assert "note" in data


def test_history_is_never_uploaded():
    src = Path(history.__file__).read_text(encoding="utf-8")
    for banned in ("requests.", "urlopen", "http://", "https://", "socket."):
        assert banned not in src, f"history module references {banned}"


# --------------------------------------------------------- premium gating

def test_safety_features_are_never_premium():
    """Charging for the ability to undo our own changes would be indefensible."""
    for fid in features.FREE_FOREVER:
        f = features.get(fid)
        assert f is not None, f"{fid} promised free but missing from the catalog"
        assert not f.is_premium, f"{fid} is a safety feature and must stay free"


def test_locked_feature_reports_locked_and_offers_no_data(monkeypatch):
    from phantom_tweeks.core import premium
    monkeypatch.setattr(premium, "is_premium", lambda: False)
    gate = features.check("history_trends")
    assert not gate.allowed
    assert not bool(gate)
    assert "Premium" in gate.reason


def test_premium_unlocks_when_licensed(monkeypatch):
    from phantom_tweeks.core import premium
    monkeypatch.setattr(premium, "is_premium", lambda: True)
    assert features.check("history_trends").allowed


def test_unknown_feature_ids_fail_open():
    """A typo must never silently disable a working feature."""
    assert features.check("not-a-real-feature").allowed


def test_free_features_are_always_allowed(monkeypatch):
    from phantom_tweeks.core import premium
    monkeypatch.setattr(premium, "is_premium", lambda: False)
    for f in features.free_features():
        assert features.check(f.id).allowed, f"{f.id} was gated"


def test_no_payment_processing_in_the_app():
    src = Path(features.__file__).read_text(encoding="utf-8")
    lowered = src.lower()
    for banned in ("stripe", "paypal", "card_number", "cvv", "checkout.session"):
        assert banned not in lowered, f"payment code found: {banned}"


def test_every_advertised_premium_feature_is_implemented():
    """No placeholder cards selling things that were never built."""
    for f in features.premium_features():
        assert f.implemented, f"{f.name} is advertised but not implemented"
        assert f.summary, f"{f.name} has no description"


def test_summary_states_the_free_promise_and_payment_position():
    data = features.summary()
    assert "free" in data["promise"].lower()
    assert "no payment processing" in data["payment_note"].lower()
