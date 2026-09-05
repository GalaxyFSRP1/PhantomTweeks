"""Restore is the user's only way back. It must degrade honestly."""
from __future__ import annotations

import importlib
import json

import pytest


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("PHANTOM_TWEEKS_HOME", str(tmp_path))
    from phantom_tweeks.core import paths
    importlib.reload(paths)
    from phantom_tweeks.engine import backup
    importlib.reload(backup)
    from phantom_tweeks.engine import optimizer
    importlib.reload(optimizer)
    yield backup, optimizer
    monkeypatch.undo()
    importlib.reload(paths)
    importlib.reload(backup)
    importlib.reload(optimizer)


def _changes(backup, n=4):
    return [backup.ChangeRecord(kind="registry", target=f"HKCU\\K{i}",
                                name="V", previous=i, applied=99)
            for i in range(n)]


def test_partial_restore_is_recorded_not_hidden(vault):
    backup, optimizer = vault
    entry = backup.VAULT.create("run", _changes(backup))
    optimizer.ws.revert = lambda c: (
        (False, "denied") if c.target == "HKCU\\K1" else (True, "ok"))

    ok, msgs = optimizer.OptimizationEngine().restore_backup(entry.id)
    assert ok is False
    saved = backup.VAULT.get(entry.id)
    assert saved.partially_restored is True
    assert saved.restored is False
    assert "Partially restored (3/4)" == saved.status
    assert any("3 of 4" in m for m in msgs)


def test_retry_resumes_and_does_not_redo_completed_work(vault):
    backup, optimizer = vault
    entry = backup.VAULT.create("run", _changes(backup))
    eng = optimizer.OptimizationEngine()

    optimizer.ws.revert = lambda c: (
        (False, "denied") if c.target == "HKCU\\K1" else (True, "ok"))
    eng.restore_backup(entry.id)

    calls = []

    def second(c):
        calls.append(c.target)
        return True, "ok"

    optimizer.ws.revert = second
    ok, _ = eng.restore_backup(entry.id)
    assert ok is True
    assert calls == ["HKCU\\K1"], f"retry redid finished work: {calls}"
    assert backup.VAULT.get(entry.id).restored is True


def test_restoring_a_finished_backup_is_a_safe_no_op(vault):
    backup, optimizer = vault
    entry = backup.VAULT.create("run", _changes(backup, 2))
    eng = optimizer.OptimizationEngine()
    optimizer.ws.revert = lambda c: (True, "ok")
    assert eng.restore_backup(entry.id)[0] is True

    calls = []
    optimizer.ws.revert = lambda c: (calls.append(c.target), (True, "ok"))[1]
    ok, msgs = eng.restore_backup(entry.id)
    assert ok is True and calls == []
    assert "already fully restored" in msgs[0]


def test_revert_exception_does_not_abort_the_whole_restore(vault):
    """One exploding change must not strand the remaining ones."""
    backup, optimizer = vault
    entry = backup.VAULT.create("run", _changes(backup, 4))

    def boom(c):
        if c.target == "HKCU\\K2":
            raise RuntimeError("winreg exploded")
        return True, "ok"

    optimizer.ws.revert = boom
    ok, msgs = optimizer.OptimizationEngine().restore_backup(entry.id)
    assert ok is False
    saved = backup.VAULT.get(entry.id)
    reverted = {c.target for c in saved.changes if c.reverted}
    assert reverted == {"HKCU\\K0", "HKCU\\K1", "HKCU\\K3"}
    assert any("Unexpected error" in m for m in msgs)


def test_restore_progress_survives_a_crash_mid_restore(vault):
    """State is flushed after each change, not just at the end."""
    backup, optimizer = vault
    entry = backup.VAULT.create("run", _changes(backup, 4))

    def die_after_two(c):
        if c.target == "HKCU\\K1":
            raise KeyboardInterrupt
        return True, "ok"

    optimizer.ws.revert = die_after_two
    with pytest.raises(KeyboardInterrupt):
        optimizer.OptimizationEngine().restore_backup(entry.id)

    saved = backup.VAULT.get(entry.id)
    assert {c.target for c in saved.changes if c.reverted} == {"HKCU\\K3", "HKCU\\K2"}
    assert [c.target for c in saved.pending_changes] == ["HKCU\\K1", "HKCU\\K0"]


def test_changes_revert_newest_first(vault):
    backup, optimizer = vault
    entry = backup.VAULT.create("run", _changes(backup, 4))
    order = []
    optimizer.ws.revert = lambda c: (order.append(c.target), (True, "ok"))[1]
    optimizer.OptimizationEngine().restore_backup(entry.id)
    assert order == ["HKCU\\K3", "HKCU\\K2", "HKCU\\K1", "HKCU\\K0"]


def test_missing_backup_reports_clearly(vault):
    backup, optimizer = vault
    ok, msgs = optimizer.OptimizationEngine().restore_backup("nope")
    assert ok is False and "not found" in msgs[0]


# ------------------------------------------------------------ verify()

def test_verify_accepts_absent_as_a_valid_prior_state(vault):
    """ABSENT means 'the key did not exist' — that IS reversible."""
    backup, _ = vault
    e = backup.BackupEntry(
        id="x", timestamp="t", title="t",
        changes=[backup.ChangeRecord(kind="registry", target="HKCU\\A", name="V",
                                     previous=backup.ABSENT, applied=1)])
    backup.VAULT._write(e)
    ok, msg = backup.VAULT.verify(e)
    assert ok is True, msg


def test_verify_rejects_a_change_with_no_prior_value(vault):
    backup, _ = vault
    e = backup.BackupEntry(
        id="y", timestamp="t", title="t",
        changes=[backup.ChangeRecord(kind="registry", target="HKCU\\A", name="V",
                                     previous=None, applied=1)])
    backup.VAULT._write(e)
    ok, msg = backup.VAULT.verify(e)
    assert ok is False and "no recorded" in msg


def test_verify_rejects_an_empty_backup(vault):
    backup, _ = vault
    e = backup.BackupEntry(id="z", timestamp="t", title="t", changes=[])
    ok, msg = backup.VAULT.verify(e)
    assert ok is False and "no change records" in msg


# ------------------------------------------------------------ compatibility

def test_backups_from_an_older_version_still_load(vault, tmp_path):
    """A backup the user cannot read is a backup they cannot roll back."""
    backup, _ = vault
    legacy = {
        "id": "legacy1", "timestamp": "2026-01-01T00:00:00", "title": "old",
        "optimization_ids": ["win.game_mode"],
        "changes": [{"kind": "registry", "target": "HKCU\\A", "name": "V",
                     "previous": 0, "applied": 1, "value_type": "REG_DWORD",
                     "note": "", "unknown_future_field": 123}],
        "restored": False, "restored_at": None,
        "some_removed_field": "ignored",
    }
    from phantom_tweeks.core import paths
    (paths.BACKUPS / "legacy1.json").write_text(json.dumps(legacy))
    e = backup.VAULT.get("legacy1")
    assert e is not None, "legacy backup failed to load"
    assert e.changes[0].reverted is False
    assert e.status == "Applied"


def test_corrupt_backup_does_not_crash_the_listing(vault):
    backup, _ = vault
    from phantom_tweeks.core import paths
    backup.VAULT.create("good", _changes(backup, 1))
    (paths.BACKUPS / "corrupt.json").write_text("{not json")
    entries = backup.VAULT.list_all()
    assert len(entries) == 1 and entries[0].title == "good"
