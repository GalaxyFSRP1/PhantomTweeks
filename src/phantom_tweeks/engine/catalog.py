"""The optimization catalog.

Each entry carries a technical justification, an evaluator that inspects the
*actual* machine, and a confidence rating. An evaluator returning NOT_RECOMMENDED
("No change recommended.") is a correct, valuable outcome — not a failure.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from .backup import ABSENT
from . import winsettings as ws


class Confidence(str, Enum):
    HIGH = "HIGH CONFIDENCE"
    MEDIUM = "MEDIUM CONFIDENCE"
    LOW = "LOW CONFIDENCE"
    NOT_RECOMMENDED = "NOT RECOMMENDED"

    @property
    def blurb(self) -> str:
        return {
            "HIGH CONFIDENCE": "Likely beneficial for this configuration.",
            "MEDIUM CONFIDENCE": "May help depending on workload.",
            "LOW CONFIDENCE": "Limited evidence.",
            "NOT RECOMMENDED": "No meaningful benefit expected.",
        }[self.value]


class Category(str, Enum):
    SAFE = "Safe"
    RECOMMENDED = "Recommended"
    OPTIONAL = "Optional"
    ADVANCED = "Advanced"
    NOT_RECOMMENDED = "Not recommended"


class Risk(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


@dataclass
class Evaluation:
    """The result of inspecting the live system for one optimization."""
    applicable: bool
    confidence: Confidence
    reason: str
    current_value: object = None
    already_optimal: bool = False


@dataclass
class Optimization:
    id: str
    title: str
    area: str                       # Windows / Graphics / Power / Storage / Network
    purpose: str                    # the "why" — shown in the info button
    expected_effect: str
    risk: Risk
    supported: str
    reversible: bool
    category: Category
    evaluate: Callable[[dict], Evaluation]
    apply: Optional[Callable[[dict], list]] = None   # -> list[ChangeRecord]
    learn_more: str = ""
    requires_admin: bool = False
    advanced: bool = False

    def info_card(self) -> str:
        return (
            f"{self.title}\n\n"
            f"Purpose:\n{self.purpose}\n\n"
            f"Expected effect:\n{self.expected_effect}\n\n"
            f"Risk:\n{self.risk.value}\n\n"
            f"Supported:\n{self.supported}\n\n"
            f"Reversible:\n{'Yes' if self.reversible else 'No'}\n"
        )


# ------------------------------------------------------------------
# Registry locations we manage
# ------------------------------------------------------------------
GAMEBAR = r"Software\Microsoft\GameBar"
GAME_DVR_USER = r"System\GameConfigStore"
GRAPHICS_PREFS = r"Software\Microsoft\DirectX\UserGpuPreferences"
GRAPHICS_DRIVERS = r"System\CurrentControlSet\Control\GraphicsDrivers"
VISUAL_FX = r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects"
DESKTOP = r"Control Panel\Desktop"
MOUSE = r"Control Panel\Mouse"
MMCSS_SYSTEM = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
MMCSS_GAMES = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games"
SEARCH = r"SOFTWARE\Microsoft\Windows Search"
NDU = r"SYSTEM\CurrentControlSet\Services\Ndu"
STORAGE_SENSE = r"SOFTWARE\Microsoft\Windows\CurrentVersion\StorageSense\Parameters\StoragePolicy"

POWER_HIGH_PERF = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
POWER_BALANCED = "381b4222-f694-41f0-9685-ff5bb260df2e"


# ------------------------------------------------------------------
# Evaluators — each inspects real state passed in `ctx`
# ------------------------------------------------------------------

def _eval_game_mode(ctx: dict) -> Evaluation:
    current = ws.read_registry("HKCU", GAMEBAR, "AutoGameModeEnabled")
    if current == 1:
        return Evaluation(False, Confidence.NOT_RECOMMENDED,
                          "Game Mode is already enabled. No change recommended.",
                          current, already_optimal=True)
    if current == ABSENT:
        return Evaluation(True, Confidence.MEDIUM,
                          "Game Mode has no explicit setting on this system. Windows "
                          "usually defaults it on; setting it explicitly makes the "
                          "state deterministic.", current)
    return Evaluation(True, Confidence.HIGH,
                      "Game Mode is disabled. It lets Windows deprioritise background "
                      "scheduling and deferrable work while a game is in the "
                      "foreground, which mainly improves frame-time consistency.",
                      current)


def _eval_hags(ctx: dict) -> Evaluation:
    current = ws.read_registry("HKLM", GRAPHICS_DRIVERS, "HwSchMode")
    supported = ctx.get("hags_supported")
    if supported is False:
        return Evaluation(False, Confidence.NOT_RECOMMENDED,
                          "Hardware-accelerated GPU scheduling is not supported by "
                          "this GPU/driver combination. No change recommended.",
                          current)
    if current == 2:
        return Evaluation(False, Confidence.NOT_RECOMMENDED,
                          "HAGS is already enabled. No change recommended.",
                          current, already_optimal=True)
    return Evaluation(True, Confidence.MEDIUM,
                      "HAGS moves frame queue management to the GPU scheduler. Effects "
                      "vary by title and driver: some see marginally lower latency, "
                      "others see none. Requires a reboot and is fully reversible.",
                      current)


def _eval_gpu_preference(ctx: dict) -> Evaluation:
    game = ctx.get("game")
    if not game or not game.get("executable_path"):
        return Evaluation(False, Confidence.NOT_RECOMMENDED,
                          "No game executable detected, so there is nothing to assign "
                          "a GPU preference to. No change recommended.")
    if ctx.get("gpu_count", 1) < 2:
        return Evaluation(False, Confidence.NOT_RECOMMENDED,
                          "Only one GPU is present. A high-performance GPU preference "
                          "has no effect on single-GPU systems. No change recommended.")
    path = game["executable_path"]
    current = ws.read_registry("HKCU", GRAPHICS_PREFS, path)
    if current != ABSENT and "GpuPreference=2" in str(current):
        return Evaluation(False, Confidence.NOT_RECOMMENDED,
                          "This game is already assigned to the high-performance GPU.",
                          current, already_optimal=True)
    return Evaluation(True, Confidence.HIGH,
                      "This system has multiple GPUs. Pinning the game to the discrete "
                      "GPU prevents Windows from running it on the integrated adapter.",
                      current)


def _eval_power_plan(ctx: dict) -> Evaluation:
    plan = (ctx.get("power_plan") or "").lower()
    is_laptop = ctx.get("is_laptop", False)
    if "high performance" in plan or "ultimate" in plan:
        return Evaluation(False, Confidence.NOT_RECOMMENDED,
                          "An unrestricted power plan is already active. No change "
                          "recommended.", plan, already_optimal=True)
    if is_laptop:
        return Evaluation(True, Confidence.LOW,
                          "This appears to be a laptop. High Performance raises minimum "
                          "core clocks, which increases heat and can cause thermal "
                          "throttling that lowers sustained FPS. Consider leaving "
                          "Balanced while on battery.", plan)
    if "balanced" in plan:
        return Evaluation(True, Confidence.MEDIUM,
                          "The Balanced plan parks cores and ramps clocks reactively, "
                          "which can add latency to bursty game threads. On a desktop "
                          "with adequate cooling, High Performance removes that ramp.",
                          plan)
    return Evaluation(True, Confidence.LOW,
                      "A non-standard power plan is active. Review it manually.", plan)


def _eval_visual_effects(ctx: dict) -> Evaluation:
    ram = ctx.get("ram_gb") or 0
    gpu_util = ctx.get("gpu_utilization")
    if ram >= 16 and (gpu_util is None or gpu_util < 90):
        return Evaluation(False, Confidence.NOT_RECOMMENDED,
                          f"This system has {ram:.0f} GB RAM and is not desktop-"
                          "composition constrained. Disabling animations will not "
                          "measurably change in-game FPS. No change recommended.")
    return Evaluation(True, Confidence.LOW,
                      "On low-memory systems, reducing desktop animations frees a small "
                      "amount of GPU and memory overhead. The effect on in-game FPS is "
                      "usually negligible; it mainly makes the desktop feel snappier.")


def _eval_gamedvr(ctx: dict) -> Evaluation:
    current = ws.read_registry("HKCU", GAME_DVR_USER, "GameDVR_Enabled")
    if ctx.get("recording_active"):
        return Evaluation(False, Confidence.NOT_RECOMMENDED,
                          "A capture application is currently active. Phantom Tweeks "
                          "will not disable background recording while you are "
                          "recording. No change recommended.")
    if current == 0:
        return Evaluation(False, Confidence.NOT_RECOMMENDED,
                          "Background recording is already off.", current,
                          already_optimal=True)
    return Evaluation(True, Confidence.MEDIUM,
                      "Xbox Game DVR background recording continuously encodes "
                      "gameplay, consuming GPU encoder time and adding frame-time "
                      "variance. Disabling it is reversible and does not affect "
                      "manual capture via OBS.", current)


def _eval_storage_cleanup(ctx: dict) -> Evaluation:
    free_pct = ctx.get("system_disk_free_pct")
    if free_pct is None:
        return Evaluation(False, Confidence.LOW, "Disk usage could not be read.")
    if free_pct > 15:
        return Evaluation(False, Confidence.NOT_RECOMMENDED,
                          f"The system drive has {free_pct:.0f}% free. Cleanup will not "
                          "improve performance. No change recommended.",
                          already_optimal=True)
    return Evaluation(True, Confidence.HIGH,
                      f"The system drive has only {free_pct:.0f}% free. SSDs lose write "
                      "performance and Windows loses paging headroom below ~10-15% free "
                      "space. Phantom Tweeks will list what can be safely removed but "
                      "will never delete personal files.")




def _eval_mouse_accel(ctx: dict) -> Evaluation:
    """Pointer acceleration breaks muscle memory in aim-based games."""
    speed = ws.read_registry("HKCU", MOUSE, "MouseSpeed")
    if speed == ABSENT:
        return Evaluation(False, Confidence.LOW,
                          "Pointer precision settings could not be read.")
    if str(speed) == "0":
        return Evaluation(False, Confidence.NOT_RECOMMENDED,
                          "Enhance Pointer Precision is already off. No change "
                          "recommended.", speed, already_optimal=True)
    return Evaluation(True, Confidence.HIGH,
                      "'Enhance pointer precision' applies non-linear acceleration to "
                      "mouse input, so the same physical movement produces different "
                      "cursor distances depending on speed. For aim-based games this "
                      "prevents consistent muscle memory. Disabling it is the standard "
                      "competitive configuration and is instantly reversible.", speed)


def _eval_mmcss_games(ctx: dict) -> Evaluation:
    """MMCSS governs how much CPU the multimedia scheduler reserves."""
    priority = ws.read_registry("HKLM", MMCSS_GAMES, "Priority")
    gpu_prio = ws.read_registry("HKLM", MMCSS_GAMES, "GPU Priority")
    if priority == 6 and gpu_prio == 8:
        return Evaluation(False, Confidence.NOT_RECOMMENDED,
                          "The MMCSS Games task profile is already at its standard "
                          "gaming values. No change recommended.", priority,
                          already_optimal=True)
    if priority == ABSENT:
        return Evaluation(False, Confidence.NOT_RECOMMENDED,
                          "The MMCSS Games profile does not exist on this system. "
                          "Phantom Tweeks will not create scheduler entries that "
                          "Windows did not define. No change recommended.")
    return Evaluation(True, Confidence.LOW,
                      "The Multimedia Class Scheduler's Games profile controls the CPU "
                      "share reserved for games registered with it. Values differing "
                      "from the Windows defaults (Priority 6, GPU Priority 8) can cause "
                      "scheduling anomalies. This restores the documented defaults; it "
                      "is not an overclock and rarely changes FPS.", priority)


def _eval_search_indexing(ctx: dict) -> Evaluation:
    free = ctx.get("system_disk_free_pct")
    media = ctx.get("system_disk_media")
    if media and "HDD" not in str(media):
        return Evaluation(False, Confidence.NOT_RECOMMENDED,
                          f"Your system drive is a {media}. Search indexing has "
                          "negligible impact on SSD performance and disabling it "
                          "breaks Start menu search. No change recommended.")
    if media is None:
        return Evaluation(False, Confidence.LOW,
                          "Drive type could not be determined, so the tradeoff cannot "
                          "be assessed. No change recommended.")
    return Evaluation(True, Confidence.MEDIUM,
                      "Your system drive is a mechanical hard disk. Search indexing "
                      "causes seek contention on HDDs that can stutter game loading. "
                      "Note this degrades Start menu search quality — a real tradeoff, "
                      "not a free win.")


def _eval_network_throttling(ctx: dict) -> Evaluation:
    """NetworkThrottlingIndex limits non-multimedia packets per second."""
    current = ws.read_registry("HKLM", MMCSS_SYSTEM, "NetworkThrottlingIndex")
    if current == 0xFFFFFFFF:
        return Evaluation(False, Confidence.NOT_RECOMMENDED,
                          "Network throttling is already disabled.", current,
                          already_optimal=True)
    if current == ABSENT:
        return Evaluation(False, Confidence.NOT_RECOMMENDED,
                          "This system has no network throttling override, which means "
                          "Windows is using its default behaviour. The default only "
                          "throttles non-multimedia traffic to 10 packets/ms and is "
                          "rarely the cause of game latency. No change recommended.")
    return Evaluation(True, Confidence.LOW,
                      "NetworkThrottlingIndex caps non-multimedia network processing to "
                      "reserve CPU for audio/video. On modern multi-core CPUs this "
                      "reservation is unnecessary. Evidence of an FPS or ping benefit is "
                      "weak — this mainly matters on very high packet-rate workloads.",
                      current)


def _eval_storage_sense(ctx: dict) -> Evaluation:
    free = ctx.get("system_disk_free_pct")
    enabled = ws.read_registry("HKCU", STORAGE_SENSE, "01")
    if free is None:
        return Evaluation(False, Confidence.LOW, "Disk usage could not be read.")
    if enabled == 1:
        return Evaluation(False, Confidence.NOT_RECOMMENDED,
                          "Storage Sense is already enabled and will reclaim temporary "
                          "files automatically. No change recommended.", enabled,
                          already_optimal=True)
    if free > 25:
        return Evaluation(False, Confidence.NOT_RECOMMENDED,
                          f"The system drive has {free:.0f}% free. Automatic cleanup is "
                          "unnecessary right now. No change recommended.")
    return Evaluation(True, Confidence.MEDIUM,
                      f"The system drive has {free:.0f}% free. Storage Sense is a "
                      "built-in Windows feature that removes temporary files and "
                      "emptied recycle-bin contents automatically. It never touches "
                      "personal documents.")


# ------------------------------------------------------------------
# Appliers
# ------------------------------------------------------------------

def _apply_game_mode(ctx: dict) -> list:
    return [
        ws.write_registry("HKCU", GAMEBAR, "AutoGameModeEnabled", 1,
                          note="Enable Windows Game Mode"),
        ws.write_registry("HKCU", GAMEBAR, "AllowAutoGameMode", 1,
                          note="Allow automatic Game Mode"),
    ]


def _apply_hags(ctx: dict) -> list:
    return [ws.write_registry("HKLM", GRAPHICS_DRIVERS, "HwSchMode", 2,
                              note="Enable hardware-accelerated GPU scheduling "
                                   "(reboot required)")]


def _apply_gpu_preference(ctx: dict) -> list:
    path = ctx["game"]["executable_path"]
    return [ws.write_registry("HKCU", GRAPHICS_PREFS, path, "GpuPreference=2;",
                              value_type="REG_SZ",
                              note="Prefer high-performance GPU for this game")]


def _apply_power_plan(ctx: dict) -> list:
    return [ws.set_power_scheme(POWER_HIGH_PERF, note="Activate High Performance plan")]


def _apply_visual_effects(ctx: dict) -> list:
    return [
        ws.write_registry("HKCU", VISUAL_FX, "VisualFXSetting", 2,
                          note="Adjust for best performance"),
        ws.write_registry("HKCU", DESKTOP, "UserPreferencesMask",
                          b"\x90\x12\x03\x80\x10\x00\x00\x00",
                          value_type="REG_BINARY", note="Reduce desktop animations"),
    ]


def _apply_gamedvr(ctx: dict) -> list:
    return [
        ws.write_registry("HKCU", GAME_DVR_USER, "GameDVR_Enabled", 0,
                          note="Disable Game DVR background recording"),
        ws.write_registry("HKCU", r"Software\Microsoft\Windows\CurrentVersion\GameDVR",
                          "AppCaptureEnabled", 0,
                          note="Disable background app capture"),
    ]




def _apply_mouse_accel(ctx: dict) -> list:
    return [
        ws.write_registry("HKCU", MOUSE, "MouseSpeed", "0", value_type="REG_SZ",
                          note="Disable Enhance Pointer Precision"),
        ws.write_registry("HKCU", MOUSE, "MouseThreshold1", "0", value_type="REG_SZ",
                          note="Clear acceleration threshold 1"),
        ws.write_registry("HKCU", MOUSE, "MouseThreshold2", "0", value_type="REG_SZ",
                          note="Clear acceleration threshold 2"),
    ]


def _apply_mmcss_games(ctx: dict) -> list:
    return [
        ws.write_registry("HKLM", MMCSS_GAMES, "Priority", 6,
                          note="Restore documented MMCSS Games priority"),
        ws.write_registry("HKLM", MMCSS_GAMES, "GPU Priority", 8,
                          note="Restore documented MMCSS GPU priority"),
    ]


def _apply_network_throttling(ctx: dict) -> list:
    return [ws.write_registry("HKLM", MMCSS_SYSTEM, "NetworkThrottlingIndex",
                              0xFFFFFFFF, note="Disable network throttling")]


def _apply_storage_sense(ctx: dict) -> list:
    return [ws.write_registry("HKCU", STORAGE_SENSE, "01", 1,
                              note="Enable Storage Sense automatic cleanup")]


# ------------------------------------------------------------------
CATALOG: list[Optimization] = [
    Optimization(
        id="win.game_mode", title="Windows Game Mode", area="Windows",
        purpose="Allows Windows to prioritize gaming workloads by deferring "
                "background scheduling and update work while a game is in focus.",
        expected_effect="Potentially improved frame-time consistency. FPS averages "
                        "usually change little.",
        risk=Risk.LOW, supported="Windows 10/11", reversible=True,
        category=Category.RECOMMENDED, evaluate=_eval_game_mode, apply=_apply_game_mode,
        learn_more="https://support.microsoft.com/windows/game-mode",
    ),
    Optimization(
        id="gfx.hags", title="Hardware-Accelerated GPU Scheduling", area="Graphics",
        purpose="Lets the GPU manage its own frame queue instead of the CPU-side "
                "scheduler, removing one buffering stage from the pipeline.",
        expected_effect="Small latency reduction on some driver/title combinations; "
                        "no effect on others. Requires a reboot.",
        risk=Risk.MEDIUM, supported="Windows 10 2004+ with WDDM 2.7 driver",
        reversible=True, category=Category.ADVANCED, evaluate=_eval_hags,
        apply=_apply_hags, requires_admin=True, advanced=True,
    ),
    Optimization(
        id="gfx.gpu_preference", title="High-Performance GPU Preference", area="Graphics",
        purpose="Assigns the detected game executable to the discrete GPU so Windows "
                "does not run it on the integrated adapter.",
        expected_effect="Large FPS improvement if the game was incorrectly running on "
                        "integrated graphics; otherwise none.",
        risk=Risk.LOW, supported="Windows 10/11, multi-GPU systems", reversible=True,
        category=Category.RECOMMENDED, evaluate=_eval_gpu_preference,
        apply=_apply_gpu_preference,
    ),
    Optimization(
        id="power.high_performance", title="High Performance Power Plan", area="Power",
        purpose="Prevents core parking and aggressive clock down-ramping so bursty "
                "game threads do not wait on frequency ramp-up.",
        expected_effect="Improved 1% lows on desktops. On laptops it can raise "
                        "temperatures and reduce sustained clocks.",
        risk=Risk.LOW, supported="Windows 10/11", reversible=True,
        category=Category.OPTIONAL, evaluate=_eval_power_plan, apply=_apply_power_plan,
    ),
    Optimization(
        id="win.game_dvr", title="Xbox Game DVR Background Recording", area="Windows",
        purpose="Stops continuous background gameplay encoding that occupies the GPU "
                "hardware encoder.",
        expected_effect="Reduced frame-time variance on systems where background "
                        "capture is active. Does not affect OBS.",
        risk=Risk.LOW, supported="Windows 10/11", reversible=True,
        category=Category.RECOMMENDED, evaluate=_eval_gamedvr, apply=_apply_gamedvr,
    ),
    Optimization(
        id="win.visual_effects", title="Desktop Visual Effects", area="Windows",
        purpose="Reduces desktop compositor animations to free a small amount of "
                "GPU and memory overhead.",
        expected_effect="Snappier desktop. In-game FPS effect is typically negligible.",
        risk=Risk.LOW, supported="Windows 10/11", reversible=True,
        category=Category.OPTIONAL, evaluate=_eval_visual_effects,
        apply=_apply_visual_effects,
    ),
    Optimization(
        id="storage.cleanup", title="Storage Headroom Review", area="Storage",
        purpose="Identifies reclaimable temporary and cache data when the system "
                "drive is critically full.",
        expected_effect="Restores SSD write performance and paging headroom below "
                        "15% free space.",
        risk=Risk.LOW, supported="Windows 10/11", reversible=False,
        category=Category.SAFE, evaluate=_eval_storage_cleanup, apply=None,
        learn_more="Phantom Tweeks lists candidates only; it never deletes files "
                   "automatically and never touches personal documents.",
    ),
    Optimization(
        id="input.mouse_accel", title="Mouse Pointer Acceleration", area="Input",
        purpose="Disables 'Enhance pointer precision', which applies non-linear "
                "acceleration so identical hand movements produce different cursor "
                "distances depending on speed.",
        expected_effect="Consistent, repeatable aim. No FPS change. This is the "
                        "standard competitive configuration.",
        risk=Risk.LOW, supported="Windows 10/11", reversible=True,
        category=Category.RECOMMENDED, evaluate=_eval_mouse_accel,
        apply=_apply_mouse_accel,
        learn_more="Affects the desktop pointer. Games using raw input are already "
                   "unaffected by this setting.",
    ),
    Optimization(
        id="input.mmcss_games", title="Multimedia Scheduler Game Profile", area="CPU",
        purpose="Restores the documented Windows defaults for the MMCSS Games task, "
                "which governs the CPU share reserved for registered game threads.",
        expected_effect="Corrects scheduling anomalies caused by third-party tools "
                        "having altered these values. Rarely changes FPS on its own.",
        risk=Risk.LOW, supported="Windows 10/11", reversible=True,
        category=Category.ADVANCED, evaluate=_eval_mmcss_games,
        apply=_apply_mmcss_games, requires_admin=True, advanced=True,
    ),
    Optimization(
        id="net.throttling_index", title="Network Throttling Index", area="Network",
        purpose="Removes the Windows cap on non-multimedia network packet processing, "
                "which exists to reserve CPU headroom for audio and video playback.",
        expected_effect="Negligible for most users. May matter only at very high "
                        "packet rates. Phantom Tweeks does not claim a ping benefit.",
        risk=Risk.LOW, supported="Windows 10/11", reversible=True,
        category=Category.OPTIONAL, evaluate=_eval_network_throttling,
        apply=_apply_network_throttling, requires_admin=True, advanced=True,
    ),
    Optimization(
        id="storage.search_index", title="Search Indexing on Mechanical Drives",
        area="Storage",
        purpose="Identifies when Windows Search indexing is competing for seeks on a "
                "mechanical system drive.",
        expected_effect="Reduced load-time stutter on HDD systems, at the cost of "
                        "degraded Start menu search.",
        risk=Risk.MEDIUM, supported="Windows 10/11", reversible=True,
        category=Category.OPTIONAL, evaluate=_eval_search_indexing, apply=None,
        learn_more="Advisory only. Phantom Tweeks will not disable a Windows service "
                   "for you; the Storage Lab explains how if you want to.",
    ),
    Optimization(
        id="storage.storage_sense", title="Storage Sense Automatic Cleanup",
        area="Storage",
        purpose="Enables the built-in Windows feature that automatically removes "
                "temporary files when disk space runs low.",
        expected_effect="Maintains free-space headroom, preserving SSD write "
                        "performance and paging room.",
        risk=Risk.LOW, supported="Windows 10/11", reversible=True,
        category=Category.SAFE, evaluate=_eval_storage_sense,
        apply=_apply_storage_sense,
        learn_more="Storage Sense never deletes personal documents.",
    ),
]

BY_ID = {o.id: o for o in CATALOG}
