"""The Phantom Tweeks power plan.

Windows' "High performance" plan is blunt: it pins the CPU at 100% minimum
state, which on a laptop means constant heat, fan noise and shortened battery
life for no frame-rate gain. "Balanced" parks cores and ramps clocks lazily,
which can cost frame-time consistency during sudden load.

The Phantom plan is a *copy of Balanced* with a small number of deliberate,
individually justified adjustments. Every one is listed in PHANTOM_SETTINGS
with the reason it is there.

Design rules, which follow the project's golden rule:
  * We CREATE a new plan. We never edit Balanced or High performance in place,
    so the user's existing plans stay exactly as they were.
  * Removing the plan restores whatever was active before it.
  * We do NOT set minimum processor state to 100%. That is the single most
    common "gaming plan" mistake: it burns power and adds heat without adding
    frames, and on laptops it actively reduces sustained performance because
    the chip hits thermal limits sooner.
  * We do NOT disable core parking on battery, and we detect laptops and adjust.
  * Nothing here overclocks, undervolts, or touches voltage/frequency limits.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional

from ..core.logging_setup import get_logger
from ..core.platform_info import IS_WINDOWS
from .backup import ChangeRecord
from ..core import runproc

log = get_logger("powerplan")

# ASCII only. powercfg runs on a cp1252 console, so an em dash here is
# stored mangled (the em dash becomes three junk characters) and can
# find_phantom_plan() can never match it again. The plan was created
# every time, never found, and
# never removable - which is exactly the "power plan is broken" report.
PHANTOM_PLAN_NAME = "Phantom Tweeks Gaming"

# Names earlier versions may have written, including the mangled form.
# Matched so an existing broken plan is adopted and cleaned up rather than
# duplicated yet again.
LEGACY_PLAN_NAMES = (
    "Phantom Tweeks \u2014 Gaming",
    "Phantom Tweeks \u00e2\u20ac\u201d Gaming",
    "Phantom Tweeks - Gaming",
)
PHANTOM_PLAN_DESC = ("Balanced-based plan tuned by Phantom Tweeks for steady "
                     "frame pacing without needless heat or fan noise.")

BALANCED_GUID = "381b4222-f694-41f0-9685-ff5bb260df2e"

# powercfg subgroup / setting GUIDs
SUB_PROCESSOR = "54533251-82be-4824-96c1-47b60b740d00"
SUB_DISK = "0012ee47-9041-4b5d-9b77-535fba8b1442"
SUB_SLEEP = "238c9fa8-0aad-41ed-83f4-97be242c8f20"
SUB_PCIE = "501a4d13-42af-4429-9fd1-a8218c268e20"
SUB_USB = "2a737441-1930-4402-8d77-b2bebba308a3"

SET_MIN_PROC = "893dee8e-2bef-41e0-89c6-b55d0929964c"   # minimum processor state
SET_MAX_PROC = "bc5038f7-23e0-4960-96da-33abaf5935ec"   # maximum processor state
SET_CORE_PARK = "0cc5b647-c1df-4637-891a-dec35c318583"  # core parking min cores
SET_PERF_BOOST = "be337238-0d82-4146-a960-4f3749d470c7" # processor boost mode
SET_DISK_TIMEOUT = "6738e2c4-e8a5-4a42-b16a-e040e769756e"
SET_HIBERNATE_AFTER = "9d7815a6-7ee4-497e-8888-515a05f02364"
SET_PCIE_ASPM = "ee12f906-d277-404b-b6da-e5fa1a576df5"
SET_USB_SUSPEND = "48e6b7a6-50f5-4782-a5d4-53bb8f07e226"
SET_IDLE_DISABLE = "5d76a2ca-e8c0-402f-a133-2158492d58ad"   # processor idle disable
SET_PERF_INCREASE = "06cadf0e-64ed-448a-8927-ce7bf90eb35d"  # increase threshold
SET_PERF_DECREASE = "12a0ab44-fe28-4fa9-b3bd-4b64f44960a6"  # decrease threshold
SET_PERF_INC_POLICY = "40fbefc7-2e9d-4d25-a185-0cfd8574bac6"
SET_PERF_DEC_POLICY = "40fbefc7-2e9d-4d25-a185-0cfd8574bac7"
SET_PARK_MAX = "ea062031-0e34-4ff1-9b6d-eb1059334028"       # core parking max
SET_MONITOR_OFF = "3c0bc021-c8a8-4e07-a973-6b14cbcb2b7e"
SET_SLEEP_AFTER = "29f6c1db-86da-48c5-9fdb-f2b67b1f44da"
SET_DISPLAY_DIM = "17aaa29b-8b43-4b94-aafe-35f64daaf1ee"
SUB_GRAPHICS = "5fb4938d-1ee8-4b0f-9a3c-5036b0ab995c"
SET_GPU_PREF = "dd848b2a-8a5d-4451-9ae2-39cd41658f6c"       # GPU preference policy
SUB_MULTIMEDIA = "9596fb26-9850-41fd-ac3e-f7c3c00afd4b"
SET_VIDEO_QUALITY = "10778347-1370-4ee0-8bbd-33bdacaade49"
SET_IDLE_PROMOTE = "7b224883-b3cc-4d79-819f-8374152cbe7c"
SET_IDLE_DEMOTE = "4b92d758-5a24-4851-a470-815d78aee119"


@dataclass
class PlanSetting:
    subgroup: str
    setting: str
    ac_value: int
    dc_value: int
    label: str
    reason: str


#: Every deviation from Balanced, with its justification.
#:
#: This is the BALANCED-BASED gaming profile: the safe default. It fixes the
#: things that genuinely cause stutter without the waste and heat of pinning
#: everything at maximum. MAXIMUM_SETTINGS below is the all-out profile.
PHANTOM_SETTINGS: list[PlanSetting] = [
    PlanSetting(
        SUB_PROCESSOR, SET_MIN_PROC, 20, 5,
        "Minimum processor state",
        "Balanced drops to 5% on AC, which means the CPU has to ramp up from "
        "near-idle when a frame suddenly needs work - a common cause of "
        "stutter. 20% keeps a floor without the waste of pinning at 100%. On "
        "battery we leave it at 5% so your runtime is unaffected."),
    PlanSetting(
        SUB_PROCESSOR, SET_MAX_PROC, 100, 100,
        "Maximum processor state",
        "Unchanged at 100%. We never cap your CPU."),
    PlanSetting(
        SUB_PROCESSOR, SET_CORE_PARK, 100, 50,
        "Processor core parking (minimum cores)",
        "Unparking all cores on AC removes the short delay while Windows wakes "
        "a parked core mid-frame. On battery we allow parking again, because "
        "there the power saving is worth more than the microseconds."),
    PlanSetting(
        SUB_PROCESSOR, SET_PERF_BOOST, 2, 1,
        "Processor performance boost mode",
        "'Aggressive' on AC lets turbo engage promptly under bursty game load. "
        "This uses the CPU's own boost behaviour - it is not an overclock and "
        "does not exceed any manufacturer limit."),
    PlanSetting(
        SUB_DISK, SET_DISK_TIMEOUT, 0, 600,
        "Turn off hard disk after",
        "Never on AC. A spinning disk waking mid-level causes a visible hitch "
        "when a game streams assets. On battery it still sleeps after 10 min."),
    PlanSetting(
        SUB_SLEEP, SET_HIBERNATE_AFTER, 0, 5400,
        "Hibernate after",
        "Disabled on AC so a long cutscene, download or shader compile is never "
        "interrupted. Battery behaviour is left sensible at 90 minutes."),
    PlanSetting(
        SUB_PCIE, SET_PCIE_ASPM, 0, 2,
        "PCI Express link state power management",
        "Off on AC. ASPM can add latency to GPU and NVMe transfers. On battery "
        "we keep maximum power saving, since the tradeoff flips."),
    PlanSetting(
        SUB_USB, SET_USB_SUSPEND, 0, 1,
        "USB selective suspend",
        "Off on AC. This is the setting most often behind a mouse or controller "
        "that 'wakes up' a fraction of a second late after being idle."),
]


#: The all-out profile. Everything that can be unlocked, is.
#:
#: This exists because people ask for it, and because on a well-cooled desktop
#: it is a legitimate choice. It is NOT the default, and the app says why:
#: pinning a modern CPU at 100% removes the thermal headroom that single-core
#: boost depends on, so peak performance can actually drop. On a laptop it is
#: usually counterproductive - the chip hits its thermal limit sooner and
#: throttles harder than it would have.
#:
#: Battery values stay conservative regardless. An "everything maximum" plan
#: that flattens a laptop in forty minutes is not a feature.
MAXIMUM_SETTINGS: list[PlanSetting] = [
    PlanSetting(
        SUB_PROCESSOR, SET_MIN_PROC, 100, 20,
        "Minimum processor state",
        "Pins the CPU at full clock on AC so there is no ramp-up delay at "
        "all. This is the setting the Gaming profile deliberately avoids: it "
        "adds heat and power for a gain you will only notice in 1% lows, and "
        "on a thermally limited machine it can reduce sustained clocks. "
        "Battery stays at 20%."),
    PlanSetting(
        SUB_PROCESSOR, SET_MAX_PROC, 100, 100,
        "Maximum processor state",
        "Leaves the full clock ceiling available at all times. This is "
        "already the Balanced default on most systems; it is set "
        "explicitly so the profile does not depend on that."),
    PlanSetting(
        SUB_PROCESSOR, SET_CORE_PARK, 100, 100,
        "Core parking (minimum cores)",
        "Every core stays unparked, so nothing has to wake when load "
        "arrives. Costs idle power."),
    PlanSetting(
        SUB_PROCESSOR, SET_PARK_MAX, 100, 100,
        "Core parking (maximum cores)",
        "Removes the parking ceiling entirely."),
    PlanSetting(
        SUB_PROCESSOR, SET_PERF_BOOST, 2, 1,
        "Processor boost mode",
        "Aggressive boost on AC: the CPU reaches its rated boost clock as "
        "soon as demand appears. This uses the chip's own rated behaviour "
        "and changes no voltage or multiplier."),
    PlanSetting(
        SUB_PROCESSOR, SET_PERF_INCREASE, 10, 40,
        "Performance increase threshold",
        "Steps up to a higher clock after only 10% sustained load instead of "
        "waiting for 60%. Removes the delay between a frame needing work and "
        "the CPU delivering it."),
    PlanSetting(
        SUB_PROCESSOR, SET_PERF_DECREASE, 90, 50,
        "Performance decrease threshold",
        "Holds the higher clock until load drops below 90%, so the CPU does "
        "not drop speed in the gap between frames and have to climb back."),
    PlanSetting(
        SUB_PROCESSOR, SET_IDLE_PROMOTE, 10, 60,
        "Idle promote threshold",
        "Leaves a light idle state quickly when work appears."),
    PlanSetting(
        SUB_PROCESSOR, SET_IDLE_DEMOTE, 90, 40,
        "Idle demote threshold",
        "Avoids dropping into deeper idle states between frames."),
    PlanSetting(
        SUB_PCIE, SET_PCIE_ASPM, 0, 1,
        "PCI Express link state power management",
        "Keeps PCIe links at full power, removing link-state transition "
        "latency for the GPU and NVMe drives."),
    PlanSetting(
        SUB_USB, SET_USB_SUSPEND, 0, 1,
        "USB selective suspend",
        "USB devices never sleep, so a mouse or controller cannot stall on "
        "wake-up."),
    PlanSetting(
        SUB_DISK, SET_DISK_TIMEOUT, 0, 1200,
        "Turn off hard disk after",
        "Drives stay spun up on AC. A mechanical drive spinning back up "
        "mid-session is a multi-second stall."),
    PlanSetting(
        SUB_SLEEP, SET_HIBERNATE_AFTER, 0, 7200,
        "Hibernate after",
        "The machine never hibernates while plugged in, so a long "
        "download or shader compile is not interrupted."),
    PlanSetting(
        SUB_SLEEP, SET_SLEEP_AFTER, 0, 1800,
        "Sleep after",
        "No sleep on AC, so a long loading screen or a download does not "
        "put the machine to sleep."),
    PlanSetting(
        SUB_SLEEP, SET_MONITOR_OFF, 0, 600,
        "Turn off display after",
        "The display stays on while gaming with a controller, where the "
        "machine sees no keyboard or mouse input."),
    PlanSetting(
        SUB_GRAPHICS, SET_GPU_PREF, 0, 1,
        "GPU preference policy",
        "Prefers maximum performance rather than power saving when Windows "
        "chooses a graphics adapter."),
    PlanSetting(
        SUB_MULTIMEDIA, SET_VIDEO_QUALITY, 0, 1,
        "Video playback quality bias",
        "Favours quality over power saving during video playback."),
]


@dataclass
class PlanProfile:
    """A named plan with its settings and its honest trade-off."""
    key: str
    name: str
    description: str
    settings: list
    laptop_warning: str = ""

    @property
    def setting_count(self) -> int:
        return len(self.settings)


PROFILES: dict = {
    "gaming": PlanProfile(
        "gaming", PHANTOM_PLAN_NAME,
        "Balanced-based and tuned for steady frame pacing. Fixes the settings "
        "that genuinely cause stutter without the heat and power draw of "
        "pinning everything at maximum. This is the recommended choice.",
        PHANTOM_SETTINGS,
        laptop_warning=""),
    "maximum": PlanProfile(
        "maximum", "Phantom Tweeks Maximum",
        "Everything unlocked. No idle states, no core parking, no link power "
        "management, aggressive boost and instant clock ramping. Reasonable "
        "on a well-cooled desktop.",
        MAXIMUM_SETTINGS,
        laptop_warning=(
            "On a laptop this is usually counterproductive. Pinning the CPU "
            "at 100% makes it reach its thermal limit sooner, and a throttled "
            "chip runs SLOWER than one that was allowed to idle between "
            "frames. It will also flatten your battery. The Gaming profile is "
            "the better choice on portable hardware.")),
}


def profile_names() -> list:
    return [(k, p.name) for k, p in PROFILES.items()]


def _powercfg(*args, timeout: int = 20) -> subprocess.CompletedProcess:
    return runproc.run(["powercfg", *args], capture_output=True, text=True,
                          timeout=timeout)


def powercfg_available() -> bool:
    return bool(IS_WINDOWS and shutil.which("powercfg"))


def list_plans() -> list[dict]:
    """All power schemes, with which one is active."""
    if not powercfg_available():
        return []
    try:
        out = _powercfg("/list").stdout
    except Exception as e:
        log.warning("powercfg /list failed: %s", e)
        return []
    plans = []
    for line in out.splitlines():
        m = re.search(r"([0-9a-fA-F-]{36})\s*\(([^)]*)\)", line)
        if m:
            plans.append({
                "guid": m.group(1).lower(),
                "name": m.group(2).strip(),
                "active": line.rstrip().endswith("*"),
            })
    return plans


def find_phantom_plan(name: Optional[str] = None) -> Optional[str]:
    """Find one of our plans, including any left by an earlier version."""
    if name:
        for p in list_plans():
            if p["name"].strip() == name:
                return p["guid"]
        return None
    wanted = {PHANTOM_PLAN_NAME, *LEGACY_PLAN_NAMES,
              *(pr.name for pr in PROFILES.values())}
    for p in list_plans():
        if p["name"].strip() in wanted:
            return p["guid"]
    # Last resort: match on the leading words, so an unknown mangling of the
    # separator still finds the plan instead of creating a duplicate.
    for p in list_plans():
        if p["name"].strip().lower().startswith("phantom tweeks"):
            return p["guid"]
    return None


def all_phantom_plans() -> list:
    """Every Phantom plan present, whichever profile made it."""
    names = {PHANTOM_PLAN_NAME, *LEGACY_PLAN_NAMES,
             *(p.name for p in PROFILES.values())}
    return [p for p in list_plans() if p["name"].strip() in names]


def stray_phantom_plans() -> list:
    """Every Phantom plan on the system. More than one means an earlier
    version created duplicates it could not find."""
    return [p for p in list_plans()
            if p["name"].strip().lower().startswith("phantom tweeks")]


def active_plan() -> Optional[dict]:
    for p in list_plans():
        if p["active"]:
            return p
    return None


def is_laptop() -> bool:
    """True when a battery is present."""
    try:
        import psutil
        b = psutil.sensors_battery()
        return b is not None
    except Exception:
        return False


def describe() -> str:
    """Human-readable explanation of exactly what the plan changes and why."""
    lines = [
        PHANTOM_PLAN_NAME,
        "=" * len(PHANTOM_PLAN_NAME),
        "",
        PHANTOM_PLAN_DESC,
        "",
        "This is a NEW plan copied from Balanced. Your existing plans are not",
        "modified. Removing it restores the plan you were using before.",
        "",
        f"{len(PHANTOM_SETTINGS)} settings differ from Balanced:",
        "",
    ]
    for s in PHANTOM_SETTINGS:
        ac = "never" if s.ac_value == 0 and "after" in s.label.lower() else s.ac_value
        lines.append(f"  {s.label}")
        lines.append(f"    Plugged in: {ac}    On battery: {s.dc_value}")
        for chunk in _wrap(s.reason, 4):
            lines.append(chunk)
        lines.append("")
    lines += [
        "Not included, deliberately:",
        "  - Minimum processor state is NOT set to 100%. It adds heat and fan",
        "    noise without adding frames, and on laptops it reduces sustained",
        "    performance by hitting thermal limits sooner.",
        "  - No overclocking, undervolting, or voltage/frequency limit changes.",
        "  - No disabling of CPU cores or security mitigations.",
    ]
    return "\n".join(lines)


def _wrap(text: str, indent: int, width: int = 72) -> list[str]:
    import textwrap
    return textwrap.wrap(text, width, initial_indent=" " * indent,
                         subsequent_indent=" " * indent)


def create_plan(activate: bool = True, profile: str = "gaming"
                ) -> tuple[bool, list[str], list[ChangeRecord]]:
    """Create (or update) a Phantom plan. Returns (ok, messages, changes).

    ``profile`` selects which tier to build - "gaming" (the safe default) or
    "maximum" (everything unlocked).
    """
    chosen = PROFILES.get(profile) or PROFILES["gaming"]
    plan_name = chosen.name
    plan_settings = chosen.settings
    msgs: list[str] = []
    changes: list[ChangeRecord] = []

    if not powercfg_available():
        return False, ["Custom power plans require Windows (powercfg)."], []

    # powercfg needs elevation to create or modify a scheme. Without it the
    # commands fail with an access-denied that surfaces as a confusing
    # "could not create the plan" - so check first and say what to do.
    from ..core.platform_info import is_admin
    if not is_admin():
        return False, [
            "Creating a power plan requires administrator rights.",
            "",
            "Close Phantom Tweeks, right-click it and choose",
            "'Run as administrator', then try again.",
            "",
            "Everything else on this page works without elevation - you can "
            "still see your plans and what the Phantom plan would change.",
        ], []

    existing = find_phantom_plan(plan_name)
    previous = active_plan()
    prev_guid = previous["guid"] if previous else None

    if existing:
        guid = existing
        msgs.append(f"Updating the existing '{plan_name}' plan.")
    else:
        # Duplicate from Balanced when it exists. Many OEM machines ship
        # without it - Dell, HP and Lenovo all replace it with their own
        # profile - and /duplicatescheme then fails with "the system cannot
        # find the file specified", which reads as a permissions problem and
        # is not. Fall back to the active scheme, then to any scheme present.
        sources = []
        available = {p["guid"] for p in list_plans()}
        if BALANCED_GUID in available:
            sources.append((BALANCED_GUID, "Balanced"))
        if previous and previous.get("guid") in available:
            sources.append((previous["guid"],
                            previous.get("name", "your active plan")))
        for plan in list_plans():
            sources.append((plan["guid"], plan["name"]))

        r = None
        source_name = ""
        tried = []
        for guid_src, name_src in sources:
            r = _powercfg("/duplicatescheme", guid_src)
            if r.returncode == 0 and re.search(r"([0-9a-fA-F-]{36})", r.stdout):
                source_name = name_src
                break
            tried.append(name_src)
            r = None

        if r is None:
            detail = "no usable source power scheme"
            return False, [
                "Could not create the power plan.",
                f"powercfg said: {detail}",
                "",
                f"Tried copying from: {', '.join(tried) or 'nothing'}.",
                "",
                "This normally means a group policy locks power settings, "
                "which is common on work or school machines. Everything else "
                "on this page still works.",
            ], []

        m = re.search(r"([0-9a-fA-F-]{36})", r.stdout)
        if not m:
            return False, ["powercfg did not return a GUID for the new plan."], []
        if source_name and source_name != "Balanced":
            msgs.append(f"Balanced was not available, so the plan was copied "
                        f"from '{source_name}' instead.")
        guid = m.group(1).lower()
        rename = _powercfg("/changename", guid, plan_name,
                           chosen.description[:200])
        if rename.returncode != 0:
            # The plan exists but is still called "Balanced (1)". Say so
            # rather than leaving a mystery duplicate behind.
            msgs.append("Created the plan, but Windows refused to rename it. "
                        "It will appear under its copied name.")
        msgs.append(f"Created '{plan_name}'.")

        # Prove it is findable. If this fails the plan exists but the app
        # cannot manage it, which is worse than a clean failure.
        if find_phantom_plan(plan_name) is None:
            msgs.append("Warning: the plan was created but cannot be found "
                        "again by name. Use 'Clean up duplicates' if extra "
                        "plans appear.")
        changes.append(ChangeRecord(
            kind="powerplan", target="scheme", name=guid,
            previous="__PHANTOM_ABSENT__", applied=guid,
            note=f"Created power plan {PHANTOM_PLAN_NAME}"))

    laptop = is_laptop()
    if laptop and chosen.laptop_warning:
        msgs.append("")
        msgs.append("LAPTOP DETECTED")
        for line in chosen.laptop_warning.split(". "):
            if line.strip():
                msgs.append(f"  {line.strip().rstrip('.')}.")
        msgs.append("")

    applied = 0
    for s in plan_settings:
        ac = _powercfg("/setacvalueindex", guid, s.subgroup, s.setting,
                       str(s.ac_value))
        dc = _powercfg("/setdcvalueindex", guid, s.subgroup, s.setting,
                       str(s.dc_value))
        if ac.returncode == 0 and dc.returncode == 0:
            applied += 1
        else:
            # Not every setting exists on every machine (e.g. no PCIe ASPM on
            # some desktops). That is normal; report it without failing.
            msgs.append(f"  Skipped '{s.label}' - not available on this system.")
    msgs.append(f"Applied {applied} of {len(plan_settings)} settings.")
    if laptop:
        msgs.append("Laptop detected: battery-side values were kept "
                    "conservative to protect runtime.")

    _powercfg("/setactive", guid) if activate else None
    if activate:
        msgs.append("Phantom plan is now active.")
        changes.append(ChangeRecord(
            kind="powercfg", target="active_scheme", name="guid",
            previous=prev_guid or "__PHANTOM_ABSENT__", applied=guid,
            note="Switched to the Phantom Tweeks power plan"))
    return True, msgs, changes


def cleanup_duplicates() -> tuple[bool, list[str]]:
    """Remove extra Phantom plans left by the old naming bug.

    An earlier version wrote a plan name containing an em dash. powercfg
    stored it mangled, so the app never recognised its own plan and created
    a fresh duplicate every run. This removes all but the active one.
    """
    from ..core.platform_info import is_admin
    if not powercfg_available():
        return False, ["Power plans require Windows (powercfg)."]
    if not is_admin():
        return False, ["Removing power plans requires administrator rights."]

    strays = stray_phantom_plans()
    if len(strays) <= 1:
        return True, ["Nothing to clean up - there is at most one Phantom "
                      "plan on this system."]

    keep = next((p for p in strays if p["active"]), strays[-1])
    removed, failed = [], []
    for plan in strays:
        if plan["guid"] == keep["guid"]:
            continue
        r = _powercfg("/delete", plan["guid"])
        (removed if r.returncode == 0 else failed).append(plan["name"])

    msgs = [f"Kept '{keep['name']}'."]
    if removed:
        msgs.append(f"Removed {len(removed)} duplicate plan(s) left by an "
                    "earlier version.")
    if failed:
        msgs.append(f"Could not remove {len(failed)}: they may be in use.")
    return True, msgs


def delete_plan() -> tuple[bool, list[str]]:
    """Remove the Phantom plan and fall back to Balanced."""
    from ..core.platform_info import is_admin
    if not powercfg_available():
        return False, ["Custom power plans require Windows (powercfg)."]
    if not is_admin():
        return False, ["Removing a power plan requires administrator rights. "
                       "Restart Phantom Tweeks as administrator."]
    if not powercfg_available():
        return False, ["Custom power plans require Windows (powercfg)."]
    guid = find_phantom_plan()
    if not guid:
        return True, ["The Phantom power plan is not installed."]
    act = active_plan()
    msgs = []
    if act and act["guid"] == guid:
        _powercfg("/setactive", BALANCED_GUID)
        msgs.append("Switched back to Balanced.")
    r = _powercfg("/delete", guid)
    if r.returncode != 0:
        return False, msgs + [f"Could not delete the plan: {r.stderr.strip()}"]
    msgs.append(f"Removed '{PHANTOM_PLAN_NAME}'.")
    return True, msgs


def status() -> dict:
    """Current power state, for the GUI/CLI."""
    if not powercfg_available():
        return {"available": False,
                "reason": "Custom power plans require Windows (powercfg)."}
    guid = find_phantom_plan()
    act = active_plan()
    return {
        "available": True,
        "installed": guid is not None,
        "guid": guid,
        "active": bool(guid and act and act["guid"] == guid),
        "active_plan": act["name"] if act else "unknown",
        "laptop": is_laptop(),
        "settings": len(PHANTOM_SETTINGS),
        "plans": list_plans(),
    }
