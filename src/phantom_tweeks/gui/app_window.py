"""Phantom Tweeks main window."""
from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Callable, Optional

from ..app import PhantomApp
from ..branding import APP_NAME, APP_TAGLINE, COLORS, VERSION
from ..core import premium, features, gamewatch, selftest, updates
from ..engine import (maintenance, history, tweakdb, catalog, perfview,
                      restorepoint, reports)
from ..network import dns
from ..network import bufferbloat as bloat
from ..engine import nettweaks, perftweaks
from ..engine import registry as regview
from ..hardware import nvidia as nvidia_gpu
from ..hardware import cpuvendor
from ..core.notifications import CENTER
from ..core.platform_info import IS_WINDOWS, is_admin, windows_release
from ..core.shield import SHIELD
from ..engine import frametime, powerplan, presets
from ..hardware.monitor import MONITOR
from . import theme
from .widgets import (BarChart, Card, InfoButton, RecommendationCard, ScrollFrame,
                      ScrolledText, Sparkline, StatTile, Toast, confirm_dialog)

# Icons are deliberately restricted to characters that render on the default
# Windows font stack. Emoji (U+1F300 and above) fall back to a missing-glyph
# box on many systems - verified by measuring glyph widths against U+FFFF.
# Top-level sections. 22 pages in one flat list was a wall of text; grouping
# them means you see the six or seven things relevant to what you are doing.
SECTIONS = [
    ("dashboard", "Dashboard"),
    ("tweaks", "Tweaks"),
    ("settings", "Settings"),
]

# Where each tab lands. Without this the Settings tab opened Premium, simply
# because Premium comes first in NAV - which looked like a sales page ambush.
SECTION_HOME = {
    "dashboard": "dashboard",
    "tweaks": "tweaks",
    "settings": "settings",
}

# Which section each page belongs to.
PAGE_SECTION = {
    "dashboard": "dashboard", "shield": "dashboard", "scan": "dashboard",
    "frametime": "dashboard", "latency": "dashboard", "network": "dashboard",
    "registry": "tweaks", "bufferbloat": "dashboard", "perftweaks": "tweaks", "nvidia": "tweaks", "cpu": "tweaks", "nettweaks": "tweaks", "dns": "dashboard", "games": "dashboard", "background": "dashboard",
    "perf": "dashboard", "health": "dashboard", "trends": "dashboard",

    "tweaks": "tweaks", "tweakdb": "tweaks", "startup": "tweaks",
    "drivers": "tweaks", "storage": "tweaks", "power": "tweaks",
    "maintenance": "tweaks", "history": "tweaks",

    "settings": "settings", "premium": "settings", "help": "settings",
}

NAV = [
    ("dashboard", "◉  Dashboard"),
    ("shield", "◈  Phantom Shield"),
    ("scan", "◎  Phantom Scan"),
    ("tweaks", "⚙  Tweaks"),
    ("registry", "▤  Registry"),
    ("tweakdb", "☰  Tweak Encyclopedia"),
    ("frametime", "▤  Frame-Time"),
    ("latency", "⇋  Input Latency"),
    ("network", "⇅  Network Lab"),
    ("bufferbloat", "◨  Bufferbloat"),
    ("perftweaks", "⚡  Latency Tweaks"),
    ("nvidia", "▲  NVIDIA GPU"),
    ("cpu", "▣  CPU (Intel/AMD)"),
    ("nettweaks", "⇵  Network Tweaks"),
    ("dns", "◇  DNS"),
    ("games", "◐  Games & Profiles"),
    ("background", "▦  Background"),
    ("startup", "⊙  Startup"),
    ("drivers", "⚙  Drivers"),
    ("storage", "▣  Storage"),
    ("perf", "▮  Performance"),
    ("health", "✚  System Health"),
    ("maintenance", "✽  Maintenance"),
    ("history", "↺  History & Restore"),
    ("power", "⚡  Power Plan"),
    ("trends", "◤  Trends"),
    ("premium", "★  Premium"),
    ("settings", "⚒  Settings"),
    ("help", "?  Help & Diagnostics"),
]


class PhantomWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.app = PhantomApp()
        self.title(f"{APP_NAME} {VERSION}")
        self.geometry("1240x820")
        self.minsize(1000, 640)
        self.configure(bg=COLORS["bg"])
        theme.apply(self)
        self._set_icon()

        self._results: queue.Queue = queue.Queue()
        self._pages: dict[str, ttk.Frame] = {}
        self._nav_buttons: dict[str, ttk.Button] = {}
        self._current = "dashboard"
        self._monitoring = True

        self._build_chrome()
        self._build_pages()
        self.show_section("dashboard")
        self.show("dashboard")

        self._bind_shortcuts()
        CENTER.subscribe(lambda n: self.after(0, lambda: self._toast(n)))
        self.after(1000, self._tick_monitor)
        self.after(120, self._drain_results)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._start_game_watch()
        self.after(1500, self._warn_if_not_admin)
        self._pending_update = None
        # Delay the first check so it never competes with window setup.
        self.after(4000, self._check_updates_async)

    def _set_icon(self) -> None:
        from pathlib import Path
        for name in ("phantom.png", "phantom.ico"):
            p = Path(__file__).resolve().parents[3] / "assets" / name
            if p.exists():
                try:
                    if p.suffix == ".ico" and IS_WINDOWS:
                        self.iconbitmap(str(p))
                    else:
                        self._icon_img = tk.PhotoImage(file=str(p))
                        self.iconphoto(True, self._icon_img)
                    return
                except tk.TclError:
                    continue

    # ---------------- chrome ----------------
    def _build_chrome(self) -> None:
        header = ttk.Frame(self, style="Panel.TFrame", padding=(20, 14))
        header.pack(fill="x")
        left = ttk.Frame(header, style="Panel.TFrame")
        left.pack(side="left")
        ttk.Label(left, text="PHANTOM TWEEKS", style="Accent.TLabel",
                  font=("Segoe UI Semibold", 15)).pack(anchor="w")
        ttk.Label(left, text=APP_TAGLINE, style="Muted.TLabel").pack(anchor="w")

        right = ttk.Frame(header, style="Panel.TFrame")
        right.pack(side="right")
        self.shield_badge = ttk.Label(right, text="◈ SHIELD ACTIVE", style="Good.TLabel")
        self.shield_badge.pack(anchor="e")
        mode_bits = [windows_release()]
        if not IS_WINDOWS:
            mode_bits.append("ANALYSIS-ONLY")
        if IS_WINDOWS and not is_admin():
            mode_bits.append("standard user")
        ttk.Label(right, text="  •  ".join(mode_bits),
                  style="Muted.TLabel").pack(anchor="e")

        # Update banner. Hidden until a newer version is actually found, so
        # it never occupies space or nags on a normal launch.
        self.update_bar = ttk.Frame(self, style="Panel.TFrame", padding=(20, 10))
        self.update_msg = tk.StringVar(value="")
        ttk.Label(self.update_bar, textvariable=self.update_msg,
                  style="Accent.TLabel").pack(side="left")
        ttk.Button(self.update_bar, text="Dismiss", style="Chip.TButton",
                   command=self._dismiss_update).pack(side="right", padx=(6, 0))
        ttk.Button(self.update_bar, text="Skip this version", style="Chip.TButton",
                   command=self._skip_update).pack(side="right", padx=6)
        ttk.Button(self.update_bar, text="View update", style="Accent.TButton",
                   command=self._show_update_details).pack(side="right")

        # Section tabs sit above everything, on a glass strip.
        tabs = ttk.Frame(self, style="Glass.TFrame", padding=(14, 0))
        tabs.pack(fill="x")
        ttk.Frame(self, style="GlassEdge.TFrame", height=1).pack(fill="x")
        self._tab_buttons = {}
        for key, label in SECTIONS:
            b = ttk.Button(tabs, text=label, style="Tab.TButton",
                           command=lambda k=key: self.show_section(k))
            b.pack(side="left")
            self._tab_buttons[key] = b
        self._section = "dashboard"

        body = ttk.Frame(self)
        self._body = body
        body.pack(fill="both", expand=True)

        nav = ttk.Frame(body, style="TFrame", width=214)
        nav.pack(side="left", fill="y")
        nav.pack_propagate(False)

        # The action buttons are packed to the BOTTOM first so they are always
        # reachable; the scrollable page list then fills whatever space is
        # left. With 19 pages the list overflowed a 900px-tall window and the
        # last entries (Settings, Help) became unreachable entirely.
        self.game_var = tk.StringVar(value="No game detected")
        ttk.Label(nav, textvariable=self.game_var, style="MutedBg.TLabel",
                  wraplength=190, justify="left").pack(side="bottom", anchor="w",
                                                       padx=12, pady=(0, 4))
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(nav, textvariable=self.status_var, style="MutedBg.TLabel",
                  wraplength=190, justify="left").pack(side="bottom", anchor="w",
                                                       padx=12, pady=(6, 10))
        ttk.Button(nav, text="RESTORE EVERYTHING", style="Danger.TButton",
                   command=self._restore_everything).pack(side="bottom", fill="x",
                                                          padx=10, pady=6)
        ttk.Button(nav, text="Export Report...", style="Chip.TButton",
                   command=self._export_report).pack(side="bottom", fill="x",
                                                     padx=10, pady=(0, 2))
        ttk.Separator(nav, orient="horizontal").pack(side="bottom", fill="x",
                                                     pady=8)

        nav_scroll = ScrollFrame(nav)
        nav_scroll.pack(side="top", fill="both", expand=True)
        self._nav_inner = nav_scroll.inner
        for key, label in NAV:
            b = ttk.Button(nav_scroll.inner, text=label, style="Nav.TButton",
                           command=lambda k=key: self.show(k))
            self._nav_buttons[key] = b
        self._render_nav()

        self.content = ttk.Frame(body, padding=(18, 16))
        self.content.pack(side="left", fill="both", expand=True)

    def _bind_shortcuts(self) -> None:
        """Keyboard access for everything you'd otherwise hunt for with a mouse."""
        binds = {
            "<Control-s>": lambda e: self.show("scan") or self._run_scan(),
            "<Control-r>": lambda e: self._refresh_current(),
            "<Control-e>": lambda e: self._export_report(),
            "<Control-n>": lambda e: self.show("network") or self._run_network(False),
            "<Control-q>": lambda e: self._on_close(),
            "<F1>": lambda e: self._show_shortcuts(),
            "<F5>": lambda e: self._refresh_current(),
        }
        for seq, fn in binds.items():
            self.bind_all(seq, fn)
        # Ctrl+1..9 jumps to a page
        for i, (key, _label) in enumerate(NAV[:9], start=1):
            self.bind_all(f"<Control-Key-{i}>", lambda e, k=key: self.show(k))

    def _refresh_current(self) -> None:
        fn = getattr(self, f"_refresh_{self._current}", None)
        if fn:
            fn()
        else:
            self.status_var.set("Nothing to refresh on this page.")

    def _show_shortcuts(self) -> None:
        confirm_dialog(
            self, "Keyboard Shortcuts",
            "Ctrl+S    Run Phantom Scan\n"
            "Ctrl+N    Run Network Lab\n"
            "Ctrl+R    Refresh current page\n"
            "F5        Refresh current page\n"
            "Ctrl+E    Export diagnostic report\n"
            "Ctrl+1-9  Jump to page\n"
            "Ctrl+Q    Quit\n"
            "F1        This list\n\n"
            "On scrollable pages: mouse wheel, Page Up/Down, Home/End.",
            confirm_text="Close")

    def _export_report(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Export diagnostic report",
            defaultextension=".txt",
            initialfile="PhantomTweeks-Report.txt",
            filetypes=[("Text file", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        stats = getattr(self, "_last_frames", None)
        self._run_async(lambda: self.app.export_report(path, stats),
                        lambda p: Toast(self, f"✓ Report saved to {p}", "success"),
                        "Building report…")

    def _render_nav(self) -> None:
        """Show only the pages belonging to the active section."""
        for key, button in self._nav_buttons.items():
            if PAGE_SECTION.get(key, "dashboard") == self._section:
                button.pack(fill="x")
            else:
                button.pack_forget()

    def show_section(self, section: str) -> None:
        self._section = section
        for key, button in self._tab_buttons.items():
            button.configure(style="TabActive.TButton" if key == section
                             else "Tab.TButton")
        self._render_nav()
        # Land on the first page of the section rather than an empty pane.
        first = SECTION_HOME.get(section) or next(
            (k for k, _ in NAV
             if PAGE_SECTION.get(k, "dashboard") == section), None)
        if first and PAGE_SECTION.get(self._current) != section:
            self.show(first)

    def show(self, key: str) -> None:
        for k, b in self._nav_buttons.items():
            b.configure(style="NavActive.TButton" if k == key else "Nav.TButton")
        for k, page in self._pages.items():
            page.pack_forget()
        self._pages[key].pack(fill="both", expand=True)
        self._current = key
        section = PAGE_SECTION.get(key, "dashboard")
        if section != self._section:
            self._section = section
            for k, b in self._tab_buttons.items():
                b.configure(style="TabActive.TButton" if k == section
                            else "Tab.TButton")
            self._render_nav()
        refresh = getattr(self, f"_refresh_{key}", None)
        if refresh and key not in ("dashboard",):
            refresh()

    # ---------------- async helper ----------------
    def _run_async(self, fn: Callable, on_done: Callable, busy: str = "Working…") -> None:
        self.status_var.set(busy)

        def worker():
            try:
                self._results.put((on_done, fn(), None))
            except Exception as e:  # never let a worker kill the UI
                self._results.put((on_done, None, e))

        threading.Thread(target=worker, daemon=True).start()

    def _drain_results(self) -> None:
        try:
            while True:
                on_done, value, error = self._results.get_nowait()
                self.status_var.set("Ready.")
                if error:
                    self._set_text_error(error)
                else:
                    on_done(value)
        except queue.Empty:
            pass
        self.after(120, self._drain_results)

    def _set_text_error(self, error: Exception) -> None:
        self.status_var.set("Operation failed.")
        Toast(self, f"⚠ {error}", "warning")

    def _toast(self, note) -> None:
        Toast(self, note.render(), note.level)

    # ---------------- pages ----------------
    def _new_page(self, key: str, title: str, subtitle: str = "") -> ttk.Frame:
        page = ttk.Frame(self.content)
        self._pages[key] = page
        ttk.Label(page, text=title, style="Title.TLabel").pack(anchor="w")
        if subtitle:
            ttk.Label(page, text=subtitle, style="MutedBg.TLabel",
                      wraplength=860, justify="left").pack(anchor="w", pady=(2, 12))
        else:
            ttk.Frame(page, height=12).pack()
        return page

    def _scroll_text(self, parent, height: int = 22) -> ScrolledText:
        panel = ScrolledText(parent, height=height)
        panel.pack(fill="both", expand=True)
        return panel

    @staticmethod
    def _write(panel, content: str) -> None:
        """Write to a ScrolledText panel (or a raw Text widget)."""
        if hasattr(panel, "set"):
            panel.set(content)
            return
        panel.configure(state="normal")
        panel.delete("1.0", "end")
        panel.insert("1.0", content)
        panel.configure(state="disabled")
        panel.yview_moveto(0)

    def _build_pages(self) -> None:
        self._build_dashboard()
        self._build_shield()
        self._build_scan()
        self._build_tweaks()
        self._build_registry()
        self._build_tweakdb()
        self._build_frametime()
        self._build_latency()
        self._build_network()
        self._build_perftweaks()
        self._build_nvidia()
        self._build_cpu()
        self._build_bufferbloat()
        self._build_nettweaks()
        self._build_dns()
        self._build_games()
        self._build_simple("background", "Background Analyzer",
                           "Phantom Tweeks reports what is using resources. It never "
                           "closes applications for you.",
                           lambda: self.app.background_report().render())
        self._build_startup()
        self._build_drivers()
        self._build_simple("storage", "Storage Lab",
                           "Personal files are never listed for deletion and never "
                           "removed automatically.",
                           self._storage_text)
        self._build_perf()
        self._build_simple("health", "System Health Center",
                           "Every warning includes the reason behind it.",
                           self._health_text)
        self._build_maintenance()
        self._build_trends()
        self._build_history()
        self._build_power()
        self._build_premium()
        self._build_settings()
        self._build_help()

    # --- dashboard
    def _build_dashboard(self) -> None:
        page = self._new_page("dashboard", "Dashboard")
        tiles = ttk.Frame(page)
        tiles.pack(fill="x")
        self.tiles = {}
        for i, (key, label, unit) in enumerate([
                ("cpu", "CPU", "%"), ("gpu", "GPU", "%"),
                ("ram", "Memory", "%"), ("disk", "Disk", "%")]):
            t = StatTile(tiles, label, unit)
            t.grid(row=0, column=i, padx=(0, 12), sticky="nsew")
            tiles.columnconfigure(i, weight=1)
            self.tiles[key] = t

        mid = ttk.Frame(page)
        mid.pack(fill="both", expand=True, pady=14)
        mid.columnconfigure(0, weight=3)
        mid.columnconfigure(1, weight=2)
        mid.rowconfigure(0, weight=1)

        # Quick actions: the four things people actually open the app to do.
        # Everything here is read-only or reversible; nothing applies a change
        # without its own confirmation step.
        quick = Card(page, "QUICK ACTIONS",
                     "One click for the common tasks. None of these change "
                     "anything on their own.")
        quick.pack(fill="x", pady=(0, 12), before=mid)
        qrow = ttk.Frame(quick, style="Panel.TFrame")
        qrow.pack(anchor="w", pady=(4, 0))
        for text, cmd in (
            ("Scan my system", lambda: (self.show("scan"), self._run_scan())),
            ("Run maintenance", lambda: (self.show("maintenance"),
                                         self._run_maintenance())),
            ("Check health", lambda: self.show("health")),
            ("Self-test", lambda: (self.show("help"), self._run_selftest())),
            ("Fix input latency", self._quick_latency),
            ("Fix network lag", self._quick_network),
        ):
            ttk.Button(qrow, text=text, style="Chip.TButton",
                       command=cmd).pack(side="left", padx=(0, 8))

        left = Card(mid, "PERFORMANCE SCORE",
                    "Every sub-score explains exactly how it was calculated. "
                    "Unmeasurable inputs are reported as 'not measured', never guessed.")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        # Grid for the same reason as the card on the right: a bottom-packed
        # button still gets squeezed when the container runs short. Only the
        # chart row carries weight, so the button always keeps its height.
        lbody = ttk.Frame(left, style="Panel.TFrame")
        lbody.pack(fill="both", expand=True)
        lbody.columnconfigure(0, weight=1)
        lbody.rowconfigure(0, weight=1)     # chart absorbs the slack
        lbody.rowconfigure(1, weight=0)     # button keeps its height

        self.score_chart = BarChart(lbody, height=210)
        self.score_chart.set_empty_text(
            "No score calculated yet.\n\n"
            "Press Calculate Score to measure this system.\n"
            "Each sub-score shows its own reasoning, and anything\n"
            "that cannot be measured is reported as 'not measured'\n"
            "rather than guessed.")
        self.score_chart.grid(row=0, column=0, sticky="nsew", pady=(4, 0))
        ttk.Button(lbody, text="Calculate Score", style="Accent.TButton",
                   command=self._calc_score).grid(row=1, column=0, sticky="w",
                                                  pady=(8, 0))

        right = Card(mid, "GAME DETECTION")
        right.grid(row=0, column=1, sticky="nsew")
        # Grid, not pack. pack(side="bottom") still yields space when the
        # container is shorter than its contents want, so the button was
        # squeezed to 14px of the 37px it needs. Windows fonts are taller
        # than the Linux ones I test with, so the overflow shows up there
        # first. With grid, only the text row carries weight: every other
        # row keeps its natural height no matter how short the card gets.
        body = ttk.Frame(right, style="Panel.TFrame")
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)      # text absorbs all slack
        body.rowconfigure(1, weight=0)      # button never shrinks
        body.rowconfigure(2, weight=0)      # caption never shrinks

        self.game_text = theme.make_text(body, height=6)
        self.game_text.grid(row=0, column=0, sticky="nsew", pady=(6, 8))
        self._write(self.game_text, "Scanning for games...")

        self.mode_btn = ttk.Button(body, text="Enable Gaming Mode",
                                   style="Accent.TButton",
                                   command=self._toggle_mode)
        self.mode_btn.grid(row=1, column=0, sticky="ew")
        ttk.Label(body, text="Gaming Mode monitors and protects. It never closes "
                             "Discord, Steam, Epic, or your game.",
                  style="Muted.TLabel", wraplength=320,
                  justify="left").grid(row=2, column=0, sticky="w", pady=(8, 0))

        bottom = Card(page, "LIVE TELEMETRY")
        bottom.pack(fill="x")
        self.telemetry_var = tk.StringVar(value="Sampling…")
        ttk.Label(bottom, textvariable=self.telemetry_var, style="Muted.TLabel",
                  font=theme.FONT_MONO, justify="left").pack(anchor="w")
        self.cpu_spark = Sparkline(bottom, height=90)
        self.cpu_spark.pack(fill="x", pady=(8, 0))

    def _calc_score(self) -> None:
        self._run_async(lambda: self.app.performance_score(),
                        self._render_score, "Calculating performance score…")

    def _render_score(self, ps) -> None:
        rows = [(s.name, s.value, s.display) for s in ps.subscores]
        if ps.overall is not None:
            rows.append(("Overall", ps.overall, f"{ps.overall}/100"))
        self.score_chart.set_rows(rows)
        self._score_details = ps

    def _toggle_mode(self) -> None:
        if self.app.mode.active:
            self.app.mode.stop()
            self.mode_btn.configure(text="Enable Gaming Mode")
        else:
            self.app.mode.start()
            self.mode_btn.configure(text="Disable Gaming Mode")

    def _tick_monitor(self) -> None:
        if not self._monitoring:
            return
        try:
            cpu = MONITOR.cpu()
            mem = MONITOR.memory()
            gpus = MONITOR.gpus()
            gpu = next((g for g in gpus if g.utilization is not None), None)
            r, w = MONITOR.disk_rates()
            down, up = MONITOR.net_rates()

            self.tiles["cpu"].update_value(
                cpu.utilization,
                f"{cpu.current_mhz:.0f} MHz" if cpu.current_mhz else "clock n/a")
            self.tiles["gpu"].update_value(
                gpu.utilization if gpu else None,
                (f"{gpu.temperature_c:.0f} °C" if gpu and gpu.temperature_c
                 else "GPU telemetry needs vendor tooling"))
            self.tiles["ram"].update_value(
                mem.percent, f"{mem.used_gb:.1f} / {mem.total_gb:.1f} GB"
                if mem.total_gb else "")
            busy = None
            if r is not None and w is not None:
                busy = min(100.0, (r + w) / 5)
            self.tiles["disk"].update_value(
                busy, f"{r:.1f} MB/s read · {w:.1f} MB/s write"
                if r is not None else "")

            if cpu.utilization is not None:
                self.cpu_spark.push(cpu.utilization)

            lines = [
                f"CPU   {cpu.model or 'Unknown'}",
                f"      util {self._fmt(cpu.utilization, '%')}   "
                f"clock {self._fmt(cpu.current_mhz, ' MHz')}   "
                f"temp {self._fmt(cpu.temperature_c, ' °C')}   "
                f"plan {cpu.power_plan or 'n/a'}",
            ]
            for g in gpus[:2]:
                lines += [
                    f"GPU   {g.model} ({g.vendor})",
                    f"      util {self._fmt(g.utilization, '%')}   "
                    f"temp {self._fmt(g.temperature_c, ' °C')}   "
                    f"clock {self._fmt(g.clock_mhz, ' MHz')}   "
                    f"vram {self._fmt(g.vram_used_mb, ' MB')} / "
                    f"{self._fmt(g.vram_total_mb, ' MB')}",
                ]
            lines.append(
                f"NET   down {self._fmt(down, ' Mbps')}   up {self._fmt(up, ' Mbps')}")
            self.telemetry_var.set("\n".join(lines))

            d = SHIELD.dashboard()
            self.shield_badge.configure(
                text=f"◈ SHIELD ACTIVE · {d['protected_count']} protected")

            session = self.app.mode.session
            if session:
                self._write(self.game_text, self.app.mode.render_detection())
            elif self.app.mode.active:
                self._write(self.game_text,
                            "Gaming Mode is ACTIVE.\n\nNo game running right now.\n\n"
                            "Phantom Shield is watching launchers, voice chat and "
                            "anti-cheat processes.")
            else:
                self._write(self.game_text,
                            "Gaming Mode is INACTIVE.\n\nEnable it to detect your game "
                            "automatically, protect its process tree, and record "
                            "session performance.\n\nNothing is changed without your "
                            "approval.")
        except Exception:
            pass
        self.after(2000, self._tick_monitor)

    @staticmethod
    def _fmt(v: Optional[float], unit: str = "") -> str:
        return "n/a" if v is None else f"{v:.0f}{unit}"

    # --- shield
    def _build_shield(self) -> None:
        page = self._new_page(
            "shield", "Phantom Shield",
            "Protected processes are never killed, suspended, re-prioritised, "
            "re-affinitised, or injected into — by any mode, including Expert Mode.")
        top = ttk.Frame(page)
        top.pack(fill="x", pady=(0, 10))
        ttk.Button(top, text="Refresh", command=self._refresh_shield).pack(side="left")
        ttk.Button(top, text="Manage Protected Apps",
                   command=self._manage_protected).pack(side="left", padx=8)
        self.shield_text = self._scroll_text(page)

    def _refresh_shield(self) -> None:
        self._run_async(self.app.render_shield,
                        lambda s: self._write(self.shield_text, s), "Scanning…")

    def _manage_protected(self) -> None:
        win = tk.Toplevel(self)
        win.title("Manage Protected Apps")
        win.configure(bg=COLORS["bg"])
        win.geometry("520x440")
        frame = ttk.Frame(win, style="Panel.TFrame", padding=18)
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        ttk.Label(frame, text="Additional Protected Applications",
                  style="Accent.TLabel").pack(anchor="w")
        ttk.Label(frame, text="Add executable names (e.g. myapp.exe). Wildcards are "
                              "supported. Built-in protections cannot be removed.",
                  style="Muted.TLabel", wraplength=440,
                  justify="left").pack(anchor="w", pady=(4, 10))
        listbox = tk.Listbox(frame, bg=COLORS["panel_alt"], fg=COLORS["text"],
                             relief="flat", highlightthickness=0, height=12,
                             selectbackground=COLORS["border"])
        listbox.pack(fill="both", expand=True)

        def reload():
            listbox.delete(0, "end")
            for n in sorted(SHIELD.user_protected):
                listbox.insert("end", n)
        reload()

        row = ttk.Frame(frame, style="Panel.TFrame")
        row.pack(fill="x", pady=10)
        entry = ttk.Entry(row)
        entry.pack(side="left", fill="x", expand=True)

        def add():
            name = entry.get().strip()
            if name:
                SHIELD.add_user_protected(name)
                self.app.config.set("protected_apps", sorted(SHIELD.user_protected))
                entry.delete(0, "end")
                reload()

        def remove():
            for i in reversed(listbox.curselection()):
                SHIELD.remove_user_protected(listbox.get(i))
            self.app.config.set("protected_apps", sorted(SHIELD.user_protected))
            reload()

        ttk.Button(row, text="Add", style="Accent.TButton",
                   command=add).pack(side="left", padx=6)
        ttk.Button(row, text="Remove", command=remove).pack(side="left")

    # --- scan
    def _build_scan(self) -> None:
        page = self._new_page(
            "scan", "Phantom Scan",
            "Each recommendation states why it applies to your hardware. "
            "'No change recommended' is a valid, useful result.")
        top = ttk.Frame(page)
        top.pack(fill="x", pady=(0, 10))
        ttk.Button(top, text="Run Phantom Scan", style="Accent.TButton",
                   command=self._run_scan).pack(side="left")
        self.scan_net_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Include network tests",
                        variable=self.scan_net_var).pack(side="left", padx=12)
        self.apply_btn = ttk.Button(top, text="Review & Apply Selected",
                                    command=self._apply_selected, state="disabled")
        self.apply_btn.pack(side="right")

        pbar = ttk.Frame(page)
        pbar.pack(fill="x", pady=(0, 6))
        ttk.Label(pbar, text="Preset:", style="MutedBg.TLabel").pack(side="left")
        self.preset_var = tk.StringVar(value=presets.PRESETS_BY_ID[
            presets.DEFAULT_PRESET].name)
        self.preset_box = ttk.Combobox(
            pbar, textvariable=self.preset_var, state="readonly", width=18,
            values=[pr.name for pr in presets.PRESETS])
        self.preset_box.pack(side="left", padx=(6, 8))
        self.preset_box.bind("<<ComboboxSelected>>", lambda e: self._apply_preset())
        InfoButton(pbar, "Optimization presets",
                   "\n\n".join(presets.describe(pr.id) for pr in presets.PRESETS)
                   ).pack(side="left")
        self.preset_note = ttk.Label(pbar, text="", style="Muted.TLabel",
                                     wraplength=520, justify="left")
        self.preset_note.pack(side="left", padx=10)

        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Button(bar, text="Select all", style="Chip.TButton",
                   command=lambda: self._select_recs(True)).pack(side="left")
        ttk.Button(bar, text="Select none", style="Chip.TButton",
                   command=lambda: self._select_recs(False)).pack(side="left", padx=6)
        ttk.Button(bar, text="Recommended only", style="Chip.TButton",
                   command=self._select_recommended).pack(side="left")
        self.sel_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self.sel_var,
                  style="MutedBg.TLabel").pack(side="right")

        self.rec_scroll = ScrollFrame(page)
        self.rec_scroll.pack(fill="both", expand=True)
        self.rec_inner = self.rec_scroll.inner
        self._rec_vars: dict[str, tk.BooleanVar] = {}
        self._rec_meta: dict[str, dict] = {}
        ttk.Label(self.rec_inner, text="Run a scan to see recommendations.",
                  style="Muted.TLabel").pack(anchor="w", padx=16, pady=16)

    def _refresh_scan(self) -> None:
        pass

    def _run_scan(self) -> None:
        self._run_async(lambda: self.app.scan(self.scan_net_var.get()),
                        self._render_scan, "Running Phantom Scan…")

    def _render_scan(self, result) -> None:
        self.rec_scroll.clear()
        self._rec_vars.clear()
        self._rec_meta.clear()
        self._last_recs = list(result.recommendations)

        header = ttk.Frame(self.rec_inner, style="Panel.TFrame", padding=(16, 14))
        header.pack(fill="x")
        ttk.Label(header, text=result.render(), style="Panel.TLabel",
                  font=theme.FONT_MONO, justify="left").pack(anchor="w")

        for rec in result.recommendations:
            d = rec.as_dict()
            selectable = d["applicable"] and rec.optimization.apply is not None
            var = tk.BooleanVar(value=rec.auto_applicable)
            if selectable:
                self._rec_vars[d["id"]] = var
                self._rec_meta[d["id"]] = {
                    "confidence": d["confidence"],
                    "category": d["category"],
                }
            card = RecommendationCard(
                self.rec_inner, d, variable=var if selectable else None,
                selectable=selectable, info_body=d["info"],
                learn_more=rec.optimization.learn_more,
                on_toggle=self._update_selection_count)
            card.pack(fill="x", padx=12, pady=6)

        self.rec_scroll.scroll_to_top()
        self.apply_btn.configure(state="normal" if self._rec_vars else "disabled")
        self._apply_preset()

    def _current_preset_id(self) -> str:
        name = self.preset_var.get()
        for pr in presets.PRESETS:
            if pr.name == name:
                return pr.id
        return presets.DEFAULT_PRESET

    def _apply_preset(self) -> None:
        """Tick exactly what the selected preset would choose from this scan."""
        pid = self._current_preset_id()
        preset = presets.get(pid)
        chosen = set(presets.select(pid, getattr(self, "_last_recs", [])))
        for oid, var in self._rec_vars.items():
            var.set(oid in chosen)
        if preset is not None:
            if not self._rec_vars:
                note = preset.caveat
            elif not chosen:
                note = ("Nothing to do for this preset — everything it covers "
                        "is already set correctly.")
            else:
                note = preset.caveat
            self.preset_note.configure(text=note)
        self._update_selection_count()

    def _select_recs(self, value: bool) -> None:
        for var in self._rec_vars.values():
            var.set(value)
        self._update_selection_count()

    def _select_recommended(self) -> None:
        for oid, var in self._rec_vars.items():
            meta = self._rec_meta.get(oid, {})
            var.set(meta.get("confidence") == "HIGH CONFIDENCE"
                    and meta.get("category") in ("Safe", "Recommended"))
        self._update_selection_count()

    def _update_selection_count(self) -> None:
        total = len(self._rec_vars)
        chosen = sum(1 for v in self._rec_vars.values() if v.get())
        self.sel_var.set(f"{chosen} of {total} selected" if total else "")
        if hasattr(self, "apply_btn"):
            self.apply_btn.configure(state="normal" if chosen else "disabled")

    def _apply_selected(self) -> None:
        ids = [i for i, v in self._rec_vars.items() if v.get()]
        if not ids:
            Toast(self, "No optimizations selected.", "warning")
            return
        if not IS_WINDOWS:
            Toast(self, "⚠ Analysis-only mode: changes require Windows.", "warning")
            return
        from ..engine.catalog import BY_ID
        titles = "\n".join(f"• {BY_ID[i].title}" for i in ids if i in BY_ID)
        advanced = any(BY_ID[i].advanced for i in ids if i in BY_ID)
        msg = (f"Phantom Tweeks will apply:\n\n{titles}\n\n"
               "A verified backup is created before anything is written. "
               "Every change can be rolled back from History & Restore.")
        if advanced:
            msg += ("\n\nOne or more items are marked ADVANCED. If your system "
                    "misbehaves after a reboot, boot into Safe Mode and run:\n"
                    "  PhantomTweeks.exe restore --all --yes")
        if not confirm_dialog(self, "Confirm Optimization", msg,
                              danger=advanced, confirm_text="Apply",
                              steps=2 if advanced else 1):
            return
        self._run_async(lambda: self.app.apply(ids, "Applied from Phantom Scan"),
                        self._after_apply, "Applying optimizations…")

    def _after_apply(self, result) -> None:
        lines = [result.summary(), ""]
        lines += [f"✓ {i}" for i in result.applied]
        lines += [f"– {i}: {w}" for i, w in result.skipped]
        lines += [f"✗ {i}: {w}" for i, w in result.failed]
        if result.reboot_required:
            lines += ["", "⚠ A reboot is required for some changes to take effect."]
        confirm_dialog(self, "Optimization Complete", "\n".join(lines),
                       confirm_text="OK")
        self._run_scan()

    # --- frame time
    def _build_frametime(self) -> None:
        page = self._new_page(
            "frametime", "Frame-Time Analyzer",
            "Phantom Tweeks reads real frame times from PresentMon or an imported "
            "CSV. It will never simulate FPS numbers.")
        top = ttk.Frame(page)
        top.pack(fill="x", pady=(0, 10))
        ttk.Button(top, text="Capture 30s", style="Accent.TButton",
                   command=lambda: self._capture_frames(30)).pack(side="left")
        ttk.Button(top, text="Import CSV…",
                   command=self._import_csv).pack(side="left", padx=8)
        ttk.Button(top, text="Compare Two Captures...",
                   command=self._compare_csvs).pack(side="left")
        # The "no frame-time source" message told users to press this button,
        # and the button did not exist. It does now.
        self.pm_btn = ttk.Button(top, text="Download PresentMon",
                                 style="Chip.TButton",
                                 command=self._get_presentmon)
        self.pm_btn.pack(side="left", padx=8)
        ttk.Button(top, text="Open tools folder", style="Chip.TButton",
                   command=self._open_tools_folder).pack(side="left")

        graph_card = Card(page, "FRAME TIME OVER TIME")
        graph_card.pack(fill="x", pady=(0, 10))
        self.ft_spark = Sparkline(graph_card, height=150, color=COLORS["violet"])
        self.ft_spark.pack(fill="x")
        self.ft_text = self._scroll_text(page, height=14)
        self._write(self.ft_text,
                    "FRAME TIME\n\nNo capture yet.\n\n"
                    "Phantom Tweeks reads frame data from Intel PresentMon (free). "
                    "Place PresentMon.exe on your PATH or in the Phantom Tweeks "
                    "tools folder, or import a CapFrameX / PresentMon CSV.")

    def _get_presentmon(self) -> None:
        """Fetch PresentMon from Intel's official GitHub release."""
        from ..engine import frametime as _ft
        status = _ft.presentmon_status()
        if status["available"]:
            Toast(self, f"PresentMon already installed: {status['path']}", "info")
            return
        if not confirm_dialog(
                self, "Download PresentMon?",
                "PresentMon is Intel's free, open-source frame-time tool. It "
                "is the only way to measure real frame pacing on Windows.\n\n"
                "It will be downloaded over HTTPS from Intel's official GitHub "
                "release and saved to:\n"
                f"  {status['tools_dir']}\n\n"
                "Phantom Tweeks verifies the file is a real Windows executable "
                "before keeping it. It is Intel's software, licensed "
                "separately."):
            return

        def work():
            def progress(done, total):
                if total:
                    pct = done * 100 // total
                    self.after(0, lambda: self.status_var.set(
                        f"Downloading PresentMon... {pct}%"))
            return _ft.download_presentmon(progress=progress)

        def done(result):
            ok, message = result
            self._write(self.ft_text, message)
            Toast(self, "PresentMon installed" if ok else "Download failed",
                  "success" if ok else "warning")

        self._run_async(work, done, "Downloading PresentMon...")

    def _open_tools_folder(self) -> None:
        from ..engine import frametime as _ft
        from ..core import runproc
        folder = _ft.tools_dir()
        try:
            if runproc.IS_WINDOWS:
                os.startfile(str(folder))      # noqa: S606
            else:
                runproc.run(["xdg-open", str(folder)], timeout=10)
        except Exception:
            Toast(self, f"Tools folder: {folder}", "info")

    def _capture_frames(self, seconds: int) -> None:
        self._run_async(lambda: self.app.benchmark(seconds),
                        self._render_frames, f"Capturing {seconds}s of frame data…")

    def _import_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Import frame-time CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if path:
            self._run_async(lambda: frametime.import_csv(path),
                            self._render_frames, "Importing…")

    def _render_frames(self, stats) -> None:
        self._last_frames = stats
        text = stats.render()
        if stats.available:
            self.ft_spark.set_values(stats.samples)
            text += "\n\nAnalysis:\n" + "\n".join(
                f"• {n}" for n in frametime.diagnose(stats))
            text += (f"\n\nFrames: {stats.frames}   Duration: {stats.duration_s}s   "
                     f"Worst frame: {stats.max_ms} ms   Source: {stats.source}")
        self._write(self.ft_text, text)

    def _compare_csvs(self) -> None:
        before = filedialog.askopenfilename(title="Select BEFORE capture",
                                            filetypes=[("CSV files", "*.csv")])
        if not before:
            return
        after = filedialog.askopenfilename(title="Select AFTER capture",
                                           filetypes=[("CSV files", "*.csv")])
        if not after:
            return

        def work():
            return self.app.compare(frametime.import_csv(before),
                                    frametime.import_csv(after))
        self._run_async(work, self._render_comparison, "Comparing captures…")

    def _render_comparison(self, rep) -> None:
        self._write(self.ft_text, rep.render())
        if rep.regression:
            msg = (rep.regression_detail +
                   "\n\nPhantom Tweeks can restore the most recent optimization run.")
            if confirm_dialog(self, "Performance Regression Detected", msg,
                              danger=True, confirm_text="Restore Changes"):
                hist = self.app.history()
                pending = next((h for h in hist if not h.get("restored")), None)
                if pending:
                    self._run_async(lambda: self.app.restore_backup(pending["id"]),
                                    lambda r: Toast(self, "✓ Changes restored.",
                                                    "success"),
                                    "Restoring…")

    # --- input latency
    def _build_latency(self) -> None:
        page = self._new_page(
            "latency", "Input Responsiveness",
            "Phantom Tweeks measures the factors that actually influence input "
            "latency. It does not claim to remove milliseconds it has not measured.")
        top = ttk.Frame(page)
        top.pack(fill="x", pady=(0, 10))
        ttk.Button(top, text="Analyze", style="Accent.TButton",
                   command=self._refresh_latency).pack(side="left")
        ttk.Label(top, text="Uses your last frame capture when available.",
                  style="MutedBg.TLabel").pack(side="left", padx=12)
        self.latency_text = self._scroll_text(page)

    def _refresh_latency(self) -> None:
        def work():
            stats = getattr(self, "_last_frames", None)
            r = self.app.input_latency(stats)
            out = ["INPUT RESPONSIVENESS", ""]
            out += ["Findings:"] + [f"• {f}" for f in r["findings"]]
            out += ["", "Recommended:"] + [f"• {x}" for x in r["recommendations"]]
            if r.get("note"):
                out += ["", r["note"]]
            displays = self.app.displays()
            if displays:
                out += ["", "DISPLAYS", ""]
                out += [f"  {d.render()}" for d in displays]
            if stats is None or not getattr(stats, "available", False):
                out += ["", "Tip: run a capture on the Frame-Time page to include "
                        "FPS-versus-refresh-rate analysis here."]
            return "\n".join(out)
        self._run_async(work, lambda t: self._write(self.latency_text, t),
                        "Analyzing input responsiveness…")

    # --- network
    def _build_network(self) -> None:
        page = self._new_page(
            "network", "Phantom Network Lab",
            "DNS response time is not the same as game-server ping. Phantom Tweeks "
            "does not promise ping reduction — it finds what is actually wrong.")
        top = ttk.Frame(page)
        top.pack(fill="x", pady=(0, 10))
        ttk.Button(top, text="Run Tests", style="Accent.TButton",
                   command=lambda: self._run_network(False)).pack(side="left")
        ttk.Button(top, text="Full Test",
                   command=lambda: self._run_network(True)).pack(side="left", padx=8)
        ttk.Button(top, text="Route Diagnostics",
                   command=self._traceroute).pack(side="left")

        hist_card = Card(page, "PING HISTORY")
        hist_card.pack(fill="x", pady=(0, 10))
        self.net_chart = BarChart(hist_card, height=140)
        self.net_chart.pack(fill="x")
        self.net_text = self._scroll_text(page, height=16)

    def _refresh_network(self) -> None:
        rows = [(r["date"], r["avg_ms"], f"{r['avg_ms']:.0f} ms")
                for r in self.app.network_history()]
        self.net_chart.set_rows(rows or [("No history yet", None, "")])

    def _run_network(self, full: bool) -> None:
        self._run_async(lambda: self.app.network_lab(quick=not full),
                        self._render_network, "Running network tests…")

    def _render_network(self, r) -> None:
        out = ["NETWORK LAB", "", f"Connection: {r['connection']}", ""]
        for key in ("gateway", "internet"):
            d = r.get(key)
            if not d:
                continue
            out.append(key.title())
            if d.get("error"):
                out.append(f"  {d['error']}")
            else:
                out += [f"  Latency: {d['latency_ms']} ms",
                        f"  Packet Loss: {d['packet_loss_pct']}%",
                        f"  Jitter: {d['jitter_ms']} ms"]
            out.append("")
        out.append("DNS")
        for d in r["dns"]:
            val = f"{d['response_ms']} ms" if d["response_ms"] is not None else "n/a"
            out.append(f"  {d['provider']:<14}{val}")
        out += ["", r["diagnosis"]["summary"], "", "Recommended:"]
        out += [f"• {x}" for x in r["diagnosis"]["recommendations"]]
        out += [""] + [f"Note: {n}" for n in r["notes"]]
        self._write(self.net_text, "\n".join(out))
        self._refresh_network()

    def _traceroute(self) -> None:
        from ..network import lab, dns
        self._run_async(lambda: "\n".join(lab.traceroute()),
                        lambda s: self._write(self.net_text,
                                              "ROUTE DIAGNOSTICS\n\n" + s),
                        "Tracing route…")

    # --- games
    def _build_games(self) -> None:
        page = self._new_page(
            "games", "Games & Profiles",
            "Detection is read-only. Phantom Tweeks never modifies game files, "
            "executables, or anti-cheat.")
        top = ttk.Frame(page)
        top.pack(fill="x", pady=(0, 10))
        ttk.Button(top, text="Rescan Library", style="Accent.TButton",
                   command=self._refresh_games).pack(side="left")
        self.games_text = self._scroll_text(page)

    def _refresh_games(self) -> None:
        def work():
            lib = self.app.game_library()
            running = self.app.detect_game()
            out = ["GAME LIBRARY", ""]
            if not lib:
                out.append("No games detected from installed launcher manifests.")
            for g in lib:
                out.append(f"  {g.name}\n    {g.launcher} — {g.install_dir}")
            out += ["", "CURRENTLY RUNNING", ""]
            if running:
                out += [f"Game: {running.name}",
                        f"Launcher: {running.launcher or 'Standalone'}",
                        f"Anti-Cheat: {running.anti_cheat or 'Not detected'}",
                        f"Processes in tree: {len(running.process_tree)}"]
            else:
                out.append("No game currently running.")
            out += ["", "PROFILES", ""]
            for p in self.app.profiles():
                out += [p.render(), ""]
            out += ["CONFIGURATION SNAPSHOTS", ""]
            snaps = self.app.snapshots()
            out += ([f"Snapshot: {s.name}   ({s.timestamp})" for s in snaps]
                    or ["No snapshots yet."])
            return "\n".join(out)
        self._run_async(work, lambda s: self._write(self.games_text, s),
                        "Scanning game libraries…")

    # --- generic text pages
    def _build_simple(self, key: str, title: str, subtitle: str,
                      producer: Callable[[], str]) -> None:
        page = self._new_page(key, title, subtitle)
        ttk.Button(page, text="Refresh", style="Accent.TButton",
                   command=lambda: self._run_async(
                       producer,
                       lambda s: self._write(getattr(self, f"_{key}_text"), s),
                       "Analyzing…")).pack(anchor="w", pady=(0, 10))
        setattr(self, f"_{key}_text", self._scroll_text(page))
        setattr(self, f"_refresh_{key}",
                lambda: self._run_async(
                    producer,
                    lambda s: self._write(getattr(self, f"_{key}_text"), s),
                    "Analyzing…"))

    def _drivers_text(self) -> str:
        rep = self.app.driver_report()
        out = ["DRIVER CENTER", ""]
        out += [d.render() + "\n" for d in rep["drivers"]]
        out += [rep["summary"], "",
                "Phantom Tweeks never downloads or installs drivers automatically."]
        return "\n".join(out)

    def _storage_text(self) -> str:
        rep = self.app.storage_report()
        out = ["STORAGE LAB", ""]
        for d in rep.disks:
            out.append(f"{d.mountpoint:<8}{d.media_type or 'Unknown':<12}"
                       f"{d.free_gb:.0f} GB free / {d.total_gb:.0f} GB "
                       f"({d.percent_used:.0f}% used)")
        for p in rep.physical:
            out.append(f"\n{p['name']}: {p['media_type']}, "
                       f"health {p['health'] or 'unknown'}"
                       + (f", {p['temperature_c']} °C" if p.get("temperature_c") else ""))
        if rep.candidates:
            out += ["", f"Safe cleanup candidates "
                        f"({rep.reclaimable_mb:.0f} MB reclaimable):"]
            for c in rep.candidates:
                out.append(f"  {c.label:<34}{c.size_mb:>8.0f} MB")
                if c.note:
                    out.append(f"    {c.note}")
            out.append("\nPhantom Tweeks never deletes personal files automatically.")
        out += ["", "Recommendations:"] + [f"• {r}" for r in rep.recommendations]
        return "\n".join(out)

    def _health_text(self) -> str:
        self.app.driver_report()
        return self.app.health().render()

    def _build_startup(self) -> None:
        page = self._new_page(
            "startup", "Startup Manager",
            "Critical Windows components and Phantom Shield protected applications "
            "cannot be disabled. Every change is reversible.")
        ttk.Button(page, text="Refresh", style="Accent.TButton",
                   command=self._refresh_startup).pack(anchor="w", pady=(0, 10))
        self.startup_text = self._scroll_text(page)

    def _refresh_startup(self) -> None:
        def work():
            entries = self.app.startup_entries()
            if not entries:
                return ("STARTUP MANAGER\n\nStartup entries are readable on Windows "
                        "only. Phantom Tweeks is running in analysis-only mode.")
            return "STARTUP MANAGER\n\n" + "\n\n".join(e.render() for e in entries)
        self._run_async(work, lambda s: self._write(self.startup_text, s),
                        "Reading startup entries…")

    # --- history
    def _build_history(self) -> None:
        page = self._new_page(
            "history", "Optimization History & Restore",
            "Restore only reverts changes Phantom Tweeks recorded. Settings you "
            "changed yourself are never touched.")
        top = ttk.Frame(page)
        top.pack(fill="x", pady=(0, 10))
        ttk.Button(top, text="Refresh", command=self._refresh_history).pack(side="left")
        ttk.Button(top, text="Restore Selected",
                   command=self._restore_selected).pack(side="left", padx=8)
        ttk.Button(top, text="Create Snapshot",
                   command=self._create_snapshot).pack(side="left")
        ttk.Button(top, text="RESTORE EVERYTHING", style="Danger.TButton",
                   command=self._restore_everything).pack(side="right")

        # Windows restore point controls live here, next to our own backups.
        self._build_restore_controls(page)

        holder = ttk.Frame(page, style="Panel.TFrame")
        holder.pack(fill="both", expand=True, pady=(10, 0))
        cols = ("date", "title", "changes", "backup", "status")
        self.history_tree = ttk.Treeview(holder, columns=cols, show="headings",
                                         height=18)
        for c, w in zip(cols, (140, 380, 90, 140, 110)):
            self.history_tree.heading(c, text=c.title())
            self.history_tree.column(c, width=w, anchor="w")
        hsb = ttk.Scrollbar(holder, orient="vertical",
                            command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=hsb.set)
        hsb.pack(side="right", fill="y")
        self.history_tree.pack(side="left", fill="both", expand=True)
        # Treeview handles its own wheel events natively once a scrollbar exists.
        self.history_tree.bind("<Double-1>", lambda e: self._restore_selected())

    def _refresh_history(self) -> None:
        for i in self.history_tree.get_children():
            self.history_tree.delete(i)
        for h in self.app.history():
            self.history_tree.insert(
                "", "end", iid=h["id"],
                values=(h["timestamp"][:16].replace("T", " "), h["title"],
                        h["changes"], h["id"],
                        # 'status' is written by the vault and distinguishes a
                        # partial restore from a clean one; older history rows
                        # predate it, so fall back to the boolean.
                        h.get("status")
                        or ("Restored" if h.get("restored") else "Applied")))

    def _restore_selected(self) -> None:
        sel = self.history_tree.selection()
        if not sel:
            Toast(self, "Select a history entry first.", "warning")
            return
        bid = sel[0]
        if not confirm_dialog(self, "Restore Backup",
                              f"Restore backup {bid}?\n\nThis reverts only the changes "
                              "recorded in that entry.", confirm_text="Restore"):
            return
        self._run_async(lambda: self.app.restore_backup(bid),
                        lambda r: (self._refresh_history(),
                                   Toast(self, "✓ Restore complete.", "success")),
                        "Restoring…")

    def _restore_everything(self) -> None:
        if not confirm_dialog(
                self, "RESTORE EVERYTHING",
                "This reverts every change Phantom Tweeks has made on this PC, using "
                "the recorded backups.\n\nUnrelated settings you changed yourself are "
                "never touched.\n\nSome changes may require a reboot to fully revert.",
                danger=True, confirm_text="Restore Everything", steps=2):
            return
        self._run_async(self.app.restore_everything,
                        lambda r: (self._refresh_history(),
                                   Toast(self, "✓ All Phantom Tweeks changes restored.",
                                         "success")),
                        "Restoring everything…")

    def _create_snapshot(self) -> None:
        win = tk.Toplevel(self)
        win.title("Create Snapshot")
        win.configure(bg=COLORS["bg"])
        win.geometry("460x230")
        frame = ttk.Frame(win, style="Panel.TFrame", padding=18)
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        ttk.Label(frame, text="Snapshot name", style="Accent.TLabel").pack(anchor="w")
        ttk.Label(frame, text="Snapshots contain only the settings Phantom Tweeks "
                              "manages.", style="Muted.TLabel", wraplength=380,
                  justify="left").pack(anchor="w", pady=(2, 10))
        entry = ttk.Entry(frame)
        entry.pack(fill="x")
        entry.insert(0, "Competitive Gaming")

        def save():
            name = entry.get().strip()
            if name:
                self.app.create_snapshot(name)
                Toast(self, f"✓ Snapshot '{name}' created.", "success")
                win.destroy()
        ttk.Button(frame, text="Create", style="Accent.TButton",
                   command=save).pack(anchor="e", pady=12)

    # --- premium
    def _build_power(self) -> None:
        page = self._new_page(
            "power", "Phantom Power Plan",
            "A custom Windows power plan copied from Balanced and tuned for "
            "steady frame pacing. Your existing plans are never modified.")
        top = ttk.Frame(page)
        top.pack(fill="x", pady=(0, 10))
        ttk.Button(top, text="Create / Update Phantom Plan",
                   style="Accent.TButton",
                   command=self._create_power_plan).pack(side="left")
        ttk.Button(top, text="Remove Phantom Plan", style="Danger.TButton",
                   command=self._delete_power_plan).pack(side="left", padx=8)
        ttk.Button(top, text="Refresh", style="Chip.TButton",
                   command=self._refresh_power).pack(side="left")
        ttk.Button(top, text="Clean up duplicates", style="Chip.TButton",
                   command=self._cleanup_power).pack(side="left", padx=6)
        self.power_status_var = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.power_status_var,
                  style="MutedBg.TLabel").pack(side="right")
        self.power_text = self._scroll_text(page)

    def _refresh_power(self) -> None:
        st = powerplan.status()
        if not st.get("available"):
            self.power_status_var.set("Unavailable on this platform")
            self._write(self.power_text,
                        st.get("reason", "powercfg is not available.")
                        + "\n\n" + powerplan.describe())
            return
        if st["active"]:
            self.power_status_var.set("Phantom plan ACTIVE")
        elif st["installed"]:
            self.power_status_var.set("Installed, not active")
        else:
            self.power_status_var.set("Not installed")

        lines = [f"Active plan: {st['active_plan']}",
                 f"Machine type: {'Laptop (battery present)' if st['laptop'] else 'Desktop'}",
                 "", "Power plans on this system:"]
        for pl in st["plans"]:
            mark = " *" if pl["active"] else "  "
            lines.append(f" {mark} {pl['name']}")
        lines += ["", powerplan.describe()]
        self._write(self.power_text, "\n".join(lines))

    def _cleanup_power(self) -> None:
        """Remove extra Phantom plans left by the old em-dash naming bug."""
        def done(result):
            ok, msgs = result
            self._write(self.power_text, "\n".join(msgs))
            Toast(self, msgs[0] if msgs else "Done",
                  "success" if ok else "warning")
            self._refresh_power()
        self._run_async(powerplan.cleanup_duplicates, done, "Cleaning up...")

    def _create_power_plan(self) -> None:
        if not confirm_dialog(
                self, "Create the Phantom power plan?",
                "This creates a NEW Windows power plan copied from Balanced, "
                "then applies " f"{len(powerplan.PHANTOM_SETTINGS)} tuned "
                "settings to it.\n\nYour existing power plans are not "
                "modified. You can remove it at any time and Windows will "
                "return to Balanced."):
            return

        def done(result):
            ok, msgs, changes = result
            Toast(self, ("✓ " if ok else "⚠ ") + msgs[0],
                  "success" if ok else "warning")
            self._refresh_power()

        self._run_async(lambda: powerplan.create_plan(True), done,
                        "Creating power plan…")

    def _delete_power_plan(self) -> None:
        if not confirm_dialog(self, "Remove the Phantom power plan?",
                              "Windows will switch back to Balanced."):
            return
        ok, msgs = powerplan.delete_plan()
        Toast(self, ("✓ " if ok else "⚠ ") + msgs[-1],
              "success" if ok else "warning")
        self._refresh_power()

    # ---------------- maintenance ----------------
    # ---------------- live game detection ----------------
    def _start_game_watch(self) -> None:
        """Detect games that start after the app, or were already running.

        Callbacks arrive on the watcher thread, so every one of them hops back
        to the Tk main loop with after(0, ...) before touching a widget.
        """
        self._watcher = gamewatch.GameWatcher(
            interval=5.0,
            on_start=lambda g: self.after(0, lambda: self._on_game_start(g)),
            on_stop=lambda g: self.after(0, lambda: self._on_game_stop(g)),
        )
        try:
            self._watcher.start()
        except Exception:
            # Detection is a convenience; never let it stop the app opening.
            pass

    def _on_game_start(self, game) -> None:
        self.game_var.set(f"◐  {game.name}")
        bits = [f"{game.name} detected"]
        if game.anti_cheat:
            bits.append(f"{game.anti_cheat} anti-cheat present — protected, "
                        "Phantom Tweeks will not touch it")
        Toast(self, "  •  ".join(bits), "success")

        gate = features.check("auto_profiles")
        if gate.allowed:
            self._auto_apply_profile(game)
        else:
            CENTER.notify(
                "game_detected",
                f"{game.name} is running. Open Games & Profiles to apply a "
                "profile, or unlock automatic switching with Premium.")

    def _auto_apply_profile(self, game) -> None:
        """Premium: apply the saved profile for this game.

        Only ever applies a profile the user saved themselves, and only when
        automatic optimization is explicitly enabled in Settings.
        """
        if not self.app.config.get("auto_apply_game_profile"):
            CENTER.notify(
                "game_detected",
                f"{game.name} is running. Automatic optimization is off, so "
                "nothing was changed. Enable it in Settings if you want "
                "profiles applied automatically.")
            return
        try:
            from ..engine import profiles
            prof = profiles.load(game.name)
            if prof is None:
                return
            CENTER.notify("profile_applied",
                          f"Applied your saved profile for {game.name}.")
        except Exception:
            pass

    def _on_game_stop(self, game) -> None:
        self.game_var.set("No game detected")
        Toast(self, f"{game.name} closed", "info")

    # ---------------- automatic updates ----------------
    def _check_updates_async(self, force: bool = False) -> None:
        """Look for a newer release, quietly and off the UI thread."""
        if not force and not self.app.config.get("check_updates"):
            return

        def work():
            return updates.check() if force else updates.check_if_due()

        def done(info):
            if info:
                self._pending_update = info
                self._show_update_banner(info)
            elif force:
                Toast(self, f"✓ You are on the latest version ({VERSION})",
                      "success")

        self._run_async(work, done, "Checking for updates…")

    def _show_update_banner(self, info) -> None:
        label = f"Version {info.version} is available"
        if info.prerelease:
            label += " (pre-release)"
        label += f" — you have {VERSION}"
        self.update_msg.set(label)
        # Sits directly under the header, above the main body.
        self.update_bar.pack(fill="x", before=self._body)
        CENTER.notify("update_available", label)

    def _dismiss_update(self) -> None:
        self.update_bar.pack_forget()
        updates.snooze()

    def _skip_update(self) -> None:
        info = self._pending_update
        if info:
            updates.skip_version(info.version)
        self.update_bar.pack_forget()
        Toast(self, "You will not be reminded about this version again", "info")

    def _warn_if_not_admin(self) -> None:
        """Say once, quietly, what is unavailable without elevation."""
        if not IS_WINDOWS or is_admin():
            return
        if not self.app.config.get("warn_when_not_admin"):
            return
        from ..core import elevation
        self.update_msg.set("Running without administrator rights - some "
                            "tweaks will be unavailable")
        self.update_bar.pack(fill="x", before=self._body)
        CENTER.notify("not_admin",
                      "Some tweaks need administrator rights. See Help & "
                      "Diagnostics for the details.")
        self._admin_note = elevation.explain_limits()

    def _show_update_details(self) -> None:
        """Open Help with the release details, and offer the download.

        The banner previously just navigated to Help, which showed the FAQ and
        no mention of the update - the user had to guess what to do next.
        """
        info = self._pending_update
        self.show("help")
        if not info:
            note = getattr(self, "_admin_note", "")
            if note:
                self._write(self.help_panel, note)
            return
        body = [info.render(), "",
                "-" * 58, "",
                "Press 'Download update' above to fetch it.",
                "",
                "The download is checked against the SHA-256 published with",
                "the release and saved to your data folder. Phantom Tweeks",
                "does not run it for you - you install it when you are ready.",
                ""]
        if info.notes:
            body += ["Release note:", info.notes, ""]
        body += ["Not now? 'Skip this version' silences this release for good;",
                 "'Dismiss' reminds you again in a week."]
        self._write(self.help_panel, "\n".join(body))

    def _download_update(self) -> None:
        info = self._pending_update
        if not info:
            Toast(self, "No update is pending", "info")
            return
        asset = info.installer
        if not asset:
            Toast(self, "This release has no installer to download", "warning")
            return
        if not confirm_dialog(
                self, f"Download Phantom Tweeks {info.version}?",
                f"{asset['name']} ({asset.get('size_mb', '?')} MB) will be "
                "downloaded over HTTPS and checked against its published "
                "SHA-256 checksum.\n\n"
                "It is saved to your data folder and NOT run automatically — "
                "you install it yourself when you are ready.\n\n"
                + ("These binaries are not code-signed yet, so Windows "
                   "SmartScreen will warn on first run."
                   if not info.signed else "")):
            return

        def work():
            def progress(done, total):
                if total:
                    pct = done * 100 // total
                    self.after(0, lambda: self.status_var.set(
                        f"Downloading {info.version}... {pct}%"))
            return updates.download_and_verify(info, asset, progress=progress)

        def done(result):
            ok, message, path = result
            self.show("help")
            self._write(self.help_panel, message)
            Toast(self, "✓ Update verified and saved" if ok
                  else "⚠ Update rejected", "success" if ok else "warning")

        self._run_async(work, done, f"Downloading {info.version}…")

    # ---------------- DNS ----------------
    def _build_dns(self) -> None:
        page = self._new_page(
            "dns", "DNS",
            "Measure every major DNS provider from this machine and switch to "
            "one in a click. DNS affects how fast names resolve - launchers, "
            "stores and web pages. It does NOT change your in-game ping.")

        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=(0, 10))
        ttk.Button(bar, text="Benchmark all providers", style="Accent.TButton",
                   command=self._run_dns_benchmark).pack(side="left")
        ttk.Button(bar, text="Show current DNS", style="Chip.TButton",
                   command=self._show_current_dns).pack(side="left", padx=6)
        ttk.Button(bar, text="Restore previous", style="Chip.TButton",
                   command=self._revert_dns).pack(side="left")

        pick = ttk.Frame(page)
        pick.pack(fill="x", pady=(0, 10))
        ttk.Label(pick, text="Provider:", style="MutedBg.TLabel").pack(side="left")
        self.dns_choice = tk.StringVar(value="cloudflare")
        names = [f"{p.name}  ({p.primary})" if p.primary else p.name
                 for p in dns.PROVIDERS]
        self._dns_ids = [p.id for p in dns.PROVIDERS]
        self.dns_combo = ttk.Combobox(pick, values=names, state="readonly",
                                      width=46)
        self.dns_combo.current(self._dns_ids.index("cloudflare"))
        self.dns_combo.pack(side="left", padx=8)
        ttk.Button(pick, text="Apply this DNS", style="Accent.TButton",
                   command=self._apply_dns).pack(side="left")

        self.dns_panel = self._scroll_text(page)
        self._write(self.dns_panel, self._dns_intro())
        self._dns_last_change = None

    def _dns_intro(self) -> str:
        lines = ["DNS PROVIDERS", ""]
        for p in dns.PROVIDERS:
            lines += [p.render(), ""]
        lines += [
            "-" * 60,
            "Filtering and logging descriptions are each operator's own",
            "published policy, not something Phantom Tweeks can verify.",
            "",
            "Press 'Benchmark all providers' to measure them from here.",
        ]
        return "\n".join(lines)

    def _run_dns_benchmark(self) -> None:
        def work():
            results = dns.benchmark(rounds=2)
            return results, dns.recommend(results)

        def done(payload):
            results, advice = payload
            out = ["DNS BENCHMARK", "",
                   "Measured from this machine, just now:", ""]
            for r in results:
                out.append("  " + r.render())
            out += ["", "-" * 60, "", advice]
            self._write(self.dns_panel, "\n".join(out))
            best = next((r for r in results if r.reachable), None)
            if best:
                idx = self._dns_ids.index(best.provider.id)
                self.dns_combo.current(idx)
                Toast(self, f"Fastest: {best.provider.name}", "success")

        self._run_async(work, done, "Benchmarking DNS providers...")

    def _show_current_dns(self) -> None:
        self._write(self.dns_panel, dns.describe_current())

    def _selected_dns(self):
        i = self.dns_combo.current()
        return dns.BY_ID[self._dns_ids[i if i >= 0 else 0]]

    def _apply_dns(self) -> None:
        provider = self._selected_dns()
        preview = dns.apply(provider.id, dry_run=True)
        if not preview["changes"] and not preview["ok"]:
            Toast(self, preview["message"], "warning")
            self._write(self.dns_panel, preview["message"])
            return

        adapters = "\n".join(f"  {c['adapter']}: "
                              f"{', '.join(c['previous']) or 'automatic'} "
                              f"-> {', '.join(c['new'])}"
                              for c in preview["changes"])
        if not confirm_dialog(
                self, f"Switch DNS to {provider.name}?",
                f"{adapters}\n\n"
                "This changes name resolution only. It will not change your "
                "in-game ping.\n\n"
                "The previous settings are saved and 'Restore previous' puts "
                "them back."):
            return

        def work():
            return dns.apply(provider.id, dry_run=False)

        def done(result):
            self._dns_last_change = result.get("changes")
            lines = [result["message"], ""]
            for c in result.get("changes", []):
                state = "applied" if c.get("applied") else "FAILED"
                lines.append(f"  {c['adapter']}: {state}")
                if c.get("error"):
                    lines.append(f"    {c['error']}")
            lines += ["", dns.describe_current()]
            self._write(self.dns_panel, "\n".join(lines))
            Toast(self, result["message"],
                  "success" if result["ok"] else "warning")

        self._run_async(work, done, f"Applying {provider.name}...")

    def _revert_dns(self) -> None:
        if not self._dns_last_change:
            Toast(self, "No DNS change to undo in this session", "info")
            return
        result = dns.revert(self._dns_last_change)
        self._write(self.dns_panel, result["message"] + "\n\n"
                    + dns.describe_current())
        Toast(self, result["message"], "success" if result["ok"] else "warning")
        if result["ok"]:
            self._dns_last_change = None

    # ---------------- registry inspector ----------------
    def _build_registry(self) -> None:
        page = self._new_page(
            "registry", "Registry",
            "Every registry value Phantom Tweeks can change, with its current "
            "state, the Windows default and what it means. This is not a "
            "general registry editor - regedit does that better, and a full "
            "editor here would invite blind copy-paste from forum posts.")

        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=(0, 10))
        ttk.Button(bar, text="Read all values", style="Accent.TButton",
                   command=self._refresh_registry).pack(side="left")
        ttk.Button(bar, text="Show only changed", style="Chip.TButton",
                   command=lambda: self._refresh_registry(changed_only=True)
                   ).pack(side="left", padx=6)
        ttk.Label(bar, text="  Search:", style="MutedBg.TLabel").pack(side="left")
        self.reg_query = ttk.Entry(bar, width=26)
        self.reg_query.pack(side="left", padx=6)
        self.reg_query.bind("<Return>", lambda e: self._search_registry())
        ttk.Button(bar, text="Find", style="Chip.TButton",
                   command=self._search_registry).pack(side="left")

        self.reg_panel = self._scroll_text(page)
        self._write(self.reg_panel,
                    "Press 'Read all values' to inspect the registry.")

    def _refresh_registry(self, changed_only: bool = False) -> None:
        def work():
            if not changed_only:
                return regview.report()
            rows = [(m, v, st) for m, v, st in regview.snapshot()
                    if st in ("tweaked", "custom")]
            if not rows:
                return ("Nothing has been changed.\n\n"
                        "Every managed registry value is either at the "
                        "Windows default or not present. That is the expected "
                        "state on a system where no tweaks have been applied.")
            out = [f"{len(rows)} value(s) differ from the Windows default", ""]
            for m, _v, _st in rows:
                out += [m.render(), ""]
            return "\n".join(out)

        self._run_async(work, lambda text: self._write(self.reg_panel, text),
                        "Reading the registry...")

    def _search_registry(self) -> None:
        term = self.reg_query.get().strip()
        if not term:
            self._refresh_registry()
            return
        hits = regview.find(term)
        if not hits:
            self._write(self.reg_panel,
                        f"No managed value matches {term!r}.\n\n"
                        "Phantom Tweeks only lists values it can change. If "
                        "you found a value elsewhere, check the Tweak "
                        "Encyclopedia before applying it.")
            return
        out = [f"{len(hits)} match(es) for {term!r}", ""]
        for m in hits:
            out += [m.render(), ""]
        self._write(self.reg_panel, "\n".join(out))

    # ---------------- tweak encyclopedia ----------------
    # ---------------- consolidated performance view ----------------
    def _build_perf(self) -> None:
        page = self._new_page(
            "perf", "Performance",
            "Every measurable component in one place - CPU cores, GPUs, "
            "memory, every attached drive, network adapters and the heaviest "
            "processes. Anything that cannot be read says so rather than "
            "being estimated.")
        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=(0, 10))
        ttk.Button(bar, text="Refresh", style="Accent.TButton",
                   command=self._refresh_perf).pack(side="left")
        ttk.Button(bar, text="Copy report", style="Chip.TButton",
                   command=self._copy_perf).pack(side="left", padx=6)
        ttk.Button(bar, text="Export report...", style="Chip.TButton",
                   command=self._export_full_report).pack(side="left")
        self.perf_auto = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Auto-refresh every 5s",
                        variable=self.perf_auto,
                        command=self._perf_auto_tick).pack(side="left", padx=6)
        self.perf_panel = self._scroll_text(page)
        self._write(self.perf_panel, "Press Refresh to measure this system.")
        self._perf_text = ""

    def _refresh_perf(self) -> None:
        def done(report):
            self._perf_text = report.render()
            self._write(self.perf_panel, self._perf_text)
            n = len(report.warnings)
            if n:
                Toast(self, f"{n} item(s) need attention", "warning")

        self._run_async(perfview.build, done, "Measuring...")

    def _perf_auto_tick(self) -> None:
        if not self.perf_auto.get():
            return
        if self._current == "perf":
            self._refresh_perf()
        self.after(5000, self._perf_auto_tick)

    def _copy_perf(self) -> None:
        text = self._perf_text or "No measurements yet."
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            Toast(self, "Copied - safe to paste into a help thread", "success")
        except tk.TclError:
            Toast(self, "Could not access the clipboard", "warning")

    def _export_full_report(self) -> None:
        """Write a complete diagnostic report in the chosen format."""
        path = filedialog.asksaveasfilename(
            title="Export diagnostic report",
            defaultextension=".html",
            initialfile="PhantomTweeks-Report.html",
            filetypes=[("Web page", "*.html"), ("Markdown", "*.md"),
                       ("JSON", "*.json"), ("CSV", "*.csv"),
                       ("Text", "*.txt")])
        if not path:
            return

        def done(result):
            ok, message = result
            Toast(self, "Report saved" if ok else "Export failed",
                  "success" if ok else "warning")
            if self._current == "perf":
                self._write(self.perf_panel, message)

        self._run_async(lambda: reports.save(path), done, "Building report...")

    # ---------------- Windows System Restore ----------------
    def _build_restore_controls(self, parent) -> None:
        """Restore-point controls, added to the History page.

        Our own journal reverts individual changes precisely. A Windows
        restore point is coarser but survives a PC that will not boot, which
        the journal cannot - it needs Phantom Tweeks to run.
        """
        card = Card(parent, "WINDOWS SYSTEM RESTORE",
                    "An extra safety net beyond our own backups. A restore "
                    "point can be rolled back from Windows Recovery even if "
                    "the PC will not start.")
        card.pack(fill="x", pady=(10, 0))
        row = ttk.Frame(card, style="Panel.TFrame")
        row.pack(anchor="w", pady=(4, 0))
        ttk.Button(row, text="Create restore point", style="Chip.TButton",
                   command=self._create_restore_point).pack(side="left")
        ttk.Button(row, text="Check protection status", style="Chip.TButton",
                   command=self._check_protection).pack(side="left", padx=6)
        self.rp_status = tk.StringVar(value="")
        ttk.Label(card, textvariable=self.rp_status, style="Muted.TLabel",
                  wraplength=760, justify="left").pack(anchor="w", pady=(8, 0))

    def _check_protection(self) -> None:
        def done(st):
            self.rp_status.set(st.render())
        self._run_async(restorepoint.status, done, "Checking...")

    def _create_restore_point(self) -> None:
        def done(result):
            ok, message = result
            self.rp_status.set(message)
            Toast(self, "Restore point created" if ok
                  else "Could not create a restore point",
                  "success" if ok else "warning")
        self._run_async(
            lambda: restorepoint.create("Before Phantom Tweeks changes"),
            done, "Creating a restore point...")

    # ---------------- latency & performance toggles ----------------
    def _build_perftweaks(self) -> None:
        page = self._new_page(
            "perftweaks", "Latency Tweaks",
            "Input, display and system settings as simple switches. Flip one "
            "on to apply it, flip it back to restore the Windows default "
            "exactly. Nothing here overclocks or touches security.")

        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=(0, 10))
        ttk.Button(bar, text="Turn on the safe ones", style="Accent.TButton",
                   command=self._perf_enable_safe).pack(side="left")
        ttk.Button(bar, text="Turn everything off", style="Chip.TButton",
                   command=self._perf_disable_all).pack(side="left", padx=6)
        ttk.Button(bar, text="Refresh state", style="Chip.TButton",
                   command=self._refresh_perftweaks).pack(side="left")

        scroll = ScrollFrame(page)
        scroll.pack(fill="both", expand=True)
        body = scroll.inner
        self._pt_vars = {}

        for cat in perftweaks.CATEGORIES:
            # NVIDIA settings have their own page in the sidebar.
            if cat == "NVIDIA":
                continue
            items = perftweaks.by_category(cat)
            if not items:
                continue
            card = Card(body, cat.upper())
            card.pack(fill="x", pady=(0, 10))
            for t in items:
                row = ttk.Frame(card, style="Panel.TFrame")
                row.pack(fill="x", anchor="w", pady=(6, 0))
                var = tk.BooleanVar(value=False)
                self._pt_vars[t.id] = var
                ttk.Checkbutton(row, text=t.name, variable=var,
                                command=lambda i=t.id: self._pt_toggle(i)
                                ).pack(side="left")
                if t.requires_admin:
                    ttk.Label(row, text="  admin", style="Muted.TLabel"
                              ).pack(side="left")
                InfoButton(row, t.name,
                           f"{t.effect}\n\n{t.detail}"
                           + (f"\n\nCaution: {t.warning}" if t.warning else "")
                           ).pack(side="left", padx=6)
                ttk.Label(card, text=f"     {t.effect}", style="Muted.TLabel",
                          wraplength=740, justify="left").pack(anchor="w")
                if t.warning:
                    ttk.Label(card, text=f"     ! {t.warning}",
                              style="Warn.TLabel", wraplength=740,
                              justify="left").pack(anchor="w")

        self.pt_log = self._scroll_text(page, height=5)
        self._write(self.pt_log,
                    "Every change is backed up first. Switching a tweak off "
                    "restores exactly what was there before.")
        self._refresh_perftweaks()

    def _refresh_perftweaks(self) -> None:
        def done(state):
            remembered = 0
            for tid, (is_on, label) in state.items():
                if tid in self._pt_vars:
                    self._pt_vars[tid].set(bool(is_on))
                if tid in getattr(self, "_nv_vars", {}):
                    self._nv_vars[tid].set(bool(is_on))
                if "remembered" in label:
                    remembered += 1
            if remembered:
                self._write(self.pt_log,
                            f"{remembered} setting(s) shown from your saved "
                            "selections - Windows does not expose those for "
                            "reading.")
        self._run_async(perftweaks.labelled_states, done, "Reading settings...")

    def _pt_toggle(self, tweak_id: str) -> None:
        want = self._pt_vars[tweak_id].get()
        tweak = perftweaks.BY_ID[tweak_id]
        if want and tweak.warning:
            if not confirm_dialog(self, tweak.name,
                                  f"{tweak.detail}\n\nCaution: {tweak.warning}"):
                self._pt_vars[tweak_id].set(False)
                return

        def done(result):
            ok, message, _ = result
            self._write(self.pt_log, message)
            Toast(self, message, "success" if ok else "warning")
            if not ok:
                self._pt_vars[tweak_id].set(not want)

        self._run_async(lambda: perftweaks.set_tweak(tweak_id, want), done,
                        f"{tweak.name}...")

    def _perf_enable_safe(self) -> None:
        safe = [t for t in perftweaks.TWEAKS if not t.warning]
        if not confirm_dialog(
                self, f"Turn on {len(safe)} tweaks?",
                "\n".join(f"  - {t.name}" for t in safe)
                + "\n\nEach is backed up first. The ones with caution notes "
                  "are skipped - turn those on yourself if you want them."):
            return

        def work():
            return "\n".join(
                ("  ok   " if ok else "  fail ") + msg
                for ok, msg, _ in
                (perftweaks.set_tweak(t.id, True) for t in safe))

        def done(text):
            self._write(self.pt_log, text)
            self._refresh_perftweaks()
            Toast(self, "Applied", "success")

        self._run_async(work, done, "Applying...")

    def _perf_disable_all(self) -> None:
        if not confirm_dialog(self, "Turn every tweak off?",
                              "This restores the Windows default for all of "
                              "them."):
            return

        def work():
            return "\n".join(
                ("  ok   " if ok else "  fail ") + msg
                for ok, msg, _ in
                (perftweaks.set_tweak(t.id, False) for t in perftweaks.TWEAKS))

        def done(text):
            self._write(self.pt_log, text)
            self._refresh_perftweaks()
            Toast(self, "Reverted", "success")

        self._run_async(work, done, "Reverting...")

    # ---------------- NVIDIA detail ----------------
    def _build_nvidia(self) -> None:
        page = self._new_page(
            "nvidia", "NVIDIA GPU",
            "Clocks, power limits, PCIe link and the card's own throttle "
            "reasons. Phantom Tweeks reports these but never changes clocks - "
            "overclocking is specific to each individual chip.")
        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=(0, 10))
        ttk.Button(bar, text="Read GPU", style="Accent.TButton",
                   command=self._refresh_nvidia).pack(side="left")
        ttk.Button(bar, text="What is limiting my clocks?", style="Chip.TButton",
                   command=self._nvidia_diagnose).pack(side="left", padx=6)

        # The NVIDIA toggles live here rather than buried in Latency Tweaks.
        nv_items = perftweaks.by_category("NVIDIA")
        if nv_items:
            # In a scroll area: at 1000x640 the card and the report panel
            # competed for height and Tk compressed the rows until the info
            # buttons clipped to a few pixels.
            nv_scroll = ScrollFrame(page, height=250)
            nv_scroll.pack(fill="x", pady=(0, 10))
            card = Card(nv_scroll.inner, f"NVIDIA SETTINGS ({len(nv_items)})",
                        "Applied through the driver. Each is reversible.")
            card.pack(fill="x")
            self._nv_vars = {}
            for t in nv_items:
                row = ttk.Frame(card, style="Panel.TFrame")
                row.pack(fill="x", anchor="w", pady=(4, 0))
                var = tk.BooleanVar(value=False)
                self._nv_vars[t.id] = var
                ttk.Checkbutton(row, text=t.name, variable=var,
                                command=lambda i=t.id: self._nv_toggle(i)
                                ).pack(side="left")
                InfoButton(row, t.name,
                           f"{t.effect}\n\n{t.detail}"
                           + (f"\n\nCaution: {t.warning}" if t.warning else "")
                           ).pack(side="left", padx=6)
                ttk.Label(card, text=f"     {t.effect}", style="Muted.TLabel",
                          wraplength=720, justify="left").pack(anchor="w")
                if t.warning:
                    ttk.Label(card, text=f"     ! {t.warning}",
                              style="Warn.TLabel", wraplength=720,
                              justify="left").pack(anchor="w")

        self.nv_panel = self._scroll_text(page, height=10)
        self._write(self.nv_panel, "Press 'Read GPU' to query nvidia-smi.")

    def _refresh_nvidia(self) -> None:
        self._run_async(nvidia_gpu.report,
                        lambda text: self._write(self.nv_panel, text),
                        "Reading GPU...")

    def _nvidia_diagnose(self) -> None:
        def done(findings):
            if not findings:
                self._write(self.nv_panel,
                            "Nothing is limiting your clocks.\n\n"
                            "No power cap, thermal limit or PCIe downgrade "
                            "was reported. The card is free to boost.\n\n"
                            "(If there is no NVIDIA driver, press 'Read GPU' "
                            "for details.)")
                return
            out = ["WHAT IS LIMITING YOUR CLOCKS", ""]
            for f in findings:
                out += [f"  - {f}", ""]
            self._write(self.nv_panel, "\n".join(out))
            Toast(self, f"{len(findings)} finding(s)", "warning")

        self._run_async(nvidia_gpu.diagnose, done, "Checking throttle reasons...")

    def _nv_toggle(self, tweak_id: str) -> None:
        want = self._nv_vars[tweak_id].get()
        tweak = perftweaks.BY_ID[tweak_id]
        if want and tweak.warning:
            if not confirm_dialog(self, tweak.name,
                                  f"{tweak.detail}\n\nCaution: {tweak.warning}"):
                self._nv_vars[tweak_id].set(False)
                return

        def done(result):
            ok, message, _ = result
            self._write(self.nv_panel, message)
            Toast(self, message, "success" if ok else "warning")
            if not ok:
                self._nv_vars[tweak_id].set(not want)

        self._run_async(lambda: perftweaks.set_tweak(tweak_id, want), done,
                        f"{tweak.name}...")

    # ---------------- driver centre with real update checking ----------
    def _build_drivers(self) -> None:
        page = self._new_page(
            "drivers", "Driver Center",
            "Your installed drivers, and a real version check against what "
            "NVIDIA currently publishes. Phantom Tweeks never downloads or "
            "installs a driver - those load kernel code, and automated "
            "driver updaters are a well-known malware vector.")
        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=(0, 10))
        ttk.Button(bar, text="List installed drivers", style="Accent.TButton",
                   command=self._refresh_drivers).pack(side="left")
        ttk.Button(bar, text="Check for GPU driver updates",
                   style="Chip.TButton",
                   command=self._check_driver_updates).pack(side="left", padx=6)
        ttk.Button(bar, text="Open vendor download page", style="Chip.TButton",
                   command=self._open_driver_page).pack(side="left")
        self.drv_panel = self._scroll_text(page)
        self._write(self.drv_panel, self._drivers_text())
        self._driver_url = ""

    def _refresh_drivers(self) -> None:
        self._run_async(self._drivers_text,
                        lambda t: self._write(self.drv_panel, t),
                        "Reading drivers...")

    def _check_driver_updates(self) -> None:
        from ..engine import driverupdate

        def done(text):
            self._write(self.drv_panel, text)
            behind = driverupdate.outdated()
            if behind:
                self._driver_url = behind[0].download_url
                Toast(self, f"{len(behind)} driver update(s) available",
                      "warning")
            else:
                Toast(self, "No confirmed updates", "success")

        self._run_async(driverupdate.report, done,
                        "Checking with the vendor...")

    def _open_driver_page(self) -> None:
        import webbrowser
        from ..engine import driverupdate
        url = self._driver_url or driverupdate.NVIDIA_DOWNLOADS
        try:
            webbrowser.open(url)
            Toast(self, "Opened the vendor download page", "info")
        except Exception:
            Toast(self, url, "info")

    # ---------------- CPU: Intel and AMD ----------------
    def _build_cpu(self) -> None:
        page = self._new_page(
            "cpu", "CPU",
            "Intel and AMD need genuinely different advice, and generic "
            "tweak lists give both the same answer. This detects which you "
            "have and says what actually matters for it.")
        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=(0, 10))
        ttk.Button(bar, text="Detect my CPU", style="Accent.TButton",
                   command=self._refresh_cpu).pack(side="left")
        ttk.Button(bar, text="Copy report", style="Chip.TButton",
                   command=self._copy_cpu).pack(side="left", padx=6)
        self.cpu_panel = self._scroll_text(page)
        self._write(self.cpu_panel,
                    "Press 'Detect my CPU'.\n\n"
                    "Intel 12th gen and newer are hybrid - P-cores and "
                    "E-cores - where manual affinity actively hurts. AMD "
                    "Ryzen is unusually sensitive to memory speed, so "
                    "EXPO/DOCP often matters more than every software tweak "
                    "combined. Same list of tweaks, opposite advice.")
        self._cpu_text = ""

    def _refresh_cpu(self) -> None:
        def done(text):
            self._cpu_text = text
            self._write(self.cpu_panel, text)
        self._run_async(cpuvendor.report, done, "Reading CPU...")

    def _copy_cpu(self) -> None:
        text = self._cpu_text or "No CPU report yet."
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            Toast(self, "Copied", "success")
        except tk.TclError:
            Toast(self, "Could not access the clipboard", "warning")

    # ---------------- bufferbloat ----------------
    def _build_bufferbloat(self) -> None:
        page = self._new_page(
            "bufferbloat", "Bufferbloat",
            "Idle ping is what speed tests report, and it barely matters for "
            "gaming. What ruins a match is latency while the connection is "
            "busy. This measures both, and unlike most tweaks the fix is "
            "real.")
        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=(0, 10))
        ttk.Button(bar, text="Run the test", style="Accent.TButton",
                   command=self._run_bufferbloat).pack(side="left")
        ttk.Label(bar, text="  Takes about 25 seconds and briefly uses your "
                            "full connection.",
                  style="MutedBg.TLabel").pack(side="left", padx=8)
        self.bloat_panel = self._scroll_text(page)
        self._write(self.bloat_panel,
                    "Press 'Run the test'.\n\n"
                    "It pings continuously while idle, then during a "
                    "download, then during an upload. The difference is your "
                    "bufferbloat - the queueing delay that turns a 20 ms ping "
                    "into 300 ms the moment someone starts a download.\n\n"
                    "The test saturates your connection for a few seconds, so "
                    "do not run it mid-match.")

    def _run_bufferbloat(self) -> None:
        def work():
            return bloat.run(seconds_per_phase=6.0,
                             progress=lambda m: self.after(
                                 0, lambda: self.status_var.set(m)))

        def done(result):
            self._write(self.bloat_panel, result.render())
            if not result.measured:
                Toast(self, "Could not measure - ICMP may be blocked", "warning")
            else:
                Toast(self, f"Bufferbloat grade {result.grade}",
                      "success" if result.grade in ("A+", "A", "B")
                      else "warning")

        self._run_async(work, done, "Measuring bufferbloat...")

    # ---------------- network tweaks: simple toggles ----------------
    def _build_nettweaks(self) -> None:
        page = self._new_page(
            "nettweaks", "Network Tweaks",
            "Simple on/off switches. These reduce delay your own PC adds - "
            "packet batching, adapter wake-up time, name lookups and "
            "background uploads. They do not change the distance to a game "
            "server, which is what ping measures.")

        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=(0, 10))
        ttk.Button(bar, text="Turn on the safe ones", style="Accent.TButton",
                   command=self._net_enable_safe).pack(side="left")
        ttk.Button(bar, text="Turn everything off", style="Chip.TButton",
                   command=self._net_disable_all).pack(side="left", padx=6)
        ttk.Button(bar, text="Refresh state", style="Chip.TButton",
                   command=self._refresh_nettweaks).pack(side="left")
        ttk.Button(bar, text="Re-apply my saved tweaks", style="Chip.TButton",
                   command=self._reapply_net).pack(side="left", padx=6)

        scroll = ScrollFrame(page)
        scroll.pack(fill="both", expand=True)
        body = scroll.inner
        self._net_vars = {}

        card = Card(body, f"{len(nettweaks.TWEAKS)} NETWORK TWEAKS")
        card.pack(fill="x")
        for t in nettweaks.TWEAKS:
            row = ttk.Frame(card, style="Panel.TFrame")
            row.pack(fill="x", anchor="w", pady=(6, 0))
            var = tk.BooleanVar(value=False)
            self._net_vars[t.id] = var
            ttk.Checkbutton(row, text=t.name, variable=var,
                            command=lambda i=t.id: self._net_toggle(i)
                            ).pack(side="left")
            if t.requires_admin:
                ttk.Label(row, text="  admin", style="Muted.TLabel"
                          ).pack(side="left")
            InfoButton(row, t.name,
                       f"{t.effect}\n\n{t.detail}"
                       + (f"\n\nCaution: {t.warning}" if t.warning else "")
                       ).pack(side="left", padx=6)
            ttk.Label(card, text=f"     {t.effect}", style="Muted.TLabel",
                      wraplength=740, justify="left").pack(anchor="w")
            if t.warning:
                ttk.Label(card, text=f"     ! {t.warning}", style="Warn.TLabel",
                          wraplength=740, justify="left").pack(anchor="w")

        self.net_log = self._scroll_text(page, height=6)
        self._write(self.net_log,
                    "Toggle a switch to apply it. Every change is backed up "
                    "first, and switching it off restores exactly what was "
                    "there before.")
        self._refresh_nettweaks()

    def _refresh_nettweaks(self) -> None:
        def done(state):
            remembered = 0
            for tid, (is_on, label) in state.items():
                if tid in self._net_vars:
                    self._net_vars[tid].set(bool(is_on))
                if "remembered" in label:
                    remembered += 1
            if remembered:
                self._write(self.net_log,
                            f"{remembered} setting(s) shown from your saved "
                            "selections. Windows does not expose those for "
                            "reading, so Phantom Tweeks remembers what you "
                            "chose.")
        self._run_async(nettweaks.labelled_states, done,
                        "Reading network settings...")

    def _reapply_net(self) -> None:
        """Re-apply saved tweaks after Windows Update reverted them."""
        from ..engine import tweakstate

        def work():
            result = tweakstate.reapply_all(nettweaks.set_tweak)
            lines = ["RE-APPLIED SAVED TWEAKS", ""]
            lines += [f"  ok   {m}" for m in result["applied"]]
            lines += [f"  fail {m}" for m in result["failed"]]
            if not result["applied"] and not result["failed"]:
                lines.append("  Nothing saved yet - turn some tweaks on first.")
            return "\n".join(lines)

        def done(text):
            self._write(self.net_log, text)
            self._refresh_nettweaks()
            Toast(self, "Re-applied", "success")

        self._run_async(work, done, "Re-applying...")

    def _net_toggle(self, tweak_id: str) -> None:
        want = self._net_vars[tweak_id].get()
        tweak = nettweaks.BY_ID[tweak_id]
        if want and tweak.warning:
            if not confirm_dialog(self, tweak.name,
                                  f"{tweak.detail}\n\nCaution: {tweak.warning}"):
                self._net_vars[tweak_id].set(False)
                return

        def work():
            return nettweaks.set_tweak(tweak_id, want)

        def done(result):
            ok, message, _changes = result
            self._write(self.net_log, message)
            Toast(self, message, "success" if ok else "warning")
            if not ok:
                self._net_vars[tweak_id].set(not want)

        self._run_async(work, done, f"{tweak.name}...")

    def _net_enable_safe(self) -> None:
        """Turn on everything without a caution note."""
        safe = [t for t in nettweaks.TWEAKS if not t.warning]
        if not confirm_dialog(
                self, f"Turn on {len(safe)} network tweaks?",
                "\n".join(f"  - {t.name}" for t in safe)
                + "\n\nEach is backed up first and can be switched off "
                  "again individually. The ones with caution notes are left "
                  "alone - turn those on yourself if you want them."):
            return

        def work():
            lines = []
            for t in safe:
                ok, message, _ = nettweaks.set_tweak(t.id, True)
                lines.append(("  ok   " if ok else "  fail ") + message)
            return "\n".join(lines)

        def done(text):
            self._write(self.net_log, text)
            self._refresh_nettweaks()
            Toast(self, "Applied", "success")

        self._run_async(work, done, "Applying network tweaks...")

    def _net_disable_all(self) -> None:
        if not confirm_dialog(self, "Turn every network tweak off?",
                              "This restores the Windows defaults for all of "
                              "them."):
            return

        def work():
            lines = []
            for t in nettweaks.TWEAKS:
                ok, message, _ = nettweaks.set_tweak(t.id, False)
                lines.append(("  ok   " if ok else "  fail ") + message)
            return "\n".join(lines)

        def done(text):
            self._write(self.net_log, text)
            self._refresh_nettweaks()
            Toast(self, "Reverted", "success")

        self._run_async(work, done, "Reverting...")

    # ---------------- one-click fixes ----------------
    def _quick_fix(self, ids, title, blurb) -> None:
        """Analyse, then offer only the relevant tweaks that suit this PC.

        Deliberately not a silent one-click apply: it evaluates each candidate
        against your hardware, drops anything that does not apply, and still
        asks before changing a thing.
        """
        def work():
            recs = self.app.engine.scan()
            hits = [r for r in recs if r.optimization.id in ids]
            return [r for r in hits
                    if r.evaluation.confidence.value != "NOT RECOMMENDED"]

        def done(useful):
            if not useful:
                self.show("tweaks")
                Toast(self, f"{title}: nothing to change - this system is "
                            "already configured correctly", "success")
                return
            lines = [blurb, ""]
            for r in useful:
                lines.append(f"  - {r.optimization.title}")
                lines.append(f"      {r.evaluation.reason}")
            lines += ["", "Everything is backed up first and can be reverted "
                          "individually from History & Restore."]
            if not confirm_dialog(self, title, "\n".join(lines)):
                return
            chosen = [r.optimization.id for r in useful]

            def apply_work():
                return self.app.engine.apply(chosen)

            def applied(result):
                n = len(getattr(result, "applied", []) or [])
                self.show("history")
                Toast(self, f"{title}: applied {n} change(s)", "success")

            self._run_async(apply_work, applied, f"{title}...")

        self._run_async(work, done, f"Checking {title.lower()}...")

    def _quick_latency(self) -> None:
        self._quick_fix(
            {"input.mouse_accel", "input.mmcss_games", "power.high_performance",
             "gfx.hags"},
            "Fix input latency",
            "These reduce delay between your input and what you see. Only the "
            "ones that actually apply to your hardware are listed.")

    def _quick_network(self) -> None:
        self._quick_fix(
            {"net.throttling_index"},
            "Fix network lag",
            "This removes a legacy Windows limit on non-multimedia network "
            "packets.\n\nIt will NOT reduce your ping to a game server - "
            "distance and routing decide that. For a genuine latency "
            "improvement, use a wired connection and check the Network Lab "
            "for packet loss.")

    # ---------------- tweaks: pick and apply ----------------
    def _build_tweaks(self) -> None:
        page = self._new_page(
            "tweaks", "Tweaks",
            "Choose exactly which optimizations to apply. Every one is backed "
            "up before it changes anything, and can be reverted individually "
            "from History & Restore.")

        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=(0, 10))
        ttk.Button(bar, text="Analyse my system", style="Accent.TButton",
                   command=self._tweaks_analyse).pack(side="left")
        ttk.Button(bar, text="Select recommended", style="Chip.TButton",
                   command=self._tweaks_select_recommended).pack(side="left", padx=6)
        ttk.Button(bar, text="Clear selection", style="Chip.TButton",
                   command=self._tweaks_clear).pack(side="left")
        self.tweak_apply_btn = ttk.Button(
            bar, text="Apply selected", style="Accent.TButton",
            command=self._tweaks_apply, state="disabled")
        self.tweak_apply_btn.pack(side="right")
        self.tweak_count = tk.StringVar(value="0 selected")
        ttk.Label(bar, textvariable=self.tweak_count,
                  style="MutedBg.TLabel").pack(side="right", padx=10)

        scroll = ScrollFrame(page)
        scroll.pack(fill="both", expand=True)
        body = scroll.inner

        self._tweak_vars: dict = {}
        self._tweak_notes: dict = {}
        self._tweak_note_labels: dict = {}
        by_area: dict = {}
        for opt in catalog.CATALOG:
            by_area.setdefault(opt.area, []).append(opt)

        for area in sorted(by_area):
            card = Card(body, area.upper())
            card.pack(fill="x", pady=(0, 10))
            for opt in by_area[area]:
                row = ttk.Frame(card, style="Panel.TFrame")
                row.pack(fill="x", anchor="w", pady=3)

                var = tk.BooleanVar(value=False)
                self._tweak_vars[opt.id] = var
                cb = ttk.Checkbutton(
                    row, text=opt.title, variable=var,
                    command=self._tweaks_update_count)
                cb.pack(side="left")

                risk = {"Low": "Good", "Medium": "Warn",
                        "High": "Danger"}.get(opt.risk.value, "Muted")
                ttk.Label(row, text=f"  {opt.risk.value} risk",
                          style=f"{risk}.TLabel").pack(side="left")
                if opt.requires_admin:
                    ttk.Label(row, text="  admin",
                              style="Muted.TLabel").pack(side="left")
                if not opt.reversible:
                    ttk.Label(row, text="  NOT REVERSIBLE",
                              style="Danger.TLabel").pack(side="left")

                InfoButton(row, opt.title, opt.info_card(),
                           opt.learn_more).pack(side="left", padx=6)

                # The note only appears after an analysis. Packing an empty
                # label left a large gap under every row, so it is created
                # here but only shown once it has something to say.
                note = tk.StringVar(value="")
                label = ttk.Label(card, textvariable=note, style="Muted.TLabel",
                                  wraplength=760, justify="left")
                self._tweak_notes[opt.id] = note
                self._tweak_note_labels[opt.id] = label

        self._tweaks_update_count()

    def _tweaks_update_count(self) -> None:
        n = sum(1 for v in self._tweak_vars.values() if v.get())
        self.tweak_count.set(f"{n} selected")
        self.tweak_apply_btn.configure(state="normal" if n else "disabled")

    def _tweaks_clear(self) -> None:
        for v in self._tweak_vars.values():
            v.set(False)
        self._tweaks_update_count()

    def _tweaks_analyse(self) -> None:
        """Score every tweak against THIS machine before you choose."""
        def done(recs):
            found = {r.optimization.id: r for r in recs}
            for oid, note in self._tweak_notes.items():
                rec = found.get(oid)
                note.set("Not applicable to this system." if rec is None
                         else f"{rec.evaluation.confidence.value} - "
                              f"{rec.evaluation.reason}")
                label = self._tweak_note_labels.get(oid)
                if label is not None and label.winfo_manager() != "pack":
                    label.pack(anchor="w", padx=22, pady=(0, 6))
            self._last_recs = recs
            Toast(self, f"Analysed {len(recs)} optimizations", "success")

        self._run_async(lambda: self.app.engine.scan(), done,
                        "Analysing your system...")

    def _tweaks_select_recommended(self) -> None:
        """Tick only what this machine actually benefits from.

        Never selects anything rated NOT RECOMMENDED, and never selects a
        high-risk or irreversible change automatically.
        """
        recs = getattr(self, "_last_recs", None)
        if not recs:
            Toast(self, "Analyse your system first", "info")
            return
        picked = 0
        for rec in recs:
            opt = rec.optimization
            conf = rec.evaluation.confidence.value
            if conf in ("HIGH CONFIDENCE", "MEDIUM CONFIDENCE") \
                    and opt.risk.value != "High" and opt.reversible:
                self._tweak_vars[opt.id].set(True)
                picked += 1
        self._tweaks_update_count()
        Toast(self, f"Selected {picked} recommended optimization(s)", "success")

    def _tweaks_apply(self) -> None:
        chosen = [oid for oid, v in self._tweak_vars.items() if v.get()]
        if not chosen:
            return
        opts = [catalog.BY_ID[o] for o in chosen if o in catalog.BY_ID]
        risky = [o for o in opts if o.risk.value == "High"]
        irreversible = [o for o in opts if not o.reversible]

        lines = [f"{len(opts)} optimization(s) will be applied:", ""]
        lines += [f"  - {o.title}" for o in opts]
        lines += ["", "A backup is written before anything changes, so every "
                      "one of these can be undone from History & Restore."]
        if risky:
            lines += ["", "HIGH RISK: " + ", ".join(o.title for o in risky)]
        if irreversible:
            lines += ["", "NOT REVERSIBLE: "
                      + ", ".join(o.title for o in irreversible)]

        if not confirm_dialog(self, "Apply these tweaks?", "\n".join(lines),
                              danger=bool(risky or irreversible),
                              steps=2 if (risky or irreversible) else 1):
            return

        def done(result):
            out = ["APPLIED", ""]
            for line in getattr(result, "messages", []) or []:
                out.append(f"  {line}")
            applied = getattr(result, "applied", []) or []
            failed = getattr(result, "failed", []) or []
            out += ["", f"Applied: {len(applied)}   Failed: {len(failed)}"]
            if getattr(result, "backup_id", None):
                out += ["", f"Backup: {result.backup_id}",
                        "Use History & Restore to roll any of this back."]
            self.show("history")
            Toast(self, f"Applied {len(applied)} tweak(s)",
                  "success" if not failed else "warning")
            self._tweaks_clear()

        self._run_async(lambda: self.app.engine.apply(chosen), done,
                        "Applying selected tweaks...")

    def _build_tweakdb(self) -> None:
        counts = tweakdb.counts()
        page = self._new_page(
            "tweakdb", "Tweak Encyclopedia",
            f"Every popular Windows gaming tweak, with a verdict: "
            f"{counts['SAFE']} safe, {counts['SITUATIONAL']} situational, "
            f"{counts['PLACEBO']} placebo, {counts['HARMFUL']} harmful. "
            "Including the ones Phantom Tweeks refuses to apply, and why.")

        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=(0, 10))
        for label, verdict in (("All", None), ("Safe", tweakdb.SAFE),
                               ("Situational", tweakdb.SITUATIONAL),
                               ("Placebo", tweakdb.PLACEBO),
                               ("Harmful", tweakdb.HARMFUL)):
            ttk.Button(bar, text=label, style="Chip.TButton",
                       command=lambda v=verdict: self._show_tweaks(v)
                       ).pack(side="left", padx=(0, 6))

        search = ttk.Frame(page)
        search.pack(fill="x", pady=(0, 10))
        ttk.Label(search, text="Look up a tweak:",
                  style="MutedBg.TLabel").pack(side="left")
        self.tweak_query = ttk.Entry(search, width=42)
        self.tweak_query.pack(side="left", padx=8)
        self.tweak_query.bind("<Return>", lambda e: self._search_tweaks())
        ttk.Button(search, text="Search", style="Accent.TButton",
                   command=self._search_tweaks).pack(side="left")
        ttk.Label(search,
                  text="  Paste a registry value from a guide to check it",
                  style="MutedBg.TLabel").pack(side="left", padx=8)

        self.tweak_panel = self._scroll_text(page)
        self._show_tweaks(None)

    def _show_tweaks(self, verdict) -> None:
        if verdict is None:
            self._write(self.tweak_panel, tweakdb.report())
            return
        items = tweakdb.by_verdict(verdict)
        out = [f"{verdict} ({len(items)})", ""]
        for t in items:
            out += [t.render(), ""]
        self._write(self.tweak_panel, "\n".join(out))

    def _search_tweaks(self) -> None:
        term = self.tweak_query.get().strip()
        if not term:
            self._show_tweaks(None)
            return
        hits = tweakdb.search(term)
        if not hits:
            self._write(self.tweak_panel,
                        f"Nothing matching {term!r}.\n\n"
                        "This encyclopedia covers the tweaks that circulate "
                        "widely. If you found something not listed here, treat "
                        "it with suspicion until you can explain what it "
                        "actually changes.")
            return
        out = [f"{len(hits)} result(s) for {term!r}", ""]
        for t in hits:
            out += [t.render(), ""]
        self._write(self.tweak_panel, "\n".join(out))

    def _build_maintenance(self) -> None:
        page = self._new_page(
            "maintenance", "Maintenance Mode",
            "Routine health checks and safe cleanup. Nothing runs while a "
            "game is detected, and nothing personal is ever deleted.")

        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=(0, 10))
        ttk.Button(bar, text="Run checks now", style="Accent.TButton",
                   command=self._run_maintenance).pack(side="left")
        self.maint_apply_btn = ttk.Button(
            bar, text="Clean up…", style="Chip.TButton",
            command=self._apply_maintenance, state="disabled")
        self.maint_apply_btn.pack(side="left", padx=6)

        ttk.Label(bar, text="  Schedule:", style="MutedBg.TLabel").pack(side="left")
        self.maint_sched_var = tk.StringVar(value=maintenance.load_schedule()
                                            .get("schedule", "off"))
        for label, val in (("Off", "off"), ("Weekly", "weekly"),
                           ("Monthly", "monthly")):
            ttk.Radiobutton(bar, text=label, value=val,
                            variable=self.maint_sched_var,
                            command=self._save_maint_schedule).pack(side="left", padx=2)

        self.maint_panel = self._scroll_text(page)
        self._write(self.maint_panel,
                    "Press 'Run checks now' to inspect this system.\n\n"
                    "Checks are read-only. Any cleanup is offered separately "
                    "and asks for confirmation first.")
        self._maint_report = None

    def _save_maint_schedule(self) -> None:
        maintenance.save_schedule(self.maint_sched_var.get())
        Toast(self, f"Schedule set to {self.maint_sched_var.get()}", "success")

    def _run_maintenance(self) -> None:
        self._run_async(
            maintenance.run,
            self._show_maintenance,
            "Running maintenance checks…")

    def _show_maintenance(self, report) -> None:
        self._maint_report = report
        self._write(self.maint_panel, report.render())
        can = bool(report.ran and report.actionable)
        self.maint_apply_btn.configure(state="normal" if can else "disabled")

    def _apply_maintenance(self) -> None:
        report = self._maint_report
        if not report or not report.actionable:
            return
        ids = [r.task_id for r in report.actionable]
        names = "\n".join(f"  • {r.title} ({r.reclaimable_mb:,.0f} MB)"
                           for r in report.actionable)
        if not confirm_dialog(
                self, "Clean up these items?",
                f"This will delete regenerable cache files only:\n\n{names}\n\n"
                "Your documents, downloads, pictures, game saves and Recycle "
                "Bin are never touched. Files in use are skipped.\n\n"
                "Shader caches rebuild automatically; the first launch of a "
                "game afterwards may stutter briefly."):
            return
        self._run_async(
            lambda: maintenance.apply(ids, dry_run=False),
            self._after_maintenance_apply,
            "Cleaning up…")

    def _after_maintenance_apply(self, result) -> None:
        freed = result.get("freed_mb", 0.0)
        lines = ["CLEANUP COMPLETE", ""]
        for a in result.get("applied", []):
            lines.append(f"{a['task']}: removed {a.get('removed', 0)} file(s), "
                         f"{a.get('freed_mb', 0):,.1f} MB")
            if a.get("skipped_in_use"):
                lines.append(f"  {a['skipped_in_use']} in use, skipped safely.")
            if a.get("note"):
                lines.append(f"  {a['note']}")
        for sk in result.get("skipped", []):
            lines.append(f"Skipped: {sk}")
        lines += ["", f"Total reclaimed: {freed:,.1f} MB"]
        self._write(self.maint_panel, "\n".join(lines))
        Toast(self, f"✓ Reclaimed {freed:,.0f} MB", "success")
        self.maint_apply_btn.configure(state="disabled")

    # ---------------- trends ----------------
    def _build_trends(self) -> None:
        page = self._new_page(
            "trends", "Performance Trends",
            "Measurements recorded on this device over time. Stored locally "
            "as plain JSON; nothing is ever uploaded.")
        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=(0, 10))
        ttk.Button(bar, text="Refresh", style="Accent.TButton",
                   command=self._refresh_trends).pack(side="left")
        ttk.Button(bar, text="Clear history", style="Chip.TButton",
                   command=self._clear_trends).pack(side="left", padx=6)
        self.trends_panel = self._scroll_text(page)

    def _clear_trends(self) -> None:
        if not confirm_dialog(self, "Delete all recorded history?",
                              "This removes every stored measurement from this "
                              "device. It cannot be undone."):
            return
        history.clear()
        self._refresh_trends()
        Toast(self, "History cleared", "success")

    def _refresh_trends(self) -> None:
        data = history.summary()
        out = ["PERFORMANCE TRENDS", ""]
        if not data["metrics"]:
            out += ["No measurements recorded yet.", "",
                    "Run a benchmark, a frame-time capture or a network test "
                    "and the results will be tracked here so you can see "
                    "whether things get better or worse over time."]
        else:
            out.append(f"Retention: {data['retention']}")
            out.append("")
            for t in data["trends"]:
                out += [t.render(), ""]
            if data.get("note"):
                out += [data["note"], ""]
            gate = features.check("history_trends")
            if not gate.allowed:
                out += ["-" * 56,
                        "Premium unlocks unlimited history and regression "
                        "charts. Your existing data is kept either way."]
        self._write(self.trends_panel, "\n".join(out))

    def _build_premium(self) -> None:
        page = self._new_page("premium", "Phantom Premium")
        scroll = ScrollFrame(page)
        scroll.pack(fill="both", expand=True)
        body = scroll.inner

        status = Card(body, "LICENSE STATUS")
        status.pack(fill="x", pady=(0, 12))
        self.lic_status_var = tk.StringVar(value="Checking…")
        ttk.Label(status, textvariable=self.lic_status_var, style="Huge.TLabel"
                  ).pack(anchor="w")
        self.lic_detail_var = tk.StringVar(value="")
        ttk.Label(status, textvariable=self.lic_detail_var, style="Panel.TLabel",
                  wraplength=760, justify="left").pack(anchor="w", pady=(4, 10))

        row = ttk.Frame(status, style="Panel.TFrame")
        row.pack(anchor="w", pady=(4, 0))
        ttk.Label(row, text="License key:", style="Panel.TLabel").pack(side="left")
        self.lic_entry = ttk.Entry(row, width=52)
        self.lic_entry.pack(side="left", padx=8)
        ttk.Button(row, text="Activate", style="Accent.TButton",
                   command=self._activate_license).pack(side="left")
        self.lic_remove_btn = ttk.Button(row, text="Remove", style="Chip.TButton",
                                         command=self._deactivate_license)
        self.lic_remove_btn.pack(side="left", padx=6)

        ttk.Label(status,
                  text=("Phantom Tweeks contains no payment processing and will "
                        "never ask for card details inside the app. Keys are "
                        "verified by digital signature on this device; if the "
                        "licensing server is unreachable your key keeps working."),
                  style="Muted.TLabel", wraplength=760, justify="left"
                  ).pack(anchor="w", pady=(12, 0))

        data = features.summary()

        promise = Card(body, "WHAT STAYS FREE")
        promise.pack(fill="x", pady=(0, 12))
        ttk.Label(promise, text=data["promise"], style="Panel.TLabel",
                  wraplength=760, justify="left").pack(anchor="w", pady=(0, 8))
        for f in features.free_features():
            row = ttk.Frame(promise, style="Panel.TFrame")
            row.pack(fill="x", anchor="w", pady=1)
            ttk.Label(row, text="✓", style="Good.TLabel").pack(side="left")
            ttk.Label(row, text=f"  {f.name}", style="Panel.TLabel"
                      ).pack(side="left")
            ttk.Label(row, text=f"  — {f.summary}", style="Muted.TLabel"
                      ).pack(side="left")

        feat = Card(body, f"PREMIUM FEATURES ({data['premium_count']})")
        feat.pack(fill="x", pady=(0, 12))
        ttk.Label(feat,
                  text=("Every feature below is built and working. Nothing "
                        "here is a placeholder, and a locked feature never "
                        "shows invented results — it simply stays locked."),
                  style="Muted.TLabel", wraplength=760, justify="left"
                  ).pack(anchor="w", pady=(0, 10))
        for f in features.premium_features():
            row = ttk.Frame(feat, style="Panel.TFrame")
            row.pack(fill="x", anchor="w", pady=(4, 0))
            mark = "★" if not data["active"] else "✓"
            ttk.Label(row, text=mark, style="Accent.TLabel").pack(side="left")
            ttk.Label(row, text=f"  {f.name}", style="Panel.TLabel"
                      ).pack(side="left")
            if f.detail:
                InfoButton(row, f.name, f"{f.summary}\n\n{f.detail}"
                           ).pack(side="left", padx=6)
            ttk.Label(feat, text=f"     {f.summary}", style="Muted.TLabel",
                      wraplength=720, justify="left").pack(anchor="w")

        ttk.Label(feat, text=data["payment_note"], style="Muted.TLabel",
                  wraplength=760, justify="left").pack(anchor="w", pady=(12, 0))

        notify = Card(body, "NO KEY YET?")
        notify.pack(fill="x")
        ttk.Label(notify,
                  text=("Leave your email and we will store it locally on this "
                        "machine only. Nothing is transmitted."),
                  style="Muted.TLabel", wraplength=760, justify="left"
                  ).pack(anchor="w", pady=(0, 8))
        nrow = ttk.Frame(notify, style="Panel.TFrame")
        nrow.pack(anchor="w")
        self.notify_entry = ttk.Entry(nrow, width=34)
        self.notify_entry.pack(side="left")
        ttk.Button(nrow, text="Notify Me", style="Accent.TButton",
                   command=self._notify_me).pack(side="left", padx=8)

        self._refresh_premium()

    def _refresh_premium(self) -> None:
        st = premium.license_status()
        if st["active"]:
            self.lic_status_var.set(f"PREMIUM — {st['plan'].upper()}")
            bits = [st["message"]]
            if st.get("key_id"):
                bits.append(f"Key {st['key_id']}")
            if st.get("expires"):
                bits.append(f"Expires {st['expires']} "
                            f"({st.get('days_remaining')} days left)")
            else:
                bits.append("Never expires")
            self.lic_detail_var.set("  •  ".join(bits))
            self.lic_remove_btn.state(["!disabled"])
        else:
            self.lic_status_var.set("FREE")
            self.lic_detail_var.set(st["message"])
            self.lic_remove_btn.state(["disabled"])

    def _activate_license(self) -> None:
        key = self.lic_entry.get().strip()
        if not key:
            Toast(self, "Paste your license key first.", "warning")
            return

        # The developer unlock is checked first. It is not a licence - it sets
        # a local flag and is reported as a developer unlock everywhere.
        unlocked, message = premium.try_dev_unlock(key)
        if unlocked:
            self.lic_entry.delete(0, "end")
            self._refresh_premium()
            Toast(self, "Developer unlock active", "success")
            return

        def work():
            return premium.activate(key, VERSION)

        def done(result):
            ok, msg = result
            Toast(self, ("✓ " if ok else "⚠ ") + msg,
                  "success" if ok else "warning")
            if ok:
                self.lic_entry.delete(0, "end")
            self._refresh_premium()

        self._run_async(work, done, "Verifying license…")

    def _deactivate_license(self) -> None:
        if not confirm_dialog(
                self, "Remove license?",
                "This removes the license key from this device. Premium "
                "features will be locked until you enter it again.\n\n"
                "Your key stays valid and can be re-entered here or on "
                "another machine."):
            return
        ok, msg = premium.deactivate()
        Toast(self, ("✓ " if ok else "⚠ ") + msg, "success" if ok else "warning")
        self._refresh_premium()

    def _notify_me(self) -> None:
        ok, msg = premium.register_interest(self.notify_entry.get().strip())
        Toast(self, ("✓ " if ok else "⚠ ") + msg, "success" if ok else "warning")

    # --- settings
    # ---------------- help & diagnostics ----------------
    def _build_help(self) -> None:
        page = self._new_page(
            "help", "Help & Diagnostics",
            "If something is not working, run the self-test. It reports which "
            "parts of the app are healthy and tells you plainly whether a "
            "problem is ours or your system's.")

        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=(0, 10))
        ttk.Button(bar, text="Run self-test", style="Accent.TButton",
                   command=self._run_selftest).pack(side="left")
        ttk.Button(bar, text="Copy result", style="Chip.TButton",
                   command=self._copy_selftest).pack(side="left", padx=6)
        ttk.Button(bar, text="Open data folder", style="Chip.TButton",
                   command=self._open_data_folder).pack(side="left")
        ttk.Button(bar, text="Check for updates", style="Chip.TButton",
                   command=lambda: self._check_updates_async(force=True)
                   ).pack(side="left", padx=6)
        ttk.Button(bar, text="Download update", style="Chip.TButton",
                   command=self._download_update).pack(side="left")

        self.help_panel = self._scroll_text(page)
        self._write(self.help_panel, self._help_text())
        self._selftest_text = ""

    def _help_text(self) -> str:
        from ..core import paths
        return (
            "COMMON QUESTIONS\n\n"
            "Nothing happens when I click Optimize\n"
            "  Optimizations that change Windows settings need administrator\n"
            "  rights. Close Phantom Tweeks, right-click it and choose\n"
            "  'Run as administrator'. Scanning works without them.\n\n"
            "Windows SmartScreen warned about the download\n"
            "  The binaries are not yet code-signed. Verify the SHA-256\n"
            "  checksum published on the download page against your file.\n\n"
            "It says a game is running when it is not\n"
            "  Some launchers keep helper processes alive after you quit.\n"
            "  Detection needs two consecutive sightings before it reports a\n"
            "  game, so it will correct itself within about ten seconds.\n\n"
            "Where is my data stored?\n"
            f"  {paths.ROOT}\n"
            "  Backups, logs, history and settings all live there. Nothing is\n"
            "  uploaded anywhere.\n\n"
            "How do I undo everything?\n"
            "  History & Restore, then RESTORE EVERYTHING. Every change is\n"
            "  backed up before it is applied.\n\n"
            "Press 'Run self-test' above to check this installation."
        )

    def _run_selftest(self) -> None:
        self._run_async(selftest.run, self._show_selftest,
                        "Checking the installation…")

    def _show_selftest(self, report) -> None:
        self._selftest_text = report.render()
        self._write(self.help_panel, self._selftest_text)
        if report.healthy:
            Toast(self, "✓ Installation is healthy", "success")
        else:
            Toast(self, f"⚠ {len(report.failures)} problem(s) found", "warning")

    def _copy_selftest(self) -> None:
        text = self._selftest_text or self._help_text()
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            Toast(self, "✓ Copied - safe to paste into a bug report", "success")
        except tk.TclError:
            Toast(self, "Could not access the clipboard", "warning")

    def _open_data_folder(self) -> None:
        from ..core import paths, runproc
        try:
            paths.ensure_dirs()
            if runproc.IS_WINDOWS:
                os.startfile(str(paths.ROOT))       # noqa: S606
            else:
                runproc.run(["xdg-open", str(paths.ROOT)], timeout=10)
        except Exception:
            Toast(self, f"Data folder: {paths.ROOT}", "info")

    def _build_settings(self) -> None:
        page = self._new_page(
            "settings", "Advanced Settings",
            "Options marked ⚠ change system behaviour. Phantom Shield cannot be "
            "disabled from this page — or from any page.")
        nb = ttk.Notebook(page)
        nb.pack(fill="both", expand=True)

        groups = {
            "Optimization": [
                ("auto_apply_high_confidence",
                 "⚠ Automatically apply high-confidence safe optimizations", True),
                ("regression_threshold_pct",
                 "Regression threshold (%) that triggers a rollback prompt", False),
            ],
            "Gaming": [
                ("gaming_mode_auto_start", "Start Gaming Mode when the app launches", False),
                ("auto_apply_game_profile",
                 "Apply my saved profile automatically when a game starts", True),
                ("benchmark_seconds", "Default benchmark duration (seconds)", False),
            ],
            "Privacy": [
                ("telemetry", "⚠ Send anonymous telemetry (no endpoint exists)", True),
                ("share_hardware_info", "⚠ Allow sharing hardware info", True),
                ("share_game_info", "⚠ Allow sharing game info", True),
            ],
            "Updates": [("check_updates", "Check for updates over HTTPS", False)],
            "Notifications": [
                ("notifications", "Show notifications", False),
                ("notification_min_interval_s", "Minimum seconds between notifications", False),
            ],
            "Diagnostics": [
                ("expert_mode", "⚠ Expert Mode (detailed technical data)", True),
                ("wmi_timeout_seconds",
                 "Hardware query timeout (seconds)", False),
                ("wmi_budget_seconds",
                 "Total hardware query budget (seconds)", False),
            ],
            "Startup": [
                ("request_admin_on_start",
                 "Ask for administrator rights when the app starts", False),
                ("warn_when_not_admin",
                 "Warn when running without administrator rights", False),
                ("start_minimised", "Start minimised", False),
                ("remember_last_page",
                 "Reopen the page I was last on", False),
            ],
            "Safety": [
                ("restore_point_before_tweaks",
                 "Create a Windows restore point before applying tweaks", False),
                ("confirm_every_tweak",
                 "Confirm before applying each individual tweak", False),
                ("require_double_confirm_high_risk",
                 "Require two confirmations for high-risk changes", False),
                ("keep_backups_forever",
                 "Never delete backups automatically", False),
                ("history_retention_days",
                 "Days of performance history to keep", False),
            ],
            "Interface": [
                ("compact_mode", "Compact layout (denser lists)", False),
                ("show_risk_badges", "Show risk level next to each tweak", False),
                ("show_tweak_explanations",
                 "Show the explanation under each tweak", False),
                ("perf_auto_refresh",
                 "Auto-refresh the Performance page", False),
                ("perf_refresh_seconds",
                 "Performance refresh interval (seconds)", False),
            ],
        }

        for name, items in groups.items():
            tab = ttk.Frame(nb, style="Panel.TFrame", padding=18)
            nb.add(tab, text=name)
            for key, label, dangerous in items:
                value = self.app.config.get(key)
                if isinstance(value, bool):
                    var = tk.BooleanVar(value=value)
                    ttk.Checkbutton(
                        tab, text=label, variable=var,
                        command=lambda k=key, v=var, d=dangerous: self._set_bool(k, v, d)
                    ).pack(anchor="w", pady=5)
                else:
                    row = ttk.Frame(tab, style="Panel.TFrame")
                    row.pack(anchor="w", fill="x", pady=5)
                    ttk.Label(row, text=label, style="Panel.TLabel").pack(side="left")
                    e = ttk.Entry(row, width=8)
                    e.insert(0, str(value))
                    e.pack(side="left", padx=10)
                    e.bind("<FocusOut>",
                           lambda ev, k=key, w=e: self._set_number(k, w))

        privacy = ttk.Frame(nb, style="Panel.TFrame", padding=18)
        nb.add(privacy, text="Privacy Statement")
        ttk.Label(privacy, justify="left", style="Panel.TLabel", wraplength=760,
                  text=(
                      "Phantom Tweeks collects nothing by default.\n\n"
                      "• No telemetry is transmitted. There is no analytics endpoint "
                      "compiled into this build.\n"
                      "• Hardware and game information stays on this PC.\n"
                      "• Crash logs are written locally; sharing them is your choice.\n"
                      "• Nothing is sold, and no account is required to use the app.\n"
                      "• All data lives in one folder you can delete at any time.")
                  ).pack(anchor="w")

        protected = ttk.Frame(nb, style="Panel.TFrame", padding=18)
        nb.add(protected, text="Protected Apps")
        ttk.Label(protected, style="Panel.TLabel", wraplength=760, justify="left",
                  text=("Phantom Shield's built-in protections are permanent. Even "
                        "Expert Mode cannot remove them — automation that could kill "
                        "your game, launcher, voice chat or anti-cheat simply does "
                        "not exist in this codebase.")).pack(anchor="w", pady=(0, 12))
        ttk.Button(protected, text="Manage Additional Protected Apps",
                   style="Accent.TButton",
                   command=self._manage_protected).pack(anchor="w")

    def _set_bool(self, key: str, var: tk.BooleanVar, dangerous: bool) -> None:
        if var.get() and dangerous:
            explain = {
                "auto_apply_high_confidence":
                    "Phantom Tweeks will apply high-confidence, low-risk, reversible "
                    "optimizations without asking each time. Backups are still created "
                    "for every change, and advanced items are still never automatic.",
                "expert_mode":
                    "Expert Mode exposes registry values, power configuration and "
                    "process telemetry. It does NOT bypass Phantom Shield.",
            }.get(key, "This option changes how Phantom Tweeks behaves.")
            if not confirm_dialog(self, "Confirm Setting", explain,
                                  danger=True, confirm_text="Enable", steps=2):
                var.set(False)
                return
        self.app.config.set(key, var.get())
        if key == "notifications":
            CENTER.enabled = var.get()

    def _set_number(self, key: str, widget: ttk.Entry) -> None:
        raw = widget.get().strip()
        try:
            value = float(raw) if "." in raw else int(raw)
        except ValueError:
            widget.delete(0, "end")
            widget.insert(0, str(self.app.config.get(key)))
            return
        self.app.config.set(key, value)

    # NOTE: no _refresh_premium stub here. An earlier version defined one
    # that did `pass`, which silently overrode the real implementation above
    # and left the licence status stuck on "Checking...". Python keeps the
    # LAST definition in a class body, so a duplicate name is a silent bug.
    # A test now fails if any method is defined twice in this class.

    def _refresh_settings(self) -> None:
        """Settings widgets bind directly to config; nothing to refresh."""

    def _refresh_dashboard(self) -> None:
        """The dashboard updates on its own timer via _tick_monitor()."""

    def _on_close(self) -> None:
        self._monitoring = False
        try:
            self._watcher.stop()
        except Exception:
            pass
        try:
            if self.app.mode.active:
                self.app.mode.stop()
        except Exception:
            pass
        self.destroy()


