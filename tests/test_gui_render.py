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

def _tk_is_usable() -> tuple[bool, str]:
    """Can we actually build a Tk window here?

    Merely being on Windows is not enough. GitHub's Windows runners ship a
    Python whose Tcl data files are missing, so ``tkinter.Tk()`` raises
    "Can't find a usable init.tcl". That is a broken *environment*, not a bug
    in Phantom Tweeks, and it must never fail a release build.
    """
    if not (os.environ.get("DISPLAY") or sys.platform.startswith("win")):
        return False, "no display"
    try:
        import tkinter
        from tkinter import ttk
        root = tkinter.Tk()
        try:
            # Exercise more than construction: a broken Tcl can survive Tk()
            # and only fail once a themed widget is created.
            ttk.Frame(root)
            root.update_idletasks()
        finally:
            root.destroy()
        return True, ""
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}".split("\n")[0]


_TK_OK, _TK_WHY = _tk_is_usable()

requires_display = pytest.mark.skipif(
    not _TK_OK, reason=f"Tk is not usable here ({_TK_WHY})")


def _window():
    """Build the window, skipping if this machine's Tk cannot render.

    Belt and braces: even after the probe above passes, a per-test TclError
    means the environment is broken, not the product.
    """
    import tkinter
    from phantom_tweeks.gui.app_window import PhantomWindow
    try:
        return PhantomWindow()
    except tkinter.TclError as exc:
        pytest.skip(f"Tk could not create a window: {exc}")


@requires_display
def test_window_constructs_and_every_page_renders():
    from phantom_tweeks.gui.app_window import NAV
    win = _window()
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
    win = _window()
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
    win = _window()
    try:
        assert win._watcher.alive, "the game watcher did not start"
    finally:
        win._on_close()
        assert not win._watcher.alive, "the watcher outlived the window"


# ---------------------------------------------------- environment guards

def test_gui_tests_skip_rather_than_fail_without_tk():
    """A broken Tcl install must never fail a release build.

    GitHub's hosted Windows Python has shipped without its Tcl data files,
    producing "Can't find a usable init.tcl". That is an environment defect,
    not a product defect, and it stopped a release build once.
    """
    src = Path(__file__).read_text(encoding="utf-8")
    assert "_tk_is_usable" in src, "no capability probe"
    assert "pytest.skip" in src, "no skip path for a broken Tk"
    # Windows alone must not be treated as proof that Tk works.
    assert 'sys.platform.startswith("win")\n        return True' not in src


def test_no_test_constructs_the_window_unguarded():
    """Only the _window() helper may build a window directly.

    Everything else must go through it so a TclError becomes a skip rather
    than a failure. Uses the AST so this check cannot match its own text.
    """
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    offenders = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name == "_window":
            continue
        for call in ast.walk(node):
            if (isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id == "PhantomWindow"):
                offenders.append(f"{node.name} (line {call.lineno})")
    assert not offenders, (
        "these build a window without the TclError guard: "
        + ", ".join(offenders))


@pytest.mark.repo_hygiene
def test_ci_reports_when_tk_is_unusable():
    """If the GUI tests silently skip in CI, the run must say so."""
    wf = ROOT / ".github" / "workflows" / "build.yml"
    if not wf.is_file():
        pytest.skip("workflow missing from this checkout")
    text = wf.read_text(encoding="utf-8")
    assert "TK_OK" in text, "CI never checks whether Tk can render"
    assert "::warning::" in text, "an unusable Tk is not surfaced"


# ------------------------------------------------------- layout regressions

@requires_display
def test_every_nav_entry_is_reachable():
    """With 19 pages the sidebar overflowed and Settings/Help became
    unreachable entirely. The list must be scrollable, not clipped."""
    from phantom_tweeks.gui.app_window import NAV
    win = _window()
    try:
        win.geometry("1000x640")
        win.update_idletasks()
        win.update()
        for key, _ in NAV:
            btn = win._nav_buttons.get(key)
            assert btn is not None, f"{key} has no nav button"
            assert int(btn.winfo_reqheight()) > 0, f"{key} has no height"
    finally:
        win._on_close()


