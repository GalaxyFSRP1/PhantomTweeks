"""Run external commands without flashing a console window.

The problem
-----------
Phantom Tweeks is built as a windowed (``console=False``) executable. When a
windowed process on Windows calls ``subprocess.run(["powercfg", ...])``, the
child gets a brand-new console allocated for it, which appears as a black box
that flashes on screen and steals focus.

The hardware monitor polls on a timer, so this is not a one-off blink: it is a
console flashing every few seconds for as long as the app is open, and it can
pull focus out of a fullscreen game. That is unacceptable in an app whose
entire purpose is not to disturb your session.

The fix
-------
Every external command in the app goes through :func:`run`, which sets
``CREATE_NO_WINDOW`` and a hidden ``STARTUPINFO``. Both are needed:
``CREATE_NO_WINDOW`` covers console programs, and ``STARTF_USESHOWWINDOW``
covers the cases where a child still tries to show a window.

Nothing here changes *what* is executed - only that it stays invisible.
"""
from __future__ import annotations

import subprocess
import sys
from typing import Optional, Sequence

# Gate on the real platform, not on attribute presence. subprocess rejects
# creationflags/startupinfo outright on POSIX ("creationflags is only
# supported on Windows platforms"), so passing them anywhere else turns a
# harmless probe into a ValueError.
IS_WINDOWS = sys.platform.startswith("win")


def _startupinfo():
    """A STARTUPINFO that hides the child window, or None off Windows."""
    if not IS_WINDOWS:
        return None
    si_cls = getattr(subprocess, "STARTUPINFO", None)
    if si_cls is None:
        return None
    si = si_cls()
    use_show = getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
    if use_show:
        si.dwFlags |= use_show
        si.wShowWindow = 0          # SW_HIDE
    return si


def hidden_kwargs() -> dict:
    """Keyword arguments that keep a child process invisible.

    Use this when you need ``Popen`` directly rather than :func:`run`.
    """
    kw: dict = {}
    if not IS_WINDOWS:
        return kw
    flag = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if flag:
        kw["creationflags"] = flag
    si = _startupinfo()
    if si is not None:
        kw["startupinfo"] = si
    return kw


def run(cmd: Sequence[str],
        timeout: Optional[float] = 15,
        capture: bool = True,
        text: bool = True,
        check: bool = False,
        **extra):
    """``subprocess.run`` that never shows a console window.

    Returns the CompletedProcess. Callers that previously used
    ``capture_output=True`` get the same behaviour by default.
    """
    kwargs = dict(hidden_kwargs())
    if capture:
        kwargs["capture_output"] = True
    if text:
        kwargs["text"] = True
    if timeout is not None:
        kwargs["timeout"] = timeout
    kwargs["check"] = check
    kwargs.update(extra)
    return subprocess.run(list(cmd), **kwargs)


def output(cmd: Sequence[str], timeout: Optional[float] = 15,
           default: str = "") -> str:
    """Return a command's stdout, or *default* if it fails.

    Convenience for the many read-only probes (``powercfg /query``,
    ``ipconfig``) where a failure simply means "information unavailable" and
    must never propagate as an exception into the UI.
    """
    try:
        proc = run(cmd, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return default
    return proc.stdout or default
