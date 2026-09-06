"""PhantomApp — the single facade the GUI and CLI both drive.

Keeping one facade means the CLI and GUI cannot drift into different safety
behaviour: both go through the same engine, the same Shield, the same vault.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .branding import APP_NAME, VERSION
from .core import games, premium
from .core.config import Config
from .core.logging_setup import get_logger
from .core.notifications import CENTER
from .core.platform_info import IS_WINDOWS, summary as platform_summary
from .core.shield import SHIELD
from .engine import (background, bottleneck, comparison, drivers, frametime,
                     gaming_mode, health, profiles, score, startup, storage)
from .engine.backup import VAULT
from .engine.optimizer import OptimizationEngine, Recommendation
from .hardware.monitor import MONITOR
from .network import lab

log = get_logger("app")


@dataclass
class ScanResult:
    recommendations: list[Recommendation] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)

    @property
    def actionable(self) -> list[Recommendation]:
        return [r for r in self.recommendations
                if r.evaluation.applicable and r.optimization.apply]

    def render(self) -> str:
        out = ["PHANTOM SCAN", ""]
        out += [f"✓ {s}" for s in self.sections]
        out += ["", "Analysis complete.", ""]
        n = len(self.actionable)
        out.append(f"{n} recommendation{'s' if n != 1 else ''} found."
                   if n else "No changes recommended for this configuration.")
        return "\n".join(out)


SCAN_SECTIONS = [
    "Hardware", "Drivers", "Windows Configuration", "Graphics Configuration",
    "Startup Programs", "Background Load", "Storage", "Network",
    "Gaming Configuration", "Protected Processes",
]


class PhantomApp:
    def __init__(self) -> None:
        self.config = Config.load()
        self.engine = OptimizationEngine(self.config)
        self.mode = gaming_mode.GamingMode(self.config)
        CENTER.enabled = bool(self.config.get("notifications"))
        CENTER.min_interval_s = int(self.config.get("notification_min_interval_s", 60))
        for name in self.config.get("protected_apps", []):
            SHIELD.add_user_protected(name)
        self._last_network: Optional[dict] = None
        self._last_drivers: Optional[dict] = None
        self._last_recs: list[Recommendation] = []

    # ---------------- info ----------------
    def about(self) -> dict:
        info = platform_summary()
        info.update({"app": APP_NAME, "version": VERSION,
                     "premium": premium.is_premium()})
        return info

    def shield_dashboard(self) -> dict:
        return SHIELD.dashboard()

    def render_shield(self) -> str:
        d = self.shield_dashboard()
        out = ["PHANTOM SHIELD", "", f"STATUS: {d['status']}", "", "Protected:"]
        for cat, labels in d["groups"].items():
            for lbl in labels:
                out.append(f"✓ {lbl}")
        if not d["groups"]:
            out.append("(no protected processes currently running)")
        out += ["", f"Processes Protected: {d['protected_count']}"]
        return "\n".join(out)

    # ---------------- scan ----------------
    def scan(self, include_network: bool = False) -> ScanResult:
        game = self.mode.session.game.as_dict() if self.mode.session else None
        if include_network:
            self._last_network = lab.full_lab(quick=True)
            lab.record_history(self._last_network)
        recs = self.engine.scan(game)
        self._last_recs = recs
        return ScanResult(recs, SCAN_SECTIONS)

    def performance_score(self, frame_stats=None):
        return score.compute(network=self._last_network,
                             frame_stats=frame_stats,
                             recommendations=self._last_recs or self.engine.scan())

    def bottleneck(self, seconds: float = 5.0):
        net = (self._last_network or {}).get("diagnosis")
        return bottleneck.analyze(seconds, net)

    def health(self):
        return health.build(self._last_network, self._last_drivers)

    # ---------------- network ----------------
    def network_lab(self, quick: bool = True) -> dict:
        report = lab.full_lab(quick=quick)
        self._last_network = report
        lab.record_history(report)
        if report["diagnosis"]["status"] == "UNSTABLE":
            CENTER.notify("network_unstable")
        return report

    def network_history(self, days: int = 7) -> list[dict]:
        return lab.daily_summary(days)

    # ---------------- optimize ----------------
    def apply(self, ids: list[str], title: str = "Optimization run"):
        game = self.mode.session.game.as_dict() if self.mode.session else None
        result = self.engine.apply(ids, game, title)
        if result.backup:
            CENTER.notify("backup_created",
                          f"Backup {result.backup.id} created "
                          f"({result.backup.change_count} changes).")
        if result.applied:
            CENTER.notify("optimize_done")
        return result

    def restore_backup(self, backup_id: str):
        ok, msgs = self.engine.restore_backup(backup_id)
        if ok:
            CENTER.notify("restored")
        return ok, msgs

    def restore_everything(self):
        ok, msgs = self.engine.restore_everything()
        if ok:
            CENTER.notify("restored", "All Phantom Tweeks changes restored.")
        return ok, msgs

    def history(self) -> list[dict]:
        return VAULT.history()

    # ---------------- modules ----------------
    def background_report(self):
        return background.analyze()

    def startup_entries(self):
        return startup.list_entries()

    def driver_report(self):
        self._last_drivers = drivers.report()
        return self._last_drivers

    def storage_report(self):
        return storage.scan()

    def game_library(self):
        return games.scan_library()

    def detect_game(self):
        return games.detect_running_game()

    def profiles(self):
        return profiles.list_profiles()

    def snapshots(self):
        return profiles.list_snapshots()

    def create_snapshot(self, name: str, note: str = ""):
        return profiles.create_snapshot(name, note)

    # ---------------- benchmarking ----------------
    def benchmark(self, seconds: int = 30, label: str = "benchmark"):
        game = self.mode.session.game.name if self.mode.session else None
        stats = frametime.capture(seconds, self.mode.session.game.executable
                                  if self.mode.session else None)
        if stats.available:
            frametime.save_benchmark(stats, label, game)
        return stats

    def compare(self, before, after):
        rep = comparison.compare(
            before, after,
            regression_threshold=float(self.config.get("regression_threshold_pct", 5.0)))
        if rep.regression:
            CENTER.notify("regression")
        elif any(m.meaningful and (m.delta_pct or 0) > 0 for m in rep.metrics):
            CENTER.notify("improvement")
        return rep

    # ---------------- input latency ----------------
    def input_latency(self, frame_stats=None) -> dict:
        from .hardware import display
        cpu = MONITOR.cpu()
        gpus = MONITOR.gpus()
        gpu_util = next((g.utilization for g in gpus if g.utilization is not None), None)
        avg_fps = getattr(frame_stats, "avg_fps", None) if frame_stats else None
        return display.analyze_input_latency(avg_fps, gpu_util, cpu.utilization)

    def displays(self):
        from .hardware import display
        return display.detect()

    # ---------------- report export ----------------
    def export_report(self, path: str, frame_stats=None) -> str:
        """Write a full diagnostic report the user can share or keep.

        Contains no credentials and nothing is transmitted.
        """
        from datetime import datetime
        from .hardware import display as display_mod

        recs = self._last_recs or self.engine.scan()
        ps = self.performance_score(frame_stats)
        cpu, mem = MONITOR.cpu(), MONITOR.memory()
        gpus = MONITOR.gpus()

        L = [f"{APP_NAME} {VERSION} — Diagnostic Report",
             f"Generated: {datetime.now().isoformat(timespec='seconds')}",
             "=" * 66, "", "SYSTEM", "-" * 66]
        for k, v in platform_summary().items():
            L.append(f"  {k:<16}{v}")

        L += ["", "HARDWARE", "-" * 66,
              f"  CPU            {cpu.model or 'Unknown'}",
              f"  Cores          {cpu.physical_cores or '?'} physical / "
              f"{cpu.logical_cores or '?'} logical",
              f"  CPU load       {cpu.utilization if cpu.utilization is not None else 'n/a'}%",
              f"  CPU temp       {cpu.temperature_c or 'n/a'}",
              f"  Power plan     {cpu.power_plan or 'n/a'}",
              f"  Memory         {mem.total_gb} GB total, {mem.percent}% used"]
        for g in gpus:
            L += [f"  GPU            {g.model} ({g.vendor})",
                  f"    driver       {g.driver_version or 'n/a'}",
                  f"    util/temp    {g.utilization if g.utilization is not None else 'n/a'}% / "
                  f"{g.temperature_c or 'n/a'}"]
        for d in MONITOR.disks():
            L.append(f"  Disk {d.mountpoint:<6} {d.media_type or 'Unknown':<10} "
                     f"{d.free_gb:.0f} GB free of {d.total_gb:.0f} GB")
        for disp in display_mod.detect():
            L.append(f"  Display        {disp.render()}")

        L += ["", "PERFORMANCE SCORE", "-" * 66]
        for sub in ps.subscores:
            L.append(f"  {sub.name:<24}{sub.display}")
            L.append(f"      {sub.explanation}")
        L.append(f"  {'Overall':<24}"
                 f"{str(ps.overall) + '/100' if ps.overall is not None else 'n/a'}")

        L += ["", "RECOMMENDATIONS", "-" * 66]
        for r in recs:
            d = r.as_dict()
            L += [f"  [{d['category']}] {d['title']} ({d['id']})",
                  f"      {d['confidence']} — {d['reason']}"]

        L += ["", "PHANTOM SHIELD", "-" * 66]
        dash = SHIELD.dashboard()
        L.append(f"  Status: {dash['status']}   Protected: {dash['protected_count']}")
        for cat, labels in dash["groups"].items():
            L.append(f"    {cat}: {', '.join(labels)}")

        if self._last_network:
            L += ["", "NETWORK", "-" * 66,
                  f"  {self._last_network['diagnosis']['summary']}"]

        L += ["", "OPTIMIZATION HISTORY", "-" * 66]
        hist = self.history()
        if not hist:
            L.append("  No changes have been applied.")
        for h in hist[:20]:
            L.append(f"  {h['timestamp'][:16]}  {h['title']}  "
                     f"({h['changes']} changes, backup {h['id']})")

        L += ["", "=" * 66,
              "This report was generated locally and has not been transmitted.",
              "It contains no passwords, keys or personal file contents."]

        text = "\n".join(L)
        from pathlib import Path as _P
        _P(path).write_text(text, encoding="utf-8")
        return path

    # ---------------- expert mode ----------------
    def presets(self) -> list:
        """Available optimization presets."""
        from .engine import presets as _p
        return list(_p.PRESETS)

    def preset_selection(self, preset_id: str, scan_result=None) -> list[str]:
        """Ids a preset would tick for the given (or a fresh) scan."""
        from .engine import presets as _p
        result = scan_result if scan_result is not None else self.scan()
        return _p.select(preset_id, result.recommendations)

    # ---------------- power plan ----------------
    def power_status(self) -> dict:
        from .engine import powerplan
        return powerplan.status()

    def power_describe(self) -> str:
        from .engine import powerplan
        return powerplan.describe()

    def create_power_plan(self, activate: bool = True):
        from .engine import powerplan
        return powerplan.create_plan(activate)

    def delete_power_plan(self):
        from .engine import powerplan
        return powerplan.delete_plan()

    # ---------------- licensing ----------------
    def license_status(self) -> dict:
        from .core import premium
        return premium.license_status()

    def activate_license(self, key: str):
        from .core import premium
        from .branding import VERSION
        return premium.activate(key, VERSION)

    def deactivate_license(self):
        from .core import premium
        return premium.deactivate()

    def expert_dump(self) -> dict:
        """Detailed technical state. Expert Mode never bypasses Phantom Shield."""
        if not self.config.get("expert_mode"):
            return {"error": "Expert Mode is disabled. Enable it in Advanced Settings."}
        from .engine import catalog
        from .engine import winsettings as ws
        return {
            "platform": platform_summary(),
            "registry": {
                "GameBar/AutoGameModeEnabled":
                    ws.read_registry("HKCU", catalog.GAMEBAR, "AutoGameModeEnabled"),
                "GameConfigStore/GameDVR_Enabled":
                    ws.read_registry("HKCU", catalog.GAME_DVR_USER, "GameDVR_Enabled"),
                "GraphicsDrivers/HwSchMode":
                    ws.read_registry("HKLM", catalog.GRAPHICS_DRIVERS, "HwSchMode"),
            },
            "power_plan": ws.active_power_scheme(),
            "shield": SHIELD.dashboard(),
            "shield_bypass_possible": False,
            "cpu": MONITOR.cpu(),
            "gpus": MONITOR.gpus(),
            "history": VAULT.history()[:20],
        }
