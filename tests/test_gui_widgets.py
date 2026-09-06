"""GUI regression tests that run without a display.

These exist because of a real shipped bug: `Sparkline` stored its canvas width in
`self._w`, which is tkinter's *internal Tcl path name* for the widget. Overwriting
it made the next pack() call fail with:

    bad argument "560": must be name of window

Widget geometry cannot be exercised headlessly, but attribute shadowing and the
pure-geometry maths can be — and those are where this class of bug lives.
"""
import ast
import pathlib

import pytest

tkinter = pytest.importorskip("tkinter")
from tkinter import ttk  # noqa: E402

GUI_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "phantom_tweeks" / "gui"

TK_BASES = {"Canvas", "Frame", "Toplevel", "Text", "Tk", "Listbox", "Label",
            "Button", "Entry", "Treeview", "Notebook", "Progressbar", "Scrollbar"}


def _reserved_names() -> set[str]:
    reserved: set[str] = set()
    for cls in (tkinter.Misc, tkinter.BaseWidget, tkinter.Widget, tkinter.Canvas,
                tkinter.Tk, tkinter.Toplevel, tkinter.Text, ttk.Frame, ttk.Button):
        reserved |= set(dir(cls))
    # Instance internals assigned in BaseWidget._setup that don't appear in dir().
    reserved |= {"_w", "_name", "_tclCommands", "master", "tk", "children"}
    return reserved


def _tk_subclasses():
    for path in sorted(GUI_DIR.glob("*.py")):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            bases = {b.attr if isinstance(b, ast.Attribute) else getattr(b, "id", "")
                     for b in cls.bases}
            if bases & TK_BASES:
                yield path, cls


def test_no_widget_shadows_tkinter_internals():
    """A widget attribute must never collide with a tkinter internal.

    `self._w` in particular holds the widget's Tcl path; clobbering it breaks
    every subsequent geometry call with a confusing error.
    """
    reserved = _reserved_names()
    offenders = []
    for path, cls in _tk_subclasses():
        for node in ast.walk(cls):
            if (isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "self"
                    and isinstance(node.ctx, ast.Store)
                    and node.attr in reserved):
                offenders.append(f"{path.name}:{node.lineno} {cls.name}.{node.attr}")
            # setattr(self, "_w", ...) is the same bug wearing a hat
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "setattr"
                    and len(node.args) >= 2
                    and isinstance(node.args[1], ast.Constant)
                    and node.args[1].value in reserved):
                offenders.append(
                    f"{path.name}:{node.lineno} {cls.name} setattr {node.args[1].value!r}")
    assert not offenders, (
        "GUI widgets shadow tkinter internal attributes:\n  " + "\n  ".join(offenders))


def test_widget_classes_are_importable():
    from phantom_tweeks.gui import widgets
    for name in ("Card", "StatTile", "Sparkline", "BarChart", "InfoButton", "Toast"):
        assert hasattr(widgets, name)


def test_sparkline_geometry_math():
    """Exercise redraw()'s maths without instantiating a widget."""
    from phantom_tweeks.gui.widgets import Sparkline

    calls = []

    class FakeSparkline(Sparkline):
        def __init__(self):           # bypass tk.Canvas.__init__
            self.color = "#00e5c0"
            self._cw, self._ch = 560, 130
            self.values = []
        def delete(self, *a): calls.append(("delete", a))
        def create_line(self, *a, **k): calls.append(("line", len(a)))
        def create_text(self, *a, **k): calls.append(("text", k.get("text")))

    s = FakeSparkline()
    s.redraw()                                   # empty -> placeholder text
    assert any(c[0] == "text" for c in calls)

    calls.clear()
    s.set_values([16.6, 16.7, 33.2, 16.5, 16.6])
    assert any(c[0] == "line" for c in calls)

    calls.clear()
    s.set_values([16.6] * 50)                    # flat series must not divide by zero
    assert any(c[0] == "line" for c in calls)

    for _ in range(700):                         # ring buffer stays bounded
        s.push(16.6)
    assert len(s.values) <= 600


def test_barchart_handles_none_values():
    from phantom_tweeks.gui.widgets import BarChart

    drawn = []

    class FakeBarChart(BarChart):
        def __init__(self):
            self.rows = []
            self._cw = 560
        def delete(self, *a): pass
        def configure(self, **k): pass
        def create_text(self, *a, **k): drawn.append(k.get("text"))
        def create_rectangle(self, *a, **k): pass

    b = FakeBarChart()
    b.set_rows([("CPU Health", 94, "94/100"),
                ("Gaming Performance", None, ""),   # unmeasured must not crash
                ("Network", 0, "0/100")])
    assert "not measured" in drawn
    assert "CPU Health" in drawn


def test_launch_reports_display_failure_cleanly():
    """A missing display must not be reported as an application crash."""
    src = (GUI_DIR / "app_window.py").read_text(encoding="utf-8")
    assert "except tk.TclError" in src
    assert "could not start" in src


