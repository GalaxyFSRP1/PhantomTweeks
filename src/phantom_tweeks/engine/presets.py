"""Optimization presets — named bundles of catalog entries.

A preset is a *filter over what the scan already found*, never a fixed list of
changes to force onto the machine. If the scan says an optimization is already
optimal or does not apply to this hardware, no preset can resurrect it. This
keeps presets honest: "Competitive" on an already-tuned PC legitimately selects
nothing, and that is a good outcome rather than a failure.

Presets never include NOT_RECOMMENDED items, and never include anything marked
`advanced`. The strictest tier available is always the default.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from .catalog import CATALOG, Category, Confidence, Optimization, Risk


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    tagline: str
    description: str
    #: Confidence levels a recommendation must have to be included.
    confidences: tuple = (Confidence.HIGH,)
    #: Risk levels permitted. Anything riskier is excluded outright.
    max_risk: Risk = Risk.LOW
    #: Optional restriction to particular catalog areas.
    areas: tuple = ()
    #: Explicit opt-outs by optimization id, whatever else matches.
    exclude: tuple = ()
    #: Honest statement of what this preset will not do.
    caveat: str = ""

    def matches(self, opt: Optimization, confidence: Confidence) -> bool:
        if opt.id in self.exclude:
            return False
        if opt.advanced:
            return False
        if confidence not in self.confidences:
            return False
        if _RISK_ORDER[opt.risk] > _RISK_ORDER[self.max_risk]:
            return False
        if self.areas and opt.area not in self.areas:
            return False
        return True


_RISK_ORDER = {Risk.LOW: 0, Risk.MEDIUM: 1, Risk.HIGH: 2}


PRESETS: list[Preset] = [
    Preset(
        id="safe",
        name="Safe",
        tagline="Only changes that are hard to get wrong.",
        description=(
            "High-confidence, low-risk, fully reversible changes only. This is "
            "the right starting point for almost everyone, and the only tier we "
            "would run unattended. If it selects nothing, your system is already "
            "in good shape."
        ),
        confidences=(Confidence.HIGH,),
        max_risk=Risk.LOW,
        caveat="Will not touch anything with a meaningful tradeoff.",
    ),
    Preset(
        id="balanced",
        name="Balanced",
        tagline="Safe changes plus a few worth considering.",
        description=(
            "Everything in Safe, plus medium-confidence changes where the "
            "tradeoff is small and clearly explained. Read the reason on each "
            "card before applying: medium confidence means we expect a benefit "
            "but cannot promise one on your specific hardware."
        ),
        confidences=(Confidence.HIGH, Confidence.MEDIUM),
        max_risk=Risk.MEDIUM,
        caveat="Some items trade a convenience feature for responsiveness.",
    ),
    Preset(
        id="competitive",
        name="Competitive",
        tagline="Input responsiveness above visual comfort.",
        description=(
            "Focuses on input latency, scheduling and frame pacing: mouse "
            "behaviour, gaming scheduler priority, capture overlays and visual "
            "effects. It deliberately ignores storage housekeeping, which does "
            "nothing for in-game responsiveness."
        ),
        confidences=(Confidence.HIGH, Confidence.MEDIUM),
        max_risk=Risk.MEDIUM,
        areas=("Windows", "Graphics", "Power", "Input", "CPU"),
        caveat=(
            "Turning off mouse acceleration changes how your aim feels. "
            "Expect an adjustment period, and re-do your in-game sensitivity."
        ),
    ),
    Preset(
        id="quiet",
        name="Quiet / Laptop",
        tagline="Leave power and thermals alone.",
        description=(
            "For laptops and small-form-factor machines. Applies responsiveness "
            "and housekeeping changes but never switches your power plan, so "
            "battery life and fan noise stay as you set them."
        ),
        confidences=(Confidence.HIGH,),
        max_risk=Risk.LOW,
        exclude=("power.high_performance",),
        caveat="Deliberately skips the high-performance power plan.",
    ),
    Preset(
        id="housekeeping",
        name="Housekeeping",
        tagline="Reclaim disk space, change nothing else.",
        description=(
            "Storage-only: temporary file cleanup and Storage Sense. Touches no "
            "graphics, input or power setting, so it cannot affect how games "
            "run. Safe to schedule."
        ),
        confidences=(Confidence.HIGH, Confidence.MEDIUM),
        max_risk=Risk.LOW,
        areas=("Storage",),
        caveat="Frees space; will not raise your frame rate.",
    ),
]

PRESETS_BY_ID = {p.id: p for p in PRESETS}
DEFAULT_PRESET = "safe"


def get(preset_id: str) -> Optional[Preset]:
    return PRESETS_BY_ID.get(preset_id)


def select(preset_id: str, recommendations) -> list[str]:
    """Return the ids from `recommendations` that this preset would tick.

    `recommendations` is the list produced by a scan; each item must expose
    `.optimization` and `.evaluation.confidence`, and only *actionable* items
    (applicable, not already optimal, with an applier) are eligible.
    """
    preset = get(preset_id)
    if preset is None:
        return []
    chosen = []
    for rec in recommendations:
        opt = getattr(rec, "optimization", None)
        ev = getattr(rec, "evaluation", None)
        if opt is None or ev is None:
            continue
        if not ev.applicable or ev.already_optimal:
            continue
        if opt.apply is None:          # advisory-only entries are never auto-ticked
            continue
        if preset.matches(opt, ev.confidence):
            chosen.append(opt.id)
    return chosen


def describe(preset_id: str) -> str:
    p = get(preset_id)
    if p is None:
        return f"Unknown preset: {preset_id}"
    lines = [p.name, "-" * len(p.name), p.tagline, "", p.description]
    if p.caveat:
        lines += ["", f"Note: {p.caveat}"]
    return "\n".join(lines)
