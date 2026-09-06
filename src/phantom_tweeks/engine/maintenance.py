"""Maintenance Mode - periodic, safe, reversible housekeeping.

What this is
------------
A checklist of routine tasks that keep a gaming PC healthy, each of which
reports findings and asks before changing anything.

Safety rules this module obeys
------------------------------
* **Nothing runs while a game is running.** Maintenance competes for CPU and
  disk; running it mid-session is exactly the kind of "help" that causes a
  stutter and loses someone a match.
* **Nothing personal is ever deleted.** Only caches the OS itself regards as
  disposable: ``%TEMP%``, Windows Update leftovers, thumbnail caches, shader
  caches. Documents, Downloads, Pictures, saves and Recycle Bin are untouched.
* **Read-only by default.** ``run()`` reports; ``apply()`` acts, and only on
  tasks the caller explicitly names.
* **No defrag on SSDs.** Windows already TRIMs them; defragmenting shortens
  their life for no benefit.
* Every task states *why* it matters, so nothing is cargo-culted.
"""
from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..core import paths


# --------------------------------------------------------------- data model

SEVERITY_OK = "OK"
SEVERITY_INFO = "INFO"
SEVERITY_ATTENTION = "ATTENTION"


@dataclass
class TaskResult:
    task_id: str
    title: str
    severity: str = SEVERITY_OK
    summary: str = ""
    detail: str = ""
    why: str = ""
    reclaimable_mb: float = 0.0
    actionable: bool = False
    action_label: str = ""
    error: str = ""

    def render(self) -> str:
        head = f"[{self.severity}] {self.title}"
        out = [head, f"  {self.summary}"]
        if self.reclaimable_mb >= 1:
            out.append(f"  Reclaimable: {self.reclaimable_mb:,.0f} MB")
        if self.detail:
            out.append(f"  {self.detail}")
        if self.why:
            out.append(f"  Why it matters: {self.why}")
        if self.error:
            out.append(f"  Could not check: {self.error}")
        return "\n".join(out)


@dataclass
class MaintenanceReport:
    results: list[TaskResult] = field(default_factory=list)
    skipped_reason: str = ""
    started: float = field(default_factory=time.time)

    @property
    def ran(self) -> bool:
        return not self.skipped_reason

    @property
    def total_reclaimable_mb(self) -> float:
        return sum(r.reclaimable_mb for r in self.results)

    @property
    def needs_attention(self) -> list[TaskResult]:
        return [r for r in self.results if r.severity == SEVERITY_ATTENTION]

    @property
    def actionable(self) -> list[TaskResult]:
        return [r for r in self.results if r.actionable]

    def render(self) -> str:
        if not self.ran:
            return f"MAINTENANCE SKIPPED\n\n{self.skipped_reason}"
        out = ["MAINTENANCE REPORT", ""]
        for r in self.results:
            out += [r.render(), ""]
        if self.total_reclaimable_mb >= 1:
            out.append(f"Total reclaimable: {self.total_reclaimable_mb:,.0f} MB")
        if not self.needs_attention:
            out.append("Nothing needs attention. No action recommended.")
        return "\n".join(out)


# ------------------------------------------------------------------ helpers

def _dir_size_mb(path: Path, cap_files: int = 20000) -> float:
    """Approximate size of a directory tree, in MB.

    Capped so a pathological folder cannot hang the scan.
    """
    total = 0
    seen = 0
    try:
        for root, _dirs, files in os.walk(path, onerror=lambda e: None):
            for f in files:
                seen += 1
                if seen > cap_files:
                    return total / (1024 * 1024)
                try:
                    total += (Path(root) / f).stat().st_size
                except (OSError, ValueError):
                    continue
    except (OSError, ValueError):
        pass
    return total / (1024 * 1024)


def _temp_dirs() -> list[Path]:
    out = []
    for var in ("TEMP", "TMP"):
        v = os.environ.get(var)
        if v:
            p = Path(v)
            if p.is_dir() and p not in out:
                out.append(p)
    return out


def game_is_running() -> Optional[str]:
    """Return the game's name if one is running, else None."""
    try:
        from ..core import games
        g = games.detect_running_game()
        return g.name if g else None
    except Exception:
        return None


# -------------------------------------------------------------------- tasks

