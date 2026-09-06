"""Request administrator rights at startup.

Why the app asks for elevation
------------------------------
Most of what Phantom Tweeks does needs it: writing under HKLM, creating a
power plan, changing network adapter settings, creating a System Restore
point. Without elevation those silently fail or refuse, which produced a
steady stream of "the power plan doesn't work" reports that were really just
missing rights.

How it asks
-----------
By relaunching itself through ShellExecute with the ``runas`` verb, which
raises the standard Windows UAC prompt. The original process then exits so
there is only ever one instance.

Deliberate choices
------------------
* **The manifest is not set to requireAdministrator.** A hard manifest
  requirement means the app cannot start at all without elevation - including
  for someone who only wants to read a report or run the CLI. Asking at
  runtime keeps read-only use available to standard users.
* **Declining is respected.** If UAC is cancelled the app carries on with
  reduced capability and says which features are unavailable, rather than
  nagging or exiting.
* ``--no-elevate`` skips the attempt entirely, which is what the CLI and the
  test suite use.
* Elevation is never attempted more than once: the relaunch passes a marker
  argument so a failed attempt cannot loop.
"""
from __future__ import annotations

import os
import sys

from .platform_info import IS_WINDOWS, is_admin

# Passed to the relaunched process so it never tries to elevate again.
_MARKER = "--elevated"
_SKIP = "--no-elevate"


def already_tried() -> bool:
    return _MARKER in sys.argv or _SKIP in sys.argv


def wanted(argv: list = None) -> bool:
    """Should we ask for elevation on this launch?"""
    argv = sys.argv if argv is None else argv
    if _SKIP in argv or _MARKER in argv:
        return False
    if not IS_WINDOWS:
        return False
    if is_admin():
        return False
    # A CLI invocation should not pop UAC: the user asked for a report, not a
    # system change. Commands that need rights say so when they run.
    return len(argv) <= 1


def relaunch_as_admin(argv: list = None) -> bool:
    """Relaunch elevated. Returns True if a new process was started.

    The caller should exit when this returns True - the elevated copy takes
    over. Returns False if elevation was declined or is unavailable, and the
    caller should continue unelevated.
    """
    argv = sys.argv if argv is None else argv
    if not IS_WINDOWS:
        return False
    try:
        import ctypes
    except ImportError:                                   # pragma: no cover
        return False

    if getattr(sys, "frozen", False):
        executable = sys.executable
        params = " ".join(f'"{a}"' for a in argv[1:] + [_MARKER])
    else:
        executable = sys.executable
        script = os.path.abspath(argv[0]) if argv else ""
        params = " ".join(f'"{a}"' for a in [script] + argv[1:] + [_MARKER])

    try:
        # SW_SHOWNORMAL = 1. A return value above 32 means it launched.
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", executable, params, None, 1)
        return int(rc) > 32
    except Exception:
        return False


def explain_limits() -> str:
    """What the user loses by running without administrator rights."""
    return (
        "Running without administrator rights.\n\n"
        "These need elevation and will report that when used:\n"
        "  - Creating or removing the Phantom power plan\n"
        "  - Registry tweaks under HKLM (HAGS, MMCSS, network throttling)\n"
        "  - Network adapter settings\n"
        "  - Creating a Windows System Restore point\n\n"
        "Everything else works normally: scanning, reporting, frame-time "
        "capture, the DNS lab, per-user tweaks and every diagnostic.\n\n"
        "To elevate, close Phantom Tweeks, right-click it and choose "
        "'Run as administrator'."
    )
