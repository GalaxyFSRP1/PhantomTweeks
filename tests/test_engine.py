"""Backup/restore, evaluation and comparison logic."""
import pytest

from phantom_tweeks.engine.backup import ABSENT, BackupVault, ChangeRecord
from phantom_tweeks.engine import comparison
from phantom_tweeks.engine.frametime import FrameTimeStats, analyze_frame_times


@pytest.fixture
def vault(tmp_path, monkeypatch):
    from phantom_tweeks.core import paths
    monkeypatch.setattr(paths, "BACKUPS", tmp_path / "backups")
    monkeypatch.setattr(paths, "HISTORY", tmp_path / "history")
    monkeypatch.setattr(paths, "HISTORY_DB", tmp_path / "history" / "history.json")
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    for p in (paths.BACKUPS, paths.HISTORY):
        p.mkdir(parents=True, exist_ok=True)
    return BackupVault()


def test_backup_roundtrip(vault):
    changes = [ChangeRecord("registry", "HKCU\\Test", "Value", 0, 1, "REG_DWORD")]
    entry = vault.create("Test run", changes, ["win.game_mode"])
    loaded = vault.get(entry.id)
    assert loaded is not None
    assert loaded.change_count == 1
    assert loaded.changes[0].previous == 0
    assert loaded.changes[0].applied == 1


def test_backup_records_absent_sentinel(vault):
    changes = [ChangeRecord("registry", "HKCU\\Test", "New", ABSENT, 1, "REG_DWORD")]
    entry = vault.create("Absent test", changes)
    assert vault.get(entry.id).changes[0].previous == ABSENT


def test_verify_rejects_empty_backup(vault):
    entry = vault.create("Empty", [])
    ok, msg = vault.verify(entry)
    assert not ok


def test_verify_accepts_valid_backup(vault):
    entry = vault.create("Valid", [ChangeRecord("registry", "H\\K", "N", 0, 1)])
    ok, msg = vault.verify(entry)
    assert ok


def test_history_records_and_marks_restored(vault):
    entry = vault.create("Run", [ChangeRecord("registry", "H\\K", "N", 0, 1)])
    assert vault.history()[0]["id"] == entry.id
    vault.mark_restored(entry)
    assert vault.history()[0]["restored"] is True


def test_unknown_change_kind_is_refused():
    from phantom_tweeks.engine import winsettings as ws
    ok, msg = ws.revert(ChangeRecord("mystery", "x", "y", 1, 2))
    assert not ok
    assert "skipped for safety" in msg


# ---------------- frame time ----------------

def test_frame_analysis_requires_enough_samples():
    st = analyze_frame_times([16.6] * 10, "test")
    assert not st.available


def test_frame_analysis_computes_lows():
    frames = [16.6] * 990 + [50.0] * 10
    st = analyze_frame_times(frames, "test")
    assert st.available
    assert st.frames == 1000
    assert st.p1_low_ms > st.avg_ms
    assert st.p01_low_ms >= st.p1_low_ms
    assert st.stutter_count == 10
    assert 55 < st.avg_fps < 62


def test_perfect_pacing_scores_high():
    st = analyze_frame_times([16.6] * 500, "test")
    assert st.pacing_score >= 95
    assert st.pacing_label == "Excellent"


def test_erratic_pacing_scores_low():
    import itertools
    frames = list(itertools.islice(itertools.cycle([8.0, 30.0]), 500))
    st = analyze_frame_times(frames, "test")
    assert st.pacing_score < 50
    assert st.pacing_label == "Poor"


# ---------------- comparison ----------------

def test_comparison_detects_regression():
    before = analyze_frame_times([10.0] * 500, "b")
    after = analyze_frame_times([12.0] * 500, "a")   # ~17% slower
    rep = comparison.compare(before, after, regression_threshold=5.0)
    assert rep.regression
    assert "restoring" in rep.conclusion.lower()


def test_comparison_reports_honest_no_change():
    before = analyze_frame_times([10.0] * 500, "b")
    after = analyze_frame_times([10.05] * 500, "a")
    rep = comparison.compare(before, after)
    assert not rep.regression
    assert "No measurable improvement" in rep.conclusion


def test_comparison_reports_improvement():
    before = analyze_frame_times([10.0] * 500, "b")
    after = analyze_frame_times([8.5] * 500, "a")
    rep = comparison.compare(before, after)
    assert not rep.regression
    assert "improved" in rep.conclusion.lower()


def test_comparison_without_data_refuses_to_claim():
    rep = comparison.compare(FrameTimeStats("none"), FrameTimeStats("none"))
    assert "will not claim" in rep.conclusion


def test_small_deltas_flagged_as_noise():
    m = comparison.Metric("FPS", 100, 101)
    assert not m.meaningful
    assert comparison.Metric("FPS", 100, 110).meaningful