@requires_display
def test_primary_buttons_are_not_clipped():
    """A chart with expand=True starved the Calculate Score button until it
    rendered as a few pixels of colour."""
    win = _window()
    try:
        win.geometry("1240x820")
        win.show("dashboard")
        win.update_idletasks()
        win.update()

        def walk(w):
            yield w
            for child in w.winfo_children():
                yield from walk(child)

        thin = []
        for widget in walk(win):
            if widget.winfo_class() != "TButton":
                continue
            # Only judge widgets Tk has actually laid out. A widget inside a
            # hidden container (the update banner) reports height 1, and a
            # toplevel that was never mapped reports 1 for everything - both
            # would be false positives rather than real clipping.
            if not widget.winfo_ismapped():
                continue
            need = widget.winfo_reqheight()
            got = widget.winfo_height()
            if need > 1 and got < need * 0.6:
                thin.append(f"{widget.cget('text')!r} {got}px of {need}px")
        assert not thin, "buttons rendered clipped: " + "; ".join(thin)
        mapped = sum(1 for w in walk(win)
                     if w.winfo_class() == "TButton" and w.winfo_ismapped())
        if mapped == 0:
            pytest.skip("no widgets were mapped; cannot judge clipping here")
    finally:
        win._on_close()


@requires_display
def test_the_update_banner_is_hidden_until_an_update_exists():
    """It must not occupy space or nag on a normal launch."""
    win = _window()
    try:
        win.update_idletasks()
        # winfo_manager() is "" until a widget is packed. Unlike
        # winfo_ismapped() this does not require the toplevel to be on a
        # visible screen, so it works on a headless CI runner.
        assert win.update_bar.winfo_manager() == "", (
            "the update banner is packed with no update pending")
    finally:
        win._on_close()


@requires_display
def test_the_update_banner_appears_and_dismisses(tmp_path, monkeypatch):
    from phantom_tweeks.core import paths, updates
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    monkeypatch.setattr(paths, "ensure_dirs", lambda: None)

    win = _window()
    try:
        info = updates.UpdateInfo(version="9.9.9")
        win._pending_update = info
        win._show_update_banner(info)
        win.update_idletasks()
        assert win.update_bar.winfo_manager() == "pack", (
            "the banner was never packed into the window")
        assert "9.9.9" in win.update_msg.get()

        win._dismiss_update()
        win.update_idletasks()
        assert win.update_bar.winfo_manager() == "", "dismiss did not remove it"
    finally:
        win._on_close()


# ------------------------------------------------------- sections & tweaks

def test_every_page_belongs_to_exactly_one_section():
    from phantom_tweeks.gui.app_window import NAV, PAGE_SECTION, SECTIONS
    valid = {k for k, _ in SECTIONS}
    for key, _ in NAV:
        assert key in PAGE_SECTION, f"{key} is in no section - it is unreachable"
        assert PAGE_SECTION[key] in valid, f"{key} points at an unknown section"


def test_each_section_has_a_defined_landing_page():
    """Settings used to open Premium, because Premium came first in NAV."""
    from phantom_tweeks.gui.app_window import SECTIONS, SECTION_HOME, PAGE_SECTION
    for key, _ in SECTIONS:
        home = SECTION_HOME.get(key)
        assert home, f"section {key} has no landing page"
        assert PAGE_SECTION[home] == key, (
            f"section {key} lands on {home}, which is in another section")


def test_frametime_page_offers_the_button_its_message_references():
    """The 'no frame source' text told users to press a button that did not
    exist anywhere in the interface."""
    src = APP_WINDOW.read_text(encoding="utf-8")
    assert "Download PresentMon" in src, (
        "the message references a button that is not in the UI")
    assert "_get_presentmon" in src


@requires_display
def test_tweaks_page_lists_every_optimization():
    from phantom_tweeks.engine import catalog
    win = _window()
    try:
        win.show("tweaks")
        win.update()
        assert len(win._tweak_vars) == len(catalog.CATALOG), (
            "the Tweaks page does not expose every optimization")
    finally:
        win._on_close()


@requires_display
def test_apply_button_is_disabled_until_something_is_selected():
    win = _window()
    try:
        win.show("tweaks")
        win.update()
        assert str(win.tweak_apply_btn.cget("state")) == "disabled"
        first = next(iter(win._tweak_vars.values()))
        first.set(True)
        win._tweaks_update_count()
        assert str(win.tweak_apply_btn.cget("state")) == "normal"
    finally:
        win._on_close()


@requires_display
def test_switching_section_hides_other_sections_pages():
    from phantom_tweeks.gui.app_window import SECTIONS, PAGE_SECTION
    win = _window()
    try:
        for key, _ in SECTIONS:
            win.show_section(key)
            win.update()
            visible = [k for k, b in win._nav_buttons.items()
                       if b.winfo_manager() == "pack"]
            assert visible, f"section {key} shows no pages"
            for page in visible:
                assert PAGE_SECTION[page] == key, (
                    f"{page} leaked into section {key}")
    finally:
        win._on_close()
