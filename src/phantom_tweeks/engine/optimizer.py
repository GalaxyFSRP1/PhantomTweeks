"""The optimization engine.

Implements the core pipeline:
  SCAN → ANALYZE → RECOMMEND → BACKUP → APPROVE → OPTIMIZE → BENCHMARK →
  COMPARE → RESTORE IF NECESSARY

Nothing here mutates the system without (a) an explicit approved id list and
(b) a verified backup written first.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..core.config import Config
from ..core.logging_setup import get_logger
from ..core.platform_info import IS_WINDOWS, is_admin
from ..hardware.monitor import MONITOR
from .backup import VAULT, BackupEntry, ChangeRecord
from .catalog import CATALOG, BY_ID, Category, Confidence, Optimization, Evaluation
from . import winsettings as ws

log = get_logger("optimizer")


@dataclass
class Recommendation:
    optimization: Optimization
    evaluation: Evaluation

    @property
    def id(self) -> str:
        return self.optimization.id

    @property
    def confidence(self) -> Confidence:
        return self.evaluation.confidence

    @property
    def category(self) -> Category:
        if not self.evaluation.applicable:
            return Category.NOT_RECOMMENDED
        return self.optimization.category

    @property
    def auto_applicable(self) -> bool:
        """Only high-confidence, low-risk, reversible, non-advanced changes."""
        o = self.optimization
        return (self.evaluation.applicable
                and self.confidence == Confidence.HIGH
                and o.category in (Category.SAFE, Category.RECOMMENDED)
                and o.reversible
                and not o.advanced
                and o.apply is not None
                and (not o.requires_admin or is_admin()))

    def as_dict(self) -> dict:
        o = self.optimization
        return {
            "id": o.id, "title": o.title, "area": o.area,
            "category": self.category.value,
            "confidence": self.confidence.value,
            "confidence_blurb": self.confidence.blurb,
            "reason": self.evaluation.reason,
            "applicable": self.evaluation.applicable,
            "already_optimal": self.evaluation.already_optimal,
            "risk": o.risk.value, "reversible": o.reversible,
            "requires_admin": o.requires_admin, "advanced": o.advanced,
            "info": o.info_card(),
        }


@dataclass
class ApplyResult:
    applied: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    backup: Optional[BackupEntry] = None
    reboot_required: bool = False

    def summary(self) -> str:
        parts = [f"Applied: {len(self.applied)}"]
        if self.skipped:
            parts.append(f"Skipped: {len(self.skipped)}")
        if self.failed:
            parts.append(f"Failed: {len(self.failed)}")
        if self.backup:
            parts.append(f"Backup: {self.backup.id}")
        return " | ".join(parts)


class OptimizationEngine:
    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config or Config.load()

    # ---------------- context ----------------
    def build_context(self, game: Optional[dict] = None) -> dict:
        cpu = MONITOR.cpu()
        mem = MONITOR.memory()
        gpus = MONITOR.gpus()
        disks = MONITOR.disks()
        system_disk = next((d for d in disks
                            if d.mountpoint.upper().startswith(("C:", "/"))), None)
        gpu_util = next((g.utilization for g in gpus if g.utilization is not None), None)
        hags_supported = None
        if gpus:
            # WDDM 2.7+ needed; we can only assert support for modern NVIDIA where
            # nvidia-smi answered, otherwise leave it unknown rather than guess.
            hags_supported = True if any(g.vendor == "NVIDIA" and g.utilization is not None
                                         for g in gpus) else None
        return {
            "game": game,
            "gpu_count": len(gpus),
            "gpus": gpus,
            "gpu_utilization": gpu_util,
            "cpu": cpu,
            "ram_gb": mem.total_gb,
            "power_plan": cpu.power_plan,
            "is_laptop": self._is_laptop(),
            "hags_supported": hags_supported,
            "system_disk_media": system_disk.media_type if system_disk else None,
            "system_disk_free_pct": (
                round(system_disk.free_gb / system_disk.total_gb * 100, 1)
                if system_disk and system_disk.total_gb else None),
            "recording_active": self._recording_active(),
        }

    def _is_laptop(self) -> bool:
        try:
            import psutil
            batt = psutil.sensors_battery()
            return batt is not None
        except Exception:
            return False

    def _recording_active(self) -> bool:
        try:
            import psutil
            capture = {"obs64.exe", "obs32.exe", "streamlabs obs.exe", "xsplit.core.exe"}
            return any((p.info.get("name") or "").lower() in capture
                       for p in psutil.process_iter(["name"]))
        except Exception:
            return False

    # ---------------- scan / analyze / recommend ----------------
    def scan(self, game: Optional[dict] = None) -> list[Recommendation]:
        ctx = self.build_context(game)
        recs: list[Recommendation] = []
        for opt in CATALOG:
            try:
                ev = opt.evaluate(ctx)
            except Exception as e:  # an evaluator must never crash the scan
                log.exception("Evaluator failed for %s", opt.id)
                ev = Evaluation(False, Confidence.LOW,
                                f"Could not evaluate this item on your system: {e}")
            recs.append(Recommendation(opt, ev))
        order = {Confidence.HIGH: 0, Confidence.MEDIUM: 1,
                 Confidence.LOW: 2, Confidence.NOT_RECOMMENDED: 3}
        recs.sort(key=lambda r: (order[r.confidence], r.optimization.title))
        return recs

    def actionable(self, recs: list[Recommendation]) -> list[Recommendation]:
        return [r for r in recs if r.evaluation.applicable and r.optimization.apply]

    # ---------------- apply ----------------
    def apply(self, approved_ids: list[str], game: Optional[dict] = None,
              title: str = "Optimization run") -> ApplyResult:
        """Apply only explicitly approved optimizations, backup-first."""
        result = ApplyResult()
        if not IS_WINDOWS:
            for oid in approved_ids:
                result.skipped.append(
                    (oid, "Analysis-only mode: system changes require Windows."))
            return result

        ctx = self.build_context(game)
        changes: list[ChangeRecord] = []
        applied_ids: list[str] = []

        for oid in approved_ids:
            opt = BY_ID.get(oid)
            if not opt:
                result.failed.append((oid, "Unknown optimization id."))
                continue
            if opt.apply is None:
                result.skipped.append((oid, "Advisory item; nothing to apply."))
                continue
            if opt.requires_admin and not is_admin():
                result.skipped.append(
                    (oid, "Requires administrator rights. Restart Phantom Tweeks "
                          "elevated to apply this item."))
                continue
            try:
                ev = opt.evaluate(ctx)
            except Exception as e:
                result.failed.append((oid, f"Evaluation failed: {e}"))
                continue
            if not ev.applicable:
                result.skipped.append((oid, ev.reason))
                continue
            try:
                produced = opt.apply(ctx)
                changes.extend(produced)
                applied_ids.append(oid)
                result.applied.append(oid)
                if oid == "gfx.hags":
                    result.reboot_required = True
                log.info("Applied %s (%d changes)", oid, len(produced))
            except Exception as e:
                log.exception("Apply failed for %s", oid)
                result.failed.append((oid, str(e)))
                # Roll back this run immediately — never leave a partial state.
                for c in reversed(changes):
                    ws.revert(c)
                changes.clear()
                applied_ids.clear()
                result.applied.clear()
                break

        if changes:
            result.backup = VAULT.create(title, changes, applied_ids)
        return result

    def apply_auto(self, game: Optional[dict] = None) -> ApplyResult:
        """Automatic mode: strictly high-confidence safe items, opt-in only."""
        if not self.config.get("auto_apply_high_confidence"):
            r = ApplyResult()
            r.skipped.append(("*", "Automatic optimization is disabled. Enable it in "
                                   "Settings → Optimization to allow this."))
            return r
        recs = self.scan(game)
        ids = [r.id for r in recs if r.auto_applicable]
        return self.apply(ids, game, title="Automatic optimization (high confidence)")

    # ---------------- restore ----------------
    def restore_backup(self, backup_id: str) -> tuple[bool, list[str]]:
        """Undo a backup, newest change first.

        Progress is recorded per change and saved as we go. If some changes
        cannot be reverted (a permission error, say), the ones that succeeded
        stay marked as done, so retrying resumes instead of redoing work — and
        the entry honestly reports itself as partially restored rather than
        silently looking untouched.
        """
        entry = VAULT.get(backup_id)
        if not entry:
            return False, [f"Backup {backup_id} not found."]

        pending = entry.pending_changes
        if not pending:
            return True, [f"Backup {backup_id} was already fully restored."]

        messages = []
        ok_all = True
        for change in pending:
            try:
                ok, msg = ws.revert(change)
            except Exception as e:                  # never abort mid-restore
                ok, msg = False, f"Unexpected error reverting {change.target}: {e}"
                log.exception("Revert raised for %s", change.target)
            change.reverted = bool(ok)
            change.revert_error = "" if ok else msg
            ok_all &= bool(ok)
            messages.append(("✓ " if ok else "✗ ") + msg)
            VAULT.save(entry)                       # survive a crash mid-restore

        VAULT.mark_partial(entry)
        if not ok_all:
            done = sum(1 for c in entry.changes if c.reverted)
            messages.append("")
            messages.append(
                f"{done} of {len(entry.changes)} changes were reverted. The rest "
                "are still recorded and can be retried — nothing was lost.")
            messages.append(
                "If a change needs administrator rights, restart Phantom Tweeks "
                "as administrator and restore again.")
        return ok_all, messages

    def restore_everything(self) -> tuple[bool, list[str]]:
        """One-click restore of every Phantom Tweeks change, newest first.

        Only reverts changes recorded in our own vault. Unrelated user changes
        are never touched.
        """
        messages: list[str] = []
        ok_all = True
        entries = [e for e in VAULT.list_all() if not e.restored]
        if not entries:
            return True, ["No Phantom Tweeks changes are currently applied."]
        for entry in entries:
            messages.append(f"— Restoring '{entry.title}' ({entry.timestamp})")
            ok, msgs = self.restore_backup(entry.id)
            ok_all &= ok
            messages.extend("  " + m for m in msgs)
        return ok_all, messages
