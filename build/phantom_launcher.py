"""Frozen-executable entry point.

Do NOT point PyInstaller at ``src/phantom_tweeks/__main__.py``. PyInstaller
executes the entry script as a top-level module named ``__main__`` with no
parent package, so every relative import inside it (``from .core import ...``)
raises:

    ImportError: attempted relative import with no known parent package

This launcher lives outside the package and uses absolute imports, which work
identically frozen and unfrozen.
"""
from __future__ import annotations

import os
import sys


def _bootstrap_path() -> None:
    """Make ``phantom_tweeks`` importable when running from source."""
    if getattr(sys, "frozen", False):
        return                      # PyInstaller already bundled the package
    here = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(os.path.dirname(here), "src")
    if os.path.isdir(src) and src not in sys.path:
        sys.path.insert(0, src)


def main() -> int:
    _bootstrap_path()

    try:
        from phantom_tweeks.core.logging_setup import install_crash_handler
        install_crash_handler()
    except Exception:
        # Never let crash-reporting setup be the thing that stops startup.
        pass

    try:
        if len(sys.argv) > 1:
            from phantom_tweeks.cli.main import run
            return run(sys.argv[1:])
        from phantom_tweeks.gui.app_window import launch
        return launch()
    except ImportError as e:
        # A packaging fault, not a user error. Say so plainly instead of
        # showing a bare traceback.
        sys.stderr.write(
            "Phantom Tweeks could not start because part of the application "
            f"is missing:\n  {e}\n\n"
            "This is a packaging problem with this build, not a problem with "
            "your PC.\nPlease report it with the text above.\n")
        return 3


if __name__ == "__main__":
    sys.exit(main())
