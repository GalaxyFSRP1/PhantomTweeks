"""Smart bottleneck detection.

Answers "what is actually limiting this system?" from sampled utilisation,
so the recommendation engine can say 'CPU tweaks are unlikely to help here'.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from ..hardware.monitor import MONITOR


@dataclass
class BottleneckReport:
    verdict: str                      # GPU_BOUND / CPU_BOUND / NETWORK / BALANCED / IDLE / UNKNOWN
    headline: str
    cpu_utilization: Optional[float] = None
    gpu_utilization: Optional[float] = None
    ram_percent: Optional[float] = None
    detail: str = ""
    recommendations: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [self.headline, ""]
        if self.cpu_utilization is not None:
            lines.append(f"CPU utilization: {self.cpu_utilization:.0f}%")
        if self.gpu_utilization is not None:
            lines.append(f"GPU utilization: {self.gpu_utilization:.0f}%")
        lines += ["", self.detail, ""]
        lines += ["Recommended:"] + [f"• {r}" for r in self.recommendations]
        return "\n".join(lines)


def sample(seconds: float = 5.0, interval: float = 0.5) -> dict:
    """Average utilisation over a window; a single instant is misleading."""
    cpu_s, gpu_s, ram_s = [], [], []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        c = MONITOR.cpu()
        if c.utilization is not None:
            cpu_s.append(c.utilization)
        gpus = MONITOR.gpus()
        util = next((g.utilization for g in gpus if g.utilization is not None), None)
        if util is not None:
            gpu_s.append(util)
        m = MONITOR.memory()
        if m.percent is not None:
            ram_s.append(m.percent)
        time.sleep(interval)
    avg = lambda xs: round(sum(xs) / len(xs), 1) if xs else None
    return {"cpu": avg(cpu_s), "gpu": avg(gpu_s), "ram": avg(ram_s),
            "gpu_measurable": bool(gpu_s)}


def analyze(seconds: float = 5.0, network: Optional[dict] = None) -> BottleneckReport:
    s = sample(seconds)
    cpu, gpu, ram = s["cpu"], s["gpu"], s["ram"]

    if network and network.get("status") == "UNSTABLE":
        return BottleneckReport(
            "NETWORK", "NETWORK ISSUE DETECTED", cpu, gpu, ram,
            network.get("summary", ""),
            network.get("recommendations", []))

    if not s["gpu_measurable"]:
        return BottleneckReport(
            "UNKNOWN", "BOTTLENECK ANALYSIS INCOMPLETE", cpu, gpu, ram,
            "GPU utilization could not be measured on this system (this requires "
            "an NVIDIA driver with nvidia-smi, or vendor tooling). Phantom Tweeks "
            "will not guess a bottleneck from CPU data alone.",
            ["Run this analysis while a game is running.",
             "Install or update your GPU driver so utilization can be read."])

    if (cpu or 0) < 25 and (gpu or 0) < 25:
        return BottleneckReport(
            "IDLE", "SYSTEM IDLE", cpu, gpu, ram,
            "Neither the CPU nor the GPU is under meaningful load, so there is no "
            "bottleneck to identify right now.",
            ["Launch a game and re-run the analysis for a useful result."])

    if (gpu or 0) >= 90 and (cpu or 0) < 80:
        return BottleneckReport(
            "GPU_BOUND", "GPU LIMIT DETECTED", cpu, gpu, ram,
            "Your system is primarily GPU-bound.\n\n"
            "CPU tweaks are unlikely to significantly improve FPS.",
            ["Optimize GPU settings",
             "Review resolution",
             "Review graphics settings (shadows, reflections and ray tracing cost the most)",
             "Configure frame pacing / cap FPS for consistency"])

    if (cpu or 0) >= 85 and (gpu or 0) < 85:
        return BottleneckReport(
            "CPU_BOUND", "CPU LIMIT DETECTED", cpu, gpu, ram,
            "Your system appears CPU-bound.\n\n"
            "Raising graphics settings may cost little FPS here, since the GPU has headroom.",
            ["Review background workload in the Background Analyzer",
             "Check CPU power behavior (core parking / clock ramp)",
             "Review game CPU settings such as draw distance, crowd density and physics",
             "Confirm memory is running at its rated speed profile"])

    if (ram or 0) >= 92:
        return BottleneckReport(
            "MEMORY", "MEMORY PRESSURE DETECTED", cpu, gpu, ram,
            f"Memory is {ram:.0f}% used. Once Windows starts paging, frame-time "
            "spikes appear regardless of CPU and GPU headroom.",
            ["Review the Background Analyzer for large memory consumers",
             "Close browser tabs before playing",
             "Consider additional RAM if this recurs under load"])

    return BottleneckReport(
        "BALANCED", "NO CLEAR BOTTLENECK", cpu, gpu, ram,
        "CPU and GPU load are reasonably matched. There is no single component "
        "obviously limiting performance in this sample.",
        ["No change recommended.",
         "If you still see stuttering, run the Frame-Time Analyzer — pacing "
         "problems do not always show up as high average utilization."])
