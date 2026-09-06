"""User configuration with safe defaults. Everything opt-in."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from . import paths

DEFAULTS = {
    "auto_apply_high_confidence": False,   # never on by default
    "gaming_mode_auto_start": False,
    # Applies a saved game profile automatically when a game is detected.
    # Off by default: nothing significant changes without the user asking.
    "auto_apply_game_profile": False,
    "expert_mode": False,
    "notifications": True,
    "notification_min_interval_s": 60,
    "telemetry": False,                    # hard-off; no endpoint exists
    "share_hardware_info": False,
    "share_game_info": False,
    "check_updates": True,
    "theme": "phantom-dark",
    "protected_apps": [],
    "active_profile": None,
    "network_targets": ["1.1.1.1", "8.8.8.8"],
    "benchmark_seconds": 30,
    "regression_threshold_pct": 5.0,
}


@dataclass
class Config:
    data: dict = field(default_factory=lambda: dict(DEFAULTS))

    @classmethod
    def load(cls) -> "Config":
        paths.ensure_dirs()
        cfg = cls()
        if paths.CONFIG_FILE.exists():
            try:
                stored = json.loads(paths.CONFIG_FILE.read_text(encoding="utf-8"))
                if isinstance(stored, dict):
                    cfg.data.update({k: v for k, v in stored.items() if k in DEFAULTS})
            except (json.JSONDecodeError, OSError):
                pass  # corrupt config must never block startup
        return cfg

    def save(self) -> None:
        paths.ensure_dirs()
        tmp = paths.CONFIG_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        tmp.replace(paths.CONFIG_FILE)

    def get(self, key, default=None):
        return self.data.get(key, DEFAULTS.get(key, default))

    def set(self, key, value) -> None:
        self.data[key] = value
        self.save()

    def reset(self) -> None:
        self.data = dict(DEFAULTS)
        self.save()
