"""Performance history - stored locally, never uploaded.

Records benchmark and scan results over time so regressions become visible.
The classic use case: a driver update quietly costs you 8% average FPS and
nothing tells you, because you only ever see today's number.

Privacy
-------
Everything is written to the local data directory as plain JSON Lines. Nothing
is transmitted anywhere. There is no telemetry in this module, and the file is
yours to read or delete.

Tiering
-------
The free tier keeps the most recent ``FREE_RETENTION`` entries per metric,
which is enough to answer "is today worse than last time?". Premium keeps the
full history and unlocks trend analysis. The free tier is genuinely useful on
its own; it is not crippled to sell the upgrade.
"""
from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

from ..core import paths

FREE_RETENTION = 10
_FILE = "history.jsonl"

# Metrics where a *lower* number is better.
LOWER_IS_BETTER = {"frametime_ms", "p1_low_ms", "latency_ms", "jitter_ms",
                   "loss_pct", "boot_seconds", "stutter_count"}


@dataclass
class Entry:
    metric: str
    value: float
    at: float = field(default_factory=time.time)
    unit: str = ""
    context: dict = field(default_factory=dict)

    @property
    def when(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(self.at))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Entry":
        return cls(
            metric=str(d.get("metric", "")),
            value=float(d.get("value", 0.0)),
            at=float(d.get("at", 0.0)),
            unit=str(d.get("unit", "")),
            context=d.get("context") or {},
        )


def _path() -> Path:
    return paths.ROOT / _FILE


def record(metric: str, value: float, unit: str = "",
           context: Optional[dict] = None) -> Entry:
    """Append one measurement. Never raises - history is not worth a crash."""
    entry = Entry(metric=metric, value=float(value), unit=unit,
                  context=context or {})
    try:
        paths.ensure_dirs()
        with _path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry.to_dict()) + "\n")
    except OSError:
        pass
    return entry


def load(metric: Optional[str] = None, limit: Optional[int] = None) -> list[Entry]:
    """Read history, oldest first. A corrupt line is skipped, not fatal."""
    p = _path()
    if not p.is_file():
        return []
    out: list[Entry] = []
    try:
        with p.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = Entry.from_dict(json.loads(line))
                except (ValueError, TypeError):
                    continue
                if metric and e.metric != metric:
                    continue
                out.append(e)
    except OSError:
        return []
    out.sort(key=lambda e: e.at)
    if limit:
        out = out[-limit:]
    return out


def metrics() -> list[str]:
    return sorted({e.metric for e in load()})


def clear(metric: Optional[str] = None) -> int:
    """Delete history. Returns how many entries were removed."""
    entries = load()
    keep = [e for e in entries if metric and e.metric != metric]
    removed = len(entries) - len(keep)
    try:
        if keep:
            with _path().open("w", encoding="utf-8") as fh:
                for e in keep:
                    fh.write(json.dumps(e.to_dict()) + "\n")
        elif _path().exists():
            _path().unlink()
    except OSError:
        return 0
    return removed


@dataclass
class Trend:
    metric: str
    samples: int = 0
    latest: Optional[float] = None
    previous: Optional[float] = None
    best: Optional[float] = None
    worst: Optional[float] = None
    mean: Optional[float] = None
    change_pct: Optional[float] = None
    improved: Optional[bool] = None
    unit: str = ""
    verdict: str = ""

    def render(self) -> str:
        if self.samples == 0:
            return f"{self.metric}: no data yet."
        if self.samples == 1:
            return (f"{self.metric}: {self.latest:g}{self.unit} "
                    "(first measurement - nothing to compare yet)")
        arrow = "" if self.improved is None else ("better" if self.improved else "worse")
        pct = "" if self.change_pct is None else f" ({self.change_pct:+.1f}%)"
        return (f"{self.metric}: {self.latest:g}{self.unit}{pct} {arrow}\n"
                f"  best {self.best:g} | worst {self.worst:g} | "
                f"mean {self.mean:.1f} over {self.samples} runs\n"
                f"  {self.verdict}")


def _noise_floor(values: list[float]) -> float:
    """Below this, a change is measurement noise rather than a real change."""
    # The floor is deliberately generous. Claiming a 2% "improvement" that is
    # really measurement noise is exactly the dishonesty this project avoids,
    # so we would rather miss a small real change than invent one.
    if len(values) < 3:
        return 5.0
    try:
        spread = statistics.pstdev(values)
        mean = statistics.fmean(values)
        if mean:
            # Two standard deviations, clamped to a sane range.
            return max(3.0, min(15.0, (spread / abs(mean)) * 100 * 2))
    except statistics.StatisticsError:
        pass
    return 5.0


def trend(metric: str, limit: Optional[int] = None) -> Trend:
    """Summarise a metric's direction over time.

    Deliberately conservative: a change smaller than the observed run-to-run
    noise is reported as "no real change" rather than dressed up as a win.
    """
    entries = load(metric, limit=limit)
    t = Trend(metric=metric, samples=len(entries))
    if not entries:
        t.verdict = "No measurements recorded yet."
        return t

    values = [e.value for e in entries]
    t.unit = entries[-1].unit
    t.latest = values[-1]
    t.mean = statistics.fmean(values)
    lower_better = metric in LOWER_IS_BETTER
    t.best = min(values) if lower_better else max(values)
    t.worst = max(values) if lower_better else min(values)

    if len(values) == 1:
        t.verdict = "First measurement. Run again later to see a trend."
        return t

    t.previous = values[-2]
    if t.previous:
        delta = (t.latest - t.previous) / abs(t.previous) * 100
        t.change_pct = delta
        floor = _noise_floor(values)
        if abs(delta) < floor:
            t.improved = None
            t.verdict = (f"Within normal variation (+/-{floor:.0f}%). "
                         "No real change.")
        else:
            t.improved = (delta < 0) if lower_better else (delta > 0)
            t.verdict = ("Improved since the last run."
                         if t.improved else
                         "Worse than the last run. If you changed drivers or "
                         "settings recently, that is the first place to look.")
    else:
        t.verdict = "Previous measurement was zero; cannot compare."
    return t


def summary(premium: Optional[bool] = None) -> dict:
    """History overview, respecting the free-tier retention limit."""
    if premium is None:
        try:
            from ..core import premium as _p
            premium = _p.is_premium()
        except Exception:
            premium = False

    all_metrics = metrics()
    limit = None if premium else FREE_RETENTION
    trends = [trend(m, limit=limit) for m in all_metrics]
    total = len(load())

    out = {
        "premium": bool(premium),
        "metrics": all_metrics,
        "trends": trends,
        "total_entries": total,
        "retention": "unlimited" if premium else f"last {FREE_RETENTION} per metric",
    }
    if not premium and total > FREE_RETENTION:
        out["note"] = (
            f"{total} measurements are stored. The free tier charts the last "
            f"{FREE_RETENTION} per metric; Premium charts all of them. "
            "Your data is kept either way - nothing is deleted."
        )
    return out


def regressions(threshold_pct: float = 10.0) -> list[Trend]:
    """Metrics that got meaningfully worse. Used for proactive warnings."""
    out = []
    for m in metrics():
        t = trend(m)
        if (t.improved is False and t.change_pct is not None
                and abs(t.change_pct) >= threshold_pct):
            out.append(t)
    return out
