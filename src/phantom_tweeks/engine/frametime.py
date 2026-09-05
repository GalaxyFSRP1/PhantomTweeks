"""Frame-Time Analyzer and benchmarking.

Honesty constraint: Phantom Tweeks cannot invent FPS data. It reads frame times
from a real source (PresentMon, shipped separately by the user, or an imported
CapFrameX/MSI Afterburner CSV). If no source is available it says so and the
FPS fields render as "n/a" — it never simulates numbers and presents them as
measurements.
"""
from __future__ import annotations

import csv
import json
import shutil
import statistics
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..core import paths
from ..core.logging_setup import get_logger
from ..core import runproc

log = get_logger("frametime")


@dataclass
class FrameTimeStats:
    source: str
    frames: int = 0
    duration_s: Optional[float] = None
    avg_fps: Optional[float] = None
    avg_ms: Optional[float] = None
    p1_low_ms: Optional[float] = None     # 1% low frame time (worst 1%)
    p01_low_ms: Optional[float] = None
    fps_1_low: Optional[float] = None
    fps_01_low: Optional[float] = None
    max_ms: Optional[float] = None
    stutter_count: int = 0
    pacing_score: Optional[float] = None  # 0-100
    pacing_label: str = "Unknown"
    available: bool = False
    message: str = ""
    samples: list[float] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["samples"] = self.samples[:2000]
        return d

    def render(self) -> str:
        if not self.available:
            return f"FRAME TIME\n\nUnavailable.\n{self.message}"
        bar_filled = int(round((self.pacing_score or 0) / 100 * 18))
        bar = "█" * bar_filled + "░" * (18 - bar_filled)
        return (
            "FRAME TIME\n\n"
            f"Average:  {self.avg_ms:.1f} ms  ({self.avg_fps:.0f} FPS)\n"
            f"1% Low:   {self.p1_low_ms:.1f} ms  ({self.fps_1_low:.0f} FPS)\n"
            f"0.1% Low: {self.p01_low_ms:.1f} ms  ({self.fps_01_low:.0f} FPS)\n\n"
            f"Frame pacing:\n{bar}  {self.pacing_label}"
        )


def _percentile_worst(sorted_desc: list[float], pct: float) -> float:
    """Worst `pct`% of frame times, averaged — the standard 1%-low definition."""
    n = max(1, int(len(sorted_desc) * pct / 100))
    return statistics.fmean(sorted_desc[:n])


def analyze_frame_times(frame_times_ms: list[float], source: str) -> FrameTimeStats:
    st = FrameTimeStats(source=source, samples=list(frame_times_ms))
    valid = [f for f in frame_times_ms if f and f > 0]
    if len(valid) < 30:
        st.message = ("Not enough frames captured for a meaningful analysis "
                      "(at least 30 required).")
        return st
    st.available = True
    st.frames = len(valid)
    st.duration_s = round(sum(valid) / 1000, 1)
    st.avg_ms = round(statistics.fmean(valid), 2)
    st.avg_fps = round(1000 / st.avg_ms, 1)
    st.max_ms = round(max(valid), 2)

    desc = sorted(valid, reverse=True)
    st.p1_low_ms = round(_percentile_worst(desc, 1.0), 2)
    st.p01_low_ms = round(_percentile_worst(desc, 0.1), 2)
    st.fps_1_low = round(1000 / st.p1_low_ms, 1)
    st.fps_01_low = round(1000 / st.p01_low_ms, 1)

    # A stutter = a frame taking more than twice the running average.
    st.stutter_count = sum(1 for f in valid if f > st.avg_ms * 2)

    # Pacing score from consecutive-frame variance, not raw stdev: the eye
    # notices frame-to-frame *changes*, not absolute spread.
    deltas = [abs(b - a) for a, b in zip(valid, valid[1:])]
    mad = statistics.fmean(deltas)
    ratio = mad / st.avg_ms if st.avg_ms else 1
    st.pacing_score = round(max(0.0, min(100.0, 100 * (1 - ratio * 4))), 1)
    st.pacing_label = ("Excellent" if st.pacing_score >= 85 else
                       "Good" if st.pacing_score >= 70 else
                       "Fair" if st.pacing_score >= 50 else "Poor")
    return st


