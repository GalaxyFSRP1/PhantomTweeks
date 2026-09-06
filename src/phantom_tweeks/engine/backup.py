"""Backup vault + rollback.

Every mutating optimization records the *prior* value before it writes anything.
Restore only ever touches keys Phantom Tweeks itself wrote — unrelated user
changes are never reverted. If a prior value did not exist, restore deletes the
key Phantom Tweeks created rather than guessing a default.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from typing import Any, Optional

from ..core import paths
from ..core.logging_setup import get_logger

log = get_logger("backup")

ABSENT = "__PHANTOM_ABSENT__"  # sentinel: key did not exist before we wrote it


@dataclass
class ChangeRecord:
    """One reversible change."""
    kind: str                 # registry | powercfg | startup | service_config
    target: str               # registry path / setting id
    name: str                 # value name
    previous: Any             # prior value, or ABSENT
    applied: Any              # what we wrote
    value_type: Optional[str] = None
    note: str = ""
    #: Set once this individual change has been successfully reverted, so a
    #: retry after a partial failure does not redo work already done.
    reverted: bool = False
    revert_error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ChangeRecord":
        # Backups written by earlier versions lack the newer fields. Drop any
        # unknown keys rather than crashing: an unreadable backup is worse than
        # a slightly stale one, because it is the user's only way back.
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class BackupEntry:
    id: str
    timestamp: str
    title: str
    optimization_ids: list[str] = field(default_factory=list)
    changes: list[ChangeRecord] = field(default_factory=list)
    restored: bool = False
    restored_at: Optional[str] = None
    #: True when a restore ran but only some changes came back.
    partially_restored: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["changes"] = [c.to_dict() for c in self.changes]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "BackupEntry":
        d = dict(d)
        d["changes"] = [ChangeRecord.from_dict(c) for c in d.get("changes", [])]
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})

    @property
    def change_count(self) -> int:
        return len(self.changes)

    @property
    def pending_changes(self) -> list["ChangeRecord"]:
        """Changes still to be undone, newest first (reverse apply order)."""
        return [c for c in reversed(self.changes) if not c.reverted]

    @property
    def status(self) -> str:
        if self.restored:
            return "Restored"
        if self.partially_restored:
            done = sum(1 for c in self.changes if c.reverted)
            return f"Partially restored ({done}/{len(self.changes)})"
        return "Applied"


class BackupVault:
    def __init__(self) -> None:
        paths.ensure_dirs()

    def _path(self, backup_id: str):
        return paths.BACKUPS / f"{backup_id}.json"

    def create(self, title: str, changes: list[ChangeRecord],
               optimization_ids: list[str] | None = None) -> BackupEntry:
        entry = BackupEntry(
            id=uuid.uuid4().hex[:12],
            timestamp=datetime.now().isoformat(timespec="seconds"),
            title=title,
            optimization_ids=optimization_ids or [],
            changes=changes,
        )
        self._write(entry)
        self._append_history(entry)
        log.info("Backup %s created: %s (%d changes)", entry.id, title, len(changes))
        return entry

    def _write(self, entry: BackupEntry) -> None:
        p = self._path(entry.id)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(entry.to_dict(), indent=2), encoding="utf-8")
        tmp.replace(p)

    def get(self, backup_id: str) -> Optional[BackupEntry]:
        p = self._path(backup_id)
        if not p.exists():
            return None
        try:
            return BackupEntry.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError, TypeError) as e:
            log.error("Backup %s unreadable: %s", backup_id, e)
            return None

    def list_all(self) -> list[BackupEntry]:
        out = []
        for p in sorted(paths.BACKUPS.glob("*.json"), reverse=True):
            try:
                out.append(BackupEntry.from_dict(json.loads(p.read_text(encoding="utf-8"))))
            except Exception:
                continue
        return sorted(out, key=lambda e: e.timestamp, reverse=True)

    def verify(self, entry: BackupEntry) -> tuple[bool, str]:
        """Pre-flight check required before any advanced change is applied."""
        if not entry.changes:
            return False, "Backup contains no change records."
        if not self._path(entry.id).exists():
            return False, "Backup file is missing from disk."
        for c in entry.changes:
            # A prior value of None is genuinely missing information. ABSENT is
            # a *valid* recorded state meaning "the key did not exist", so it
            # must not be treated as an error.
            if c.previous is None:
                return False, (f"Change '{c.target}\\{c.name}' has no recorded "
                               "prior value; refusing to call this reversible.")
            if not c.kind:
                return False, f"Change '{c.target}\\{c.name}' has no change kind."
        return True, f"Backup {entry.id} verified: {len(entry.changes)} reversible changes."

    def _append_history(self, entry: BackupEntry) -> None:
        hist = self.history()
        hist.insert(0, {
            "id": entry.id, "timestamp": entry.timestamp, "title": entry.title,
            "changes": entry.change_count, "restored": entry.restored,
        })
        tmp = paths.HISTORY_DB.with_suffix(".tmp")
        tmp.write_text(json.dumps(hist[:500], indent=2), encoding="utf-8")
        tmp.replace(paths.HISTORY_DB)

    def history(self) -> list[dict]:
        if not paths.HISTORY_DB.exists():
            return []
        try:
            return json.loads(paths.HISTORY_DB.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def save(self, entry: BackupEntry) -> None:
        """Persist an entry mid-restore so progress survives a crash."""
        self._write(entry)

    def mark_partial(self, entry: BackupEntry) -> None:
        entry.partially_restored = not all(c.reverted for c in entry.changes)
        entry.restored = all(c.reverted for c in entry.changes)
        if entry.restored:
            entry.restored_at = datetime.now().isoformat(timespec="seconds")
            entry.partially_restored = False
        self._write(entry)
        self._sync_history(entry)

    def _sync_history(self, entry: BackupEntry) -> None:
        hist = self.history()
        for h in hist:
            if h.get("id") == entry.id:
                h["restored"] = entry.restored
                h["status"] = entry.status
        tmp = paths.HISTORY_DB.with_suffix(".tmp")
        tmp.write_text(json.dumps(hist, indent=2), encoding="utf-8")
        tmp.replace(paths.HISTORY_DB)

    def mark_restored(self, entry: BackupEntry) -> None:
        entry.restored = True
        entry.restored_at = datetime.now().isoformat(timespec="seconds")
        self._write(entry)
        hist = self.history()
        for h in hist:
            if h.get("id") == entry.id:
                h["restored"] = True
        tmp = paths.HISTORY_DB.with_suffix(".tmp")
        tmp.write_text(json.dumps(hist, indent=2), encoding="utf-8")
        tmp.replace(paths.HISTORY_DB)


VAULT = BackupVault()
