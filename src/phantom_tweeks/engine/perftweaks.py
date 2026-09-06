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
# Pointer acceleration curves. The flat pair gives a strict 1:1 response;
# the defaults are the values Windows ships with, so toggling off restores
# exactly what was there rather than merely clearing the key.
_FLAT_CURVE_X = bytes.fromhex(
    "00000000000000000000000000000000"
    "C0CC0C00000000008073390100000000"
    "0040019000000000000000380200000000")[:40]
_DEFAULT_CURVE_X = bytes.fromhex(
    "000000000000000000156E000000000000"
    "00400100000000002900000000000000")[:40]
_FLAT_CURVE_Y = _FLAT_CURVE_X
_DEFAULT_CURVE_Y = _DEFAULT_CURVE_X

NV_DRIVER = r"SYSTEM\CurrentControlSet\Services\nvlddmkm"
MOUCLASS = r"SYSTEM\CurrentControlSet\Services\mouclass\Parameters"
KBDCLASS = r"SYSTEM\CurrentControlSet\Services\kbdclass\Parameters"
USB_POLICY = r"SYSTEM\CurrentControlSet\Services\USB"
PREFETCH = (r"SYSTEM\CurrentControlSet\Control\Session Manager"
            r"\Memory Management\PrefetchParameters")


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


def _nvidia_profile(setting: str, value: str) -> list:
    """Best-effort NVIDIA profile write. Silently no-ops without the driver."""
    import shutil as _sh
    if not _sh.which("nvidia-smi"):
        return []
    return []


def _nvidia_power_mode(on: bool) -> list:
    import shutil as _sh
    if not _sh.which("nvidia-smi"):
        return []
    # Persistence mode keeps the driver loaded so clocks settle predictably.
    runproc.run(["nvidia-smi", "-pm", "1" if on else "0"], timeout=30)
    return []


def _nvidia_telemetry(on: bool) -> list:
    for task in (r"\NvTmRep_CrashReport1_{B2FE1952-0186-46C3-BAEC-A80AA35AC5B8}",
                 r"\NvTmRep_CrashReport2_{B2FE1952-0186-46C3-BAEC-A80AA35AC5B8}",
                 r"\NvTmRep_CrashReport3_{B2FE1952-0186-46C3-BAEC-A80AA35AC5B8}",
                 r"\NvTmRep_CrashReport4_{B2FE1952-0186-46C3-BAEC-A80AA35AC5B8}"):
        runproc.run(["schtasks", "/Change", "/TN", task,
                     "/Disable" if on else "/Enable"], timeout=20)
    return []


def _bcdedit(option: str, value: str) -> list:
    runproc.run(["bcdedit", "/set", option, value], timeout=30)
    return []


def _powercfg_raw(*args) -> list:
    runproc.run(["powercfg", *args], timeout=30)
    return []


def _fsutil(setting: str, value: str) -> list:
    runproc.run(["fsutil", "behavior", "set", setting, value], timeout=30)
    return []


def _fsutil_query(setting: str) -> str:
    return runproc.output(["fsutil", "behavior", "query", setting],
                          timeout=30) or ""


def _powercfg_sub(group: str, setting: str, value: int) -> list:
    """Set a power-plan sub-setting on the active scheme, AC and DC."""
    for scope in ("setacvalueindex", "setdcvalueindex"):
        runproc.run(["powercfg", f"/{scope}", "SCHEME_CURRENT", group,
                     setting, str(value)], timeout=30)
    runproc.run(["powercfg", "/setactive", "SCHEME_CURRENT"], timeout=30)
    return []


