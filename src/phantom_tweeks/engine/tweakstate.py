"""Remembers which tweaks you turned on.

Why this is needed
------------------
Most tweaks can be read back from the registry, so the UI can show their real
state. Some cannot: a powercfg sub-setting, a scheduled task, an adapter
property on a driver that does not expose it. Those used to report ``False``
unconditionally, so every switch you flipped appeared OFF again the next time
you opened the app - and there was no way to tell "off" from "unknown".

This records what you chose, so the app can show:

* **on/off** - read from the system, authoritative;
* **on/off (remembered)** - we applied it and the system cannot confirm;
* **changed elsewhere** - we applied it but the system now disagrees, which
  usually means Windows Update or a driver reinstall reverted it.

The record is never treated as more truthful than the machine. Where the
registry can be read, the registry wins.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..core import paths

_FILE = "tweak-state.json"

# What the UI should show for a given tweak.
CONFIRMED_ON = "on"
CONFIRMED_OFF = "off"
REMEMBERED_ON = "on (remembered)"
REMEMBERED_OFF = "off (remembered)"
DRIFTED = "changed outside Phantom Tweeks"
UNKNOWN = "unknown"


@dataclass
class Record:
    tweak_id: str
    enabled: bool
    applied_at: float
    group: str = ""

    @property
    def when(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(self.applied_at))


@dataclass
class StateFile:
    records: dict = field(default_factory=dict)

    def get(self, tweak_id: str) -> Optional[Record]:
        return self.records.get(tweak_id)


def _path() -> Path:
    return paths.ROOT / _FILE


def load() -> StateFile:
    """Read the saved selections. A corrupt file is ignored, never fatal."""
    state = StateFile()
    try:
        raw = json.loads(_path().read_text(encoding="utf-8"))
    except Exception:
        return state
    for tweak_id, entry in (raw.get("tweaks") or {}).items():
        try:
            state.records[tweak_id] = Record(
                tweak_id=tweak_id,
                enabled=bool(entry.get("enabled")),
                applied_at=float(entry.get("applied_at") or 0),
                group=str(entry.get("group") or ""),
            )
        except (TypeError, ValueError):
            continue
    return state


def save(state: StateFile) -> bool:
    try:
        paths.ensure_dirs()
        payload = {
            "version": 1,
            "saved_at": time.time(),
            "tweaks": {
                r.tweak_id: {"enabled": r.enabled, "applied_at": r.applied_at,
                             "group": r.group}
                for r in state.records.values()
            },
        }
        tmp = _path().with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(_path())
        return True
    except OSError:
        return False


def remember(tweak_id: str, enabled: bool, group: str = "") -> None:
    """Record that a tweak was applied or reverted."""
    state = load()
    state.records[tweak_id] = Record(tweak_id, enabled, time.time(), group)
    save(state)


def forget(tweak_id: str) -> None:
    state = load()
    state.records.pop(tweak_id, None)
    save(state)


def clear() -> int:
    """Drop every remembered selection. Returns how many were removed."""
    state = load()
    count = len(state.records)
    state.records.clear()
    save(state)
    return count


def resolve(tweak_id: str, detected: Optional[bool],
            detectable: bool = True) -> tuple:
    """Work out what to show for one tweak.

    ``detected`` is what the system reports, or None when unreadable.
    ``detectable`` is False for tweaks whose state cannot be read at all.

    Returns (is_on, label).
    """
    record = load().get(tweak_id)

    if detectable and detected is not None:
        # The machine is authoritative when it can answer.
        if record is not None and record.enabled != detected:
            # We applied it and the system now disagrees. Worth flagging:
            # Windows Update and driver reinstalls both revert settings.
            return detected, DRIFTED
        return detected, CONFIRMED_ON if detected else CONFIRMED_OFF

    if record is not None:
        return record.enabled, (REMEMBERED_ON if record.enabled
                                else REMEMBERED_OFF)
    return False, UNKNOWN


def summary() -> str:
    state = load()
    if not state.records:
        return ("No tweaks have been applied yet.\n\n"
                "Once you turn something on, Phantom Tweeks remembers it here "
                "so the switch still shows correctly after a restart - even "
                "for settings Windows will not read back.")

    on = [r for r in state.records.values() if r.enabled]
    off = [r for r in state.records.values() if not r.enabled]
    out = ["SAVED TWEAK SELECTIONS", "",
           f"{len(on)} enabled, {len(off)} explicitly reverted.", ""]
    for record in sorted(on, key=lambda r: r.applied_at, reverse=True):
        label = f"{record.group}/" if record.group else ""
        out.append(f"  on   {label}{record.tweak_id}    {record.when}")
    for record in sorted(off, key=lambda r: r.applied_at, reverse=True):
        label = f"{record.group}/" if record.group else ""
        out.append(f"  off  {label}{record.tweak_id}    {record.when}")
    out += ["", "Where Windows can read a setting back, the machine is",
            "believed over this record - it exists for the settings Windows",
            "does not expose."]
    return "\n".join(out)


def reapply_all(apply_fn) -> dict:
    """Re-apply every remembered ON tweak.

    Used after a Windows update or driver reinstall reverts things.
    ``apply_fn(tweak_id, True)`` should return (ok, message, changes).
    """
    result = {"applied": [], "failed": [], "skipped": []}
    for record in load().records.values():
        if not record.enabled:
            continue
        try:
            ok, message, _ = apply_fn(record.tweak_id, True)
        except Exception as exc:
            result["failed"].append(f"{record.tweak_id}: {exc}")
            continue
        (result["applied"] if ok else result["failed"]).append(
            f"{record.tweak_id}: {message}")
    return result
