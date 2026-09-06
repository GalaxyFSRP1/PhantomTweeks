"""CPU vendor detection and vendor-specific guidance.

Why this exists
---------------
Intel and AMD need genuinely different advice, and generic tweak lists give
the same answer to both - which is how people end up disabling SMT on a Ryzen
or hunting for a Core Parking setting that their Intel chip does not use.

The differences that actually matter:

* **AMD Ryzen** is unusually sensitive to memory speed and Infinity Fabric
  timing. Enabling EXPO/DOCP is frequently worth more than every software
  tweak combined. Ryzen also has preferred cores (CPPC) and, on dual-CCD
  parts, a cross-CCD latency penalty that game-bar core parking handles.
* **Intel 12th gen and newer** are hybrid: P-cores and E-cores. Thread
  Director decides placement, and manual affinity - which older guides
  recommend - actively breaks it by pinning games to efficiency cores.

Everything here is read-only. No overclocking, no undervolting, no core
disabling. Vendor-specific *settings* are surfaced as guidance because they
live in the BIOS, where this app deliberately does not reach.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from ..core import runproc
from ..core.platform_info import IS_WINDOWS

INTEL = "Intel"
AMD = "AMD"
UNKNOWN = "Unknown"


@dataclass
class CPUProfile:
    vendor: str = UNKNOWN
    model: str = ""
    family: str = ""
    physical_cores: Optional[int] = None
    logical_cores: Optional[int] = None
    hybrid: bool = False
    p_cores: Optional[int] = None
    e_cores: Optional[int] = None
    ccds: Optional[int] = None
    base_mhz: Optional[int] = None
    max_mhz: Optional[int] = None
    smt: Optional[bool] = None

    @property
    def is_intel(self) -> bool:
        return self.vendor == INTEL

    @property
    def is_amd(self) -> bool:
        return self.vendor == AMD

    def render(self) -> str:
        out = [f"{self.model or 'Unknown CPU'}",
               f"  Vendor            {self.vendor}"]
        if self.family:
            out.append(f"  Generation        {self.family}")
        if self.physical_cores:
            line = f"  Cores             {self.physical_cores} physical"
            if self.logical_cores:
                line += f" / {self.logical_cores} logical"
            out.append(line)
        if self.hybrid and self.p_cores:
            out.append(f"  Hybrid layout     {self.p_cores} P-cores, "
                       f"{self.e_cores or 0} E-cores")
        if self.ccds and self.ccds > 1:
            out.append(f"  Chiplets          {self.ccds} CCDs "
                       "(cross-chiplet latency applies)")
        if self.smt is not None:
            out.append(f"  SMT / Hyper-Threading  "
                       f"{'enabled' if self.smt else 'disabled'}")
        if self.base_mhz:
            out.append(f"  Base clock        {self.base_mhz} MHz"
                       + (f"   max {self.max_mhz} MHz" if self.max_mhz else ""))
        return "\n".join(out)


def _wmi_cpu() -> dict:
    if not IS_WINDOWS:
        return {}
    ps = ("Get-CimInstance Win32_Processor | Select-Object Name,Manufacturer,"
          "NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed | "
          "ConvertTo-Json -Compress")
    out = runproc.output(["powershell", "-NoProfile", "-NonInteractive",
                          "-Command", ps], timeout=25)
    if not out.strip():
        return {}
    try:
        import json
        data = json.loads(out)
        return data[0] if isinstance(data, list) else data
    except (ValueError, IndexError):
        return {}


def _proc_cpuinfo() -> dict:
    """Linux fallback so the module is testable off Windows."""
    try:
        text = open("/proc/cpuinfo", encoding="utf-8").read()
    except OSError:
        return {}
    model = re.search(r"model name\s*:\s*(.+)", text)
    vendor = re.search(r"vendor_id\s*:\s*(.+)", text)
    return {
        "Name": model.group(1).strip() if model else "",
        "Manufacturer": vendor.group(1).strip() if vendor else "",
        "NumberOfLogicalProcessors": text.count("processor\t:") or None,
    }


def detect() -> CPUProfile:
    """Identify the CPU and its layout. Never raises."""
    raw = _wmi_cpu() or _proc_cpuinfo()
    profile = CPUProfile()
    name = str(raw.get("Name") or "")
    maker = str(raw.get("Manufacturer") or "")
    profile.model = name.strip()

    blob = f"{name} {maker}".lower()
    if "amd" in blob or "authenticamd" in blob or "ryzen" in blob:
        profile.vendor = AMD
    elif "intel" in blob or "genuineintel" in blob or "core(tm)" in blob:
        profile.vendor = INTEL

    profile.physical_cores = raw.get("NumberOfCores")
    profile.logical_cores = raw.get("NumberOfLogicalProcessors")
    profile.max_mhz = raw.get("MaxClockSpeed")
    if profile.physical_cores and profile.logical_cores:
        profile.smt = profile.logical_cores > profile.physical_cores

    if profile.vendor == INTEL:
        gen = re.search(r"i[3579][- ](\d{4,5})", name)
        if gen:
            digits = gen.group(1)
            generation = int(digits[:2]) if len(digits) == 5 else int(digits[0])
            profile.family = f"{generation}th generation"
            # 12th gen and later are hybrid P-core/E-core designs.
            profile.hybrid = generation >= 12
        if "ultra" in name.lower():
            profile.family = "Core Ultra"
            profile.hybrid = True
        if profile.hybrid and profile.physical_cores and profile.logical_cores:
            # E-cores have no SMT, so logical minus physical gives P-core count.
            profile.p_cores = profile.logical_cores - profile.physical_cores
            profile.e_cores = max(0, profile.physical_cores - (profile.p_cores or 0))

    elif profile.vendor == AMD:
        m = re.search(r"ryzen\s+(\d)", name.lower())
        if m:
            profile.family = f"Ryzen {m.group(1)} series"
        if profile.physical_cores:
            # Ryzen CCDs hold up to 8 cores each.
            profile.ccds = max(1, -(-profile.physical_cores // 8))
    return profile


# --------------------------------------------------------------- guidance

@dataclass
class Advice:
    title: str
    detail: str
    where: str = ""
    impact: str = "medium"      # high | medium | low

    def render(self) -> str:
        mark = {"high": "**", "medium": "  ", "low": "  "}[self.impact]
        out = [f" {mark} {self.title}"]
        for line in _wrap(self.detail, 66):
            out.append(f"      {line}")
        if self.where:
            out.append(f"      Where: {self.where}")
        return "\n".join(out)


def _wrap(text: str, width: int) -> list:
    words, line, out = text.split(), "", []
    for w in words:
        if len(line) + len(w) + 1 > width:
            out.append(line)
            line = w
        else:
            line = (line + " " + w).strip()
    if line:
        out.append(line)
    return out


def advice_for(profile: Optional[CPUProfile] = None) -> list:
    """Vendor-specific guidance. Generic lists get this wrong constantly."""
    profile = profile or detect()
    out = []

    if profile.is_amd:
        out.append(Advice(
            "Enable EXPO or DOCP in the BIOS",
            "Ryzen performance scales with memory speed more than any other "
            "consumer platform, because the Infinity Fabric that links the "
            "core chiplets runs in step with it. RAM sold as 6000 MT/s runs "
            "at 4800 until you enable its profile. This is routinely worth "
            "more to 1% lows than every software tweak combined.",
            "BIOS > Memory > EXPO / DOCP / A-XMP", "high"))
        out.append(Advice(
            "Install the AMD chipset driver",
            "It supplies the Ryzen power plan and the CPPC preferred-core "
            "data Windows uses to place threads on the fastest cores. "
            "Without it, Windows schedules blind. Commonly missed after a "
            "clean Windows install.",
            "amd.com support page for your motherboard", "high"))
        if (profile.ccds or 1) > 1:
            out.append(Advice(
                "Your CPU has multiple chiplets",
                f"{profile.ccds} CCDs. A game whose threads land on both "
                "pays a cross-chiplet latency penalty. Windows Game Bar and "
                "the AMD chipset driver handle this automatically on current "
                "builds - manual affinity usually makes it worse, not "
                "better.", "", "medium"))
        out.append(Advice(
            "Leave SMT enabled",
            "Guides telling you to disable SMT date from a handful of 2015 "
            "titles with genuine scheduler bugs. Modern games use 8 or more "
            "threads and lose measurable performance without it.",
            "", "medium"))
        out.append(Advice(
            "Curve Optimizer is not a one-click setting",
            "Undervolting can genuinely raise sustained boost by lowering "
            "temperature. It is also specific to your individual chip: a "
            "value stable on someone else's Ryzen causes crashes hours "
            "later on yours. Phantom Tweeks will not automate it.",
            "BIOS > Precision Boost Overdrive", "low"))

    elif profile.is_intel:
        if profile.hybrid:
            out.append(Advice(
                "Do not set CPU affinity manually",
                "Your CPU has performance and efficiency cores. Thread "
                "Director, in the CPU itself, tells Windows where to put "
                "each thread. Manual affinity - which older guides "
                "recommend - overrides that and can pin your game to "
                "efficiency cores, which is dramatically worse.",
                "", "high"))
            out.append(Advice(
                "Keep the Balanced or High Performance power plan",
                "Thread Director needs the standard Windows scheduler to "
                "work. Third-party 'ultimate' plans and forced minimum "
                "processor states can defeat E-core parking and make "
                "placement worse.", "", "medium"))
        out.append(Advice(
            "Enable XMP in the BIOS",
            "Less dramatic than on Ryzen but still real: memory sold as "
            "6000 MT/s runs at 4800 until the profile is enabled. Free "
            "performance you have already paid for.",
            "BIOS > Memory > XMP", "high"))
        out.append(Advice(
            "Check your power limits if boost is short-lived",
            "Intel chips boost until they hit PL1/PL2 or a thermal limit. "
            "On many prebuilts and laptops those limits are set low by the "
            "vendor, so the chip drops to base clock after a few seconds. "
            "That is a firmware setting, not something software can fix.",
            "BIOS > CPU power limits", "medium"))
        out.append(Advice(
            "Leave Hyper-Threading enabled",
            "Same reasoning as SMT on AMD. Halving your thread count costs "
            "real performance in anything modern.", "", "medium"))

    else:
        out.append(Advice(
            "CPU vendor not identified",
            "Vendor-specific guidance needs the processor name, which is "
            "read through WMI on Windows. Everything else in Phantom Tweeks "
            "works normally.", "", "low"))

    # Applies to both vendors.
    out.append(Advice(
        "Check your cooling before tweaking anything",
        "A thermally throttled CPU loses far more performance than any "
        "setting on this page can recover. Dust in the heatsink and dried "
        "thermal paste are the two most common causes of a machine that "
        "'got slower over time'.", "", "high"))
    return out


def report() -> str:
    profile = detect()
    out = ["CPU DETAIL AND VENDOR GUIDANCE", "", profile.render(), "",
           "-" * 60, "",
           f"Guidance for {profile.vendor} processors",
           "(** marks the changes with the largest real effect)", ""]
    for item in advice_for(profile):
        out += [item.render(), ""]
    out += ["Phantom Tweeks reports these but does not apply them: they live",
            "in your BIOS, and the ones that do not are specific to your",
            "individual chip. Nothing here is overclocking advice."]
    return "\n".join(out)
