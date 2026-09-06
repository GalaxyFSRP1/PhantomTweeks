"""Advanced Startup Manager.

Lists startup entries with impact, publisher and path. Disabling is manual,
reversible, and blocked for critical Windows and protected components.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..core.logging_setup import get_logger
from ..core.platform_info import IS_WINDOWS, require_windows
from ..core.shield import SHIELD
from .backup import ABSENT, ChangeRecord
from ..core import runproc

log = get_logger("startup")

RUN_KEYS = [
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Run"),
    ("HKLM", r"Software\Microsoft\Windows\CurrentVersion\Run"),
    ("HKLM", r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"),
]

# Never offer to disable these.
CRITICAL_STARTUP = {
    "securityhealth", "windowsdefender", "securityhealthsystray",
    "onedrive setup", "usbccgpsyncservice", "realtekaudiomanager",
    "rtkaudiouniversalservice", "igfxtray", "nvbackend",
}


@dataclass
class StartupEntry:
    name: str
    command: str
    location: str
    hive: str
    publisher: Optional[str] = None
    path: Optional[str] = None
    enabled: bool = True
    impact: str = "Unknown"
    critical: bool = False
    protected: bool = False

    def render(self) -> str:
        flag = " [critical]" if self.critical else (" [protected]" if self.protected else "")
        return (f"{self.name}{flag}\n"
                f"  Status:    {'Enabled' if self.enabled else 'Disabled'}\n"
                f"  Impact:    {self.impact}\n"
                f"  Publisher: {self.publisher or 'Unknown'}\n"
                f"  Path:      {self.path or self.command}")


def _exe_from_command(cmd: str) -> Optional[str]:
    cmd = cmd.strip()
    if cmd.startswith('"'):
        end = cmd.find('"', 1)
        return cmd[1:end] if end > 0 else None
    return cmd.split(" ")[0] if cmd else None


def _publisher(path: Optional[str]) -> Optional[str]:
    if not path or not IS_WINDOWS or not Path(path).exists():
        return None
    try:
        import subprocess, json
        ps = (f"(Get-Item -LiteralPath '{path}').VersionInfo.CompanyName")
        out = runproc.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        return out or None
    except Exception:
        return None


def _impact(path: Optional[str]) -> str:
    """Estimate impact from file size — an honest heuristic, labelled as such."""
    if not path or not Path(path).exists():
        return "Unknown"
    try:
        mb = Path(path).stat().st_size / 1024 / 1024
    except OSError:
        return "Unknown"
    return "High" if mb > 40 else "Medium" if mb > 8 else "Low"


def list_entries() -> list[StartupEntry]:
    entries: list[StartupEntry] = []
    if not IS_WINDOWS:
        return entries
    import winreg
    hives = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}
    for hive, sub in RUN_KEYS:
        try:
            with winreg.OpenKey(hives[hive], sub) as k:
                for i in range(winreg.QueryInfoKey(k)[1]):
                    try:
                        name, value, _ = winreg.EnumValue(k, i)
                    except OSError:
                        continue
                    exe = _exe_from_command(str(value))
                    e = StartupEntry(
                        name=name, command=str(value), location=sub, hive=hive,
                        path=exe, publisher=_publisher(exe), impact=_impact(exe),
                        critical=name.lower().replace(" ", "") in CRITICAL_STARTUP,
                        protected=SHIELD.is_protected(Path(exe).name if exe else None),
                    )
                    entries.append(e)
        except OSError:
            continue
    # Startup folder shortcuts
    import os
    for base, hive in ((os.environ.get("APPDATA"), "HKCU"),
                       (os.environ.get("PROGRAMDATA"), "HKLM")):
        if not base:
            continue
        folder = Path(base) / r"Microsoft\Windows\Start Menu\Programs\Startup"
        if folder.exists():
            for item in folder.iterdir():
                if item.name.lower() == "desktop.ini":
                    continue
                entries.append(StartupEntry(
                    name=item.stem, command=str(item), location=str(folder),
                    hive=hive, path=str(item), impact="Unknown"))
    return sorted(entries, key=lambda e: e.name.lower())


DISABLED_KEY = r"Software\PhantomTweeks\DisabledStartup"


def disable(entry: StartupEntry) -> ChangeRecord:
    """Disable by moving the value into our own key — fully reversible."""
    require_windows("disable a startup entry")
    if entry.critical:
        raise PermissionError(
            f"'{entry.name}' is a critical Windows startup component and cannot be "
            "disabled by Phantom Tweeks.")
    if entry.protected:
        raise PermissionError(
            f"'{entry.name}' belongs to a Phantom Shield protected application.")
    import winreg
    from . import winsettings as ws
    hive = winreg.HKEY_CURRENT_USER if entry.hive == "HKCU" else winreg.HKEY_LOCAL_MACHINE
    with winreg.OpenKey(hive, entry.location, 0, winreg.KEY_SET_VALUE) as k:
        winreg.DeleteValue(k, entry.name)
    ws.write_registry("HKCU", DISABLED_KEY, entry.name,
                      f"{entry.hive}|{entry.location}|{entry.command}",
                      value_type="REG_SZ", note="Startup entry stash")
    log.info("Disabled startup entry %s", entry.name)
    return ChangeRecord("startup", f"{entry.hive}\\{entry.location}", entry.name,
                        entry.command, ABSENT, "REG_SZ",
                        f"Disabled startup entry '{entry.name}'")


def revert_startup(change: ChangeRecord) -> tuple[bool, str]:
    if not IS_WINDOWS:
        return False, "Restore requires Windows."
    import winreg
    hive_name, _, sub = change.target.partition("\\")
    hive = winreg.HKEY_CURRENT_USER if hive_name == "HKCU" else winreg.HKEY_LOCAL_MACHINE
    try:
        with winreg.CreateKeyEx(hive, sub, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, change.name, 0, winreg.REG_SZ, str(change.previous))
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, DISABLED_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
            try:
                winreg.DeleteValue(k, change.name)
            except FileNotFoundError:
                pass
        return True, f"Re-enabled startup entry '{change.name}'."
    except OSError as e:
        return False, f"Could not re-enable '{change.name}': {e}"