# ---------------------------------------------------------------- scrolling

def test_scrollframe_wheel_delta_conventions():
    """The three wheel conventions must all produce a scroll in the right direction.

    Windows sends <MouseWheel> with delta in multiples of 120, macOS sends small
    deltas, X11 sends Button-4 (up) / Button-5 (down). Getting this wrong is why
    'I can't scroll' happens.
    """
    from phantom_tweeks.gui.widgets import ScrollFrame

    scrolled = []

    class FakeCanvas:
        def yview_scroll(self, n, what): scrolled.append((n, what))

    class Fake(ScrollFrame):
        def __init__(self):
            self.canvas = FakeCanvas()
        def scrollable(self): return True

    f = Fake()

    class Ev:
        def __init__(self, delta=0, num=None):
            self.delta, self.num = delta, num

    f._on_wheel(Ev(delta=120))       # Windows wheel up
    f._on_wheel(Ev(delta=-120))      # Windows wheel down
    f._on_wheel(Ev(num=4))           # X11 up
    f._on_wheel(Ev(num=5))           # X11 down
    f._on_wheel(Ev(delta=3))         # macOS up
    f._on_wheel(Ev(delta=-3))        # macOS down

    directions = [n for n, _ in scrolled]
    assert directions == [-1, 1, -1, 1, -1, 1], directions
    assert all(what == "units" for _, what in scrolled)


def test_scrollframe_ignores_wheel_when_content_fits():
    """Wheel events must not scroll (or steal input) when there is nothing to scroll."""
    from phantom_tweeks.gui.widgets import ScrollFrame

    scrolled = []

    class Fake(ScrollFrame):
        def __init__(self):
            self.canvas = type("C", (), {"yview_scroll": lambda s, n, w: scrolled.append(n)})()
        def scrollable(self): return False

    f = Fake()
    assert f._on_wheel(type("E", (), {"delta": -120, "num": None})()) == "break"
    assert scrolled == []


def test_scrollframe_binds_all_wheel_sequences():
    """All three platform sequences must be bound, or one OS silently can't scroll."""
    import inspect
    from phantom_tweeks.gui.widgets import ScrollFrame
    src = inspect.getsource(ScrollFrame._bind_wheel)
    for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        assert seq in src, f"{seq} not bound"
    # and unbound again on leave, so one pane doesn't hijack the whole window
    unsrc = inspect.getsource(ScrollFrame._unbind_wheel)
    for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        assert seq in unsrc


def test_scrollframe_has_keyboard_paging():
    import inspect
    from phantom_tweeks.gui.widgets import ScrollFrame
    src = inspect.getsource(ScrollFrame.__init__)
    for seq in ("<Prior>", "<Next>", "<Home>", "<End>"):
        assert seq in src, f"{seq} keyboard scrolling missing"


# ---------------------------------------------------------------- clicking

def test_recommendation_card_toggles_from_whole_card():
    """Clicking the card body must toggle it, not just the tiny indicator."""
    import inspect
    from phantom_tweeks.gui.widgets import RecommendationCard

    src = inspect.getsource(RecommendationCard.__init__)
    assert '"<Button-1>"' in src, "card body is not clickable"
    assert "hand2" in src, "no affordance that the card is clickable"

    toggled = []

    class FakeVar:
        def __init__(self): self.v = False
        def get(self): return self.v
        def set(self, v): self.v = v

    class Fake(RecommendationCard):
        def __init__(self):
            self.var = FakeVar()
            self.selectable = True
            self._on_toggle = lambda: toggled.append(True)

    c = Fake()
    assert c.var.get() is False
    c._toggle()
    assert c.var.get() is True, "clicking the card did not select it"
    c._toggle()
    assert c.var.get() is False
    assert len(toggled) == 2, "toggle callback did not fire"


def test_recommendation_card_non_selectable_is_inert():
    from phantom_tweeks.gui.widgets import RecommendationCard

    class Fake(RecommendationCard):
        def __init__(self):
            self.var = None
            self.selectable = False
            self._on_toggle = None

    assert Fake()._toggle() == "break"   # must not raise


def test_checkbox_indicator_has_contrast():
    """The clam indicator defaults to dark-on-dark, which reads as unclickable."""
    from phantom_tweeks.gui import theme
    import inspect
    src = inspect.getsource(theme.apply)
    assert "indicatorbackground" in src
    assert "indicatorforeground" in src
    assert "Card.TCheckbutton" in src


def test_scrolledtext_is_readonly_but_scrollable():
    import inspect
    from phantom_tweeks.gui.widgets import ScrolledText
    init = inspect.getsource(ScrolledText.__init__)
    assert 'state="disabled"' in init
    assert "<Enter>" in init and "<Leave>" in init
    assert "yscrollcommand" in init
