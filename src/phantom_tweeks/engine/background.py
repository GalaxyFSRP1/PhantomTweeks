"""Smart Background Analyzer.

Reports resource consumers. It never terminates, suspends, or reprioritises
anything — every candidate action is routed through Phantom Shield first, and
even unprotected apps are only ever *suggested* to the user.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from ..core.shield import SHIELD, WINDOWS_ESSENTIAL


@dataclass
class BackgroundApp:
    name: str
    pid: int
    cpu_percent: float
    ram_mb: float
    protected: bool
    protection_label: str = ""
    instances: int = 1

    def render(self) -> str:
        line = (f"{self.name}\nCPU: {self.cpu_percent:.0f}%\n"
                f"RAM: {self.ram_mb/1024:.1f} GB" if self.ram_mb >= 1024
                else f"{self.name}\nCPU: {self.cpu_percent:.0f}%\nRAM: {self.ram_mb:.0f} MB")
        if self.protected:
            line += "\nProtected ✓"
        return line


@dataclass
class BackgroundReport:
    apps: list[BackgroundApp] = field(default_factory=list)
    recommendation: str = ""
    heavy: list[BackgroundApp] = field(default_factory=list)

    def render(self) -> str:
        out = ["BACKGROUND ANALYZER", ""]
        for a in self.apps[:12]:
            out += [a.render(), ""]
        out += ["Recommendation:", self.recommendation]
        return "\n".join(out)


def analyze(top: int = 12, sample_seconds: float = 1.0,
            cpu_threshold: float = 10.0) -> BackgroundReport:
    try:
        import psutil
    except ImportError:
        return BackgroundReport(recommendation="Process information unavailable.")

    procs = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            p.cpu_percent(None)   # prime
            procs.append(p)
        except Exception:
            continue
    time.sleep(sample_seconds)

    cores = psutil.cpu_count() or 1
    merged: dict[str, BackgroundApp] = {}
    for p in procs:
        try:
            name = p.info.get("name") or ""
            if not name or name.lower() in ("system idle process",):
                continue
            cpu = p.cpu_percent(None) / cores
            ram = p.memory_info().rss / 1024 / 1024
        except Exception:
            continue
        hit = SHIELD.classify(name)
        key = (hit[1] if hit else name)
        if key in merged:
            a = merged[key]
            a.cpu_percent += cpu
            a.ram_mb += ram
            a.instances += 1
        else:
            merged[key] = BackgroundApp(
                name=key, pid=p.info["pid"], cpu_percent=cpu, ram_mb=ram,
                protected=bool(hit), protection_label=hit[1] if hit else "")

    apps = sorted(merged.values(),
                  key=lambda a: (a.cpu_percent, a.ram_mb), reverse=True)[:top]
    report = BackgroundReport(apps=apps)
    report.heavy = [a for a in apps
                    if a.cpu_percent >= cpu_threshold
                    and not a.protected
                    and a.name.lower() not in WINDOWS_ESSENTIAL]

    if not report.heavy:
        report.recommendation = "No action required."
    else:
        lines = []
        for a in report.heavy:
            lines.append(
                f"{a.name} is using {a.cpu_percent:.0f}% CPU and "
                f"{a.ram_mb:.0f} MB RAM. Closing it may improve available CPU "
                f"resources, but Phantom Tweeks will not close it automatically.")
        report.recommendation = "\n\n".join(lines)
    return report


def request_close(process_name: str) -> tuple[bool, str]:
    """There is deliberately no automatic kill path. This explains why."""
    decision = SHIELD.guard(process_name, "terminate")
    if not decision.allowed:
        return False, decision.reason
    return False, (
        f"Phantom Tweeks does not terminate applications. Close {process_name} "
        "yourself if you want its resources back — this keeps the product from "
        "ever killing something you needed.")