def task_temp_files() -> TaskResult:
    r = TaskResult(
        task_id="temp",
        title="Temporary files",
        why=("Temp files do not slow a modern PC down, but they consume space "
             "that games need. This is about disk space, not speed."),
    )
    dirs = _temp_dirs()
    if not dirs:
        r.summary = "No temp directory found."
        return r
    mb = sum(_dir_size_mb(d) for d in dirs)
    r.reclaimable_mb = mb
    r.summary = f"{mb:,.0f} MB in {len(dirs)} temp folder(s)."
    r.detail = "Files in use are skipped automatically."
    if mb > 2048:
        r.severity = SEVERITY_ATTENTION
        r.actionable = True
        r.action_label = "Clear temp files"
    elif mb > 200:
        r.severity = SEVERITY_INFO
        r.actionable = True
        r.action_label = "Clear temp files"
    return r


def task_shader_cache() -> TaskResult:
    r = TaskResult(
        task_id="shader",
        title="GPU shader caches",
        why=("A corrupt shader cache causes stutter and visual glitches. "
             "Clearing it is safe: games rebuild it, though the first run "
             "afterwards may stutter briefly while it repopulates."),
    )
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        r.summary = "LOCALAPPDATA not set; cannot locate caches."
        return r
    base = Path(local)
    candidates = {
        "NVIDIA": base / "NVIDIA" / "DXCache",
        "NVIDIA (GL)": base / "NVIDIA" / "GLCache",
        "AMD": base / "AMD" / "DxCache",
        "Intel": base / "Intel" / "ShaderCache",
        "D3D": base / "D3DSCache",
    }
    found = {k: v for k, v in candidates.items() if v.is_dir()}
    if not found:
        r.summary = "No shader caches found."
        r.detail = "Normal - they are created on demand by your GPU driver."
        return r
    mb = sum(_dir_size_mb(v) for v in found.values())
    r.reclaimable_mb = mb
    r.summary = f"{mb:,.0f} MB across {len(found)} cache(s): {', '.join(found)}."
    r.detail = ("Only clear these if you are seeing stutter or artifacts. "
                "There is no benefit to clearing a healthy cache.")
    r.severity = SEVERITY_INFO if mb > 500 else SEVERITY_OK
    r.actionable = bool(found)
    r.action_label = "Clear shader caches"
    return r


def task_disk_space() -> TaskResult:
    r = TaskResult(
        task_id="disk",
        title="Free disk space",
        why=("Windows needs free space for the pagefile and shader "
             "compilation. Below roughly 10% free, stutter and long load "
             "times are common."),
    )
    try:
        target = Path(os.environ.get("SystemDrive", "C:") + os.sep)
        usage = shutil.disk_usage(target)
    except Exception as exc:
        r.error = str(exc)
        return r
    free_gb = usage.free / (1024 ** 3)
    total_gb = usage.total / (1024 ** 3)
    pct = (usage.free / usage.total * 100) if usage.total else 0
    r.summary = f"{free_gb:,.0f} GB free of {total_gb:,.0f} GB ({pct:.0f}%)."
    if pct < 5:
        r.severity = SEVERITY_ATTENTION
        r.detail = "Critically low. Windows may fail to page or update."
    elif pct < 10:
        r.severity = SEVERITY_ATTENTION
        r.detail = "Low. Expect stutter during shader compilation."
    elif pct < 20:
        r.severity = SEVERITY_INFO
        r.detail = "Adequate, but keep an eye on it."
    return r


def task_pending_reboot() -> TaskResult:
    r = TaskResult(
        task_id="reboot",
        title="Pending restart",
        why=("A deferred restart leaves half-applied updates and stale "
             "drivers in memory, which is a common cause of odd, "
             "hard-to-reproduce performance problems."),
    )
    try:
        import winreg
    except ImportError:
        r.summary = "Not applicable on this platform."
        return r
    keys = [
        (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing"
         r"\RebootPending"),
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired",
    ]
    pending = []
    for k in keys:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, k):
                pending.append(k.rsplit("\\", 1)[-1])
        except OSError:
            continue
    if pending:
        r.severity = SEVERITY_ATTENTION
        r.summary = "A restart is pending."
        r.detail = "Restart when convenient - never mid-session."
    else:
        r.summary = "No restart pending."
    return r


