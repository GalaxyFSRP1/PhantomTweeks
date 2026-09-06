"""Platform gating.

Phantom Tweeks performs system changes on Windows only. On any other OS the
application runs in ANALYSIS-ONLY mode: monitoring, network and reporting work,
but every mutating operation refuses politely instead of guessing.
"""
from __future__ import annotations

import os
import platform
import sys


IS_WINDOWS = os.name == "nt"


def windows_release() -> str:
    if not IS_WINDOWS:
        return f"{platform.system()} {platform.release()}"
    ver = platform.version()          # e.g. 10.0.22631
    try:
        build = int(ver.split(".")[2])
    except (IndexError, ValueError):
        build = 0
    name = "Windows 11" if build >= 22000 else "Windows 10"
    return f"{name} (build {build})"


def is_supported_windows() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        return int(platform.version().split(".")[2]) >= 17763
    except (IndexError, ValueError):
        return False


def is_admin() -> bool:
    """True when the process can write machine-wide settings."""
    if not IS_WINDOWS:
        return os.geteuid() == 0 if hasattr(os, "geteuid") else False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


class UnsupportedPlatform(RuntimeError):
    """Raised when a mutating operation is attempted off Windows."""


def require_windows(operation: str) -> None:
    if not IS_WINDOWS:
        raise UnsupportedPlatform(
            f"'{operation}' changes Windows settings and is unavailable on "
            f"{platform.system()}. Phantom Tweeks is running in analysis-only mode."
        )


def summary() -> dict:
    return {
        "os": windows_release(),
        "supported": is_supported_windows(),
        "analysis_only": not IS_WINDOWS,
        "elevated": is_admin(),
        "python": sys.version.split()[0],
        "arch": platform.machine(),
    }
