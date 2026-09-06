"""Phantom Performance Score.

Every sub-score is computed from a stated measurement with a stated rule.
If the input cannot be measured, the sub-score is reported as unavailable
rather than filled with a flattering default.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..hardware.monitor import MONITOR


@dataclass
class SubScore:
    name: str
    value: Optional[int]
    explanation: str
    inputs: dict = field(default_factory=dict)

    @property
    def display(self) -> str:
        return f"{self.value}/100" if self.value is not None else "n/a"


@dataclass
class PerformanceScore:
    subscores: list[SubScore]
    overall: Optional[int]

    def render(self) -> str:
        lines = ["PERFORMANCE SCORE", ""]
        for s in self.subscores:
            lines.append(f"{s.name:<22}{s.display:>8}")
        lines += ["", f"{'Overall':<22}{(str(self.overall)+'/100') if self.overall is not None else 'n/a':>8}"]
        return "\n".join(lines)

    def as_dict(self) -> dict:
        return {
            "overall": self.overall,
            "subscores": [
                {"name": s.name, "value": s.value,
                 "explanation": s.explanation, "inputs": s.inputs}
                for s in self.subscores
            ],
        }


def _clamp(v: float) -> int:
    return int(max(0, min(100, round(v))))


def compute(bottleneck=None, network: Optional[dict] = None,
            frame_stats=None, recommendations=None) -> PerformanceScore:
    cpu = MONITOR.cpu()
    mem = MONITOR.memory()
    gpus = MONITOR.gpus()
    disks = MONITOR.disks()
    subs: list[SubScore] = []

    # --- CPU Health: thermal headroom + sustained load
    if cpu.utilization is not None:
        load_pen = max(0, cpu.utilization - 40) * 0.5
        temp_pen = 0.0
        temp_note = "temperature unavailable (no sensor readable without a kernel driver)"
        if cpu.temperature_c is not None:
            temp_pen = max(0, cpu.temperature_c - 75) * 2.0
            temp_note = f"{cpu.temperature_c:.0f} °C"
        subs.append(SubScore(
            "CPU Health", _clamp(100 - load_pen - temp_pen),
            f"Starts at 100. Idle load above 40% costs 0.5 points per point "
            f"(measured {cpu.utilization:.0f}%); temperature above 75 °C costs "
            f"2 points per degree ({temp_note}).",
            {"utilization": cpu.utilization, "temperature_c": cpu.temperature_c}))
    else:
        subs.append(SubScore(
            "CPU Health", None,
            "CPU utilization could not be read on this system, so no health score "
            "can be calculated. Phantom Tweeks reports this rather than assuming "
            "a default value.", {}))

    # --- GPU Health
    gpu = next((g for g in gpus if g.utilization is not None), gpus[0] if gpus else None)
    if gpu and gpu.utilization is not None:
        temp_pen = max(0, (gpu.temperature_c or 0) - 80) * 2.0 if gpu.temperature_c else 0
        vram_pen = 0.0
        if gpu.vram_total_mb and gpu.vram_used_mb:
            pct = gpu.vram_used_mb / gpu.vram_total_mb * 100
            vram_pen = max(0, pct - 90) * 2.0
        subs.append(SubScore(
            "GPU Health", _clamp(100 - temp_pen - vram_pen),
            f"Starts at 100. Temperature above 80 °C costs 2 points per degree "
            f"({(str(gpu.temperature_c)+' °C') if gpu.temperature_c else 'unavailable'}); "
            f"VRAM usage above 90% costs 2 points per percent.",
            {"temperature_c": gpu.temperature_c, "utilization": gpu.utilization}))
    else:
        subs.append(SubScore(
            "GPU Health", None,
            "GPU telemetry is unavailable. Live utilization requires nvidia-smi "
            "(NVIDIA) or vendor tooling; Phantom Tweeks will not estimate it.", {}))

    # --- Memory
    if mem.percent is not None:
        cap_pen = 0 if (mem.total_gb or 0) >= 16 else (10 if (mem.total_gb or 0) >= 8 else 25)
        subs.append(SubScore(
            "Memory", _clamp(100 - max(0, mem.percent - 60) * 1.2 - cap_pen),
            f"Starts at 100. Usage above 60% costs 1.2 points per percent "
            f"(measured {mem.percent:.0f}%). Systems under 16 GB lose 10 points, "
            f"under 8 GB lose 25 ({mem.total_gb} GB installed).",
            {"percent": mem.percent, "total_gb": mem.total_gb}))
    else:
        subs.append(SubScore(
            "Memory", None,
            "Memory statistics are unavailable on this system, so no score can be "
            "calculated from measured usage and installed capacity.", {}))

    # --- Storage
    sysd = next((d for d in disks if d.mountpoint.upper().startswith(("C:", "/"))), None)
    if sysd and sysd.total_gb:
        free_pct = sysd.free_gb / sysd.total_gb * 100
        media_pen = {"HDD": 25, "SATA SSD": 5}.get(sysd.media_type or "", 0)
        subs.append(SubScore(
            "Storage", _clamp(100 - max(0, 20 - free_pct) * 3 - media_pen),
            f"Starts at 100. Free space below 20% costs 3 points per percent "
            f"({free_pct:.0f}% free). A system HDD costs 25 points, SATA SSD 5, "
            f"NVMe 0 (detected: {sysd.media_type or 'unknown'}).",
            {"free_pct": round(free_pct, 1), "media": sysd.media_type}))
    else:
        subs.append(SubScore(
            "Storage", None,
            "The system drive could not be read, so free-space headroom and media "
            "type (HDD / SATA SSD / NVMe) could not be scored.", {}))

    # --- Network
    if network and (network.get("internet") or {}).get("latency_ms") is not None:
        net = network["internet"]
        lat, jit = net.get("latency_ms") or 0, net.get("jitter_ms") or 0
        loss = net.get("packet_loss_pct") or 0
        subs.append(SubScore(
            "Network", _clamp(100 - max(0, lat - 30) * 0.5 - jit * 2 - loss * 10),
            f"Starts at 100. Latency above 30 ms costs 0.5/ms ({lat} ms); jitter "
            f"costs 2 points/ms ({jit} ms); packet loss costs 10 points per percent "
            f"({loss}%).",
            {"latency_ms": lat, "jitter_ms": jit, "loss_pct": loss}))
    else:
        subs.append(SubScore(
            "Network", None,
            "Requires a Network Lab run. This score is computed from measured "
            "latency, jitter and packet loss — Phantom Tweeks will not estimate "
            "connection quality without probing it.", {}))

    # --- Background load
    bg = _background_load()
    if bg is not None:
        subs.append(SubScore(
            "Background Load", _clamp(100 - bg * 2),
            f"Starts at 100 and loses 2 points per percent of CPU consumed by "
            f"non-essential background applications (measured {bg:.0f}%).",
            {"background_cpu_pct": round(bg, 1)}))
    else:
        subs.append(SubScore(
            "Background Load", None,
            "The process list is unavailable, so CPU consumed by non-essential "
            "background applications could not be measured.", {}))

    # --- System Configuration
    if recommendations is not None:
        from .catalog import Confidence
        high = sum(1 for r in recommendations if r.confidence == Confidence.HIGH
                   and r.evaluation.applicable)
        med = sum(1 for r in recommendations if r.confidence == Confidence.MEDIUM
                  and r.evaluation.applicable)
        subs.append(SubScore(
            "System Configuration", _clamp(100 - high * 10 - med * 4),
            f"Starts at 100. Each unapplied high-confidence recommendation costs "
            f"10 points ({high} found), each medium-confidence one costs 4 ({med} found).",
            {"high": high, "medium": med}))
    else:
        subs.append(SubScore(
            "System Configuration", None,
            "Requires a Phantom Scan. This score is derived from how many "
            "applicable recommendations remain unapplied on this system, so it "
            "cannot be calculated before the catalog has been evaluated.", {}))

    # --- Gaming Performance (only from measured frames)
    if frame_stats is not None and getattr(frame_stats, "available", False):
        pacing = frame_stats.pacing_score or 0
        ratio = (frame_stats.fps_1_low / frame_stats.avg_fps
                 if frame_stats.avg_fps else 0)
        subs.append(SubScore(
            "Gaming Performance", _clamp(pacing * 0.6 + ratio * 100 * 0.4),
            f"60% frame-pacing score ({pacing:.0f}/100) plus 40% from the ratio of "
            f"1% lows to average FPS ({ratio*100:.0f}%). Derived only from captured "
            f"frame data — never estimated.",
            {"pacing": pacing, "low_ratio": round(ratio, 3)}))
    else:
        subs.append(SubScore(
            "Gaming Performance", None,
            "Requires a real frame-time capture. Run a benchmark while gaming; "
            "Phantom Tweeks does not estimate this from hardware specs.", {}))

    order = ["Gaming Performance", "CPU Health", "GPU Health", "Memory",
             "Storage", "Network", "Background Load", "System Configuration"]
    subs.sort(key=lambda s: order.index(s.name) if s.name in order else 99)
    vals = [s.value for s in subs if s.value is not None]
    return PerformanceScore(subs, int(round(sum(vals) / len(vals))) if vals else None)


def _background_load() -> Optional[float]:
    try:
        import psutil
        from ..core.shield import SHIELD, WINDOWS_ESSENTIAL
    except ImportError:
        return None
    total = 0.0
    try:
        for p in psutil.process_iter(["name", "cpu_percent"]):
            name = (p.info.get("name") or "").lower()
            if name in WINDOWS_ESSENTIAL:
                continue
            total += p.info.get("cpu_percent") or 0.0
    except Exception:
        return None
    cores = psutil.cpu_count() or 1
    return min(100.0, total / cores)
