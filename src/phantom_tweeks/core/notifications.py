"""Subtle notification system with anti-spam throttling."""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional


@dataclass
class Notification:
    icon: str
    message: str
    level: str = "info"      # info | warning | success
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%H:%M"))

    def render(self) -> str:
        return f"{self.icon} {self.message}"


PRESETS = {
    "update_available": ("\u2191", "A new version is available.", "info"),
    "game_detected": ("🎮", "Game detected — Phantom Shield active.", "info"),
    "network_unstable": ("⚠", "Network instability detected.", "warning"),
    "optimize_done": ("✓", "Optimization complete.", "success"),
    "backup_created": ("✓", "Backup created.", "success"),
    "improvement": ("⚡", "Performance improvement detected.", "success"),
    "regression": ("⚠", "Performance regression detected.", "warning"),
    "restored": ("✓", "Changes restored.", "success"),
    "update_available": ("\u2191", "A new version is available.", "info"),
    "game_detected": ("🎮", "A game is running.", "info"),
    "profile_applied": ("🎮", "Game profile applied.", "success"),
}


class NotificationCenter:
    def __init__(self, min_interval_s: int = 60, enabled: bool = True) -> None:
        self.min_interval_s = min_interval_s
        self.enabled = enabled
        self.history: deque[Notification] = deque(maxlen=100)
        self._last: dict[str, float] = {}
        self._sinks: list[Callable[[Notification], None]] = []

    def subscribe(self, sink: Callable[[Notification], None]) -> None:
        self._sinks.append(sink)

    def notify(self, key: str, message: Optional[str] = None,
               force: bool = False) -> Optional[Notification]:
        if not self.enabled:
            return None
        icon, default_msg, level = PRESETS.get(key, ("•", message or key, "info"))
        now = time.monotonic()
        if not force and now - self._last.get(key, -1e9) < self.min_interval_s:
            return None   # throttled: never spam the user
        self._last[key] = now
        note = Notification(icon, message or default_msg, level)
        self.history.appendleft(note)
        for sink in list(self._sinks):
            try:
                sink(note)
            except Exception:
                continue
        return note


CENTER = NotificationCenter()
