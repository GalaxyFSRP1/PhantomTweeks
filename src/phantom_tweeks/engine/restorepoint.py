"""Windows System Restore points.

Why this matters
----------------
Phantom Tweeks already journals every change it makes and can revert each one
individually. That covers the expected case. It does not cover the case where
something *else* goes wrong afterwards - a driver update, a Windows update, an
unrelated installer - and you want the machine back the way it was.

A System Restore point is the operating system's own safety net: it captures
the registry and system files, and it can be rolled back from the Windows
Recovery Environment even if the machine will not boot. Our journal cannot do
that, because it needs Phantom Tweeks to run.

Design decisions
----------------
* **Never a substitute for the journal.** Restore points are coarse; the
  journal is precise. This is an extra layer, not a replacement.
* **Never silently assumed to work.** If System Protection is disabled - which
  it is by default on many OEM Windows 11 installs - creating a point fails.
  We detect that and say so, rather than proceeding while implying a safety
  net exists that does not.
* **We never enable System Protection ourselves.** It allocates disk space and
  changes system configuration; that is the user's decision, and we show them
  the exact command.
* Windows rate-limits restore points to one per 24 hours by default. We detect
  that specific failure and explain it instead of reporting a generic error.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from ..core import runproc
from ..core.platform_info import IS_WINDOWS, is_admin
from ..core.logging_setup import get_logger

log = get_logger("restorepoint")

# Creating a restore point needs an elevated PowerShell call.
_PS = ["powershell", "-NoProfile", "-NonInteractive", "-Command"]


@dataclass
class RestorePoint:
    sequence: Optional[int] = None
    description: str = ""
    created: str = ""
    kind: str = ""

    def render(self) -> str:
        when = self.created or "unknown date"
        return f"  #{self.sequence or '?'}  {when}  {self.description}"


@dataclass
class ProtectionStatus:
    supported: bool = False
    enabled: bool = False
    admin: bool = False
    drives: list = field(default_factory=list)
    message: str = ""

    @property
    def can_create(self) -> bool:
        return self.supported and self.enabled and self.admin

    def render(self) -> str:
        if not self.supported:
            return f"System Restore is unavailable.\n  {self.message}"
        out = ["System Protection: " + ("ON" if self.enabled else "OFF")]
        if self.drives:
            out.append("  Protected drives: " + ", ".join(self.drives))
        if not self.enabled:
            out += [
                "",
                "  Windows is not keeping restore points on this PC. Many",
                "  OEM installs ship with System Protection disabled.",
                "",
                "  Phantom Tweeks will not turn it on for you: it reserves",
                "  disk space and changes system configuration, so that is",
                "  your call. To enable it yourself, in an admin PowerShell:",
                "",
                "    Enable-ComputerRestore -Drive \"C:\\\\\"",
                "",
                "  Your changes are still individually reversible from",
                "  History & Restore either way - this is an extra layer,",
                "  not the only one.",
            ]
        elif not self.admin:
            out += ["", "  Creating a restore point needs administrator rights."]
        return "\n".join(out)


def _ps(script: str, timeout: int = 60):
    return runproc.run(_PS + [script], timeout=timeout)


def status() -> ProtectionStatus:
    """Is System Protection on, and can we use it right now?"""
    st = ProtectionStatus()
    if not IS_WINDOWS:
        st.message = "System Restore is a Windows feature."
        return st
    st.supported = True
    st.admin = is_admin()

    # Get-ComputerRestorePoint fails when protection is off, so query the
    # configured shadow-copy volumes instead: that reflects real state.
    script = ("try { (Get-CimInstance -Namespace root/default "
              "-ClassName SystemRestoreConfig -ErrorAction Stop) | "
              "Out-Null } catch { }; "
              "vssadmin list shadowstorage 2>&1 | Out-String")
    out = _ps(script, timeout=40).stdout or ""
    drives = sorted(set(re.findall(r"[Vv]olume:.*?\(([A-Z]:)\)", out)))
    st.drives = drives
    st.enabled = bool(drives)

    if not st.enabled:
        # Second opinion: an existing restore point proves it works.
        probe = _ps("(Get-ComputerRestorePoint | Measure-Object).Count",
                    timeout=40).stdout.strip()
        if probe.isdigit() and int(probe) > 0:
            st.enabled = True
    return st


def list_points(limit: int = 10) -> list[RestorePoint]:
    """Existing restore points, newest first. Never raises."""
    if not IS_WINDOWS:
        return []
    script = ("Get-ComputerRestorePoint | "
              "Select-Object SequenceNumber,Description,CreationTime,"
              "RestorePointType | ConvertTo-Json -Compress")
    out = (_ps(script, timeout=60).stdout or "").strip()
    if not out:
        return []
    try:
        import json
        data = json.loads(out)
    except ValueError:
        return []
    if isinstance(data, dict):
        data = [data]

    points = []
    for row in data:
        created = str(row.get("CreationTime") or "")
        # WMI returns /Date(1234567890123)/ - convert to something readable.
        m = re.search(r"/Date\((\d+)", created)
        if m:
            import datetime
            created = datetime.datetime.fromtimestamp(
                int(m.group(1)) / 1000).strftime("%Y-%m-%d %H:%M")
        points.append(RestorePoint(
            sequence=row.get("SequenceNumber"),
            description=str(row.get("Description") or ""),
            created=created,
            kind=str(row.get("RestorePointType") or ""),
        ))
    points.sort(key=lambda p: p.sequence or 0, reverse=True)
    return points[:limit]


def create(description: str = "Before Phantom Tweeks changes") -> tuple[bool, str]:
    """Create a restore point. Returns (ok, message).

    Fails honestly: every failure mode gets a specific explanation rather than
    a generic error, because a user who believes they have a restore point and
    does not is worse off than one who knows they do not.
    """
    if not IS_WINDOWS:
        return False, "System Restore is a Windows feature."

    st = status()
    if not st.enabled:
        return False, ("System Protection is turned off, so Windows cannot "
                       "create a restore point.\n\n" + st.render())
    if not st.admin:
        return False, ("Creating a restore point requires administrator "
                       "rights. Restart Phantom Tweeks as administrator.")

    safe = description.replace("'", "''")[:200]
    proc = _ps(f"Checkpoint-Computer -Description '{safe}' "
               "-RestorePointType 'MODIFY_SETTINGS'", timeout=180)
    if proc.returncode == 0:
        log.info("Created restore point: %s", description)
        return True, (f"Restore point created: {description}\n\n"
                      "You can roll the whole system back to this point from "
                      "Windows System Restore, even if the PC will not boot.")

    err = (proc.stderr or proc.stdout or "").strip()
    lowered = err.lower()
    if "24 hour" in lowered or "frequency" in lowered or "1440" in lowered:
        return False, ("Windows only allows one restore point every 24 hours "
                       "by default, and one already exists from today.\n\n"
                       "That existing point still protects you. Your Phantom "
                       "Tweeks changes are individually reversible from "
                       "History & Restore regardless.")
    if "disabled" in lowered or "0x8007" in lowered:
        return False, ("Windows reported that System Protection is disabled "
                       "for this drive.\n\n" + st.render())
    return False, f"Windows could not create a restore point.\n  {err[:300]}"