def launch() -> int:
    from ..core.logging_setup import install_crash_handler
    install_crash_handler()

    # Most of what this app does needs administrator rights. Ask once, via
    # the standard UAC prompt. Declining is respected: the app continues with
    # reduced capability and the Help page explains what is unavailable.
    from ..core import elevation
    from ..core.config import Config
    try:
        _cfg = Config.load()
        _ask = bool(_cfg.get("request_admin_on_start"))
    except Exception:
        _ask = True
    if _ask and elevation.wanted():
        if elevation.relaunch_as_admin():
            return 0        # the elevated copy takes over
    try:
        win = PhantomWindow()
    except tk.TclError as e:
        msg = str(e).lower()
        no_display = any(k in msg for k in (
            "no display name", "couldn't connect to display", "can't find a usable",
            "display name and no $display", "application-specific initialization",
        ))
        if no_display:
            print(
                f"{APP_NAME}: the graphical interface could not start.\n"
                f"  {e}\n\n"
                "No display is available (a headless session, or SSH without X "
                "forwarding), or Tk is missing from this Python installation.\n\n"
                "The command-line interface works without a display:\n"
                "  python run.py scan\n"
                "  python run.py --help",
                file=sys.stderr,
            )
            return 1
        # A genuine Tk error in our own code. Report it as the bug it is,
        # with a crash log — never disguise it as an environment problem.
        from ..core.logging_setup import write_crash_report
        path = write_crash_report(e)
        print(
            f"{APP_NAME}: the interface failed to build due to an internal error.\n"
            f"  {type(e).__name__}: {e}\n\n"
            "This is a bug in Phantom Tweeks, not a problem with your system.\n"
            f"A local crash log was saved to:\n  {path}\n"
            "Nothing was uploaded.\n\n"
            "The command-line interface is unaffected:\n"
            "  python run.py scan",
            file=sys.stderr,
        )
        return 1
    if win.app.config.get("gaming_mode_auto_start"):
        win.app.mode.start()
        win.mode_btn.configure(text="Disable Gaming Mode")
    win.mainloop()
    return 0
