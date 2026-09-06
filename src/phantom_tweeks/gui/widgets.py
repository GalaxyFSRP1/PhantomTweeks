"""Reusable Phantom Tweeks GUI widgets."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional

from ..branding import COLORS
from .theme import FONT, FONT_BOLD, FONT_SMALL, FONT_TITLE


class Card(ttk.Frame):
    """A titled panel."""

    def __init__(self, parent, title: str = "", subtitle: str = "", **kw):
        super().__init__(parent, style="Panel.TFrame", padding=16, **kw)
        if title:
            ttk.Label(self, text=title, style="Accent.TLabel").pack(anchor="w")
        if subtitle:
            # A fixed wraplength clips whenever the card is narrower than the
            # guess (it was, inside grid columns on the dashboard). Re-wrap to
            # the card's real width whenever it is resized.
            self._subtitle = ttk.Label(self, text=subtitle, style="Muted.TLabel",
                                       wraplength=520, justify="left")
            self._subtitle.pack(anchor="w", pady=(2, 8), fill="x")
            self.bind("<Configure>", self._rewrap, add="+")

    def _rewrap(self, event) -> None:
        label = getattr(self, "_subtitle", None)
        if label is None:
            return
        # Subtract the frame padding so text never touches the border.
        width = max(160, event.width - 36)
        if abs(int(label.cget("wraplength")) - width) > 8:
            label.configure(wraplength=width)


class GlassCard(ttk.Frame):
    """A panel with a lighter surface and a bright top edge.

    Tk has no backdrop blur, so real translucency is impossible. Rather than
    fake it with stipple patterns - which look muddy at these sizes - depth
    comes from a lighter fill plus a one-pixel highlight along the top edge,
    the way light catches the lip of a pane of glass.
    """

    def __init__(self, parent, title: str = "", subtitle: str = "", **kw):
        outer = kw.pop("outer", None)
        super().__init__(parent, style="Glass.TFrame", padding=0, **kw)
        edge = ttk.Frame(self, style="GlassEdge.TFrame", height=1)
        edge.pack(fill="x", side="top")
        self.body = ttk.Frame(self, style="Glass.TFrame", padding=16)
        self.body.pack(fill="both", expand=True)
        if title:
            ttk.Label(self.body, text=title, style="GlassAccent.TLabel"
                      ).pack(anchor="w")
        if subtitle:
            self._sub = ttk.Label(self.body, text=subtitle,
                                  style="GlassMuted.TLabel",
                                  wraplength=520, justify="left")
            self._sub.pack(anchor="w", pady=(2, 8), fill="x")
            self.bind("<Configure>", self._rewrap, add="+")

    def _rewrap(self, event) -> None:
        lab = getattr(self, "_sub", None)
        if lab is None:
            return
        width = max(160, event.width - 40)
        if abs(int(lab.cget("wraplength")) - width) > 8:
            lab.configure(wraplength=width)


class StatTile(ttk.Frame):
    """A live metric tile: big value, label, optional bar."""

    def __init__(self, parent, label: str, unit: str = "", show_bar: bool = True):
        super().__init__(parent, style="Panel.TFrame", padding=14)
        self.unit = unit
        ttk.Label(self, text=label.upper(), style="Muted.TLabel").pack(anchor="w")
        self.value_var = tk.StringVar(value="n/a")
        ttk.Label(self, textvariable=self.value_var, style="Huge.TLabel").pack(anchor="w")
        self.sub_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.sub_var, style="Muted.TLabel").pack(anchor="w")
        self.bar = None
        if show_bar:
            self.bar = ttk.Progressbar(self, maximum=100, length=180)
            self.bar.pack(anchor="w", pady=(8, 0), fill="x")

    def update_value(self, value: Optional[float], sub: str = "",
                     fmt: str = "{:.0f}") -> None:
        if value is None:
            self.value_var.set("n/a")
            self.sub_var.set(sub or "not measurable on this system")
            if self.bar:
                self.bar["value"] = 0
            return
        self.value_var.set(fmt.format(value) + self.unit)
        self.sub_var.set(sub)
        if self.bar:
            self.bar["value"] = max(0, min(100, value))


class Sparkline(tk.Canvas):
    """Lightweight line graph for frame time / ping history."""

    def __init__(self, parent, width: int = 560, height: int = 130,
                 color: Optional[str] = None, **kw):
        super().__init__(parent, width=width, height=height, bg=COLORS["panel"],
                         highlightthickness=0, **kw)
        self.color = color or COLORS["accent"]
        self._cw, self._ch = width, height
        self.values: list[float] = []
        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event) -> None:
        self._cw, self._ch = event.width, event.height
        self.redraw()

    def set_values(self, values: list[float]) -> None:
        self.values = list(values)[-600:]
        self.redraw()

    def push(self, value: float) -> None:
        self.values.append(value)
        if len(self.values) > 600:
            self.values.pop(0)
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        w, h, pad = self._cw, self._ch, 8
        vals = self.values
        if len(vals) < 2:
            self.create_text(w / 2, h / 2, text="No data captured yet",
                             fill=COLORS["muted"], font=FONT_SMALL)
            return
        lo, hi = min(vals), max(vals)
        if hi - lo < 1e-6:
            hi = lo + 1
        # grid
        for frac in (0.25, 0.5, 0.75):
            y = pad + (h - 2 * pad) * frac
            self.create_line(pad, y, w - pad, y, fill=COLORS["border"])
        step = (w - 2 * pad) / (len(vals) - 1)
        pts = []
        for i, v in enumerate(vals):
            x = pad + i * step
            y = h - pad - (v - lo) / (hi - lo) * (h - 2 * pad)
            pts += [x, y]
        self.create_line(*pts, fill=self.color, width=2, smooth=True)
        self.create_text(pad + 4, pad + 6, text=f"{hi:.1f}", anchor="w",
                         fill=COLORS["muted"], font=FONT_SMALL)
        self.create_text(pad + 4, h - pad - 6, text=f"{lo:.1f}", anchor="w",
                         fill=COLORS["muted"], font=FONT_SMALL)


class BarChart(tk.Canvas):
    """Horizontal labelled bars — used by the Performance Score and history."""

    def __init__(self, parent, width: int = 560, height: int = 260, **kw):
        super().__init__(parent, width=width, height=height, bg=COLORS["panel"],
                         highlightthickness=0, **kw)
        self.rows: list[tuple[str, Optional[float], str]] = []
        self.empty_text = ""
        self._cw = width
        self.bind("<Configure>", lambda e: (setattr(self, "_cw", e.width), self.redraw()))

    def set_empty_text(self, text: str) -> None:
        """Shown when there are no rows, so the card is never a blank void."""
        self.empty_text = text
        self.redraw()

    def set_rows(self, rows: list[tuple[str, Optional[float], str]]) -> None:
        self.rows = rows
        self.configure(height=max(60, len(rows) * 34 + 16))
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        if not self.rows:
            if self.empty_text:
                for i, line in enumerate(self.empty_text.split("\n")):
                    self.create_text(14, 20 + i * 20, text=line, anchor="w",
                                     fill=COLORS["muted"], font=FONT_SMALL)
            return
        label_w, pad = 170, 12
        max_val = max([r[1] or 0 for r in self.rows] + [100])
        for i, (label, value, note) in enumerate(self.rows):
            y = 18 + i * 34
            self.create_text(pad, y, text=label, anchor="w",
                             fill=COLORS["text"], font=FONT)
            track_x = label_w
            track_w = max(40, self._cw - label_w - 90)
            self.create_rectangle(track_x, y - 8, track_x + track_w, y + 8,
                                  fill=COLORS["panel_alt"], outline="")
            if value is None:
                self.create_text(track_x + 8, y, text="not measured", anchor="w",
                                 fill=COLORS["muted"], font=FONT_SMALL)
                continue
            frac = max(0.0, min(1.0, value / max_val))
            color = (COLORS["good"] if value >= 85 else
                     COLORS["accent"] if value >= 70 else
                     COLORS["warn"] if value >= 50 else COLORS["danger"])
            self.create_rectangle(track_x, y - 8, track_x + track_w * frac, y + 8,
                                  fill=color, outline="")
            self.create_text(track_x + track_w + 12, y, text=note or f"{value:.0f}",
                             anchor="w", fill=COLORS["text"], font=FONT_BOLD)


class InfoButton(ttk.Button):
    """The 'why' button attached to every optimization."""

    def __init__(self, parent, title: str, body: str, learn_more: str = ""):
        super().__init__(parent, text="ⓘ", width=3,
                         command=lambda: self._show(title, body, learn_more))

    def _show(self, title: str, body: str, learn_more: str) -> None:
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=COLORS["bg"])
        win.geometry("520x460")
        frame = ttk.Frame(win, style="Panel.TFrame", padding=20)
        frame.pack(fill="both", expand=True, padx=14, pady=14)
        ttk.Label(frame, text=title, style="Accent.TLabel").pack(anchor="w")
        txt = tk.Text(frame, wrap="word", relief="flat", bg=COLORS["panel"],
                      fg=COLORS["text"], font=FONT, borderwidth=0, padx=0, pady=10)
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", body)
        if learn_more:
            txt.insert("end", f"\nLearn more:\n{learn_more}\n")
        txt.configure(state="disabled")
        ttk.Button(frame, text="Close", command=win.destroy).pack(anchor="e")


def confirm_dialog(parent, title: str, message: str, danger: bool = False,
                   confirm_text: str = "Confirm", steps: int = 1) -> bool:
    """Multi-step confirmation. `steps=2` is used for anything that could weaken safety."""
    result = {"ok": False}
    win = tk.Toplevel(parent)
    win.title(title)
    win.configure(bg=COLORS["bg"])
    win.transient(parent)
    win.grab_set()
    win.geometry("540x330")

    frame = ttk.Frame(win, style="Panel.TFrame", padding=22)
    frame.pack(fill="both", expand=True, padx=14, pady=14)
    ttk.Label(frame, text=title, style="Accent.TLabel").pack(anchor="w")
    ttk.Label(frame, text=message, style="Panel.TLabel", wraplength=470,
              justify="left").pack(anchor="w", pady=14)

    acks = []
    ack1 = tk.BooleanVar()
    ttk.Checkbutton(frame, text="I understand what this changes.",
                    variable=ack1).pack(anchor="w")
    acks.append(ack1)
    if steps > 1:
        ack2 = tk.BooleanVar()
        ttk.Checkbutton(
            frame,
            text="I confirm again. Phantom Shield protections remain enforced.",
            variable=ack2).pack(anchor="w", pady=(6, 0))
        acks.append(ack2)

    btns = ttk.Frame(frame, style="Panel.TFrame")
    btns.pack(side="bottom", fill="x", pady=(18, 0))

    def accept():
        if all(a.get() for a in acks):
            result["ok"] = True
            win.destroy()

    ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="right", padx=6)
    ttk.Button(btns, text=confirm_text, command=accept,
               style="Danger.TButton" if danger else "Accent.TButton").pack(side="right")
    parent.wait_window(win)
    return result["ok"]


class Toast(tk.Toplevel):
    """Subtle bottom-right notification."""

    def __init__(self, parent, text: str, level: str = "info", ms: int = 4200):
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        color = {"warning": COLORS["warn"], "success": COLORS["good"]}.get(
            level, COLORS["accent"])
        outer = tk.Frame(self, bg=color)
        outer.pack(fill="both", expand=True)
        inner = tk.Frame(outer, bg=COLORS["panel_alt"])
        inner.pack(fill="both", expand=True, padx=(3, 0))
        tk.Label(inner, text=text, bg=COLORS["panel_alt"], fg=COLORS["text"],
                 font=FONT, padx=18, pady=13, wraplength=320,
                 justify="left").pack()
        self.update_idletasks()
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            self.geometry(f"+{px + pw - self.winfo_width() - 28}"
                          f"+{py + ph - self.winfo_height() - 28}")
        except tk.TclError:
            pass
        self.after(ms, self.destroy)


class ScrollFrame(ttk.Frame):
    """A vertically scrollable container that actually scrolls.

    Handles the three separate wheel conventions (Windows/macOS <MouseWheel>,
    X11 <Button-4/5>), keyboard paging, and resizes its inner frame to the
    canvas width so content reflows instead of being clipped.
    """

    def __init__(self, parent, bg: Optional[str] = None, **kw):
        super().__init__(parent, **kw)
        bg = bg or COLORS["panel"]
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._on_scrollbar_set)

        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = ttk.Frame(self.canvas, style="Panel.TFrame")
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Wheel support must be bound while the pointer is over the widget,
        # otherwise it either does nothing or hijacks the whole app.
        for w in (self.canvas, self.inner):
            w.bind("<Enter>", self._bind_wheel)
            w.bind("<Leave>", self._unbind_wheel)

        self.canvas.bind("<Prior>", lambda e: self._page(-1))
        self.canvas.bind("<Next>", lambda e: self._page(1))
        self.canvas.bind("<Home>", lambda e: self.canvas.yview_moveto(0))
        self.canvas.bind("<End>", lambda e: self.canvas.yview_moveto(1))

    # -- geometry ----------------------------------------------------------
    def _on_inner_configure(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._sync_scrollbar()

    def _on_canvas_configure(self, event) -> None:
        # Match inner width to the canvas so labels wrap instead of clipping.
        self.canvas.itemconfigure(self._win, width=event.width)
        self._sync_scrollbar()

    def _on_scrollbar_set(self, first, last) -> None:
        self.vsb.set(first, last)

    def _sync_scrollbar(self) -> None:
        """Hide the scrollbar when everything already fits."""
        try:
            bbox = self.canvas.bbox("all")
            if not bbox:
                return
            content_h = bbox[3] - bbox[1]
            if content_h <= self.canvas.winfo_height():
                self.vsb.pack_forget()
            elif not self.vsb.winfo_ismapped():
                self.vsb.pack(side="right", fill="y", before=self.canvas)
        except tk.TclError:
            pass

    def scrollable(self) -> bool:
        bbox = self.canvas.bbox("all")
        if not bbox:
            return False
        return (bbox[3] - bbox[1]) > self.canvas.winfo_height()

    # -- wheel -------------------------------------------------------------
    def _bind_wheel(self, _event=None) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)       # Windows / macOS
        self.canvas.bind_all("<Button-4>", self._on_wheel)          # X11 up
        self.canvas.bind_all("<Button-5>", self._on_wheel)          # X11 down
        self.canvas.bind_all("<Shift-MouseWheel>", lambda e: "break")

    def _unbind_wheel(self, _event=None) -> None:
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>", "<Shift-MouseWheel>"):
            try:
                self.canvas.unbind_all(seq)
            except tk.TclError:
                pass

    def _on_wheel(self, event) -> str:
        if not self.scrollable():
            return "break"
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        else:
            # Windows reports multiples of 120; macOS reports small values.
            raw = event.delta
            delta = -1 * (raw // 120) if abs(raw) >= 120 else (-1 if raw > 0 else 1)
        self.canvas.yview_scroll(int(delta), "units")
        return "break"

    def _page(self, direction: int) -> str:
        self.canvas.yview_scroll(direction, "pages")
        return "break"

    def scroll_to_top(self) -> None:
        self.canvas.yview_moveto(0)

    def clear(self) -> None:
        for child in self.inner.winfo_children():
            child.destroy()


class ScrolledText(ttk.Frame):
    """Read-only text panel with a working scrollbar and mousewheel."""

    def __init__(self, parent, height: int = 20, mono: bool = True, **kw):
        super().__init__(parent, style="Panel.TFrame", **kw)
        from .theme import make_text
        self.text = make_text(self, height=height, mono=mono)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=self.vsb.set, state="disabled")
        self.vsb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)

        self.text.bind("<Enter>", self._bind_wheel)
        self.text.bind("<Leave>", self._unbind_wheel)
        # Allow selection/copy but not editing.
        self.text.bind("<Control-c>", lambda e: None)

    def _bind_wheel(self, _e=None) -> None:
        self.text.bind_all("<MouseWheel>", self._on_wheel)
        self.text.bind_all("<Button-4>", self._on_wheel)
        self.text.bind_all("<Button-5>", self._on_wheel)

    def _unbind_wheel(self, _e=None) -> None:
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                self.text.unbind_all(seq)
            except tk.TclError:
                pass

    def _on_wheel(self, event) -> str:
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        else:
            raw = event.delta
            delta = -1 * (raw // 120) if abs(raw) >= 120 else (-1 if raw > 0 else 1)
        self.text.yview_scroll(int(delta), "units")
        return "break"

    def set(self, content: str) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self.text.configure(state="disabled")
        self.text.yview_moveto(0)

    def append(self, content: str) -> None:
        self.text.configure(state="normal")
        self.text.insert("end", content)
        self.text.configure(state="disabled")
        self.text.see("end")


class RecommendationCard(ttk.Frame):
    """One scan result: a big clickable row, not a tiny checkbox.

    Clicking anywhere on the card toggles it, because a 13px indicator is a
    poor target and users reported it as unclickable.
    """

    CONF_COLORS = {
        "HIGH CONFIDENCE": "good",
        "MEDIUM CONFIDENCE": "accent",
        "LOW CONFIDENCE": "warn",
        "NOT RECOMMENDED": "muted",
    }

    def __init__(self, parent, data: dict, variable: Optional[tk.BooleanVar] = None,
                 selectable: bool = True, info_body: str = "", learn_more: str = "",
                 on_toggle=None):
        super().__init__(parent, style="Card.TFrame", padding=14)
        self.data = data
        self.var = variable
        self.selectable = selectable
        self._on_toggle = on_toggle
        c = COLORS

        row = ttk.Frame(self, style="Card.TFrame")
        row.pack(fill="x")

        if selectable and variable is not None:
            self.check = ttk.Checkbutton(row, variable=variable,
                                         style="Card.TCheckbutton",
                                         command=self._changed)
            self.check.pack(side="left", padx=(0, 8))
        else:
            tk.Label(row, text="—", bg=c["panel_alt"], fg=c["muted"],
                     font=FONT).pack(side="left", padx=(0, 8))

        title = tk.Label(row, text=data["title"], bg=c["panel_alt"], fg=c["text"],
                         font=FONT_BOLD, cursor="hand2" if selectable else "")
        title.pack(side="left")

        conf_key = self.CONF_COLORS.get(data["confidence"], "muted")
        tk.Label(row, text=data["confidence"], bg=c["panel_alt"],
                 fg=c[conf_key], font=FONT_SMALL).pack(side="left", padx=10)

        tk.Label(row, text=f"[{data['category']}] · Risk: {data['risk']}"
                 + ("  · needs admin" if data.get("requires_admin") else ""),
                 bg=c["panel_alt"], fg=c["muted"],
                 font=FONT_SMALL).pack(side="left")

        InfoButton(row, data["title"], info_body, learn_more).pack(side="right")

        self.reason = tk.Label(self, text=data["reason"], bg=c["panel_alt"],
                               fg=c["muted"], font=FONT_SMALL, justify="left",
                               anchor="w")
        self.reason.pack(anchor="w", fill="x", pady=(7, 0))
        self.bind("<Configure>",
                  lambda e: self.reason.configure(wraplength=max(240, e.width - 40)))

        # Whole-card click target.
        if selectable and variable is not None:
            for w in (self, row, title, self.reason):
                w.bind("<Button-1>", self._toggle)
                try:
                    w.configure(cursor="hand2")
                except tk.TclError:
                    pass

    def _toggle(self, _event=None) -> str:
        if self.selectable and self.var is not None:
            self.var.set(not self.var.get())
            self._changed()
        return "break"

    def _changed(self) -> None:
        if self._on_toggle:
            self._on_toggle()
