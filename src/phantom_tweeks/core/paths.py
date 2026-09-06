"""Filesystem locations used by Phantom Tweeks.

Everything Phantom Tweeks writes lives under one root so uninstall/rollback is
trivially auditable. On Windows that is %LOCALAPPDATA%\\PhantomTweeks.
A portable build sets PHANTOM_TWEEKS_HOME next to the executable.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from ..branding import APP_SLUG


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def is_portable() -> bool:
    """True for the portable build.

    The portable EXE carries a 'portable.flag' marker baked in by the spec
    file. Build-time environment variables are NOT sufficient here: they do
    not survive into the running executable, which would silently make the
    "portable" build write to %LOCALAPPDATA% like the installed one.
    """
    if os.environ.get("PHANTOM_TWEEKS_PORTABLE") == "1":
        return True
    if is_frozen():
        return (Path(sys._MEIPASS) / "portable.flag").exists()
    return False


def executable_dir() -> Path:
    """Folder containing the running EXE (or the repo root in dev)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def _default_root() -> Path:
    override = os.environ.get("PHANTOM_TWEEKS_HOME")
    if override:
        return Path(override)
    if is_portable():
        # Keep everything beside the executable so the user can carry it on a
        # USB stick and leave no trace on the host machine.
        return executable_dir() / "PhantomTweeksData"
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return Path(base) / APP_SLUG
    # Non-Windows: development / analysis mode only.
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return Path(base) / APP_SLUG


ROOT = _default_root()
BACKUPS = ROOT / "backups"
SNAPSHOTS = ROOT / "snapshots"
PROFILES = ROOT / "profiles"
LOGS = ROOT / "logs"
CRASH = LOGS / "crash"
HISTORY = ROOT / "history"
BENCHMARKS = ROOT / "benchmarks"
CONFIG_FILE = ROOT / "config.json"
HISTORY_DB = HISTORY / "history.json"
NETWORK_HISTORY = HISTORY / "network.json"


def ensure_dirs() -> None:
    for p in (ROOT, BACKUPS, SNAPSHOTS, PROFILES, LOGS, CRASH, HISTORY, BENCHMARKS):
        p.mkdir(parents=True, exist_ok=True)
