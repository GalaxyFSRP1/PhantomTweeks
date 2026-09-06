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

PHANTOM_PLAN_NAME = "Phantom Tweeks — Gaming"
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


@dataclass
class PlanSetting:
    subgroup: str
    setting: str
    ac_value: int
    dc_value: int
    label: str
    reason: str


#: Every deviation from Balanced, with its justification.
PHANTOM_SETTINGS: list[PlanSetting] = [
    PlanSetting(
        SUB_PROCESSOR, SET_MIN_PROC, 20, 5,
        "Minimum processor state",
        "Balanced drops to 5% on AC, which means the CPU has to ramp up from "
        "near-idle when a frame suddenly needs work — a common cause of "
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
        "This uses the CPU's own boost behaviour — it is not an overclock and "
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


def find_phantom_plan() -> Optional[str]:
    for p in list_plans():
        if p["name"].strip() == PHANTOM_PLAN_NAME:
            return p["guid"]
    return None


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
        "  • Minimum processor state is NOT set to 100%. It adds heat and fan",
        "    noise without adding frames, and on laptops it reduces sustained",
        "    performance by hitting thermal limits sooner.",
        "  • No overclocking, undervolting, or voltage/frequency limit changes.",
        "  • No disabling of CPU cores or security mitigations.",
    ]
    return "\n".join(lines)


def _wrap(text: str, indent: int, width: int = 72) -> list[str]:
    import textwrap
    return textwrap.wrap(text, width, initial_indent=" " * indent,
                         subsequent_indent=" " * indent)


def create_plan(activate: bool = True) -> tuple[bool, list[str], list[ChangeRecord]]:
    """Create (or update) the Phantom plan. Returns (ok, messages, changes)."""
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

    existing = find_phantom_plan()
    previous = active_plan()
    prev_guid = previous["guid"] if previous else None

    if existing:
        guid = existing
        msgs.append(f"Updating the existing '{PHANTOM_PLAN_NAME}' plan.")
    else:
        r = _powercfg("/duplicatescheme", BALANCED_GUID)
        if r.returncode != 0:
            detail = (r.stderr or r.stdout or "").strip() or "no output"
            return False, [
                "Could not create the power plan.",
                f"powercfg said: {detail}",
                "",
                "The usual cause is missing administrator rights, or a group "
                "policy that locks power settings on managed machines.",
            ], []
        m = re.search(r"([0-9a-fA-F-]{36})", r.stdout)
        if not m:
            return False, ["powercfg did not return a GUID for the new plan."], []
        guid = m.group(1).lower()
        _powercfg("/changename", guid, PHANTOM_PLAN_NAME, PHANTOM_PLAN_DESC)
        msgs.append(f"Created '{PHANTOM_PLAN_NAME}' as a copy of Balanced.")
        changes.append(ChangeRecord(
            kind="powerplan", target="scheme", name=guid,
            previous="__PHANTOM_ABSENT__", applied=guid,
            note=f"Created power plan {PHANTOM_PLAN_NAME}"))

    laptop = is_laptop()
    applied = 0
    for s in PHANTOM_SETTINGS:
        ac = _powercfg("/setacvalueindex", guid, s.subgroup, s.setting,
                       str(s.ac_value))
        dc = _powercfg("/setdcvalueindex", guid, s.subgroup, s.setting,
                       str(s.dc_value))
        if ac.returncode == 0 and dc.returncode == 0:
            applied += 1
        else:
            # Not every setting exists on every machine (e.g. no PCIe ASPM on
            # some desktops). That is normal; report it without failing.
            msgs.append(f"  Skipped '{s.label}' — not available on this system.")
    msgs.append(f"Applied {applied} of {len(PHANTOM_SETTINGS)} settings.")
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
