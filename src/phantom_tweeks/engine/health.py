"""System Health Center. Every warning carries an explanation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..core.platform_info import is_supported_windows, windows_release
from ..hardware.monitor import MONITOR

OK, WARN, UNKNOWN = "Healthy", "Warning", "Unknown"


@dataclass
class HealthItem:
    name: str
    status: str
    detail: str = ""

    @property
    def icon(self) -> str:
        return {OK: "✓", WARN: "⚠", UNKNOWN: "?"}.get(self.status, "?")

    def render(self) -> str:
        label = {OK: "Healthy", WARN: "Unstable", UNKNOWN: "Unknown"}
        return f"{self.name:<10}{self.icon} {self.status}"


@dataclass
class HealthReport:
    items: list[HealthItem] = field(default_factory=list)

    def render(self) -> str:
        out = ["SYSTEM HEALTH", ""]
        out += [i.render() for i in self.items]
        warns = [i for i in self.items if i.status != OK]
        if warns:
            out += ["", "Explanations:"]
            out += [f"• {i.name}: {i.detail}" for i in warns]
        return "\n".join(out)


def build(network: Optional[dict] = None, drivers: Optional[dict] = None) -> HealthReport:
    rep = HealthReport()
    cpu, mem, gpus = MONITOR.cpu(), MONITOR.memory(), MONITOR.gpus()

    if cpu.temperature_c is not None and cpu.temperature_c > 90:
        rep.items.append(HealthItem("CPU", WARN,
            f"Package temperature is {cpu.temperature_c:.0f} °C. Sustained "
            "temperatures this high cause thermal throttling and lower sustained "
            "clocks. Check case airflow and cooler mounting."))
    elif cpu.utilization is not None:
        rep.items.append(HealthItem("CPU", OK))
    else:
        rep.items.append(HealthItem("CPU", UNKNOWN, "CPU telemetry unavailable."))

    hot_gpu = next((g for g in gpus if g.temperature_c and g.temperature_c > 85), None)
    if hot_gpu:
        rep.items.append(HealthItem("GPU", WARN,
            f"{hot_gpu.model} is at {hot_gpu.temperature_c:.0f} °C, which will cause "
            "clock throttling. Check fan curves and dust build-up."))
    elif gpus:
        rep.items.append(HealthItem("GPU", OK))
    else:
        rep.items.append(HealthItem("GPU", UNKNOWN, "No GPU detected."))

    if mem.percent is not None and mem.percent > 90:
        rep.items.append(HealthItem("RAM", WARN,
            f"Memory is {mem.percent:.0f}% used at idle. Windows will start paging "
            "during gameplay, producing frame-time spikes."))
    elif mem.percent is not None:
        rep.items.append(HealthItem("RAM", OK))
    else:
        rep.items.append(HealthItem("RAM", UNKNOWN, "Memory telemetry unavailable."))

    disks = MONITOR.disks()
    low = [d for d in disks if d.total_gb and d.free_gb is not None
           and d.free_gb / d.total_gb < 0.10]
    if low:
        rep.items.append(HealthItem("Storage", WARN,
            "Drive(s) " + ", ".join(d.mountpoint for d in low) +
            " are over 90% full, which degrades SSD write performance."))
    else:
        rep.items.append(HealthItem("Storage", OK if disks else UNKNOWN,
                                    "" if disks else "No drives readable."))

    if network:
        diag = network.get("diagnosis", {})
        if diag.get("status") == "UNSTABLE":
            rep.items.append(HealthItem("Network", WARN, diag.get("summary", "")))
        else:
            rep.items.append(HealthItem("Network", OK))
    else:
        rep.items.append(HealthItem("Network", UNKNOWN,
                                    "Run the Network Lab to evaluate this."))

    if drivers:
        outdated = drivers.get("outdated") or []
        if outdated:
            rep.items.append(HealthItem("Drivers", WARN,
                f"{len(outdated)} driver(s) are over a year old: " +
                ", ".join(d.device for d in outdated[:3]) +
                ". Update from the official vendor page only."))
        else:
            rep.items.append(HealthItem("Drivers", OK))
    else:
        rep.items.append(HealthItem("Drivers", UNKNOWN, "Run the Driver Center."))

    if is_supported_windows():
        rep.items.append(HealthItem("Windows", OK))
    else:
        rep.items.append(HealthItem("Windows", WARN,
            f"{windows_release()} is not a supported Windows 10/11 build. Phantom "
            "Tweeks runs in analysis-only mode and will not change settings."))
    return rep