def task_storage_health() -> TaskResult:
    r = TaskResult(
        task_id="storage_health",
        title="Drive type and optimization",
        why=("SSDs must never be defragmented - it wears the flash for no "
             "gain. Windows TRIMs them instead. Only mechanical drives "
             "benefit from defragmentation."),
    )
    try:
        from . import storage
        info = storage.scan()
        physical = info.physical or []
        if not physical:
            r.summary = "Drive type could not be determined."
            r.detail = "Physical disk details need WMI, which is Windows-only."
            return r
        hdds = [p for p in physical if p.get("media_type") == "HDD"]
        ssds = [p for p in physical if p.get("media_type") == "SSD"]
        unhealthy = [p for p in physical
                     if p.get("health") and p["health"] != "Healthy"]
        r.summary = (f"{len(physical)} drive(s): {len(ssds)} SSD, "
                     f"{len(hdds)} HDD.")
        if unhealthy:
            r.severity = SEVERITY_ATTENTION
            names = ", ".join(p.get("name", "?") for p in unhealthy)
            r.detail = (f"{names} reports a non-healthy status. Back up your "
                        "data and check the manufacturer's tool. This is a "
                        "hardware warning, not something software can fix.")
        elif hdds:
            r.detail = ("Mechanical drives benefit from Windows' scheduled "
                        "Optimize Drives task. Phantom Tweeks never "
                        "defragments anything itself.")
        else:
            r.detail = "All SSDs. Windows handles TRIM automatically."
    except Exception as exc:
        r.error = str(exc)
    return r


def task_restore_points() -> TaskResult:
    r = TaskResult(
        task_id="restore",
        title="Backup coverage",
        why=("Every change Phantom Tweeks makes is reversible, but that only "
             "helps if the backups still exist."),
    )
    try:
        from .backup import BackupVault
        items = BackupVault().list_all()
        n = len(items)
        if n == 0:
            r.severity = SEVERITY_INFO
            r.summary = "No backups yet."
            r.detail = "One is created automatically before any change."
        else:
            r.summary = f"{n} backup(s) available."
            r.detail = "You can roll back any applied optimization."
    except Exception as exc:
        r.error = str(exc)
    return r


def task_log_size() -> TaskResult:
    r = TaskResult(
        task_id="logs",
        title="Phantom Tweeks logs",
        why=("Logs stay on your machine and are never uploaded. They are "
             "only useful for diagnosing a problem you have actually hit."),
    )
    try:
        root = paths.ROOT
        logs = root / "logs" if (root / "logs").is_dir() else root
        mb = _dir_size_mb(logs)
        r.reclaimable_mb = mb if mb > 50 else 0.0
        r.summary = f"{mb:,.1f} MB of local logs."
        if mb > 200:
            r.severity = SEVERITY_INFO
            r.actionable = True
            r.action_label = "Trim old logs"
    except Exception as exc:
        r.error = str(exc)
    return r


TASKS: dict[str, Callable[[], TaskResult]] = {
    "disk": task_disk_space,
    "temp": task_temp_files,
    "shader": task_shader_cache,
    "reboot": task_pending_reboot,
    "storage_health": task_storage_health,
    "restore": task_restore_points,
    "logs": task_log_size,
}


# --------------------------------------------------------------------- runs

def run(only: Optional[list[str]] = None,
        allow_during_game: bool = False) -> MaintenanceReport:
    """Run the read-only maintenance checks.

    Refuses to run while a game is detected unless explicitly overridden.
    """
    report = MaintenanceReport()
    if not allow_during_game:
        playing = game_is_running()
        if playing:
            report.skipped_reason = (
                f"{playing} is running. Maintenance is postponed so it cannot "
                "compete with your game for CPU and disk. It will run when "
                "you finish playing."
            )
            return report

    wanted = only or list(TASKS)
    for task_id in wanted:
        fn = TASKS.get(task_id)
        if not fn:
            continue
        try:
            report.results.append(fn())
        except Exception as exc:                       # pragma: no cover
            report.results.append(TaskResult(
                task_id=task_id, title=task_id,
                severity=SEVERITY_INFO, error=str(exc)))
    return report


def _clear_dir(path: Path, dry_run: bool) -> tuple[int, float, int]:
    """Delete files under *path*. Returns (removed, mb_freed, skipped)."""
    removed = skipped = 0
    freed = 0.0
    if not path.is_dir():
        return 0, 0.0, 0
    for root, _dirs, files in os.walk(path, topdown=False, onerror=lambda e: None):
        for name in files:
            f = Path(root) / name
            try:
                size = f.stat().st_size
            except OSError:
                skipped += 1
                continue
            if dry_run:
                removed += 1
                freed += size / (1024 * 1024)
                continue
            try:
                f.unlink()
                removed += 1
                freed += size / (1024 * 1024)
            except OSError:
                # In use, or protected. Skipping is correct.
                skipped += 1
    return removed, freed, skipped


