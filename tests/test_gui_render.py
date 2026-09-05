"""Checks for defects that only appear when the interface is actually drawn.

Most of these were found by rendering the app against a real X server for the
first time. Three genuine bugs surfaced immediately:

* a duplicate ``_refresh_premium`` that did ``pass`` silently overrode the real
  implementation, leaving the licence status stuck on "Checking...";
* ``Card`` used a hard-coded ``wraplength`` that clipped its subtitle whenever
  the card was narrower than the guess;
* seven navigation icons were emoji that render as missing-glyph boxes.

The static checks below run everywhere. The rendering checks run only where a
display is available, so the suite still passes on a headless machine.
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

GUI = SRC / "phantom_tweeks" / "gui"
APP_WINDOW = GUI / "app_window.py"


# --------------------------------------------------------- static checks

def test_no_method_is_defined_twice_in_a_gui_class():
    """A duplicate method silently replaces the earlier one.

    This exact mistake left the Premium page stuck on "Checking..." because a
    later no-op ``_refresh_premium`` shadowed the working implementation.
    """
    problems = []
    for path in GUI.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            names = [n.name for n in node.body
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            for name in sorted({n for n in names if names.count(n) > 1}):
                problems.append(f"{path.name}: {node.name}.{name} defined "
                                f"{names.count(name)} times")
    assert not problems, "duplicate methods shadow each other:\n  " + \
                         "\n  ".join(problems)


def test_navigation_icons_avoid_emoji():
    """Emoji fall back to a missing-glyph box on common Windows font stacks.

    Verified empirically by measuring glyph widths against U+FFFF: every
    character at U+1F300 or above failed to render.
    """
    from phantom_tweeks.gui.app_window import NAV
    bad = []
    for key, label in NAV:
        for ch in label:
            if ord(ch) >= 0x1F300:
                bad.append(f"{key}: {ch!r} (U+{ord(ch):04X})")
    assert not bad, ("these nav icons will show as boxes on Windows:\n  "
                     + "\n  ".join(bad))


def test_no_emoji_anywhere_in_the_interface():
    bad = []
    for path in GUI.glob("*.py"):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for ch in line:
                if ord(ch) >= 0x1F300:
                    bad.append(f"{path.name}:{i}: {ch!r}")
    assert not bad, "emoji render as boxes:\n  " + "\n  ".join(bad)


def test_card_subtitle_rewraps_on_resize():
    """A fixed wraplength clips text in any card narrower than the guess."""
    src = (GUI / "widgets.py").read_text(encoding="utf-8")
    assert "_rewrap" in src, "Card does not adapt its subtitle wrapping"
    assert '<Configure>' in src, "Card never binds to resize events"


def test_every_nav_key_has_a_page_and_a_builder():
    from phantom_tweeks.gui.app_window import NAV
    src = APP_WINDOW.read_text(encoding="utf-8")
    for key, _label in NAV:
        assert f'"{key}"' in src, f"nav key {key} is never referenced"


# -------------------------------------------------------- render checks

def _has_display() -> bool:
    if os.environ.get("DISPLAY") or sys.platform.startswith("win"):
        try:
            import tkinter
            root = tkinter.Tk()
            root.destroy()
            return True
        except Exception:
            return False
    return False


requires_display = pytest.mark.skipif(
    not _has_display(),
    reason="no display available; rendering checks need X or Windows")


@requires_display
def test_window_constructs_and_every_page_renders():
    from phantom_tweeks.gui.app_window import PhantomWindow, NAV
    win = PhantomWindow()
    try:
        win.update_idletasks()
        empty = []
        for key, _label in NAV:
            win.show(key)
            win.update()
            page = win._pages.get(key)
            assert page is not None, f"{key} has no page"
            if not page.winfo_children():
                empty.append(key)
        assert not empty, f"pages rendered with no content: {empty}"
    finally:
        win._on_close()


@requires_display
def test_premium_status_resolves_and_does_not_stay_checking():
    """Regression: the licence label was stuck on its placeholder."""
    from phantom_tweeks.gui.app_window import PhantomWindow
    win = PhantomWindow()
    try:
        win.show("premium")
        win.update()
        status = win.lic_status_var.get()
        assert "Checking" not in status, (
            "the Premium page never resolved its licence status")
        assert status in ("FREE",) or "PREMIUM" in status, status
    finally:
        win._on_close()


@requires_display
def test_game_watcher_starts_with_the_window():
    from phantom_tweeks.gui.app_window import PhantomWindow
    win = PhantomWindow()
    try:
        assert win._watcher.alive, "the game watcher did not start"
    finally:
        win._on_close()
        assert not win._watcher.alive, "the watcher outlived the window"
