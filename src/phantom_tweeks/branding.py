"""Central branding constants. The official spelling is 'Phantom Tweeks'."""

APP_NAME = "Phantom Tweeks"
APP_SLUG = "PhantomTweeks"
APP_TAGLINE = "Optimize Smarter. Game Better."
APP_DESCRIPTION = (
    "Advanced Windows performance optimization built around real system data."
)
VERSION = "0.2.1"
PUBLISHER = "Phantom Tweeks"
WEBSITE = "https://phantomtweeks.example"

# Palette used by GUI + website so branding stays consistent.
COLORS = {
    "bg": "#0a0d14",
    "panel": "#111725",
    "panel_alt": "#161e30",
    # Layered "glass" tones. Tk cannot blur, so depth comes from a lighter
    # surface plus a brighter top edge that reads as a specular highlight.
    "glass": "#151d2e",
    "glass_edge": "#2b3a5a",
    "border": "#222e47",
    "text": "#e6ecf7",
    "muted": "#8493ad",
    "accent": "#00e5c0",
    "accent_dim": "#00a88e",
    "violet": "#7b61ff",
    "warn": "#ffb020",
    "danger": "#ff4d6d",
    "good": "#3ddc84",
}

GOLDEN_RULE = (
    "Phantom Tweeks must never break the user's PC in an attempt to make it faster. "
    "When forced to choose between marginal performance and stability, choose stability. "
    "When forced to choose between claiming success and reporting honestly, choose honesty."
)
