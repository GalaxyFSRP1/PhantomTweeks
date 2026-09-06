"""NVIDIA GPU detail, clocks and throttle diagnosis via nvidia-smi.

Why read-only
-------------
This module reports clocks; it never sets them. Silicon quality varies between
individual chips, so a clock offset that is stable on one card produces driver
timeouts, artifacts or silent memory corruption on another. The failure mode is
usually delayed - a crash hours later, a corrupted save - which makes it look
like the game's fault.

What it does instead is more useful than a slider: it reads the card's own
**throttle reasons**. When your GPU is not hitting its boost clock, the driver
already knows why - power limit, thermal limit, or an external cap. Reporting
that tells you whether the fix is better cooling, a higher power limit in
vendor software, or nothing at all.

Everything here comes from nvidia-smi, which ships with the driver. Nothing is
estimated. If a field is unavailable it is reported as unavailable.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from typing import Optional

from ..core import runproc

# Meanings from the NVML clocks_throttle_reasons documentation.
THROTTLE_MEANINGS = {
    "gpu_idle": ("Idle", "info",
                 "The GPU is idle, so it has clocked down. Normal."),
    "applications_clocks_setting": (
        "Application clock limit", "info",
        "An application or administrator set a fixed clock target."),
    "sw_power_cap": (
        "Power limit", "warn",
        "The card wants more power than its limit allows, so the driver is "
        "holding clocks down. Raising the power limit in vendor software can "
        "recover this, within the card's rated range."),
    "hw_slowdown": (
        "Hardware slowdown", "bad",
        "The card triggered a hardware protection. Usually overheating or "
        "insufficient power delivery. Check cooling and the PSU."),
    "sync_boost": ("Sync boost", "info",
                   "Clocks are synchronised with another GPU in a group."),
    "sw_thermal_slowdown": (
        "Thermal limit", "warn",
        "The GPU is at its temperature target and reducing clocks to stay "
        "there. Better airflow or a cleaned heatsink recovers real "
        "performance here - more than any software tweak."),
    "hw_thermal_slowdown": (
        "Hardware thermal slowdown", "bad",
        "Emergency thermal protection is active. Stop and check cooling "
        "before continuing."),
    "hw_power_brake_slowdown": (
        "Power brake", "bad",
        "An external power brake signal is asserted, usually from the PSU or "
        "board power circuitry."),
    "display_clock_setting": (
        "Display clock limit", "info",
        "Clocks are constrained by a display configuration."),
}


@dataclass
class ClockReading:
    label: str
    current: Optional[float] = None
    maximum: Optional[float] = None
    unit: str = "MHz"

    @property
    def headroom_pct(self) -> Optional[float]:
        if not self.current or not self.maximum:
            return None
        return (self.current / self.maximum) * 100

    def render(self) -> str:
        if self.current is None:
            return f"  {self.label:<22} not available"
        line = f"  {self.label:<22} {self.current:.0f} {self.unit}"
        if self.maximum:
            line += f"  (max {self.maximum:.0f}, {self.headroom_pct:.0f}% of peak)"
        return line


@dataclass
class ThrottleReason:
    key: str
    active: bool
    label: str
    level: str
    explanation: str


@dataclass
class NvidiaGPU:
    index: int = 0
    name: str = ""
    driver: str = ""
    vbios: str = ""
    clocks: list = field(default_factory=list)
    throttles: list = field(default_factory=list)
    power_draw_w: Optional[float] = None
    power_limit_w: Optional[float] = None
    power_max_w: Optional[float] = None
    temperature_c: Optional[float] = None
    temp_target_c: Optional[float] = None
    fan_percent: Optional[float] = None
    pcie_gen: Optional[int] = None
    pcie_gen_max: Optional[int] = None
    pcie_width: Optional[int] = None
    pcie_width_max: Optional[int] = None
    utilization: Optional[float] = None
    memory_util: Optional[float] = None

    @property
    def active_throttles(self) -> list:
        return [t for t in self.throttles if t.active and t.key != "gpu_idle"]

    @property
    def pcie_downgraded(self) -> bool:
        """A card below its rated PCIe link is a real, findable fault."""
        if not (self.pcie_gen and self.pcie_gen_max
                and self.pcie_width and self.pcie_width_max):
            return False
        return (self.pcie_gen < self.pcie_gen_max
                or self.pcie_width < self.pcie_width_max)

    def render(self) -> str:
        out = [f"GPU {self.index}: {self.name}",
               f"  Driver {self.driver}"
               + (f"   VBIOS {self.vbios}" if self.vbios else ""), ""]
        out += [c.render() for c in self.clocks]
        out.append("")

        if self.power_draw_w is not None:
            line = f"  {'Power draw':<22} {self.power_draw_w:.0f} W"
            if self.power_limit_w:
                line += f"  (limit {self.power_limit_w:.0f} W"
                if self.power_max_w and self.power_max_w > self.power_limit_w:
                    line += f", card supports up to {self.power_max_w:.0f} W"
                line += ")"
            out.append(line)

        if self.temperature_c is not None:
            line = f"  {'Temperature':<22} {self.temperature_c:.0f} C"
            if self.temp_target_c:
                line += f"  (slowdown target {self.temp_target_c:.0f} C)"
            out.append(line)
        if self.fan_percent is not None:
            out.append(f"  {'Fan':<22} {self.fan_percent:.0f}%")

        if self.pcie_gen:
            line = f"  {'PCIe link':<22} Gen {self.pcie_gen} x{self.pcie_width}"
            if self.pcie_downgraded:
                line += (f"  <- below Gen {self.pcie_gen_max} "
                         f"x{self.pcie_width_max}")
            out.append(line)

        out.append("")
        active = self.active_throttles
        if active:
            out.append("  Why clocks are being held back:")
            for t in active:
                mark = ("!!" if t.level == "bad"
                        else "! " if t.level == "warn" else "  ")
                out.append(f"   {mark} {t.label}")
                out.append(f"       {t.explanation}")
        else:
            out.append("  No throttling reported. The card is free to boost.")
        return "\n".join(out)


_QUERY = (
    "index,name,driver_version,vbios_version,"
    "clocks.current.graphics,clocks.max.graphics,"
    "clocks.current.memory,clocks.max.memory,"
    "clocks.current.sm,clocks.max.sm,"
    "power.draw,power.limit,power.max_limit,"
    "temperature.gpu,temperature.gpu.tlimit,fan.speed,"
    "pcie.link.gen.current,pcie.link.gen.max,"
    "pcie.link.width.current,pcie.link.width.max,"
    "utilization.gpu,utilization.memory"
)

_THROTTLE_QUERY = ",".join(
    f"clocks_throttle_reasons.{k}" for k in THROTTLE_MEANINGS)


def available() -> bool:
    return shutil.which("nvidia-smi") is not None


def _num(v: str) -> Optional[float]:
    v = (v or "").strip()
    if not v or v.lower() in ("n/a", "[n/a]", "not supported",
                              "[not supported]"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _run(query: str) -> list:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    out = runproc.output(
        [exe, f"--query-gpu={query}", "--format=csv,noheader,nounits"],
        timeout=20)
    return [[c.strip() for c in line.split(",")]
            for line in (out or "").splitlines() if line.strip()]


def probe() -> list:
    """Read every NVIDIA GPU. Returns [] when there is no NVIDIA driver."""
    rows = _run(_QUERY)
    if not rows:
        return []
    throttle_rows = _run(_THROTTLE_QUERY)
    keys = list(THROTTLE_MEANINGS)

    gpus = []
    for i, p in enumerate(rows):
        if len(p) < 22:
            continue
        g = NvidiaGPU(
            index=int(_num(p[0]) or i), name=p[1], driver=p[2], vbios=p[3],
            power_draw_w=_num(p[10]), power_limit_w=_num(p[11]),
            power_max_w=_num(p[12]), temperature_c=_num(p[13]),
            temp_target_c=_num(p[14]), fan_percent=_num(p[15]),
            pcie_gen=int(_num(p[16]) or 0) or None,
            pcie_gen_max=int(_num(p[17]) or 0) or None,
            pcie_width=int(_num(p[18]) or 0) or None,
            pcie_width_max=int(_num(p[19]) or 0) or None,
            utilization=_num(p[20]), memory_util=_num(p[21]),
        )
        g.clocks = [
            ClockReading("Graphics clock", _num(p[4]), _num(p[5])),
            ClockReading("Memory clock", _num(p[6]), _num(p[7])),
            ClockReading("SM clock", _num(p[8]), _num(p[9])),
        ]
        if i < len(throttle_rows):
            flags = throttle_rows[i]
            for j, key in enumerate(keys):
                if j >= len(flags):
                    break
                label, level, why = THROTTLE_MEANINGS[key]
                g.throttles.append(ThrottleReason(
                    key=key, active=flags[j].strip() in ("Active", "1"),
                    label=label, level=level, explanation=why))
        gpus.append(g)
    return gpus


def report() -> str:
    """Human-readable NVIDIA report, honest when nothing is present."""
    if not available():
        return ("NVIDIA GPU DETAIL\n\n"
                "nvidia-smi was not found, so there is no NVIDIA driver on "
                "this system (or it is not on PATH).\n\n"
                "This page reports clocks, power limits and the card's own "
                "throttle reasons. Phantom Tweeks never changes clocks: "
                "silicon quality varies between individual chips, and a "
                "setting stable on one card can corrupt data on another.\n\n"
                "AMD and Intel users: your vendor tooling (Adrenalin, Arc "
                "Control) exposes the same information.")

    gpus = probe()
    if not gpus:
        return ("NVIDIA GPU DETAIL\n\n"
                "nvidia-smi is present but returned no usable data. That "
                "usually means the driver is mid-update or its service is "
                "not running.")

    out = ["NVIDIA GPU DETAIL", ""]
    for g in gpus:
        out += [g.render(), ""]
    out += [
        "-" * 60, "",
        "Phantom Tweeks reports clocks but never changes them. Overclocking",
        "is silicon-specific: a preset stable on one card can cause artifacts,",
        "driver timeouts or silent corruption on another, often hours later.",
        "If you want to overclock, do it deliberately in vendor software with",
        "your own stability testing.",
    ]
    return "\n".join(out)


def diagnose() -> list:
    """Actionable findings only. Empty when nothing is wrong."""
    findings = []
    for g in probe():
        for t in g.active_throttles:
            if t.level in ("warn", "bad"):
                findings.append(f"GPU {g.index}: {t.label} - {t.explanation}")
        if g.pcie_downgraded:
            findings.append(
                f"GPU {g.index}: PCIe link is running at Gen {g.pcie_gen} "
                f"x{g.pcie_width} instead of Gen {g.pcie_gen_max} "
                f"x{g.pcie_width_max}. Reseat the card and check it is in the "
                "primary slot - this costs real performance and is a hardware "
                "or BIOS issue, not a software one.")
        if (g.temperature_c and g.temp_target_c
                and g.temperature_c >= g.temp_target_c - 3):
            findings.append(
                f"GPU {g.index}: {g.temperature_c:.0f} C is at the "
                f"{g.temp_target_c:.0f} C slowdown target. Cleaning dust and "
                "improving airflow recovers more performance here than any "
                "software setting.")
        if (g.power_draw_w and g.power_limit_w
                and g.power_draw_w >= g.power_limit_w * 0.98
                and g.power_max_w and g.power_max_w > g.power_limit_w):
            findings.append(
                f"GPU {g.index}: sitting at its {g.power_limit_w:.0f} W power "
                f"limit while the card supports {g.power_max_w:.0f} W. "
                "Raising the limit in vendor software is within spec and can "
                "recover boost clocks.")
    return findings