def apply(task_ids: list[str], dry_run: bool = True,
          allow_during_game: bool = False) -> dict:
    """Perform the cleanup for the named tasks.

    ``dry_run=True`` by default: callers must opt in to real deletion, and the
    GUI only does so after an explicit confirmation.
    """
    out: dict = {"applied": [], "skipped": [], "freed_mb": 0.0,
                 "dry_run": dry_run, "errors": []}

    if not allow_during_game:
        playing = game_is_running()
        if playing:
            out["skipped"].append(f"All tasks - {playing} is running.")
            return out

    for task_id in task_ids:
        if task_id == "temp":
            total = 0.0
            n = s = 0
            for d in _temp_dirs():
                r, mb, sk = _clear_dir(d, dry_run)
                n += r
                s += sk
                total += mb
            out["applied"].append(
                {"task": "temp", "removed": n, "skipped_in_use": s,
                 "freed_mb": round(total, 1)})
            out["freed_mb"] += total

        elif task_id == "shader":
            local = os.environ.get("LOCALAPPDATA")
            if not local:
                out["errors"].append("LOCALAPPDATA not set.")
                continue
            base = Path(local)
            total = 0.0
            n = s = 0
            for sub in ("NVIDIA/DXCache", "NVIDIA/GLCache", "AMD/DxCache",
                        "Intel/ShaderCache", "D3DSCache"):
                r, mb, sk = _clear_dir(base / sub, dry_run)
                n += r
                s += sk
                total += mb
            out["applied"].append(
                {"task": "shader", "removed": n, "skipped_in_use": s,
                 "freed_mb": round(total, 1),
                 "note": "Games rebuild these; expect brief first-run stutter."})
            out["freed_mb"] += total

        elif task_id == "logs":
            root = paths.ROOT
            logs = root / "logs" if (root / "logs").is_dir() else None
            if not logs:
                out["skipped"].append("logs - no log directory.")
                continue
            cutoff = time.time() - (30 * 86400)
            n = 0
            total = 0.0
            for f in logs.glob("*"):
                try:
                    if f.is_file() and f.stat().st_mtime < cutoff:
                        size = f.stat().st_size
                        if not dry_run:
                            f.unlink()
                        n += 1
                        total += size / (1024 * 1024)
                except OSError:
                    continue
            out["applied"].append(
                {"task": "logs", "removed": n, "freed_mb": round(total, 1),
                 "note": "Only logs older than 30 days."})
            out["freed_mb"] += total

        else:
            out["skipped"].append(f"{task_id} - reporting only, nothing to apply.")

    out["freed_mb"] = round(out["freed_mb"], 1)
    return out


# ------------------------------------------------------------- scheduling

SCHEDULE_OFF = "off"
SCHEDULE_WEEKLY = "weekly"
SCHEDULE_MONTHLY = "monthly"
SCHEDULES = (SCHEDULE_OFF, SCHEDULE_WEEKLY, SCHEDULE_MONTHLY)

_INTERVALS = {SCHEDULE_WEEKLY: 7 * 86400, SCHEDULE_MONTHLY: 30 * 86400}


def _state_file() -> Path:
    return paths.ROOT / "maintenance.json"


def load_schedule() -> dict:
    import json
    try:
        return json.loads(_state_file().read_text(encoding="utf-8"))
    except Exception:
        return {"schedule": SCHEDULE_OFF, "last_run": 0.0}


def save_schedule(schedule: str, last_run: Optional[float] = None) -> dict:
    import json
    if schedule not in SCHEDULES:
        raise ValueError(f"unknown schedule: {schedule}")
    cur = load_schedule()
    data = {"schedule": schedule,
            "last_run": cur.get("last_run", 0.0) if last_run is None else last_run}
    try:
        _state_file().parent.mkdir(parents=True, exist_ok=True)
        _state_file().write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass
    return data


def is_due(now: Optional[float] = None) -> bool:
    """True if a scheduled check is overdue. Never true while gaming."""
    data = load_schedule()
    interval = _INTERVALS.get(data.get("schedule", SCHEDULE_OFF))
    if not interval:
        return False
    now = time.time() if now is None else now
    if (now - float(data.get("last_run", 0.0))) < interval:
        return False
    return game_is_running() is None