def diagnose(stats: FrameTimeStats, cpu_util: Optional[float] = None,
             gpu_util: Optional[float] = None) -> list[str]:
    if not stats.available:
        return [stats.message]
    notes: list[str] = []
    if stats.stutter_count:
        rate = stats.stutter_count / stats.frames * 100
        notes.append(f"{stats.stutter_count} frame-time spikes detected "
                     f"({rate:.1f}% of frames took more than double the average).")
    if stats.fps_1_low and stats.avg_fps and stats.fps_1_low < stats.avg_fps * 0.6:
        notes.append("1% lows are far below the average frame rate. This is felt as "
                     "stutter even when the average FPS looks healthy.")
    if (gpu_util or 0) >= 95:
        notes.append("The GPU is saturated during capture: spikes are most likely "
                     "GPU-bound. Lowering graphics settings should raise the lows.")
    elif (cpu_util or 0) >= 90:
        notes.append("The CPU was near saturation during capture: spikes are most "
                     "likely CPU-bound or caused by background load.")
    elif stats.stutter_count and (gpu_util or 0) < 80 and (cpu_util or 0) < 80:
        notes.append("Neither the CPU nor GPU was saturated during the spikes, which "
                     "points at background interference, shader compilation, or "
                     "storage stalls rather than raw hardware limits.")
    if not notes:
        notes.append("Frame pacing looks healthy. No change recommended.")
    return notes


# ---------------- capture sources ----------------

def find_presentmon() -> Optional[str]:
    """PresentMon is the only reliable frame-time source on Windows.

    We never bundle or auto-download it; the user supplies it and we use it if present.
    """
    for name in ("PresentMon.exe", "PresentMon-2.3.0-x64.exe", "presentmon"):
        found = shutil.which(name)
        if found:
            return found
    local = paths.ROOT / "tools" / "PresentMon.exe"
    return str(local) if local.exists() else None


def capture(seconds: int = 30, process_name: Optional[str] = None) -> FrameTimeStats:
    """Capture live frame times via PresentMon when available."""
    exe = find_presentmon()
    if not exe:
        return FrameTimeStats(
            source="none",
            message=("No frame-time source available. Phantom Tweeks reads real frame "
                     "data from PresentMon (Intel, free) — place PresentMon.exe in "
                     f"{paths.ROOT / 'tools'} or on PATH. Phantom Tweeks will not "
                     "estimate or simulate FPS."))
    out_csv = paths.BENCHMARKS / f"capture-{datetime.now():%Y%m%d-%H%M%S}.csv"
    cmd = [exe, "-output_file", str(out_csv), "-timed", str(seconds),
           "-terminate_after_timed", "-stop_existing_session"]
    if process_name:
        cmd += ["-process_name", process_name]
    try:
        runproc.run(cmd, capture_output=True, timeout=seconds + 60)
    except Exception as e:
        return FrameTimeStats(source="presentmon",
                              message=f"PresentMon capture failed: {e}")
    return import_csv(out_csv)


def import_csv(path: str | Path) -> FrameTimeStats:
    """Import PresentMon / CapFrameX / Afterburner style CSV frame data."""
    p = Path(path)
    if not p.exists():
        return FrameTimeStats(source="csv", message=f"File not found: {p}")
    candidates = ("msbetweenpresents", "frametime", "frame time", "ms",
                  "msbetweendisplaychange")
    try:
        with p.open(newline="", encoding="utf-8", errors="ignore") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                return FrameTimeStats(source="csv", message="CSV has no header row.")
            col = next((f for f in reader.fieldnames
                        if f and f.strip().lower() in candidates), None)
            if col is None:
                col = next((f for f in reader.fieldnames
                            if f and any(c in f.strip().lower() for c in candidates)), None)
            if col is None:
                return FrameTimeStats(
                    source="csv",
                    message="No frame-time column found. Expected a column such as "
                            "'msBetweenPresents' or 'frametime'.")
            values = []
            for row in reader:
                try:
                    values.append(float(row[col]))
                except (TypeError, ValueError):
                    continue
    except OSError as e:
        return FrameTimeStats(source="csv", message=f"Could not read CSV: {e}")
    return analyze_frame_times(values, source=f"csv:{p.name}")


# ---------------- benchmark storage ----------------

def save_benchmark(stats: FrameTimeStats, label: str, game: Optional[str] = None,
                   network_ms: Optional[float] = None) -> str:
    paths.ensure_dirs()
    rec = {
        "id": f"{datetime.now():%Y%m%d-%H%M%S}",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "label": label, "game": game, "network_ms": network_ms,
        "stats": stats.as_dict(),
    }
    path = paths.BENCHMARKS / f"bench-{rec['id']}.json"
    path.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    return str(path)


def list_benchmarks(game: Optional[str] = None) -> list[dict]:
    out = []
    for p in sorted(paths.BENCHMARKS.glob("bench-*.json"), reverse=True):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if game is None or rec.get("game") == game:
            out.append(rec)
    return out
