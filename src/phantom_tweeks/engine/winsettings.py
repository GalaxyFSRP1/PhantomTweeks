"""Thin, auditable wrapper over the Windows settings Phantom Tweeks manages.

Only these primitives may mutate the system. They all:
  * read the prior value first and return a ChangeRecord,
  * refuse to run off Windows,
  * refuse to touch anything on the security deny-list.
"""
from __future__ import annotations

from typing import Any, Optional

from ..core.logging_setup import get_logger
from ..core.platform_info import IS_WINDOWS, require_windows
from .backup import ABSENT, ChangeRecord
from ..core import runproc

log = get_logger("winsettings")

if IS_WINDOWS:  # pragma: no cover - platform specific
    import winreg
else:
    winreg = None  # type: ignore

HIVES = {
    "HKCU": "HKEY_CURRENT_USER",
    "HKLM": "HKEY_LOCAL_MACHINE",
}

# Registry subtrees automation must never write to, regardless of mode.
FORBIDDEN_PREFIXES = (
    r"software\microsoft\windows defender",
    r"software\policies\microsoft\windows defender",
    r"system\currentcontrolset\services\windefend",
    r"system\currentcontrolset\services\mpssvc",
    r"system\currentcontrolset\services\wuauserv",
    r"system\currentcontrolset\control\session manager\memory management\featuresettings",
    r"software\policies\microsoft\windows\windowsupdate",
    r"system\currentcontrolset\services\easyanticheat",
    r"system\currentcontrolset\services\beservice",
    r"system\currentcontrolset\services\vgc",
)


class ForbiddenSetting(PermissionError):
    """Raised when a write targets protected security/update configuration."""


def _check_allowed(hive: str, subkey: str, name: str) -> None:
    low = subkey.lower().lstrip("\\")
    for bad in FORBIDDEN_PREFIXES:
        if low.startswith(bad):
            raise ForbiddenSetting(
                f"Phantom Tweeks refuses to modify {hive}\\{subkey}\\{name}: "
                "Defender, Firewall, Windows Update, anti-cheat and security "
                "mitigations are permanently off-limits."
            )


def _hive_handle(hive: str):
    if hive.upper() == "HKCU":
        return winreg.HKEY_CURRENT_USER
    if hive.upper() == "HKLM":
        return winreg.HKEY_LOCAL_MACHINE
    raise ValueError(f"Unsupported hive: {hive}")


def read_registry(hive: str, subkey: str, name: str) -> Any:
    """Return the current value, or ABSENT when unset. Never raises for missing keys."""
    if not IS_WINDOWS:
        return ABSENT
    try:
        with winreg.OpenKey(_hive_handle(hive), subkey, 0, winreg.KEY_READ) as k:
            value, _ = winreg.QueryValueEx(k, name)
            return value
    except FileNotFoundError:
        return ABSENT
    except OSError as e:
        log.warning("Read failed %s\\%s\\%s: %s", hive, subkey, name, e)
        return ABSENT


def write_registry(hive: str, subkey: str, name: str, value: Any,
                   value_type: str = "REG_DWORD", note: str = "") -> ChangeRecord:
    """Write a value and return the reversible ChangeRecord."""
    require_windows(f"write {hive}\\{subkey}\\{name}")
    _check_allowed(hive, subkey, name)
    previous = read_registry(hive, subkey, name)
    reg_type = getattr(winreg, value_type)
    with winreg.CreateKeyEx(_hive_handle(hive), subkey, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, name, 0, reg_type, value)
    log.info("Wrote %s\\%s\\%s = %r (was %r)", hive, subkey, name, value, previous)
    return ChangeRecord("registry", f"{hive}\\{subkey}", name, previous, value,
                        value_type, note)


def revert_registry(change: ChangeRecord) -> tuple[bool, str]:
    """Undo one registry ChangeRecord."""
    if not IS_WINDOWS:
        return False, "Restore requires Windows."
    hive, _, subkey = change.target.partition("\\")
    try:
        _check_allowed(hive, subkey, change.name)
    except ForbiddenSetting as e:
        return False, str(e)
    try:
        if change.previous == ABSENT:
            with winreg.OpenKey(_hive_handle(hive), subkey, 0, winreg.KEY_SET_VALUE) as k:
                try:
                    winreg.DeleteValue(k, change.name)
                except FileNotFoundError:
                    pass
            return True, f"Removed {change.target}\\{change.name} (did not exist before)."
        reg_type = getattr(winreg, change.value_type or "REG_DWORD")
        with winreg.CreateKeyEx(_hive_handle(hive), subkey, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, change.name, 0, reg_type, change.previous)
        return True, f"Restored {change.target}\\{change.name} = {change.previous!r}."
    except OSError as e:
        return False, f"Could not restore {change.target}\\{change.name}: {e}"


# ---------------- power configuration ----------------

def active_power_scheme() -> Optional[str]:
    import shutil
    import subprocess
    if not IS_WINDOWS or not shutil.which("powercfg"):
        return None
    try:
        out = runproc.run(["powercfg", "/getactivescheme"],
                             capture_output=True, text=True, timeout=10).stdout
        parts = out.split(":")
        if len(parts) > 1:
            return parts[1].strip().split(" ")[0]
    except Exception:
        return None
    return None


def set_power_scheme(guid: str, note: str = "") -> ChangeRecord:
    import subprocess
    require_windows("change the active power plan")
    previous = active_power_scheme() or ABSENT
    runproc.run(["powercfg", "/setactive", guid], check=True, timeout=15)
    return ChangeRecord("powercfg", "active_scheme", "guid", previous, guid, None, note)


def revert_power_scheme(change: ChangeRecord) -> tuple[bool, str]:
    import subprocess
    if not IS_WINDOWS:
        return False, "Restore requires Windows."
    if change.previous == ABSENT:
        return False, "No prior power plan recorded; leaving current plan untouched."
    try:
        runproc.run(["powercfg", "/setactive", str(change.previous)],
                       check=True, timeout=15)
        return True, f"Restored power plan {change.previous}."
    except Exception as e:
        return False, f"Could not restore power plan: {e}"


def revert(change: ChangeRecord) -> tuple[bool, str]:
    """Dispatch a revert by change kind."""
    if change.kind == "registry":
        return revert_registry(change)
    if change.kind == "powercfg":
        return revert_power_scheme(change)
    if change.kind == "startup":
        from .startup import revert_startup
        return revert_startup(change)
    return False, f"Unknown change kind '{change.kind}'; skipped for safety."
