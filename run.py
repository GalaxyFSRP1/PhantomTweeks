#!/usr/bin/env python3
"""Phantom Tweeks launcher.

Runs the app straight from a source checkout without installing anything.
This exists because the project uses a src/ layout, so `python -m phantom_tweeks`
from the repo root fails unless the package is installed or PYTHONPATH is set.

    python run.py            launch the GUI
    python run.py scan       run a CLI command
    python run.py --help     list all commands
"""
import os
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
if not (SRC / "phantom_tweeks" / "__init__.py").exists():
    sys.exit(
        "Phantom Tweeks: could not find src/phantom_tweeks next to run.py.\n"
        f"Looked in: {SRC}\n"
        "Run this script from inside the extracted phantom-tweeks folder."
    )
sys.path.insert(0, str(SRC))

if sys.version_info < (3, 10):
    sys.exit(
        f"Phantom Tweeks requires Python 3.10 or newer "
        f"(found {sys.version.split()[0]} at {sys.executable})."
    )

try:
    import psutil  # noqa: F401
except ImportError:
    sys.exit(
        "Phantom Tweeks: the 'psutil' package is required.\n\n"
        f"Install it with:\n    \"{sys.executable}\" -m pip install psutil\n"
    )

from phantom_tweeks.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
