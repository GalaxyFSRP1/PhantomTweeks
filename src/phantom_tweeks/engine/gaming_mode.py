"""Gaming Mode, Streaming Mode and Creator Mode.

Gaming Mode monitors and protects. It does not close Discord, Steam, Epic, or
the game, and it never terminates background applications automatically. Its
only mutating power is applying optimizations the user already approved — and
only if they explicitly enabled automatic optimization.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from ..core import games
from ..core.config import Config
from ..core.logging_setup import get_logger
from ..core.notifications import CENTER
from ..core.shield import SHIELD
from ..hardware.monitor import MONITOR
from . import profiles
from .optimizer import OptimizationEngine

log = get_logger("gaming_mode")


@dataclass
class SessionSample:
    at: str
    cpu: Optional[float]
    gpu: Optional[float]
    ram: Optional[float]


@dataclass
class GameSession:
    game: games.RunningGame
    profile: profiles.GameProfile
    started: str
    samples: list[SessionSample] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def duration_min(self) -> float:
        started = datetime.fromisoformat(self.started)
        return round((datetime.now() - started).total_seconds() / 60, 1)


class GamingMode:
    """Monitors the active game. Read-only by default."""

    MODES = ("gaming", "streaming", "creator")

    def __init__(self, config: Optional[Config] = None, mode: str = "gaming") -> None:
        self.config = config or Config.load()
        self.mode = mode if mode in self.MODES else "gaming"
        self.engine = OptimizationEngine(self.config)
        self.active = False
        self.session: Optional[GameSession] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._library: list[games.InstalledGame] = []
        self.on_event: list[Callable[[str, dict], None]] = []

    # ---------------- lifecycle ----------------
    def start(self, poll_seconds: int = 5) -> None:
        if self.active:
            return
        for name in self.config.get("protected_apps", []):
            SHIELD.add_user_protected(name)
        self._library = games.scan_library()
        self.active = True
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, args=(poll_seconds,),
                                        daemon=True, name="PhantomGamingMode")
        self._thread.start()
        log.info("%s Mode started", self.mode.title())
        self._emit("mode_started", {"mode": self.mode})

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)
        self.active = False
        self.session = None
        SHIELD.set_game_processes([])
        log.info("%s Mode stopped", self.mode.title())
        self._emit("mode_stopped", {"mode": self.mode})

    def _emit(self, event: str, payload: dict) -> None:
        for cb in list(self.on_event):
            try:
                cb(event, payload)
            except Exception:
                continue

    # ---------------- main loop ----------------
    def _loop(self, poll_seconds: int) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:
                log.exception("Gaming Mode tick failed")
            self._stop.wait(poll_seconds)

    def _tick(self) -> None:
        running = games.detect_running_game(self._library)

        if running and (not self.session or self.session.game.pid != running.pid):
            self._on_game_start(running)
        elif not running and self.session:
            self._on_game_stop()

        if self.session:
            cpu = MONITOR.cpu()
            gpus = MONITOR.gpus()
            mem = MONITOR.memory()
            self.session.samples.append(SessionSample(
                datetime.now().isoformat(timespec="seconds"),
                cpu.utilization,
                next((g.utilization for g in gpus if g.utilization is not None), None),
                mem.percent))
            if len(self.session.samples) > 5000:
                self.session.samples = self.session.samples[-5000:]

    def _on_game_start(self, running: games.RunningGame) -> None:
        # 1. Shield first, always — before anything else looks at the system.
        SHIELD.set_game_processes(games.game_process_names(running))
        profile = profiles.profile_for_game(running.name)
        if self.mode == "streaming":
            profile = profiles.load("Streaming") or profile
        elif self.mode == "creator":
            profile = profiles.load("Creator") or profile

        self.session = GameSession(running, profile,
                                   datetime.now().isoformat(timespec="seconds"))
        dash = SHIELD.dashboard()
        log.info("Game detected: %s (%s) — %d processes protected",
                 running.name, running.launcher, dash["protected_count"])
        CENTER.notify("game_detected",
                      f"{running.name} detected — Phantom Shield active "
                      f"({dash['protected_count']} processes protected).")
        self._emit("game_detected", {
            "game": running.as_dict(), "profile": profile.name,
            "protected": dash["protected_count"],
        })

        # 2. Only ever auto-apply when the user opted in AND the profile allows it.
        if self.config.get("auto_apply_high_confidence") and profile.auto_apply:
            result = self.engine.apply_auto(running.as_dict())
            if result.applied:
                CENTER.notify("optimize_done",
                              f"Applied {len(result.applied)} high-confidence "
                              f"optimization(s). Backup {result.backup.id} created.")
                self._emit("auto_optimized", {"result": result.summary()})
        else:
            self._emit("recommendation_ready", {
                "message": "Recommended configuration available. Nothing has been "
                           "changed — open Phantom Tweeks to review and approve."})

    def _on_game_stop(self) -> None:
        session = self.session
        self.session = None
        SHIELD.set_game_processes([])
        if session:
            log.info("Game session ended: %s after %.1f min",
                     session.game.name, session.duration_min)
            self._emit("game_ended", {
                "game": session.game.name, "duration_min": session.duration_min})

    # ---------------- reporting ----------------
    def status(self) -> dict:
        dash = SHIELD.dashboard()
        out = {
            "mode": self.mode,
            "active": self.active,
            "shield": dash,
            "game": None,
            "profile": None,
            "auto_apply": bool(self.config.get("auto_apply_high_confidence")),
        }
        if self.session:
            out["game"] = self.session.game.as_dict()
            out["profile"] = self.session.profile.name
            out["duration_min"] = self.session.duration_min
        return out

    def render_detection(self) -> str:
        if not self.session:
            return "No game currently detected."
        g = self.session.game
        cpu = MONITOR.cpu()
        gpus = MONITOR.gpus()
        vendor = gpus[0].vendor if gpus else "Unknown"
        cpu_vendor = "AMD" if "amd" in (cpu.model or "").lower() else (
            "Intel" if "intel" in (cpu.model or "").lower() else "Unknown")
        return (
            "GAME DETECTED\n\n"
            f"Game: {g.name}\n"
            f"Launcher: {g.launcher or 'Standalone'}\n"
            f"Anti-Cheat: {g.anti_cheat or 'Not detected'}\n"
            f"GPU: {vendor}\n"
            f"CPU: {cpu_vendor}\n\n"
            "Phantom Shield:\n"
            f"{SHIELD.dashboard()['protected_count']} processes protected\n\n"
            f"{self.mode.title()} Mode:\nACTIVE" if self.active else "INACTIVE")
