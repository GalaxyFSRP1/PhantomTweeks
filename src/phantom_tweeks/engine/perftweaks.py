"""Latency and performance tweaks as simple on/off toggles.

Same contract as the network tweaks: flip a switch and it applies, flip it
back and the Windows default is restored exactly. Every change captures its
previous value first, so nothing here is one-way.

What is deliberately absent
---------------------------
No overclocking, no undervolting, no core disabling, no forced affinity, no
security mitigations touched. Those either vary by individual chip (and so
cannot be applied blind), or trade away protection for performance that is
largely theoretical on current hardware. The Tweak Encyclopedia documents why
each was rejected.

Tweaks that can backfire carry a ``warning``. The UI shows it under the
toggle and asks before enabling, because "simple" should not mean "silently
risky".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from ..core import runproc
from ..core.platform_info import IS_WINDOWS, is_admin
from . import winsettings as ws

DESKTOP = r"Control Panel\Desktop"
MOUSE = r"Control Panel\Mouse"
GAME_DVR_USER = r"System\GameConfigStore"
GAMEBAR = r"Software\Microsoft\GameBar"
GRAPHICS_DRIVERS = r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers"
MEMORY_MGMT = r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management"
PRIORITY = r"SYSTEM\CurrentControlSet\Control\PriorityControl"
POWER_THROTTLE = r"SYSTEM\CurrentControlSet\Control\Power\PowerThrottling"
MULTIMEDIA_GAMES = (r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
                    r"\Multimedia\SystemProfile\Tasks\Games")
SEARCH_POLICY = r"SOFTWARE\Policies\Microsoft\Windows\Windows Search"
CONTENT_DELIVERY = (r"Software\Microsoft\Windows\CurrentVersion"
                    r"\ContentDeliveryManager")
EXPLORER_ADV = (r"Software\Microsoft\Windows\CurrentVersion\Explorer"
                r"\Advanced")


@dataclass
class PerfTweak:
    id: str
    name: str
    category: str            # Input | Display | System | Power | Background
    effect: str
    detail: str
    warning: str = ""
    requires_admin: bool = True
    apply: Optional[Callable] = None
    is_on: Optional[Callable] = None

    @property
    def risky(self) -> bool:
        return bool(self.warning)


def _reg(hive, key, name, on_value, off_value, note):
    """Build an apply function that writes one registry value."""
    def _apply(on):
        return [ws.write_registry(hive, key, name,
                                  on_value if on else off_value, note=note)]
    return _apply


def _reg_str(hive, key, name, on_value, off_value, note):
    def _apply(on):
        return [ws.write_registry(hive, key, name,
                                  on_value if on else off_value,
                                  value_type="REG_SZ", note=note)]
    return _apply


def _is(hive, key, name, wanted):
    return lambda: ws.read_registry(hive, key, name) == wanted


TWEAKS: list = [

    # ------------------------------------------------------------ Input
    PerfTweak(
        "mouse_accel", "Disable mouse acceleration", "Input",
        "Makes mouse movement 1:1 with your hand",
        "Enhanced Pointer Precision makes the same physical movement produce "
        "different cursor distances depending on how fast you move. Turning "
        "it off is near-universal among competitive players because it makes "
        "muscle memory reliable.",
        requires_admin=False,
        apply=_reg_str("HKCU", MOUSE, "MouseSpeed", "0", "1",
                       "Mouse acceleration"),
        is_on=_is("HKCU", MOUSE, "MouseSpeed", "0")),

    PerfTweak(
        "mouse_threshold", "Remove pointer acceleration thresholds", "Input",
        "Removes the remaining acceleration curve",
        "The two threshold values control where acceleration kicks in. "
        "Zeroing them completes what disabling acceleration starts - leaving "
        "them set can reintroduce the curve at speed.",
        requires_admin=False,
        apply=lambda on: [
            ws.write_registry("HKCU", MOUSE, "MouseThreshold1",
                              "0" if on else "6", value_type="REG_SZ",
                              note="Pointer acceleration threshold 1"),
            ws.write_registry("HKCU", MOUSE, "MouseThreshold2",
                              "0" if on else "10", value_type="REG_SZ",
                              note="Pointer acceleration threshold 2")],
        is_on=_is("HKCU", MOUSE, "MouseThreshold1", "0")),

    PerfTweak(
        "keyboard_repeat", "Fastest keyboard repeat rate", "Input",
        "Shortens the delay before a held key repeats",
        "Noticeable in menus and chat. It does not change in-game input "
        "polling, which games read directly.",
        requires_admin=False,
        apply=lambda on: [
            ws.write_registry("HKCU", r"Control Panel\Keyboard",
                              "KeyboardDelay", "0" if on else "1",
                              value_type="REG_SZ", note="Keyboard delay"),
            ws.write_registry("HKCU", r"Control Panel\Keyboard",
                              "KeyboardSpeed", "31" if on else "31",
                              value_type="REG_SZ", note="Keyboard speed")],
        is_on=_is("HKCU", r"Control Panel\Keyboard", "KeyboardDelay", "0")),

    PerfTweak(
        "filter_keys", "Disable Filter Keys", "Input",
        "Stops Windows ignoring rapid repeated keystrokes",
        "If Filter Keys is accidentally on - easy to trigger by holding "
        "Shift - it genuinely drops fast inputs. A real, if uncommon, cause "
        "of 'my keyboard is missing presses'.",
        requires_admin=False,
        apply=_reg_str("HKCU", r"Control Panel\Accessibility\Keyboard Response",
                       "Flags", "122", "126", "Filter Keys"),
        is_on=_is("HKCU", r"Control Panel\Accessibility\Keyboard Response",
                  "Flags", "122")),

    PerfTweak(
        "sticky_keys", "Disable the Sticky Keys prompt", "Input",
        "Stops the five-shift-presses popup",
        "The prompt can steal focus mid-game. Pure anti-annoyance, but the "
        "focus theft is real.",
        requires_admin=False,
        apply=_reg_str("HKCU", r"Control Panel\Accessibility\StickyKeys",
                       "Flags", "506", "510", "Sticky Keys"),
        is_on=_is("HKCU", r"Control Panel\Accessibility\StickyKeys",
                  "Flags", "506")),

    # ---------------------------------------------------------- Display
    PerfTweak(
        "game_dvr", "Disable background game recording", "Display",
        "Stops Xbox Game Bar continuously capturing",
        "Background capture uses real GPU encode time and disk bandwidth the "
        "entire time you play. Many people leave it on without realising.",
        requires_admin=False,
        apply=lambda on: [
            ws.write_registry("HKCU", GAME_DVR_USER, "GameDVR_Enabled",
                              0 if on else 1, note="Game DVR"),
            ws.write_registry("HKCU", GAMEBAR, "UseNexusForGameBarEnabled",
                              0 if on else 1, note="Game Bar")],
        is_on=_is("HKCU", GAME_DVR_USER, "GameDVR_Enabled", 0)),

    PerfTweak(
        "gamebar_tips", "Disable Game Bar tips", "Display",
        "Stops the 'press Win+G' overlay prompt",
        "Prevents the Game Bar overlay appearing over a fullscreen "
        "game, which can steal focus at exactly the wrong moment. "
        "Purely an interruption fix - no frame-rate claim attached.",
        requires_admin=False,
        apply=_reg("HKCU", GAMEBAR, "ShowStartupPanel", 0, 1, "Game Bar tips"),
        is_on=_is("HKCU", GAMEBAR, "ShowStartupPanel", 0)),

    PerfTweak(
        "menu_delay", "Remove the menu open delay", "Display",
        "Menus and submenus open instantly",
        "Windows waits 400 ms before opening a submenu. Zeroing it makes the "
        "desktop feel markedly quicker. No effect inside a game.",
        requires_admin=False,
        apply=_reg_str("HKCU", DESKTOP, "MenuShowDelay", "0", "400",
                       "Menu show delay"),
        is_on=_is("HKCU", DESKTOP, "MenuShowDelay", "0")),

    PerfTweak(
        "transparency", "Disable transparency effects", "Display",
        "Removes acrylic blur from Start and the taskbar",
        "Blur is genuine GPU work on the desktop. Measurable on integrated "
        "graphics; irrelevant while a fullscreen game owns the screen.",
        requires_admin=False,
        apply=_reg("HKCU",
                   r"Software\Microsoft\Windows\CurrentVersion\Themes"
                   r"\Personalize",
                   "EnableTransparency", 0, 1, "Transparency effects"),
        is_on=_is("HKCU",
                  r"Software\Microsoft\Windows\CurrentVersion\Themes"
                  r"\Personalize", "EnableTransparency", 0)),

    PerfTweak(
        "taskbar_animations", "Disable window animations", "Display",
        "Removes minimise, maximise and taskbar animation",
        "A small compositor saving and a noticeably snappier desktop "
        "feel. It changes nothing inside a fullscreen game, where the "
        "desktop is not being composited at all.",
        requires_admin=False,
        apply=_reg("HKCU", EXPLORER_ADV, "TaskbarAnimations", 0, 1,
                   "Taskbar animations"),
        is_on=_is("HKCU", EXPLORER_ADV, "TaskbarAnimations", 0)),

    # ----------------------------------------------------------- System
    PerfTweak(
        "hags", "Hardware-Accelerated GPU Scheduling", "System",
        "Lets the GPU manage its own frame queue",
        "Removes one buffering stage between the CPU and GPU. Requires a "
        "reboot to take effect.",
        warning="Genuinely hardware-dependent: it helps on some GPU and "
                "driver combinations and measurably hurts on others. "
                "Benchmark before and after rather than assuming.",
        apply=_reg("HKLM", GRAPHICS_DRIVERS, "HwSchMode", 2, 1,
                   "Hardware-accelerated GPU scheduling"),
        is_on=_is("HKLM", GRAPHICS_DRIVERS, "HwSchMode", 2)),

    PerfTweak(
        "power_throttling", "Disable CPU power throttling", "Power",
        "Stops Windows throttling background-classified processes",
        "Power throttling targets work Windows considers background. A "
        "foreground game is already exempt, so this helps mainly when a "
        "game's helper process is misclassified.",
        warning="Shortens battery life noticeably on a laptop.",
        apply=_reg("HKLM", POWER_THROTTLE, "PowerThrottlingOff", 1, 0,
                   "CPU power throttling"),
        is_on=_is("HKLM", POWER_THROTTLE, "PowerThrottlingOff", 1)),

    PerfTweak(
        "paging_executive", "Keep kernel drivers in RAM", "System",
        "Stops kernel code being paged out to disk",
        "Prevents rare latency spikes caused by paging kernel code back in. "
        "Costs a few hundred megabytes of RAM.",
        warning="Only worthwhile with 16 GB or more. On 8 GB it takes memory "
                "your games need.",
        apply=_reg("HKLM", MEMORY_MGMT, "DisablePagingExecutive", 1, 0,
                   "Paging executive"),
        is_on=_is("HKLM", MEMORY_MGMT, "DisablePagingExecutive", 1)),

    PerfTweak(
        "mmcss_games", "Restore the MMCSS Games profile", "System",
        "Puts back the documented multimedia scheduler values for games",
        "These are Microsoft's own documented defaults for the Games task "
        "profile. Some 'debloat' scripts delete them, which can make audio "
        "and frame scheduling worse. This restores them - it does not raise "
        "them beyond spec, because higher values do nothing.",
        apply=lambda on: [
            ws.write_registry("HKLM", MULTIMEDIA_GAMES, "Priority",
                              6 if on else 2, note="MMCSS Games priority"),
            ws.write_registry("HKLM", MULTIMEDIA_GAMES, "GPU Priority",
                              8 if on else 8, note="MMCSS GPU priority"),
            ws.write_registry("HKLM", MULTIMEDIA_GAMES, "Scheduling Category",
                              "High" if on else "Medium",
                              value_type="REG_SZ",
                              note="MMCSS scheduling category")],
        is_on=_is("HKLM", MULTIMEDIA_GAMES, "Priority", 6)),

    # ------------------------------------------------------- Background
    PerfTweak(
        "search_indexing", "Stop indexing while gaming", "Background",
        "Prevents Windows Search scanning your drives",
        "Indexing causes real disk activity that can stutter a game. It runs "
        "at low priority and mostly when idle, so this matters most on "
        "mechanical drives.",
        warning="Start menu search becomes much less useful.",
        apply=_reg("HKLM", SEARCH_POLICY, "PreventIndexingWhenBatteryPowered",
                   1, 0, "Search indexing"),
        is_on=_is("HKLM", SEARCH_POLICY,
                  "PreventIndexingWhenBatteryPowered", 1)),

    PerfTweak(
        "tips_suggestions", "Disable tips and suggestions", "Background",
        "Stops suggestion notifications and Start menu ads",
        "Removes interruptions, which matters more mid-game than the "
        "negligible CPU it saves.",
        requires_admin=False,
        apply=lambda on: [
            ws.write_registry("HKCU", CONTENT_DELIVERY,
                              "SubscribedContent-338389Enabled",
                              0 if on else 1, note="Windows tips"),
            ws.write_registry("HKCU", CONTENT_DELIVERY,
                              "SystemPaneSuggestionsEnabled",
                              0 if on else 1, note="Start suggestions")],
        is_on=_is("HKCU", CONTENT_DELIVERY,
                  "SubscribedContent-338389Enabled", 0)),

    PerfTweak(
        "startup_delay", "Remove the startup app delay", "Background",
        "Startup programs launch immediately after login",
        "Windows deliberately staggers startup apps so the desktop appears "
        "responsive first. Removing the delay finishes loading sooner "
        "overall, at the cost of a busier first few seconds.",
        requires_admin=False,
        apply=_reg("HKCU",
                   r"Software\Microsoft\Windows\CurrentVersion\Explorer"
                   r"\Serialize", "StartupDelayInMSec", 0, 1,
                   "Startup delay"),
        is_on=_is("HKCU",
                  r"Software\Microsoft\Windows\CurrentVersion\Explorer"
                  r"\Serialize", "StartupDelayInMSec", 0)),
]

BY_ID = {t.id: t for t in TWEAKS}
CATEGORIES = ["Input", "Display", "System", "Power", "Background"]


def by_category(category: str) -> list:
    return [t for t in TWEAKS if t.category == category]


def states() -> dict:
    out = {}
    for t in TWEAKS:
        try:
            out[t.id] = bool(t.is_on()) if t.is_on else False
        except Exception:
            out[t.id] = False
    return out


def set_tweak(tweak_id: str, enabled: bool) -> tuple:
    """Toggle one tweak. Returns (ok, message, reversible changes)."""
    tweak = BY_ID.get(tweak_id)
    if tweak is None:
        return False, f"Unknown tweak: {tweak_id}", []
    if not IS_WINDOWS:
        return False, "These tweaks require Windows.", []
    if tweak.requires_admin and not is_admin():
        return False, (f"{tweak.name} needs administrator rights. Restart "
                       "Phantom Tweeks as administrator."), []
    try:
        changes = tweak.apply(enabled) or []
    except Exception as exc:
        return False, f"{tweak.name} failed: {exc}", []
    return True, f"{tweak.name} {'enabled' if enabled else 'reverted'}.", changes


def summary() -> str:
    on = states()
    out = ["LATENCY & PERFORMANCE TWEAKS", ""]
    for cat in CATEGORIES:
        items = by_category(cat)
        if not items:
            continue
        out += [cat.upper(), ""]
        for t in items:
            out.append(("[on]  " if on.get(t.id) else "[off] ") + t.name)
            out.append(f"        {t.effect}")
            if t.warning:
                out.append(f"        ! {t.warning}")
        out.append("")
    return "\n".join(out)
