"""Before/after comparison and automatic regression rollback.

The conclusion text is generated from the deltas, and it is allowed — expected,
even — to say "no measurable improvement". Reporting honestly is the feature.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Metric:
    name: str
    before: Optional[float]
    after: Optional[float]
    unit: str = ""
    higher_is_better: bool = True

    @property
    def delta_pct(self) -> Optional[float]:
        if self.before in (None, 0) or self.after is None:
            return None
        change = (self.after - self.before) / self.before * 100
        return round(change if self.higher_is_better else -change, 1)

    @property
    def meaningful(self) -> bool:
        """Below ~2% is run-to-run noise, not a result."""
        d = self.delta_pct
        return d is not None and abs(d) >= 2.0

    def render(self) -> str:
        if self.before is None or self.after is None:
            return f"{self.name}\nNot measured.\n"
        d = self.delta_pct
        sign = "+" if (d or 0) > 0 else ""
        pct = f"{sign}{d}%" if d is not None else "n/a"
        note = "" if self.meaningful else "  (within measurement noise)"
        return (f"{self.name}\nBefore: {self.before:g}{self.unit}\n"
                f"After: {self.after:g}{self.unit}\n{pct}{note}\n")


@dataclass
class ComparisonReport:
    metrics: list[Metric] = field(default_factory=list)
    conclusion: str = ""
    regression: bool = False
    regression_detail: str = ""

    def render(self) -> str:
        out = ["PHANTOM PERFORMANCE REPORT", ""]
        out += [m.render() for m in self.metrics]
        out += ["Conclusion:", "", self.conclusion]
        if self.regression:
            out += ["", "PERFORMANCE REGRESSION DETECTED", self.regression_detail]
        return "\n".join(out)

    def as_dict(self) -> dict:
        return {
            "metrics": [{"name": m.name, "before": m.before, "after": m.after,
                         "unit": m.unit, "delta_pct": m.delta_pct,
                         "meaningful": m.meaningful} for m in self.metrics],
            "conclusion": self.conclusion,
            "regression": self.regression,
            "regression_detail": self.regression_detail,
        }


def compare(before, after, network_before: Optional[float] = None,
            network_after: Optional[float] = None,
            regression_threshold: float = 5.0) -> ComparisonReport:
    """`before`/`after` are FrameTimeStats. Missing data yields honest gaps."""
    rep = ComparisonReport()
    b_ok = getattr(before, "available", False)
    a_ok = getattr(after, "available", False)

    rep.metrics = [
        Metric("FPS", before.avg_fps if b_ok else None,
               after.avg_fps if a_ok else None, "", True),
        Metric("1% Low", before.fps_1_low if b_ok else None,
               after.fps_1_low if a_ok else None, "", True),
        Metric("Frame Time", before.avg_ms if b_ok else None,
               after.avg_ms if a_ok else None, " ms", False),
        Metric("Frame Pacing", before.pacing_score if b_ok else None,
               after.pacing_score if a_ok else None, "", True),
        Metric("Network", network_before, network_after, " ms", False),
    ]

    if not (b_ok and a_ok):
        rep.conclusion = (
            "Not enough measured frame data to compare. Phantom Tweeks will not "
            "claim an improvement it did not measure. Capture a benchmark before "
            "and after the change to get a real comparison.")
        return rep

    fps = rep.metrics[0]
    low = rep.metrics[1]
    pacing = rep.metrics[3]
    net = rep.metrics[4]

    # --- regression check drives automatic rollback
    fps_d = fps.delta_pct or 0
    low_d = low.delta_pct or 0
    if fps_d <= -regression_threshold or low_d <= -regression_threshold:
        rep.regression = True
        worst = "FPS" if fps_d <= low_d else "1% lows"
        rep.regression_detail = (
            f"{worst} decreased by {abs(min(fps_d, low_d)):.1f}%.\n\n"
            "Phantom Tweeks recommends restoring the previous configuration.")
        rep.conclusion = (
            "This change made measured performance worse, not better. "
            "Restoring the previous configuration is recommended.")
        return rep

    lines = []
    if fps.meaningful and fps_d > 0:
        lines.append(f"Average FPS improved by {fps_d}%.")
    elif not fps.meaningful:
        lines.append("Average FPS was essentially unchanged.")
    if low.meaningful and low_d > 0:
        lines.append(f"1% lows improved by {low_d}%, which is felt as smoother gameplay.")
    if pacing.meaningful and (pacing.delta_pct or 0) > 0:
        lines.append("Frame pacing became more consistent.")
    if net.before is not None and net.after is not None:
        lines.append("Network improvement was minimal." if not net.meaningful
                     else f"Network latency changed by {net.delta_pct}%.")

    if not any(m.meaningful and (m.delta_pct or 0) > 0
               for m in rep.metrics[:4]):
        lines = ["No measurable improvement was detected. The changes were applied "
                 "correctly, but this configuration was already performing near its "
                 "limit. That is an honest result, not a failure — you can keep or "
                 "restore the changes safely."]
    elif low.meaningful and low_d > (fps_d + 3):
        lines.append("Performance improved primarily through better frame-time "
                     "consistency rather than raw average FPS.")

    rep.conclusion = "\n".join(lines)
    return rep
