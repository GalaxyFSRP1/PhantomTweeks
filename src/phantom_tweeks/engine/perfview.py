"""A single consolidated view of everything measurable on this PC.

Why this exists
---------------
The information was already there, but scattered: CPU on the dashboard, disks
in Storage Lab, GPU in Hardware, temperatures in Health. If you wanted to
answer "is anything on this machine struggling right now?" you had to visit
five pages and hold the numbers in your head.

This assembles one report covering every CPU core, every GPU, memory, and
**every attached drive** - not just the system drive - plus network adapters
and the hottest processes.

Honesty rules
-------------
* Anything that cannot be read is reported as ``not measured``. There are no
  estimated or interpolated values anywhere in this module.
* Verdicts describe what was measured, never a predicted improvement.
* A drive reporting a non-healthy SMART status is surfaced prominently,
  because that is hardware failure and no software tweak addresses it.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


def _fmt(value, unit="", nd=0):
    if value is None:
        return "not measured"
    if isinstance(value, float):
        return f"{value:.{nd}f}{unit}"
    return f"{value}{unit}"


@dataclass
class Reading:
    """One measured value with an interpretation."""

    label: str
    value: Optional[float] = None
    unit: str = ""
    detail: str = ""
    level: str = "ok"          # ok | info | warn | bad
    decimals: int = 0

    def render(self) -> str:
        mark = {"ok": "  ", "info": "  ", "warn": "! ", "bad": "!!"}[self.level]
        out = f"{mark}{self.label:<26} {_fmt(self.value, self.unit, self.decimals)}"
        if self.detail:
            out += f"\n      {self.detail}"
        return out


@dataclass
class Section:
    title: str
    readings: list = field(default_factory=list)
    note: str = ""

    @property
    def worst(self) -> str:
        order = {"ok": 0, "info": 1, "warn": 2, "bad": 3}
        return max((r.level for r in self.readings), key=lambda l: order[l],
                   default="ok")

    def render(self) -> str:
        out = [f"{self.title}", "-" * max(20, len(self.title))]
        out += [r.render() for r in self.readings]
        if self.note:
            out += ["", f"  {self.note}"]
        return "\n".join(out)


@dataclass
class PerfReport:
    sections: list = field(default_factory=list)
    at: float = field(default_factory=time.time)

    @property
    def warnings(self) -> list:
        return [r for s in self.sections for r in s.readings
                if r.level in ("warn", "bad")]

    def render(self) -> str:
        stamp = time.strftime("%H:%M:%S", time.localtime(self.at))
        out = [f"SYSTEM PERFORMANCE  ({stamp})", ""]
        for s in self.sections:
            out += [s.render(), ""]
        problems = self.warnings
        if problems:
            out += ["ATTENTION", "-" * 20]
            out += [f"  {r.label}: {r.detail or 'see above'}" for r in problems]
        else:
            out += ["Nothing needs attention. Every measurable value is within "
                    "a normal range."]
        return "\n".join(out)


# ------------------------------------------------------------------ CPU

def cpu_section() -> Section:
    from ..hardware.monitor import MONITOR
    s = Section("PROCESSOR")
    try:
        c = MONITOR.cpu()
    except Exception as exc:
        s.note = f"CPU details unavailable: {exc}"
        return s

    s.readings.append(Reading("Model", None, detail=c.model or "unknown"))
    s.readings.append(Reading(
        "Cores", c.physical_cores, " physical",
        detail=f"{c.logical_cores or '?'} logical threads ({c.architecture})"))
    s.readings.append(Reading("Clock", c.current_mhz, " MHz",
                              detail=f"maximum {_fmt(c.max_mhz, ' MHz')}"))

    util = c.utilization
    level = "ok"
    detail = ""
    if util is not None:
        if util >= 95:
            level, detail = "warn", ("Pinned at maximum. Something is using "
                                     "every cycle available.")
        elif util >= 80:
            level, detail = "info", "Heavily loaded."
    s.readings.append(Reading("Utilisation", util, "%", detail, level))

    temp = c.temperature_c
    tl, td = "ok", ""
    if temp is not None:
        if temp >= 95:
            tl, td = "bad", ("Thermal throttling is very likely. Clean the "
                             "cooler and check airflow - this costs more "
                             "performance than any software tweak recovers.")
        elif temp >= 85:
            tl, td = "warn", "Running hot. Check cooling and dust."
    elif not td:
        td = "No readable sensor. Most consumer boards need vendor tooling."
    s.readings.append(Reading("Temperature", temp, " C", td, tl))

    per_core = getattr(c, "per_core", None)
    if per_core:
        hottest = max(per_core)
        spread = hottest - min(per_core)
        s.readings.append(Reading(
            "Busiest core", hottest, "%",
            f"{len(per_core)} cores, {spread:.0f}% spread between busiest and "
            "quietest" + (". A single saturated core usually means a "
                          "single-threaded bottleneck." if spread > 60 else ""),
            "info" if spread > 60 else "ok"))

    s.readings.append(Reading("Power plan", None, detail=c.power_plan or "unknown"))
    return s


# ------------------------------------------------------------------ GPU

def gpu_section() -> Section:
    from ..hardware.monitor import MONITOR
    s = Section("GRAPHICS")
    try:
        gpus = MONITOR.gpus()
    except Exception as exc:
        s.note = f"GPU details unavailable: {exc}"
        return s
    if not gpus:
        s.note = ("No GPU reported. On Windows this needs WMI; vendor tools "
                  "give fuller data.")
        return s

    for i, g in enumerate(gpus):
        prefix = f"GPU {i}" if len(gpus) > 1 else "GPU"
        s.readings.append(Reading(f"{prefix} model", None,
                                  detail=f"{g.model} ({g.vendor})"))
        s.readings.append(Reading(f"{prefix} driver", None,
                                  detail=g.driver_version or "not measured"))
        if g.vram_total_mb:
            used = g.vram_used_mb
            pct = (used / g.vram_total_mb * 100) if used else None
            lvl = "warn" if pct and pct >= 92 else "ok"
            s.readings.append(Reading(
                f"{prefix} memory", g.vram_total_mb, " MB",
                (f"{used:.0f} MB in use ({pct:.0f}%)" if used else "usage not measured")
                + (". Exceeding VRAM causes severe stutter as textures stream "
                   "over PCIe - lowering texture quality one step usually "
                   "fixes it." if lvl == "warn" else ""), lvl))
        s.readings.append(Reading(f"{prefix} load", g.utilization, "%"))
        gl = "warn" if (g.temperature_c or 0) >= 85 else "ok"
        s.readings.append(Reading(f"{prefix} temperature", g.temperature_c, " C",
                                  "Hot. Check case airflow." if gl == "warn" else "",
                                  gl))
    return s


# --------------------------------------------------------------- memory

def memory_section() -> Section:
    from ..hardware.monitor import MONITOR
    s = Section("MEMORY")
    try:
        m = MONITOR.memory()
    except Exception as exc:
        s.note = f"Memory details unavailable: {exc}"
        return s

    lvl, detail = "ok", ""
    if m.percent is not None:
        if m.percent >= 92:
            lvl, detail = "warn", ("Almost full. Windows will start paging to "
                                   "disk, which causes stutter.")
        elif m.percent >= 80:
            lvl = "info"
    s.readings.append(Reading("Total", m.total_gb, " GB",
                              f"{m.used_gb} GB in use ({m.percent}%)", lvl))
    if detail:
        s.readings[-1].detail = detail

    if m.speed_mhz:
        slow = m.speed_mhz < 3000
        s.readings.append(Reading(
            "Speed", m.speed_mhz, " MT/s",
            f"across {m.modules} module(s)"
            + (". If your kit is rated faster than this, XMP/EXPO is probably "
               "off in the BIOS - one of the few changes with a large, "
               "consistent effect." if slow else ""),
            "info" if slow else "ok"))
    else:
        s.readings.append(Reading("Speed", None,
                                  detail="Not measured (needs WMI on Windows)"))
    return s


# --------------------------------------------------------------- storage

def storage_section() -> Section:
    """Every attached drive, not just the system one."""
    s = Section("STORAGE")
    try:
        from . import storage as _storage
        report = _storage.scan()
    except Exception as exc:
        s.note = f"Storage details unavailable: {exc}"
        return s

    disks = report.disks or []
    if not disks:
        s.note = "No drives reported."
        return s

    for d in disks:
        name = d.mountpoint or d.device or "?"
        pct = d.percent_used
        lvl, detail = "ok", ""
        if pct is not None:
            free_pct = 100 - pct
            if free_pct < 5:
                lvl, detail = "bad", ("Critically full. Windows needs free "
                                      "space for paging and shader "
                                      "compilation.")
            elif free_pct < 10:
                lvl, detail = "warn", ("Low. Expect stutter during shader "
                                       "compilation.")
            elif free_pct < 20:
                lvl = "info"
        media = d.media_type or "type not measured"
        s.readings.append(Reading(
            f"{name}", d.total_gb, " GB",
            f"{_fmt(d.free_gb, ' GB', 1)} free ({100 - (pct or 0):.0f}%)  -  {media}"
            + (f"\n      {detail}" if detail else ""), lvl, 1))

        if d.read_mb_s is not None or d.write_mb_s is not None:
            s.readings.append(Reading(
                f"  {name} throughput", None,
                detail=f"read {_fmt(d.read_mb_s, ' MB/s', 1)}, "
                       f"write {_fmt(d.write_mb_s, ' MB/s', 1)}"))
        if d.temperature_c is not None:
            tl = "warn" if d.temperature_c >= 70 else "ok"
            s.readings.append(Reading(f"  {name} temperature", d.temperature_c,
                                      " C", "NVMe drives throttle when hot."
                                      if tl == "warn" else "", tl))
        if d.health and d.health.lower() not in ("healthy", "ok"):
            s.readings.append(Reading(
                f"  {name} SMART", None,
                detail=f"Reports '{d.health}'. Back up your data now and check "
                       "with the manufacturer's tool. This is hardware, and no "
                       "software setting will fix it.", level="bad"))

    hdds = [p for p in (report.physical or []) if p.get("media_type") == "HDD"]
    if hdds:
        s.note = ("A mechanical drive is present. Moving your most-played game "
                  "to an SSD is the single largest real-world improvement "
                  "available on this system - far more than any software "
                  "tweak.")
    return s


# --------------------------------------------------------------- network

def network_section() -> Section:
    s = Section("NETWORK")
    try:
        import psutil
    except ImportError:
        s.note = "psutil is not available, so adapters cannot be listed."
        return s

    try:
        stats = psutil.net_if_stats()
        counters = psutil.net_io_counters(pernic=True)
    except Exception as exc:
        s.note = f"Adapter details unavailable: {exc}"
        return s

    live = [(n, st) for n, st in stats.items() if st.isup and n != "lo"]
    if not live:
        s.note = "No active adapters."
        return s

    for name, st in live:
        speed = st.speed or None
        io = counters.get(name)
        detail = f"{_fmt(speed, ' Mb/s')} link"
        if io:
            detail += (f", {io.bytes_recv / 1e9:.1f} GB received, "
                       f"{io.bytes_sent / 1e9:.1f} GB sent")
            if io.dropin or io.dropout:
                detail += f", {io.dropin + io.dropout} dropped"
        lvl = "warn" if (io and (io.errin or io.errout)) else "ok"
        if lvl == "warn":
            detail += (f"\n      {io.errin + io.errout} errors - a failing "
                       "cable or driver is a real cause of lag spikes.")
        s.readings.append(Reading(name, None, detail=detail, level=lvl))
    return s


# ------------------------------------------------------------- processes

def process_section(top: int = 6) -> Section:
    s = Section("HEAVIEST PROCESSES")
    try:
        import psutil
    except ImportError:
        s.note = "psutil is not available."
        return s

    try:
        procs = []
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                p.cpu_percent(None)
                procs.append(p)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        time.sleep(0.4)
        rows = []
        for p in procs:
            try:
                cpu = p.cpu_percent(None)
                mem = (p.info.get("memory_info").rss / 1048576
                       if p.info.get("memory_info") else 0)
                rows.append((p.info.get("name") or "?", cpu, mem))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as exc:
        s.note = f"Process list unavailable: {exc}"
        return s

    rows.sort(key=lambda r: (r[1], r[2]), reverse=True)
    for name, cpu, mem in rows[:top]:
        s.readings.append(Reading(name, cpu, "% CPU",
                                  f"{mem:.0f} MB memory"))
    s.note = ("Reported only. Phantom Tweeks never terminates or reprioritises "
              "a process on your behalf.")
    return s


# ---------------------------------------------------------------- report

def build() -> PerfReport:
    report = PerfReport()
    for fn in (cpu_section, gpu_section, memory_section, storage_section,
               network_section, process_section):
        try:
            report.sections.append(fn())
        except Exception as exc:                      # pragma: no cover
            report.sections.append(
                Section(fn.__name__, note=f"Unavailable: {exc}"))
    return report
