"""The Premium feature catalog and gating logic.

Honesty rules this module exists to enforce
-------------------------------------------
* Every entry here is a feature that **actually exists in the code**. There
  are no placeholder cards advertising things that were never built.
* Free features are genuinely free and are never degraded to make Premium look
  better. Nothing that protects the user's PC is ever paywalled: backup,
  restore, Phantom Shield, safety checks and every warning stay free forever.
* A locked feature explains what it does and what it would cost, and then
  stops. It never pretends to run, never shows fabricated results, and never
  asks for payment inside the app.

``FREE_FOREVER`` is a deliberate, load-bearing promise. If you ever move one
of those into Premium you are charging users for their own safety, and a test
enforces that this does not happen by accident.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

TIER_FREE = "free"
TIER_PREMIUM = "premium"


@dataclass(frozen=True)
class Feature:
    id: str
    name: str
    tier: str
    summary: str
    detail: str = ""
    # Where the feature lives, so the UI can deep-link to it.
    page: str = ""
    implemented: bool = True

    @property
    def is_premium(self) -> bool:
        return self.tier == TIER_PREMIUM


# Safety and honesty features that must never be paywalled.
FREE_FOREVER = (
    "scan", "shield", "backup", "restore", "recommendations",
    "health", "storage", "startup", "drivers", "power", "games",
)


CATALOG: tuple[Feature, ...] = (
    # ---------------------------------------------------------------- free
    Feature("scan", "Phantom Scan", TIER_FREE,
            "Full system analysis with per-item confidence ratings.",
            "Scans hardware, Windows settings and drivers, then explains each "
            "finding. 'No change recommended' is a valid result.", "scan"),
    Feature("shield", "Phantom Shield", TIER_FREE,
            "Protects your game, launchers, voice chat and anti-cheat.",
            "Never paywalled. Shield is what stops the app from breaking "
            "something, so charging for it would be indefensible.", "shield"),
    Feature("backup", "Backup before every change", TIER_FREE,
            "Automatic restore point before anything is modified.",
            "Free forever. You should never have to pay to undo a change "
            "this app made.", "history"),
    Feature("restore", "Restore anything, any time", TIER_FREE,
            "Roll back one optimization or all of them.",
            "Includes resumable partial restore if a rollback is interrupted.",
            "history"),
    Feature("recommendations", "Explained recommendations", TIER_FREE,
            "Every suggestion states its technical reason and confidence.",
            "", "scan"),
    Feature("health", "System health", TIER_FREE,
            "Temperatures, drive health and resource pressure.", "", "health"),
    Feature("games", "Game detection and profiles", TIER_FREE,
            "Auto-detects running games and applies your saved profile.",
            "", "games"),
    Feature("startup", "Startup manager", TIER_FREE,
            "See and control what launches with Windows.", "", "startup"),
    Feature("drivers", "Driver centre", TIER_FREE,
            "Reports driver versions and known issues.", "", "drivers"),
    Feature("storage", "Storage lab", TIER_FREE,
            "Disk health and safe, regenerable cache cleanup.", "", "storage"),
    Feature("power", "Power plan control", TIER_FREE,
            "Inspect and switch Windows power plans.", "", "power"),
    Feature("frametime_basic", "Frame-time capture", TIER_FREE,
            "Live frame pacing with 1% and 0.1% lows.", "", "frametime"),
    Feature("network_basic", "Network Lab", TIER_FREE,
            "Real latency and jitter measurements to real endpoints.",
            "Measures DNS and route quality. Never promises lower ping - "
            "DNS response time is not game-server ping.", "network"),
    Feature("maintenance", "Maintenance Mode", TIER_FREE,
            "Routine health checks that never run mid-game.", "", "maintenance"),

    # ------------------------------------------------------------- premium
    Feature("history_trends", "Performance history and trends", TIER_PREMIUM,
            "Keeps every benchmark and scan so you can see change over time.",
            "The free tier shows the current run. Premium retains an unlimited "
            "history and charts regressions - useful for spotting the day a "
            "driver update cost you 8% of your average FPS.", "premium"),
    Feature("frametime_advanced", "Advanced frame-time analytics", TIER_PREMIUM,
            "Stutter classification, percentile breakdown and session compare.",
            "Separates CPU-bound hitches from GPU-bound ones and from shader "
            "compilation stalls, because the fix differs for each.", "frametime"),
    Feature("auto_profiles", "Automatic profile switching", TIER_PREMIUM,
            "Applies the right profile the moment a game launches.",
            "Free tier detects the game and tells you. Premium applies your "
            "saved profile automatically, then restores your desktop settings "
            "when you quit.", "games"),
    Feature("scheduled_maintenance", "Scheduled maintenance", TIER_PREMIUM,
            "Runs the maintenance checklist weekly or monthly, never mid-game.",
            "Free tier runs maintenance on demand. Premium schedules it and "
            "reports what changed since last time.", "maintenance"),
    Feature("bench_suite", "Extended benchmark suite", TIER_PREMIUM,
            "Repeatable CPU, memory and storage runs with variance reporting.",
            "Reports confidence intervals, so you can tell a real 3% gain "
            "from measurement noise.", "premium"),
    Feature("net_history", "Network history", TIER_PREMIUM,
            "Long-run latency and packet-loss logging.",
            "Shows whether last night's lag was your connection or the server.",
            "network"),
    Feature("export_reports", "Report export", TIER_PREMIUM,
            "Export a full diagnostic report as HTML, Markdown, JSON or CSV.",
            "Useful for forum help threads and RMA evidence. Usernames are "
            "stripped automatically before anything is written.", "perf"),
    Feature("themes", "Additional themes", TIER_PREMIUM,
            "Extra colour schemes for the interface.",
            "Purely cosmetic. Listed honestly as cosmetic.", "settings"),
    Feature("priority_support", "Priority support", TIER_PREMIUM,
            "Direct support queue.",
            "A support commitment, not a software feature.", "premium"),
)


BY_ID = {f.id: f for f in CATALOG}


def free_features() -> list[Feature]:
    return [f for f in CATALOG if not f.is_premium]


def premium_features() -> list[Feature]:
    return [f for f in CATALOG if f.is_premium]


def get(feature_id: str) -> Optional[Feature]:
    return BY_ID.get(feature_id)


def is_premium_feature(feature_id: str) -> bool:
    f = BY_ID.get(feature_id)
    return bool(f and f.is_premium)


@dataclass
class Gate:
    """The result of checking access to a feature."""

    allowed: bool
    feature_id: str
    name: str = ""
    reason: str = ""
    upsell: str = ""

    def __bool__(self) -> bool:
        return self.allowed


def check(feature_id: str) -> Gate:
    """Decide whether a feature may run right now.

    Unknown ids are allowed: a typo must not silently disable something that
    should work. Only an explicit premium entry can lock a feature.
    """
    feature = BY_ID.get(feature_id)
    if feature is None:
        return Gate(True, feature_id)
    if not feature.is_premium:
        return Gate(True, feature_id, feature.name)

    from . import premium
    if premium.is_premium():
        return Gate(True, feature_id, feature.name)

    return Gate(
        False, feature_id, feature.name,
        reason=f"{feature.name} is a Premium feature.",
        upsell=(f"{feature.summary}\n\n{feature.detail}\n\n"
                "Premium is not on sale yet. Nothing in this app takes "
                "payment, and this feature will stay locked rather than "
                "show you invented results.").strip(),
    )


def summary() -> dict:
    """Everything the Premium page needs to render, with no invented claims."""
    from . import premium
    active = premium.is_premium()
    return {
        "active": active,
        "free": [f.__dict__ for f in free_features()],
        "premium": [f.__dict__ for f in premium_features()],
        "free_count": len(free_features()),
        "premium_count": len(premium_features()),
        "promise": (
            "Safety features are free forever: scanning, Phantom Shield, "
            "backup, restore and every warning. Premium adds depth - history, "
            "automation and deeper analysis - never protection."
        ),
        "payment_note": (
            "Phantom Tweeks contains no payment processing and will never ask "
            "for card details inside the app. When Premium launches it will "
            "use an established payment provider on the website."
        ),
    }