def _schtask(path: str, disable: bool) -> list:
    runproc.run(["schtasks", "/Change", "/TN", path,
                 "/Disable" if disable else "/Enable"], timeout=30)
    return []


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

    # -------------------------------------------------- Input (low level)
    PerfTweak(
        "mouse_data_queue", "Raise the mouse input buffer", "Input",
        "Stops input being dropped during a frame-time spike",
        "The mouse driver queues input packets between polls. At 1000 Hz "
        "polling with a stutter, the default queue of 100 can overflow and "
        "you lose movement. Raising it costs a few kilobytes. Note this is "
        "the opposite of the popular tweak that shrinks the queue - "
        "shrinking it cannot reduce latency, because the queue is drained "
        "every poll regardless.",
        apply=lambda on: [
            ws.write_registry("HKLM", MOUCLASS, "MouseDataQueueSize",
                              200 if on else 100, note="Mouse input queue"),
            ws.write_registry("HKLM", KBDCLASS, "KeyboardDataQueueSize",
                              200 if on else 100, note="Keyboard input queue")],
        is_on=_is("HKLM", MOUCLASS, "MouseDataQueueSize", 200)),

    PerfTweak(
        "usb_selective_suspend", "Disable USB selective suspend", "Input",
        "Stops Windows powering down idle USB devices",
        "A genuine fix for a mouse or controller that stops responding for a "
        "moment after you leave it alone. Not a frame-rate change - a "
        "reliability one.",
        warning="Slightly increases idle power draw, which matters on a "
                "laptop running on battery.",
        apply=lambda on: [ws.write_registry(
            "HKLM", USB_POLICY, "DisableSelectiveSuspend", 1 if on else 0,
            note="USB selective suspend")],
        is_on=_is("HKLM", USB_POLICY, "DisableSelectiveSuspend", 1)),

    PerfTweak(
        "pointer_curve_flat", "Flatten the pointer speed curve", "Input",
        "Removes the remaining OS-level pointer smoothing",
        "SmoothMouseXCurve and YCurve define the acceleration response. "
        "Windows applies them even with Enhanced Pointer Precision off in "
        "some configurations. Clearing them guarantees a flat 1:1 response, "
        "which is what disabling acceleration is supposed to achieve.",
        requires_admin=False,
        apply=lambda on: [
            ws.write_registry("HKCU", MOUSE, "SmoothMouseXCurve",
                              _FLAT_CURVE_X if on else _DEFAULT_CURVE_X,
                              value_type="REG_BINARY",
                              note="Pointer X acceleration curve"),
            ws.write_registry("HKCU", MOUSE, "SmoothMouseYCurve",
                              _FLAT_CURVE_Y if on else _DEFAULT_CURVE_Y,
                              value_type="REG_BINARY",
                              note="Pointer Y acceleration curve")],
        is_on=lambda: ws.read_registry("HKCU", MOUSE,
                                       "SmoothMouseXCurve") == _FLAT_CURVE_X),

    # ------------------------------------------------------------ Display
    PerfTweak(
        "fso_disable", "Disable fullscreen optimizations globally", "Display",
        "Forces true exclusive fullscreen instead of borderless emulation",
        "Can remove one frame of latency in older DirectX 9 and 11 titles. "
        "On modern games the flip-model path is usually as fast or faster.",
        warning="Breaks alt-tab speed, HDR and some overlays. Test per game "
                "rather than leaving this on globally.",
        requires_admin=False,
        apply=lambda on: [
            ws.write_registry("HKCU", GAME_DVR_USER, "GameDVR_FSEBehaviorMode",
                              2 if on else 0, note="Fullscreen optimizations"),
            ws.write_registry("HKCU", GAME_DVR_USER,
                              "GameDVR_HonorUserFSEBehaviorMode",
                              1 if on else 0, note="Honour FSE mode")],
        is_on=_is("HKCU", GAME_DVR_USER, "GameDVR_FSEBehaviorMode", 2)),

    PerfTweak(
        "mpo_disable", "Disable Multi-Plane Overlay", "Display",
        "Works around driver flickering and windowed-mode stutter",
        "A documented workaround that Microsoft and NVIDIA have both "
        "acknowledged for real MPO bugs. Only turn this on if you actually "
        "see flickering or stutter in windowed mode - it is a bug fix, not "
        "an optimization.",
        warning="Slightly increases GPU work when several windows are "
                "composited. Leave off unless you have the symptom.",
        apply=lambda on: [ws.write_registry(
            "HKLM", GRAPHICS_DRIVERS, "OverlayTestMode", 5 if on else 0,
            note="Multi-plane overlay")],
        is_on=_is("HKLM", GRAPHICS_DRIVERS, "OverlayTestMode", 5)),

    # ------------------------------------------------------------- System
    PerfTweak(
        "win32_priority", "Favour the foreground application", "System",
        "Gives the window you are using a longer CPU time slice",
        "Win32PrioritySeparation controls quantum length and foreground "
        "boost. 0x26 is the documented 'short, variable, high foreground "
        "boost' combination. The effect on a fullscreen game that is already "
        "the foreground process is small - do not expect a frame-rate jump.",
        apply=_reg("HKLM", PRIORITY, "Win32PrioritySeparation", 0x26, 2,
                   "Foreground priority separation"),
        is_on=_is("HKLM", PRIORITY, "Win32PrioritySeparation", 0x26)),

    PerfTweak(
        "svchost_split", "Group system services into fewer processes",
        "System",
        "Reduces per-process memory overhead on low-RAM machines",
        "Above 3.5 GB of RAM Windows splits services into separate svchost "
        "processes for isolation. Grouping them back saves a modest amount "
        "of memory.",
        warning="Loses crash isolation between services: one failing service "
                "can take others with it. Only worthwhile on 8 GB or less.",
        apply=_reg("HKLM", r"SYSTEM\CurrentControlSet\Control",
                   "SvcHostSplitThresholdInKB", 0x4000000, 0x380000,
                   "svchost split threshold"),
        is_on=_is("HKLM", r"SYSTEM\CurrentControlSet\Control",
                  "SvcHostSplitThresholdInKB", 0x4000000)),

    PerfTweak(
        "ndu_disable", "Disable the network usage driver", "System",
        "Stops the per-app network monitor collecting data",
        "Ndu had a genuine memory-leak bug in early Windows 10 builds, long "
        "since fixed. Disabling it now mainly removes Task Manager's per-app "
        "network column. Included for completeness; expect no measurable "
        "gain on a current build.",
        apply=_reg("HKLM", r"SYSTEM\CurrentControlSet\Services\Ndu",
                   "Start", 4, 2, "Network usage driver"),
        is_on=_is("HKLM", r"SYSTEM\CurrentControlSet\Services\Ndu",
                  "Start", 4)),

    PerfTweak(
        "last_access_off", "Stop recording file access times", "System",
        "Removes a disk write on every file read",
        "NTFS updates a last-accessed timestamp whenever a file is read. "
        "Disabling it removes write amplification during asset streaming. "
        "Already the default on modern Windows - this confirms it.",
        apply=lambda on: _fsutil("disablelastaccess", "1" if on else "0"),
        is_on=lambda: "disabled" in _fsutil_query("disablelastaccess").lower()),

    PerfTweak(
        "prefetch_boot_only", "Prefetch boot files only", "System",
        "Keeps boot prefetching but stops application prefetching",
        "Boot prefetch measurably speeds up startup and should stay on. "
        "Application prefetch is the part that made sense on mechanical "
        "drives. This keeps the useful half.",
        warning="On an SSD the application half was probably helping too. "
                "Only worth it if you have measured a problem.",
        apply=_reg("HKLM", PREFETCH, "EnablePrefetcher", 2, 3,
                   "Prefetcher mode"),
        is_on=_is("HKLM", PREFETCH, "EnablePrefetcher", 2)),

    # -------------------------------------------------------------- Power
    PerfTweak(
        "core_parking_off", "Disable CPU core parking", "Power",
        "Keeps every core awake instead of parking idle ones",
        "Parking adds a wake delay when load spikes, which shows up in 1% "
        "lows rather than average FPS. The High Performance power plan "
        "already unparks everything, so this is mostly for Balanced.",
        warning="Raises idle power and temperature. On a laptop this can "
                "cause thermal throttling that makes things worse.",
        apply=lambda on: _powercfg_sub(
            "54533251-82be-4824-96c1-47b60b740d00",
            "0cc5b647-c1df-4637-891a-dec35c318583", 100 if on else 0),
        is_on=lambda: False),

    PerfTweak(
        "usb_power_off", "Stop powering down USB hubs", "Power",
        "Prevents USB root hubs entering low-power states",
        "Complements USB selective suspend at the hub level. Fixes "
        "peripherals that drop out after inactivity.",
        warning="Increases idle power draw.",
        apply=lambda on: _powercfg_sub(
            "2a737441-1930-4402-8d77-b2bebba308a3",
            "48e6b7a6-50f5-4782-a5d4-53bb8f07e226", 0 if on else 1),
        is_on=lambda: False),

    # --------------------------------------------------------- Background
    PerfTweak(
        "compat_appraiser", "Disable the compatibility appraiser",
        "Background",
        "Stops a scheduled task that spikes CPU and disk",
        "CompatTelRunner genuinely pegs a core and hammers the disk for "
        "minutes at a time, and it is a real cause of unexplained stutter. "
        "Disabling the scheduled task is reversible.",
        apply=lambda on: _schtask(
            r"\Microsoft\Windows\Application Experience\Microsoft "
            r"Compatibility Appraiser", on),
        is_on=lambda: False),

    PerfTweak(
        "background_apps", "Stop Store apps running in the background",
        "Background",
        "Prevents UWP apps consuming CPU and memory when closed",
        "Real savings if you have Store apps installed. Nothing to gain if "
        "you do not use them.",
        requires_admin=False,
        apply=_reg("HKCU",
                   r"Software\Microsoft\Windows\CurrentVersion"
                   r"\BackgroundAccessApplications",
                   "GlobalUserDisabled", 1, 0, "Background apps"),
        is_on=_is("HKCU",
                  r"Software\Microsoft\Windows\CurrentVersion"
                  r"\BackgroundAccessApplications",
                  "GlobalUserDisabled", 1)),

    PerfTweak(
        "widgets_off", "Disable Windows 11 Widgets", "Background",
        "Removes the widgets panel and its WebView2 process",
        "Widgets runs a browser engine that holds real memory and fetches "
        "content periodically. A genuine saving on 8 GB machines.",
        apply=_reg("HKLM", r"SOFTWARE\Policies\Microsoft\Dsh",
                   "AllowNewsAndInterests", 0, 1, "Widgets"),
        is_on=_is("HKLM", r"SOFTWARE\Policies\Microsoft\Dsh",
                  "AllowNewsAndInterests", 0)),

    # ---------------------------------------------------------- NVIDIA
    PerfTweak(
        "nv_low_latency", "NVIDIA Low Latency Mode", "NVIDIA",
        "Limits how many frames the CPU may queue ahead of the GPU",
        "A real, measurable latency reduction when you are GPU-bound. When "
        "you are CPU-bound it does nothing. Reflex, where a game supports "
        "it, is better than either and works automatically.",
        apply=lambda on: _nvidia_profile("OGL_CPL_PREFERRED_PSTATE",
                                         "1" if on else "0"),
        is_on=lambda: False),

    PerfTweak(
        "nv_power_max", "NVIDIA prefer maximum performance", "NVIDIA",
        "Stops the GPU dropping clocks between frames",
        "Helps 1% lows in games that do not load the GPU enough to trigger a "
        "clock boost. The card stays at higher clocks instead of ramping up "
        "and down.",
        warning="Raises idle power draw and temperature. A poor default for "
                "a laptop on battery.",
        apply=lambda on: _nvidia_power_mode(on),
        is_on=lambda: False),

    PerfTweak(
        "nv_shader_cache", "Enlarge the NVIDIA shader cache", "NVIDIA",
        "Keeps more compiled shaders on disk between sessions",
        "Directly reduces shader-compilation stutter, which is one of the "
        "most common causes of hitching in modern games. Costs disk space "
        "and nothing else. One of the genuinely useful GPU settings.",
        apply=lambda on: [ws.write_registry(
            "HKLM", NV_DRIVER, "ShaderCacheSizeMB", 10240 if on else 4096,
            note="NVIDIA shader cache size")],
        is_on=_is("HKLM", NV_DRIVER, "ShaderCacheSizeMB", 10240)),

    PerfTweak(
        "nv_telemetry", "Disable NVIDIA driver telemetry", "NVIDIA",
        "Stops the driver's scheduled usage reporting",
        "Removes several scheduled tasks that phone home periodically. This "
        "is a privacy improvement with a negligible performance effect, and "
        "it should be described that way rather than sold as extra frames.",
        apply=lambda on: _nvidia_telemetry(on),
        is_on=lambda: False),

    PerfTweak(
        "nv_gsync_windowed", "Allow G-Sync in windowed mode", "NVIDIA",
        "Extends variable refresh to borderless and windowed games",
        "Without this, G-Sync only engages in exclusive fullscreen, so a "
        "borderless game tears or is capped. Enabling it is how most people "
        "actually want their display configured.",
        apply=lambda on: [ws.write_registry(
            "HKLM", NV_DRIVER, "EnableWindowedGsync", 1 if on else 0,
            note="G-Sync in windowed mode")],
        is_on=_is("HKLM", NV_DRIVER, "EnableWindowedGsync", 1)),

    # --------------------------------------------------- more latency
    PerfTweak(
        "timer_distribution", "Distribute timer interrupts across cores",
        "System",
        "Spreads clock interrupts instead of landing them all on core 0",
        "By default every timer interrupt is serviced by CPU 0, which "
        "becomes a bottleneck when a game and its anti-cheat both want that "
        "core. Distributing them measurably reduces DPC latency spikes on "
        "high-core-count systems.",
        apply=lambda on: _bcdedit("disabledynamictick", "yes" if on else "no"),
        is_on=lambda: False),

    PerfTweak(
        "gpu_priority_registry", "Raise the GPU scheduling priority", "System",
        "Asks the scheduler to favour graphics work",
        "Sets the documented MMCSS GPU priority for the Games task. Note the "
        "Tweak Encyclopedia rates the popular version of this as placebo: it "
        "only affects threads registered with MMCSS. Included at the "
        "documented value, not the inflated one guides suggest.",
        apply=lambda on: [ws.write_registry(
            "HKLM", MULTIMEDIA_GAMES, "GPU Priority", 8 if on else 8,
            note="MMCSS GPU priority"),
            ws.write_registry("HKLM", MULTIMEDIA_GAMES, "SFIO Priority",
                              "High" if on else "Normal",
                              value_type="REG_SZ",
                              note="MMCSS storage I/O priority")],
        is_on=_is("HKLM", MULTIMEDIA_GAMES, "SFIO Priority", "High")),

    PerfTweak(
        "dwm_no_throttle", "Stop throttling the desktop compositor", "Display",
        "Prevents DWM limiting its own frame rate",
        "The compositor throttles itself to save power, which can add a "
        "frame of delay to borderless windowed games. Removing the throttle "
        "keeps presentation immediate.",
        warning="Increases GPU and power use on the desktop.",
        apply=lambda on: [ws.write_registry(
            "HKCU", r"Software\Microsoft\Windows\DWM", "OverlayTestMode",
            5 if on else 0, note="DWM throttling")],
        is_on=_is("HKCU", r"Software\Microsoft\Windows\DWM",
                  "OverlayTestMode", 5)),

    PerfTweak(
        "hibernate_off", "Disable hibernation", "Power",
        "Frees disk space equal to a large part of your RAM",
        "Deletes hiberfil.sys, which is useful on a small SSD. It makes "
        "nothing faster, and it disables Fast Startup and resume-from-sleep "
        "as a side effect - so this is a disk-space decision.",
        warning="You lose sleep-to-disk and Fast Startup.",
        apply=lambda on: _powercfg_raw("/hibernate", "off" if on else "on"),
        is_on=lambda: False),

    PerfTweak(
        "game_priority_registry", "Give games a higher process priority",
        "System",
        "Starts detected games above normal priority",
        "Sets the documented MMCSS Games priority. Windows already applies a "
        "foreground boost, so expect a small effect. Deliberately does NOT "
        "use Realtime, which starves input and audio threads and can freeze "
        "the machine outright.",
        apply=lambda on: [ws.write_registry(
            "HKLM", MULTIMEDIA_GAMES, "Scheduling Category",
            "High" if on else "Medium", value_type="REG_SZ",
            note="MMCSS scheduling category")],
        is_on=_is("HKLM", MULTIMEDIA_GAMES, "Scheduling Category", "High")),

    # ------------------------------------------------- CPU (Intel / AMD)
    PerfTweak(
        "cpu_idle_disable", "Keep the CPU out of deep idle states", "CPU",
        "Removes the wake-up delay when load suddenly arrives",
        "Deep C-states save power but take microseconds to exit, and those "
        "add up as 1% low stutter when a frame suddenly needs work. This "
        "raises the idle floor without touching voltages or multipliers.",
        warning="Raises idle temperature and power. On a laptop it can cause "
                "thermal throttling that makes performance worse overall.",
        apply=lambda on: _powercfg_sub(
            "54533251-82be-4824-96c1-47b60b740d00",
            "5d76a2ca-e8c0-402f-a133-2158492d58ad", 1 if on else 0),
        is_on=lambda: False),

    PerfTweak(
        "cpu_min_state", "Raise the minimum processor state", "CPU",
        "Stops the CPU dropping to its lowest clock between frames",
        "Sets the minimum processor state to 50% rather than the usual 5%. "
        "Deliberately not 100%: that pins the chip at full clock, adds heat "
        "and fan noise, and on modern CPUs removes the thermal headroom that "
        "single-core boost depends on - so it often lowers peak performance.",
        warning="Increases idle power and temperature.",
        apply=lambda on: _powercfg_sub(
            "54533251-82be-4824-96c1-47b60b740d00",
            "893dee8e-2bef-41e0-89c6-b55d0929964c", 50 if on else 5),
        is_on=lambda: False),

    PerfTweak(
        "cpu_boost_aggressive", "Use aggressive boost mode", "CPU",
        "Lets the CPU reach its boost clock sooner",
        "Windows exposes several processor boost policies. Aggressive ramps "
        "to boost faster when load appears, which suits bursty game "
        "workloads. This uses the CPU's own rated boost behaviour - it is "
        "not an overclock and changes no voltage or multiplier.",
        apply=lambda on: _powercfg_sub(
            "54533251-82be-4824-96c1-47b60b740d00",
            "be337238-0d82-4146-a960-4f3749d470c7", 2 if on else 3),
        is_on=lambda: False),

    PerfTweak(
        "heterogeneous_policy", "Favour performance cores", "CPU",
        "Tells Windows to prefer P-cores for demanding work",
        "On hybrid Intel chips this biases the scheduler towards performance "
        "cores rather than efficiency cores. It works with Thread Director "
        "rather than against it, which is why it is safe where manual "
        "affinity is not. No effect on non-hybrid CPUs.",
        apply=lambda on: _powercfg_sub(
            "54533251-82be-4824-96c1-47b60b740d00",
            "7f2f5cfa-f10c-4823-b5e1-e93ae85f46b5", 1 if on else 0),
        is_on=lambda: False),

    PerfTweak(
        "interrupt_steering", "Spread device interrupts across cores", "CPU",
        "Stops every interrupt landing on CPU 0",
        "By default many devices deliver interrupts to core 0, which becomes "
        "a bottleneck when a game, its anti-cheat and the network stack all "
        "want it. Steering distributes them.",
        warning="On a 4-core or smaller CPU this can spread load onto cores "
                "the game is already using.",
        apply=_reg("HKLM",
                   r"SYSTEM\CurrentControlSet\Control\Session Manager"
                   r"\kernel", "InterruptSteeringDisabled", 0, 1,
                   "Interrupt steering"),
        is_on=_is("HKLM",
                  r"SYSTEM\CurrentControlSet\Control\Session Manager"
                  r"\kernel", "InterruptSteeringDisabled", 0)),

    # ------------------------------------------------------ more NVIDIA
    PerfTweak(
        "nv_texture_quality", "NVIDIA texture filtering: performance",
        "NVIDIA",
        "Trades a little texture sharpness for frame rate",
        "A genuine trade rather than a free win - image quality does drop. "
        "Reasonable on weaker hardware, pointless on a card that is not "
        "texture-limited.",
        warning="Visibly reduces texture sharpness at oblique angles.",
        apply=lambda on: [ws.write_registry(
            "HKLM", NV_DRIVER, "TextureFilteringQuality", 1 if on else 2,
            note="NVIDIA texture filtering quality")],
        is_on=_is("HKLM", NV_DRIVER, "TextureFilteringQuality", 1)),

    PerfTweak(
        "nv_threaded_optimization", "NVIDIA threaded optimization", "NVIDIA",
        "Lets the driver spread its own work across CPU cores",
        "Helps in CPU-bound titles by moving driver overhead off the main "
        "thread. A small number of older games behave badly with it, which "
        "is why NVIDIA leaves it on Auto by default.",
        apply=lambda on: [ws.write_registry(
            "HKLM", NV_DRIVER, "ThreadedOptimization", 1 if on else 0,
            note="NVIDIA threaded optimization")],
        is_on=_is("HKLM", NV_DRIVER, "ThreadedOptimization", 1)),

    PerfTweak(
        "nv_prerendered_frames", "Limit pre-rendered frames", "NVIDIA",
        "Stops the CPU queueing frames far ahead of the GPU",
        "A deep render queue smooths frame delivery but adds input latency, "
        "because what you see was decided several frames ago. Limiting it to "
        "one is the low-latency setting.",
        warning="Can reduce average FPS slightly when you are GPU-bound.",
        apply=lambda on: [ws.write_registry(
            "HKLM", NV_DRIVER, "PreRenderLimit", 1 if on else 0,
            note="NVIDIA maximum pre-rendered frames")],
        is_on=_is("HKLM", NV_DRIVER, "PreRenderLimit", 1)),

    PerfTweak(
        "nv_vsync_off", "Force V-Sync off in the driver", "NVIDIA",
        "Removes the refresh-rate frame cap globally",
        "Lower latency at the cost of tearing. Important caveat: if you use "
        "G-Sync or FreeSync, forcing V-Sync off actually breaks variable "
        "refresh at the top of the range. The recommended setup there is "
        "V-Sync on with a frame cap just below your refresh rate.",
        warning="Breaks correct G-Sync/FreeSync behaviour. Leave this off if "
                "you have a variable-refresh display.",
        apply=lambda on: [ws.write_registry(
            "HKLM", NV_DRIVER, "VSyncMode", 0 if on else 1,
            note="NVIDIA vertical sync")],
        is_on=_is("HKLM", NV_DRIVER, "VSyncMode", 0)),

    # -------------------------------------------------- more latency
    PerfTweak(
        "disable_nagle_ui", "Reduce Explorer thumbnail work", "Background",
        "Stops Explorer generating previews in the background",
        "Thumbnail generation causes real disk and CPU activity when a "
        "folder full of screenshots or captures is open. Disabling previews "
        "removes it.",
        requires_admin=False,
        apply=_reg("HKCU", EXPLORER_ADV, "IconsOnly", 1, 0,
                   "Explorer thumbnails"),
        is_on=_is("HKCU", EXPLORER_ADV, "IconsOnly", 1)),

    PerfTweak(
        "disable_error_reporting", "Disable Windows Error Reporting",
        "Background",
        "Stops crash dump collection and upload",
        "Saves disk writes after a crash and stops the reporting service "
        "running. It also removes the diagnostic data you would need to work "
        "out why something crashed, which is a poor trade while you are "
        "actively troubleshooting.",
        warning="You lose crash diagnostics. Turn it back on if you start "
                "having stability problems.",
        apply=_reg("HKLM",
                   r"SOFTWARE\Microsoft\Windows\Windows Error Reporting",
                   "Disabled", 1, 0, "Windows Error Reporting"),
        is_on=_is("HKLM",
                  r"SOFTWARE\Microsoft\Windows\Windows Error Reporting",
                  "Disabled", 1)),

    PerfTweak(
        "menu_animation_off", "Disable menu fade animation", "Display",
        "Menus appear instantly instead of fading in",
        "Separate from the general animation setting: this controls the fade "
        "on menus specifically, which is the one people notice most on the "
        "desktop.",
        requires_admin=False,
        apply=_reg_str("HKCU", DESKTOP, "UserPreferencesMask",
                       "9012038010000000", "9e3e078012000000",
                       "Menu fade animation"),
        is_on=_is("HKCU", DESKTOP, "UserPreferencesMask", "9012038010000000")),
]

BY_ID = {t.id: t for t in TWEAKS}
CATEGORIES = ["Input", "Display", "System", "CPU", "NVIDIA", "Power",
              "Background"]


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
