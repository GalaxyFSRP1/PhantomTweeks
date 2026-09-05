"""Entry point: ``python -m phantom_tweeks``.

This module must survive being executed in three different ways, because all
three happen in practice:

1. ``python -m phantom_tweeks``      - normal, has package context.
2. ``python src/phantom_tweeks/__main__.py`` - bare script, NO package context.
3. Frozen by PyInstaller as the entry script - also no package context.

Case 2 and 3 are why every import below is **absolute**. PyInstaller runs its
entry script as a top-level module named ``__main__`` with no parent package,
so a relative import such as ``from .gui import app_window`` raises:

    ImportError: attempted relative import with no known parent package

That exact error shipped in an early build. The frozen executable should use
``build/phantom_launcher.py`` rather than this file, but this module is now
self-sufficient either way so the mistake cannot recur silently.
"""
import os
import sys


def _ensure_package() -> None:
    """Make ``phantom_tweeks`` importable however we were started."""
    if getattr(sys, "frozen", False):
        return                      # PyInstaller bundled the package already
    here = os.path.dirname(os.path.abspath(__file__))       # .../phantom_tweeks
    src = os.path.dirname(here)                             # .../src
    if os.path.isdir(os.path.join(src, "phantom_tweeks")) and src not in sys.path:
        sys.path.insert(0, src)


def main() -> int:
    _ensure_package()

    try:
        from phantom_tweeks.core.logging_setup import install_crash_handler
        install_crash_handler()
    except Exception:
        # Crash reporting must never be the reason startup fails.
        pass

    try:
        if len(sys.argv) > 1:
            from phantom_tweeks.cli.main import run
            return run(sys.argv[1:])
        from phantom_tweeks.gui.app_window import launch
        return launch()
    except ImportError as exc:
        sys.stderr.write(
            "Phantom Tweeks could not start because part of the application "
            f"is missing:\n  {exc}\n\n"
            "This is a packaging problem with this build, not a problem with "
            "your PC.\nPlease report it with the text above.\n")
        return 3


if __name__ == "__main__":
    sys.exit(main())
