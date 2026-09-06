"""Continuous game auto-detection.

Polls for a running game on a background thread and fires callbacks when one
starts or stops, so the app notices a game that was launched *after* Phantom
Tweeks, or that was already running when the app opened.

Design notes
------------
* Detection is **observation only**. This module never touches the game
  process: no priority changes, no affinity, no suspension, no injection.
  It reports what it sees; acting on that is a separate, user-approved step.
* Callbacks run on the watcher thread. GUI code must marshal back to the Tk
  main loop (``widget.after(0, ...)``) rather than touching widgets directly.
* A game must be seen for ``confirm_polls`` consecutive polls before it counts
  as started. Launchers spawn short-lived helper processes, and a naive
  detector flaps between "game running" and "no game" during startup.
* The library scan is expensive (registry + disk), so it is cached and only
  refreshed periodically; process polling is cheap and runs every tick.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from . import games


@dataclass
class WatchState:
    """A snapshot of what the watcher currently believes."""

    game: Optional[games.RunningGame] = None
    since: float = 0.0
    detections: int = 0
    last_poll: float = 0.0
    last_error: str = ""

    @property
    def running(self) -> bool:
        return self.game is not None

    @property
    def session_seconds(self) -> float:
        if not self.running or not self.since:
            return 0.0
        return max(0.0, time.time() - self.since)

    def render(self) -> str:
        if not self.running:
            return "No game detected."
        mins = int(self.session_seconds // 60)
        g = self.game
        bits = [f"{g.name} (PID {g.pid})"]
        if g.launcher:
            bits.append(f"Launcher: {g.launcher}")
        if g.anti_cheat:
            bits.append(f"Anti-cheat: {g.anti_cheat} - protected, never touched")
        bits.append(f"Session: {mins} min" if mins else "Session: just started")
        return "\n".join(bits)


class GameWatcher:
    """Background poller that detects games starting and stopping.

    Usage::

        w = GameWatcher(on_start=..., on_stop=...)
        w.start()
        ...
        w.stop()

    Both callbacks are optional and receive the ``RunningGame``.
    """

    def __init__(
        self,
        interval: float = 5.0,
        confirm_polls: int = 2,
        library_refresh: float = 300.0,
        on_start: Optional[Callable[[games.RunningGame], None]] = None,
        on_stop: Optional[Callable[[games.RunningGame], None]] = None,
        on_poll: Optional[Callable[[WatchState], None]] = None,
    ) -> None:
        if interval <= 0:
            raise ValueError("interval must be positive")
        if confirm_polls < 1:
            raise ValueError("confirm_polls must be at least 1")
        self.interval = interval
        self.confirm_polls = confirm_polls
        self.library_refresh = library_refresh
        self.on_start = on_start
        self.on_stop = on_stop
        self.on_poll = on_poll

        self.state = WatchState()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._library: list[games.InstalledGame] = []
        self._library_at = 0.0
        # A candidate seen but not yet confirmed.
        self._pending: Optional[games.RunningGame] = None
        self._pending_count = 0

    # ------------------------------------------------------------ lifecycle

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="phantom-gamewatch", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=timeout)
        self._thread = None

    @property
    def alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ------------------------------------------------------------ internals

    def _library_now(self) -> list[games.InstalledGame]:
        now = time.time()
        if not self._library or (now - self._library_at) > self.library_refresh:
            try:
                self._library = games.scan_library()
            except Exception:
                # A failed library scan must not kill the watcher; process
                # matching still works on executable name alone.
                self._library = self._library or []
            self._library_at = now
        return self._library

    def poll_once(self) -> WatchState:
        """One detection cycle. Public so tests and the GUI can force a check."""
        try:
            found = games.detect_running_game(self._library_now())
            self.state.last_error = ""
        except Exception as exc:                      # pragma: no cover
            self.state.last_error = str(exc)
            found = None

        self.state.last_poll = time.time()
        current = self.state.game

        if found is not None:
            same = current is not None and found.pid == current.pid
            if same:
                self._pending, self._pending_count = None, 0
            else:
                # Require N consecutive sightings of the SAME pid before
                # declaring a start, so launcher helper processes do not flap.
                if self._pending is not None and self._pending.pid == found.pid:
                    self._pending_count += 1
                else:
                    self._pending, self._pending_count = found, 1

                if self._pending_count >= self.confirm_polls:
                    if current is not None:
                        self._fire_stop(current)
                    self._begin(found)
                    self._pending, self._pending_count = None, 0
        else:
            self._pending, self._pending_count = None, 0
            if current is not None:
                self._fire_stop(current)
                self.state.game = None
                self.state.since = 0.0

        if self.on_poll:
            self._safe(self.on_poll, self.state)
        return self.state

    def _begin(self, game: games.RunningGame) -> None:
        with self._lock:
            self.state.game = game
            self.state.since = time.time()
            self.state.detections += 1
        if self.on_start:
            self._safe(self.on_start, game)

    def _fire_stop(self, game: games.RunningGame) -> None:
        with self._lock:
            self.state.game = None
            self.state.since = 0.0
        if self.on_stop:
            self._safe(self.on_stop, game)

    @staticmethod
    def _safe(fn: Callable, arg) -> None:
        """A broken callback must never stop detection."""
        try:
            fn(arg)
        except Exception:
            pass

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.poll_once()
            # wait() rather than sleep() so stop() is responsive.
            self._stop.wait(self.interval)


# A process-wide watcher the GUI and CLI can share.
WATCHER = GameWatcher()
