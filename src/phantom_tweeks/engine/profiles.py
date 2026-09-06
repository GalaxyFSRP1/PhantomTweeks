"""Game optimization profiles and configuration snapshots.

A snapshot may only contain settings Phantom Tweeks actually manages, so
restoring one can never clobber something the user set elsewhere.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional

from ..core import paths
from .catalog import BY_ID

MANAGED_IDS = set(BY_ID.keys())


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", name.lower()).strip("-") or "profile"


@dataclass
class GameProfile:
    name: str
    game: Optional[str] = None
    preset: str = "Balanced"           # Competitive / Balanced / Quality / Streaming
    graphics_notes: list[str] = field(default_factory=list)
    fps_target: Optional[int] = None
    frame_pacing: str = "Cap FPS slightly below refresh rate for consistent pacing."
    optimization_ids: list[str] = field(default_factory=list)
    network_notes: list[str] = field(default_factory=list)
    display_notes: list[str] = field(default_factory=list)
    background_notes: list[str] = field(default_factory=list)
    benchmark_ids: list[str] = field(default_factory=list)
    auto_apply: bool = False           # explicit opt-in, per profile
    builtin: bool = False

    def sanitize(self) -> None:
        self.optimization_ids = [i for i in self.optimization_ids if i in MANAGED_IDS]

    def as_dict(self) -> dict:
        return asdict(self)

    def render(self) -> str:
        return (
            f"Game Profile: {self.name}\n"
            f"├── Preset: {self.preset}\n"
            f"├── Graphics: {'; '.join(self.graphics_notes) or 'no notes'}\n"
            f"├── FPS target: {self.fps_target or 'unset'}\n"
            f"├── Frame pacing: {self.frame_pacing}\n"
            f"├── Windows settings: {', '.join(self.optimization_ids) or 'none'}\n"
            f"├── Network: {'; '.join(self.network_notes) or 'no notes'}\n"
            f"├── Display: {'; '.join(self.display_notes) or 'no notes'}\n"
            f"├── Background: {'; '.join(self.background_notes) or 'no notes'}\n"
            f"└── Benchmarks recorded: {len(self.benchmark_ids)}"
        )


BUILTIN_PRESETS = [
    GameProfile(
        name="Competitive", preset="Competitive", fps_target=None, builtin=True,
        graphics_notes=["Lower shadows, reflections and effects first — they cost "
                        "the most FPS for the least competitive information.",
                        "Keep texture quality high if VRAM allows; it is nearly free."],
        frame_pacing="Cap FPS a few frames below your refresh rate so the GPU never "
                     "fully saturates, which keeps input latency low and stable.",
        optimization_ids=["win.game_mode", "win.game_dvr"],
        display_notes=["Confirm the monitor is running at its maximum refresh rate.",
                       "Enable VRR (G-SYNC/FreeSync) plus an FPS cap for the lowest "
                       "consistent latency."],
        network_notes=["Prefer Ethernet. Run the Network Lab stability test before "
                       "a ranked session."],
        background_notes=["Review the Background Analyzer; close browsers manually."],
    ),
    GameProfile(
        name="Balanced", preset="Balanced", builtin=True,
        graphics_notes=["Use the in-game preset closest to your monitor's resolution "
                        "and adjust only the two heaviest settings."],
        optimization_ids=["win.game_mode"],
        display_notes=["Enable VRR if available for smooth frame delivery."],
    ),
    GameProfile(
        name="Quality", preset="Quality", builtin=True,
        graphics_notes=["Prioritise texture and lighting quality; cap FPS to your "
                        "refresh rate to keep frame times even."],
        optimization_ids=["win.game_mode"],
    ),
    GameProfile(
        name="Streaming", preset="Streaming", builtin=True,
        graphics_notes=["Leave GPU headroom for the encoder — cap in-game FPS so the "
                        "GPU is not at 100% while OBS encodes."],
        optimization_ids=["win.game_mode"],
        background_notes=["OBS, Discord and audio software stay protected and running.",
                          "Do not disable Game DVR settings while actively recording."],
    ),
    GameProfile(
        name="Creator", preset="Creator", builtin=True,
        graphics_notes=["Optimise for encoder and editing throughput rather than "
                        "maximum game FPS."],
        optimization_ids=[],
        background_notes=["Capture and editing applications are never deprioritised.",
                          "Storage throughput matters more than GPU clocks here."],
    ),
]


def save(profile: GameProfile) -> str:
    paths.ensure_dirs()
    profile.sanitize()
    p = paths.PROFILES / f"{_slug(profile.name)}.json"
    p.write_text(json.dumps(profile.as_dict(), indent=2), encoding="utf-8")
    return str(p)


def load(name: str) -> Optional[GameProfile]:
    p = paths.PROFILES / f"{_slug(name)}.json"
    if not p.exists():
        return next((b for b in BUILTIN_PRESETS if _slug(b.name) == _slug(name)), None)
    try:
        prof = GameProfile(**json.loads(p.read_text(encoding="utf-8")))
        prof.sanitize()
        return prof
    except Exception:
        return None


def list_profiles() -> list[GameProfile]:
    out = list(BUILTIN_PRESETS)
    for p in sorted(paths.PROFILES.glob("*.json")):
        try:
            prof = GameProfile(**json.loads(p.read_text(encoding="utf-8")))
            prof.sanitize()
            out.append(prof)
        except Exception:
            continue
    return out


def profile_for_game(game_name: str) -> GameProfile:
    """Pick a sensible profile: user profile for this game, else Competitive for
    known esports titles, else Balanced."""
    for prof in list_profiles():
        if prof.game and prof.game.lower() == game_name.lower():
            return prof
    esports = ("counter-strike", "valorant", "rocket league", "overwatch",
               "apex legends", "rainbow six", "dota", "league of legends",
               "fortnite", "call of duty")
    low = game_name.lower()
    if any(e in low for e in esports):
        return next(p for p in BUILTIN_PRESETS if p.name == "Competitive")
    return next(p for p in BUILTIN_PRESETS if p.name == "Balanced")


# ---------------- snapshots ----------------

@dataclass
class Snapshot:
    name: str
    timestamp: str
    values: dict                        # optimization_id -> recorded state
    note: str = ""


def create_snapshot(name: str, note: str = "") -> Snapshot:
    """Capture the current value of every setting Phantom Tweeks manages."""
    from . import winsettings as ws
    from .catalog import (GAMEBAR, GAME_DVR_USER, GRAPHICS_DRIVERS, VISUAL_FX)
    values = {
        "win.game_mode": ws.read_registry("HKCU", GAMEBAR, "AutoGameModeEnabled"),
        "win.game_dvr": ws.read_registry("HKCU", GAME_DVR_USER, "GameDVR_Enabled"),
        "gfx.hags": ws.read_registry("HKLM", GRAPHICS_DRIVERS, "HwSchMode"),
        "win.visual_effects": ws.read_registry("HKCU", VISUAL_FX, "VisualFXSetting"),
        "power.high_performance": ws.active_power_scheme(),
    }
    snap = Snapshot(name, datetime.now().isoformat(timespec="seconds"), values, note)
    paths.ensure_dirs()
    (paths.SNAPSHOTS / f"{_slug(name)}.json").write_text(
        json.dumps(asdict(snap), indent=2), encoding="utf-8")
    return snap


def list_snapshots() -> list[Snapshot]:
    out = []
    for p in sorted(paths.SNAPSHOTS.glob("*.json")):
        try:
            out.append(Snapshot(**json.loads(p.read_text(encoding="utf-8"))))
        except Exception:
            continue
    return out


def load_snapshot(name: str) -> Optional[Snapshot]:
    p = paths.SNAPSHOTS / f"{_slug(name)}.json"
    if not p.exists():
        return None
    try:
        return Snapshot(**json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return None
