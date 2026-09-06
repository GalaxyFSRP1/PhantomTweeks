"""Registry inspector for the keys Phantom Tweeks manages.

Why this is deliberately narrow
-------------------------------
This is not a general-purpose registry editor. Regedit already exists and is
better at that job, and a full editor inside an optimizer invites exactly the
kind of blind copy-paste from forum posts that breaks machines.

What it does instead: show every registry value the app can touch, its current
state, the Windows default, and what the value means. You can see at a glance
whether a tweak is applied, whether something else changed it behind your back,
and what a "restore defaults" would actually do.

Safety
------
* Reads are unrestricted within the managed set; writes go through
  ``winsettings.write_registry``, which refuses anything under the forbidden
  security prefixes and records a reversible ChangeRecord.
* Editing a value by hand requires an explicit call with ``confirm=True``, so
  a stray click cannot change anything.
* Nothing here can create arbitrary keys: the path must already be in the
  managed catalogue.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from . import winsettings as ws
from .catalog import ABSENT


@dataclass
class ManagedValue:
    hive: str
    key: str
    name: str
    meaning: str
    default: Any
    good: Any = None            # the value a tweak sets, when there is one
    tweak_id: str = ""
    value_type: str = "REG_DWORD"

    def read(self) -> Any:
        return ws.read_registry(self.hive, self.key, self.name)

    def state(self) -> str:
        current = self.read()
        if current is ABSENT:
            return "not set"
        if self.good is not None and current == self.good:
            return "tweaked"
        if current == self.default:
            return "default"
        return "custom"

    def render(self) -> str:
        current = self.read()
        shown = "not set" if current is ABSENT else repr(current)
        state = self.state()
        mark = {"tweaked": "[T]", "default": "[ ]", "not set": "[-]",
                "custom": "[?]"}[state]
        out = [f"{mark} {self.name}",
               f"      {self.hive}\\{self.key}",
               f"      now: {shown}    default: {self.default!r}"]
        if self.good is not None:
            out.append(f"      tweaked value: {self.good!r}")
        if self.meaning:
            out.append(f"      {self.meaning}")
        if self.tweak_id:
            out.append(f"      set by the '{self.tweak_id}' toggle")
        return "\n".join(out)


# Everything Phantom Tweeks can write, with its documented default.
MANAGED: list = [
    ManagedValue("HKCU", r"Control Panel\Mouse", "MouseSpeed",
                 "Pointer acceleration. 0 is a 1:1 response.",
                 "1", "0", "mouse_accel", "REG_SZ"),
    ManagedValue("HKCU", r"Control Panel\Mouse", "MouseThreshold1",
                 "First acceleration threshold. 0 disables it.",
                 "6", "0", "mouse_threshold", "REG_SZ"),
    ManagedValue("HKCU", r"Control Panel\Mouse", "MouseThreshold2",
                 "Second acceleration threshold. 0 disables it.",
                 "10", "0", "mouse_threshold", "REG_SZ"),
    ManagedValue("HKCU", r"Control Panel\Desktop", "MenuShowDelay",
                 "Milliseconds before a submenu opens.",
                 "400", "0", "menu_delay", "REG_SZ"),
    ManagedValue("HKCU", r"System\GameConfigStore", "GameDVR_Enabled",
                 "Background game recording. 0 disables it.",
                 1, 0, "game_dvr"),
    ManagedValue("HKCU", r"System\GameConfigStore",
                 "GameDVR_FSEBehaviorMode",
                 "Fullscreen optimizations. 2 forces exclusive fullscreen.",
                 0, 2, "fso_disable"),
    ManagedValue("HKCU", r"Software\Microsoft\GameBar", "ShowStartupPanel",
                 "The 'press Win+G' prompt. 0 hides it.",
                 1, 0, "gamebar_tips"),
    ManagedValue("HKLM",
                 r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers",
                 "HwSchMode",
                 "Hardware-accelerated GPU scheduling. 2 enables it.",
                 1, 2, "hags"),
    ManagedValue("HKLM",
                 r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers",
                 "OverlayTestMode",
                 "Multi-plane overlay. 5 disables MPO as a bug workaround.",
                 0, 5, "mpo_disable"),
    ManagedValue("HKLM",
                 r"SYSTEM\CurrentControlSet\Control\PriorityControl",
                 "Win32PrioritySeparation",
                 "CPU quantum and foreground boost. 0x26 favours the "
                 "foreground window.",
                 2, 0x26, "win32_priority"),
    ManagedValue("HKLM",
                 r"SYSTEM\CurrentControlSet\Control\Power\PowerThrottling",
                 "PowerThrottlingOff",
                 "CPU power throttling for background work. 1 disables it.",
                 0, 1, "power_throttling"),
    ManagedValue("HKLM",
                 r"SYSTEM\CurrentControlSet\Control\Session Manager"
                 r"\Memory Management", "DisablePagingExecutive",
                 "Keeps kernel drivers resident in RAM. 1 enables that.",
                 0, 1, "paging_executive"),
    ManagedValue("HKLM",
                 r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia"
                 r"\SystemProfile", "NetworkThrottlingIndex",
                 "Legacy multimedia network throttle. 0xFFFFFFFF lifts it.",
                 10, 0xFFFFFFFF, "network_throttling"),
    ManagedValue("HKLM",
                 r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia"
                 r"\SystemProfile", "SystemResponsiveness",
                 "Percentage of CPU MMCSS reserves for background work.",
                 20, 10, "system_responsiveness"),
    ManagedValue("HKLM",
                 r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia"
                 r"\SystemProfile\Tasks\Games", "Priority",
                 "MMCSS Games task priority. 6 is Microsoft's documented "
                 "default.",
                 2, 6, "mmcss_games"),
    ManagedValue("HKLM",
                 r"SYSTEM\CurrentControlSet\Services\mouclass\Parameters",
                 "MouseDataQueueSize",
                 "Mouse input buffer depth. Larger avoids dropped input "
                 "during a stall.",
                 100, 200, "mouse_data_queue"),
    ManagedValue("HKLM",
                 r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters",
                 "MaxUserPort",
                 "Highest usable ephemeral port.",
                 5000, 65534, "max_user_port"),
    ManagedValue("HKLM",
                 r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters",
                 "DefaultTTL", "IP hop limit for outgoing packets.",
                 128, 64, "default_ttl"),
    ManagedValue("HKLM", r"SYSTEM\CurrentControlSet\Services\Ndu", "Start",
                 "Network usage driver. 4 disables the service.",
                 2, 4, "ndu_disable"),
]

BY_KEY = {(m.hive, m.key, m.name): m for m in MANAGED}


def snapshot() -> list:
    """Read every managed value. Never raises."""
    out = []
    for m in MANAGED:
        try:
            out.append((m, m.read(), m.state()))
        except Exception:
            out.append((m, ABSENT, "not set"))
    return out


def counts() -> dict:
    tally = {"tweaked": 0, "default": 0, "not set": 0, "custom": 0}
    for _m, _v, state in snapshot():
        tally[state] = tally.get(state, 0) + 1
    return tally


def report() -> str:
    tally = counts()
    out = ["MANAGED REGISTRY VALUES", "",
           f"{len(MANAGED)} values Phantom Tweeks is able to change.",
           f"  {tally['tweaked']} tweaked   {tally['default']} at default   "
           f"{tally['not set']} not set   {tally['custom']} changed elsewhere",
           "",
           "[T] tweaked by Phantom Tweeks    [ ] Windows default",
           "[-] not present                  [?] set to something else",
           "",
           "This lists only what the app can touch. It is not a general",
           "registry editor - regedit already does that job better, and a",
           "full editor here would invite blind copy-paste from forum posts.",
           ""]
    for m, _value, _state in snapshot():
        out += [m.render(), ""]
    return "\n".join(out)


def find(term: str) -> list:
    """Search managed values by name, path or meaning."""
    needle = (term or "").strip().lower()
    if not needle:
        return []
    return [m for m in MANAGED
            if needle in f"{m.name} {m.key} {m.meaning}".lower()]


def set_value(hive: str, key: str, name: str, value: Any,
              confirm: bool = False) -> tuple:
    """Write one managed value by hand.

    Requires ``confirm=True`` so an accidental call cannot change anything,
    and refuses any path that is not already in the managed catalogue.
    """
    managed = BY_KEY.get((hive, key, name))
    if managed is None:
        return False, ("That value is not one Phantom Tweeks manages. Use "
                       "regedit if you genuinely need to change it - and "
                       "make sure you know what it does first."), None
    if not confirm:
        return False, "Refusing to write without explicit confirmation.", None
    try:
        change = ws.write_registry(hive, key, name, value,
                                   value_type=managed.value_type,
                                   note=f"Manual edit: {managed.meaning}")
    except Exception as exc:
        return False, f"Could not write the value: {exc}", None
    return True, (f"{name} set to {value!r}. This was backed up and can be "
                  "reverted from History & Restore."), change


def restore_default(hive: str, key: str, name: str,
                    confirm: bool = False) -> tuple:
    """Put a managed value back to the Windows default."""
    managed = BY_KEY.get((hive, key, name))
    if managed is None:
        return False, "Not a managed value.", None
    return set_value(hive, key, name, managed.default, confirm=confirm)
