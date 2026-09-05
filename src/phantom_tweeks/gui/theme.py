"""Phantom Tweeks dark theme for Tk widgets."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..branding import COLORS

FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI Semibold", 10)
FONT_TITLE = ("Segoe UI Semibold", 18)
FONT_HUGE = ("Segoe UI Light", 34)
FONT_MONO = ("Consolas", 10)
FONT_SMALL = ("Segoe UI", 9)


def apply(root: tk.Misc) -> ttk.Style:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    c = COLORS
    root.configure(bg=c["bg"])

    style.configure(".", background=c["bg"], foreground=c["text"],
                    fieldbackground=c["panel"], font=FONT, borderwidth=0)
    style.configure("TFrame", background=c["bg"])
    style.configure("Panel.TFrame", background=c["panel"], relief="flat")
    style.configure("Card.TFrame", background=c["panel_alt"])
    style.configure("TLabel", background=c["bg"], foreground=c["text"])
    style.configure("Panel.TLabel", background=c["panel"], foreground=c["text"])
    style.configure("Muted.TLabel", background=c["panel"], foreground=c["muted"],
                    font=FONT_SMALL)
    style.configure("MutedBg.TLabel", background=c["bg"], foreground=c["muted"],
                    font=FONT_SMALL)
    style.configure("Title.TLabel", background=c["bg"], foreground=c["text"],
                    font=FONT_TITLE)
    style.configure("Huge.TLabel", background=c["panel"], foreground=c["accent"],
                    font=FONT_HUGE)
    style.configure("Accent.TLabel", background=c["panel"], foreground=c["accent"],
                    font=FONT_BOLD)
    style.configure("Good.TLabel", background=c["panel"], foreground=c["good"])
    style.configure("Warn.TLabel", background=c["panel"], foreground=c["warn"])
    style.configure("Danger.TLabel", background=c["panel"], foreground=c["danger"])

    style.configure("TButton", background=c["panel_alt"], foreground=c["text"],
                    padding=(14, 8), relief="flat", font=FONT)
    style.map("TButton",
              background=[("active", c["border"]), ("disabled", c["panel"])],
              foreground=[("disabled", c["muted"])])
    style.configure("Accent.TButton", background=c["accent"], foreground="#04120f",
                    font=FONT_BOLD, padding=(16, 9))
    style.map("Accent.TButton", background=[("active", c["accent_dim"])])
    style.configure("Danger.TButton", background=c["danger"], foreground="#20060c",
                    font=FONT_BOLD, padding=(16, 9))
    style.map("Danger.TButton", background=[("active", "#d43f5b")])
    style.configure("Chip.TButton", background=c["panel_alt"], foreground=c["muted"],
                    padding=(11, 5), font=FONT_SMALL, relief="flat")
    style.map("Chip.TButton", background=[("active", c["border"])],
              foreground=[("active", c["accent"])])
    style.configure("Nav.TButton", background=c["bg"], foreground=c["muted"],
                    anchor="w", padding=(18, 11), font=FONT)
    style.map("Nav.TButton",
              background=[("active", c["panel"])], foreground=[("active", c["text"])])
    style.configure("NavActive.TButton", background=c["panel"], foreground=c["accent"],
                    anchor="w", padding=(18, 11), font=FONT_BOLD)

    # The clam indicator defaults to a dark box on our dark panel, which made
    # checkboxes effectively invisible (and so felt unclickable). Force contrast.
    style.configure("TCheckbutton", background=c["panel"], foreground=c["text"],
                    focuscolor=c["accent"], indicatorforeground=c["accent"],
                    indicatorbackground=c["bg"], indicatorrelief="flat",
                    padding=(2, 3))
    style.map("TCheckbutton",
              background=[("active", c["panel"])],
              indicatorbackground=[("selected", c["accent"]),
                                   ("active", c["border"]),
                                   ("!selected", c["bg"])],
              indicatorforeground=[("selected", "#04120f")],
              foreground=[("active", c["accent"])])
    style.configure("Card.TCheckbutton", background=c["panel_alt"],
                    foreground=c["text"], indicatorbackground=c["bg"],
                    indicatorforeground=c["accent"], padding=(2, 3))
    style.map("Card.TCheckbutton",
              background=[("active", c["panel_alt"])],
              indicatorbackground=[("selected", c["accent"]),
                                   ("active", c["border"]),
                                   ("!selected", c["bg"])],
              indicatorforeground=[("selected", "#04120f")])
    style.configure("TRadiobutton", background=c["panel"], foreground=c["text"],
                    indicatorbackground=c["bg"], indicatorforeground=c["accent"])
    style.map("TRadiobutton", background=[("active", c["panel"])],
              indicatorbackground=[("selected", c["accent"])])
    style.configure("TEntry", fieldbackground=c["panel_alt"], foreground=c["text"],
                    bordercolor=c["border"], insertcolor=c["accent"],
                    lightcolor=c["border"], darkcolor=c["border"], padding=6)
    style.map("TEntry", bordercolor=[("focus", c["accent"])])
    style.configure("TCombobox", fieldbackground=c["panel_alt"], background=c["panel_alt"],
                    foreground=c["text"], arrowcolor=c["accent"], padding=5)
    style.configure("TNotebook", background=c["bg"], borderwidth=0)
    style.configure("TNotebook.Tab", background=c["panel"], foreground=c["muted"],
                    padding=(16, 8))
    style.map("TNotebook.Tab", background=[("selected", c["panel_alt"])],
              foreground=[("selected", c["accent"])])
    style.configure("TProgressbar", background=c["accent"], troughcolor=c["panel_alt"],
                    borderwidth=0, thickness=8)
    style.configure("Treeview", background=c["panel"], fieldbackground=c["panel"],
                    foreground=c["text"], rowheight=26, borderwidth=0)
    style.configure("Treeview.Heading", background=c["panel_alt"],
                    foreground=c["muted"], font=FONT_SMALL, relief="flat")
    style.map("Treeview", background=[("selected", c["border"])])
    style.configure("TSeparator", background=c["border"])
    style.configure("Vertical.TScrollbar", background=c["panel_alt"],
                    troughcolor=c["bg"], borderwidth=0, arrowsize=12)
    return style


def make_text(parent, height: int = 20, mono: bool = True) -> tk.Text:
    c = COLORS
    txt = tk.Text(parent, height=height, wrap="word", relief="flat",
                  bg=c["panel"], fg=c["text"], insertbackground=c["accent"],
                  font=FONT_MONO if mono else FONT, padx=16, pady=14,
                  selectbackground=c["border"], borderwidth=0)
    txt.tag_configure("h1", foreground=c["accent"], font=("Segoe UI Semibold", 13))
    txt.tag_configure("good", foreground=c["good"])
    txt.tag_configure("warn", foreground=c["warn"])
    txt.tag_configure("danger", foreground=c["danger"])
    txt.tag_configure("muted", foreground=c["muted"])
    return txt
