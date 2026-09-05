"""Phantom Tweeks command-line interface.

Mutating commands require explicit confirmation (--yes) and, where relevant,
elevation. Read-only commands work everywhere.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from ..app import PhantomApp
from ..branding import APP_NAME, APP_SLUG, GOLDEN_RULE, VERSION
from ..core import premium
from ..core.platform_info import IS_WINDOWS, is_admin

RULE = "─" * 62


def _h(title: str) -> None:
    print(f"\n{RULE}\n  {title}\n{RULE}")


def _confirm(prompt: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        print("Refusing to proceed without confirmation. Re-run with --yes.")
        return False
    return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")


# ---------------- commands ----------------

def cmd_version(app: PhantomApp, args) -> int:
    info = app.about()
    print(f"{APP_NAME} {VERSION}")
    for k in ("os", "arch", "supported", "elevated", "analysis_only", "python"):
        print(f"  {k:<14}{info[k]}")
    if info["analysis_only"]:
        print("\n  Analysis-only mode: system changes are disabled off Windows.")
    return 0


def cmd_hardware(app: PhantomApp, args) -> int:
    from ..hardware.monitor import MONITOR
    _h("HARDWARE")
    cpu = MONITOR.cpu()
    print(f"CPU:         {cpu.model or 'Unknown'}")
    print(f"  Cores:     {cpu.physical_cores or '?'} physical / "
          f"{cpu.logical_cores or '?'} logical ({cpu.architecture})")
    print(f"  Clock:     {f'{cpu.current_mhz:.0f} MHz' if cpu.current_mhz else 'n/a'}"
          f"  (max {f'{cpu.max_mhz:.0f} MHz' if cpu.max_mhz else 'n/a'})")
    print(f"  Load:      {cpu.utilization:.0f}%" if cpu.utilization is not None else "  Load:      n/a")
    print(f"  Temp:      {f'{cpu.temperature_c} °C' if cpu.temperature_c else 'n/a (no readable sensor)'}")
    print(f"  Power:     {cpu.power_plan or 'n/a'}")

    for g in MONITOR.gpus():
        print(f"\nGPU:         {g.model} ({g.vendor})")
        print(f"  Driver:    {g.driver_version or 'n/a'}")
        print(f"  VRAM:      {f'{g.vram_used_mb:.0f}/{g.vram_total_mb:.0f} MB' if g.vram_total_mb and g.vram_used_mb else (f'{g.vram_total_mb:.0f} MB' if g.vram_total_mb else 'n/a')}")
        print(f"  Load:      {f'{g.utilization:.0f}%' if g.utilization is not None else 'n/a'}")
        print(f"  Temp:      {f'{g.temperature_c} °C' if g.temperature_c else 'n/a'}")
        print(f"  Clock:     {f'{g.clock_mhz:.0f} MHz' if g.clock_mhz else 'n/a'}")
        print(f"  Power:     {f'{g.power_w} W' if g.power_w else 'n/a'}")

    m = MONITOR.memory()
    print(f"\nMemory:      {m.total_gb} GB total, {m.used_gb} GB used ({m.percent}%)")
    if m.speed_mhz:
        print(f"  Speed:     {m.speed_mhz} MT/s across {m.modules} module(s)")

    print()
    for d in MONITOR.disks():
        print(f"Disk {d.mountpoint:<6} {d.media_type or 'Unknown':<10} "
              f"{d.free_gb:.0f} GB free of {d.total_gb:.0f} GB")
    return 0


def cmd_shield(app: PhantomApp, args) -> int:
    _h("PHANTOM SHIELD")
    print(app.render_shield())
    return 0


def cmd_power(app: PhantomApp, args) -> int:
    _h("PHANTOM POWER PLAN")
    if args.create:
        ok, msgs, _ = app.create_power_plan(activate=not args.no_activate)
        for m in msgs:
            print(" ", m)
        return 0 if ok else 1
    if args.remove:
        ok, msgs = app.delete_power_plan()
        for m in msgs:
            print(" ", m)
        return 0 if ok else 1
    st = app.power_status()
    if not st.get("available"):
        print(" ", st.get("reason"))
        print()
        print(app.power_describe())
        return 0
    print(f"  Installed : {'yes' if st['installed'] else 'no'}")
    print(f"  Active    : {'yes' if st['active'] else 'no'}")
    print(f"  Now using : {st['active_plan']}")
    print(f"  Machine   : {'laptop' if st['laptop'] else 'desktop'}")
    print()
    print(app.power_describe())
    return 0


def cmd_license(app: PhantomApp, args) -> int:
    _h("LICENSE")
    if args.activate:
        ok, msg = app.activate_license(args.activate)
        print(("  ✓ " if ok else "  ✗ ") + msg)
        return 0 if ok else 1
    if args.remove:
        ok, msg = app.deactivate_license()
        print(("  ✓ " if ok else "  ✗ ") + msg)
        return 0 if ok else 1
    st = app.license_status()
    print(f"  Plan    : {st['plan']}")
    print(f"  Active  : {'yes' if st['active'] else 'no'}")
    if st.get("key_id"):
        print(f"  Key ID  : {st['key_id']}")
    if st.get("expires"):
        print(f"  Expires : {st['expires']} ({st.get('days_remaining')} days)")
    print(f"  {st['message']}")
    return 0


def cmd_presets(app: PhantomApp, args) -> int:
    from ..engine import presets as _p

    if args.name:
        preset = _p.get(args.name)
        if preset is None:
            print(f"Unknown preset: {args.name}")
            print("Available: " + ", ".join(pr.id for pr in _p.PRESETS))
            return 2
        _h(f"PRESET: {preset.name.upper()}")
        print(_p.describe(preset.id))
        print()
        _h("WHAT IT WOULD SELECT ON THIS SYSTEM")
        result = app.scan()
        ids = _p.select(preset.id, result.recommendations)
        if not ids:
            print("  Nothing — everything this preset covers is already correct.")
            print("  That is a good result, not a failure.")
        else:
            by_id = {r.optimization.id: r for r in result.recommendations}
            for oid in ids:
                rec = by_id[oid]
                print(f"  • {rec.optimization.title}  ({oid})")
            print()
            print(f"  {len(ids)} change(s) would be selected. Nothing has been")
            print("  applied. Use 'apply' with these ids to proceed.")
        return 0

    _h("OPTIMIZATION PRESETS")
    for pr in _p.PRESETS:
        print(f"  {pr.id:14} {pr.name}")
        for line in _wrap(pr.tagline, 4):
            print(line)
        if pr.caveat:
            for line in _wrap(f"Note: {pr.caveat}", 4):
                print(line)
        print()
    print("  Run 'presets <id>' to see what one would change here.")
    return 0


def cmd_scan(app: PhantomApp, args) -> int:
    _h("PHANTOM SCAN")
    result = app.scan(include_network=args.network)
    print(result.render())
    print()
    for rec in result.recommendations:
        d = rec.as_dict()
        marker = {"HIGH CONFIDENCE": "▲", "MEDIUM CONFIDENCE": "■",
                  "LOW CONFIDENCE": "▫", "NOT RECOMMENDED": "·"}[d["confidence"]]
        print(f"{marker} [{d['category']}] {d['title']}  ({d['id']})")
        print(f"    {d['confidence']} — {d['confidence_blurb']}")
        print(f"    Risk: {d['risk']} | Reversible: {'Yes' if d['reversible'] else 'No'}"
              + ("  | Requires admin" if d["requires_admin"] else ""))
        for line in _wrap(d["reason"], 4):
            print(line)
        print()
    if args.json:
        print(json.dumps([r.as_dict() for r in result.recommendations], indent=2))
    return 0


def _wrap(text: str, indent: int = 0, width: int = 74) -> list[str]:
    import textwrap
    pad = " " * indent
    out = []
    for para in text.split("\n"):
        out.extend(textwrap.wrap(para, width - indent,
                                 initial_indent=pad, subsequent_indent=pad) or [pad])
    return out


def cmd_score(app: PhantomApp, args) -> int:
    _h("PERFORMANCE SCORE")
    app.scan()
    ps = app.performance_score()
    print(ps.render())
    print("\nHow each score was calculated:")
    for s in ps.subscores:
        print(f"\n{s.name} — {s.display}")
        for line in _wrap(s.explanation, 2):
            print(line)
    return 0


def cmd_bottleneck(app: PhantomApp, args) -> int:
    _h("BOTTLENECK ANALYSIS")
    print(f"Sampling for {args.seconds} seconds...\n")
    print(app.bottleneck(args.seconds).render())
    return 0


def cmd_network(app: PhantomApp, args) -> int:
    _h("NETWORK LAB")
    print("Running tests...\n")
    r = app.network_lab(quick=not args.full)
    print(f"Connection: {r['connection']}\n")
    for key in ("gateway", "internet"):
        d = r.get(key)
        if not d:
            continue
        print(f"{key.title()}")
        if d.get("error"):
            print(f"  {d['error']}")
        else:
            print(f"  Latency: {d['latency_ms']} ms")
            print(f"  Packet Loss: {d['packet_loss_pct']}%")
            print(f"  Jitter: {d['jitter_ms']} ms")
        print()
    print("DNS")
    for d in r["dns"]:
        print(f"  {d['provider']:<12}{d['response_ms'] if d['response_ms'] is not None else 'n/a'} ms")
    print()
    diag = r["diagnosis"]
    print(diag["summary"])
    print("\nRecommended:")
    for rec in diag["recommendations"]:
        for line in _wrap(f"• {rec}", 0):
            print(line)
    print()
    for note in r["notes"]:
        for line in _wrap(f"Note: {note}"):
            print(line)
    if args.trace:
        print("\nRoute diagnostics:")
        for line in __import__("phantom_tweeks.network.lab", fromlist=["lab"]).traceroute():
            print("  " + line)
    return 0


def cmd_history(app: PhantomApp, args) -> int:
    _h("PING HISTORY")
    rows = app.network_history(args.days)
    if not rows:
        print("No network history recorded yet. Run 'network-test' a few times.")
        return 0
    peak = max(r["avg_ms"] for r in rows) or 1
    for r in rows:
        bar = "█" * max(1, int(r["avg_ms"] / peak * 30))
        print(f"{r['date']}  {r['avg_ms']:>6.1f} ms  {bar}")
    return 0


def cmd_optimize(app: PhantomApp, args) -> int:
    _h("OPTIMIZE")
    if not IS_WINDOWS:
        print("Analysis-only mode: Phantom Tweeks does not change settings off Windows.")
        return 2
    result_scan = app.scan()
    candidates = result_scan.actionable
    if args.ids:
        chosen = [i for i in args.ids]
    elif args.auto:
        chosen = [r.id for r in candidates if r.auto_applicable]
    else:
        chosen = [r.id for r in candidates]

    if not chosen:
        print("No change recommended for this configuration. Nothing to do.")
        return 0

    print("The following changes will be applied:\n")
    for cid in chosen:
        rec = next((r for r in result_scan.recommendations if r.id == cid), None)
        if rec:
            print(f"  • {rec.optimization.title} ({rec.confidence.value})")
    print("\nA backup will be created first. Every change is reversible with "
          f"'{APP_SLUG}.exe restore'.\n")
    if not _confirm("Apply these changes?", args.yes):
        print("Cancelled. Nothing was changed.")
        return 1

    result = app.apply(chosen, title=args.title or "CLI optimization")
    print(f"\n{result.summary()}")
    for oid in result.applied:
        print(f"  ✓ {oid}")
    for oid, why in result.skipped:
        print(f"  – {oid}: {why}")
    for oid, why in result.failed:
        print(f"  ✗ {oid}: {why}")
    if result.reboot_required:
        print("\n⚠ A reboot is required for some changes to take effect.")
    return 0 if not result.failed else 1


def cmd_benchmark(app: PhantomApp, args) -> int:
    _h("BENCHMARK")
    if args.csv:
        from ..engine import frametime
        stats = frametime.import_csv(args.csv)
    else:
        print(f"Capturing frame times for {args.seconds} seconds...")
        stats = app.benchmark(args.seconds, args.label)
    print()
    print(stats.render())
    if stats.available:
        from ..engine import frametime, history
        print("\nAnalysis:")
        for note in frametime.diagnose(stats):
            for line in _wrap(f"• {note}"):
                print(line)

        # Record locally so 'trends' can show whether things are getting
        # better or worse. Stored on this machine only; never uploaded.
        ctx = {"label": getattr(args, "label", "") or "", "frames": stats.frames}
        if stats.avg_fps:
            history.record("avg_fps", stats.avg_fps, "fps", ctx)
        if stats.p1_low_ms:
            history.record("p1_low_ms", stats.p1_low_ms, "ms", ctx)
        if stats.stutter_count is not None:
            history.record("stutter_count", float(stats.stutter_count), "", ctx)

        t = history.trend("avg_fps")
        if t.samples > 1:
            print("\nCompared with your history:")
            for line in _wrap("  " + t.verdict):
                print(line)
    return 0


def cmd_compare(app: PhantomApp, args) -> int:
    from ..engine import frametime
    _h("PERFORMANCE COMPARISON")
    before = frametime.import_csv(args.before)
    after = frametime.import_csv(args.after)
    rep = app.compare(before, after)
    print(rep.render())
    if rep.regression:
        print("\n[ Restore Changes ]  → run: PhantomTweeks.exe restore --last")
        print("[ Keep Changes ]     → no action needed")
    return 0


def cmd_restore(app: PhantomApp, args) -> int:
    _h("RESTORE")
    if args.all:
        print("This restores every change Phantom Tweeks has made, using recorded")
        print("backups. Unrelated settings you changed yourself are not touched.\n")
        if not _confirm("Restore everything?", args.yes):
            print("Cancelled.")
            return 1
        ok, msgs = app.restore_everything()
    elif args.last:
        hist = app.history()
        pending = next((h for h in hist if not h.get("restored")), None)
        if not pending:
            print("No Phantom Tweeks changes are currently applied.")
            return 0
        if not _confirm(f"Restore '{pending['title']}' ({pending['timestamp']})?", args.yes):
            print("Cancelled.")
            return 1
        ok, msgs = app.restore_backup(pending["id"])
    elif args.id:
        if not _confirm(f"Restore backup {args.id}?", args.yes):
            print("Cancelled.")
            return 1
        ok, msgs = app.restore_backup(args.id)
    else:
        hist = app.history()
        if not hist:
            print("No optimization history yet.")
            return 0
        print("Optimization History\n")
        for h in hist[:25]:
            flag = " (restored)" if h.get("restored") else ""
            print(f"{h['timestamp'][:10]}  {h['title']}")
            print(f"  {h['changes']} changes | backup {h['id']}{flag}")
        print("\nUse --id <backup>, --last, or --all.")
        return 0
    for m in msgs:
        print(" ", m)
    return 0 if ok else 1


def cmd_games(app: PhantomApp, args) -> int:
    _h("GAME LIBRARY")
    lib = app.game_library()
    if not lib:
        print("No games detected. Launcher libraries are read from Steam, Epic, "
              "Xbox, Battle.net, EA, Ubisoft and GOG manifests.")
    for g in lib:
        print(f"  {g.name}\n    {g.launcher} — {g.install_dir}")
    running = app.detect_game()
    print()
    if running:
        print("Currently running:")
        print(f"  {running.name} (pid {running.pid}) via {running.launcher}")
        print(f"  Anti-cheat: {running.anti_cheat or 'not detected'}")
    else:
        print("No game currently running.")
    return 0


def cmd_background(app: PhantomApp, args) -> int:
    _h("BACKGROUND ANALYZER")
    print(app.background_report().render())
    return 0


def cmd_startup(app: PhantomApp, args) -> int:
    _h("STARTUP MANAGER")
    entries = app.startup_entries()
    if not entries:
        print("No startup entries readable (Windows only).")
        return 0
    for e in entries:
        print(e.render())
        print()
    return 0


def cmd_drivers(app: PhantomApp, args) -> int:
    _h("DRIVER CENTER")
    rep = app.driver_report()
    for d in rep["drivers"]:
        print(d.render())
        print()
    print(rep["summary"])
    print("\nPhantom Tweeks never downloads or installs drivers automatically.")
    return 0


def cmd_storage(app: PhantomApp, args) -> int:
    _h("STORAGE LAB")
    rep = app.storage_report()
    for d in rep.disks:
        print(f"{d.mountpoint:<8}{d.media_type or 'Unknown':<12}"
              f"{d.free_gb:.0f} GB free / {d.total_gb:.0f} GB "
              f"({d.percent_used:.0f}% used)")
    for p in rep.physical:
        print(f"\n{p['name']}: {p['media_type']}, health {p['health'] or 'unknown'}"
              + (f", {p['temperature_c']} °C" if p.get("temperature_c") else ""))
    if rep.candidates:
        print(f"\nSafe cleanup candidates ({rep.reclaimable_mb:.0f} MB reclaimable):")
        for c in rep.candidates:
            print(f"  {c.label:<32}{c.size_mb:>8.0f} MB")
            if c.note:
                print(f"    {c.note}")
        print("\nPhantom Tweeks never deletes personal files automatically.")
    print("\nRecommendations:")
    for r in rep.recommendations:
        for line in _wrap(f"• {r}"):
            print(line)
    return 0


def cmd_health(app: PhantomApp, args) -> int:
    app.driver_report()
    _h("SYSTEM HEALTH")
    print(app.health().render())
    return 0


def cmd_profiles(app: PhantomApp, args) -> int:
    _h("GAME PROFILES")
    for p in app.profiles():
        print(p.render())
        print()
    return 0


def cmd_snapshot(app: PhantomApp, args) -> int:
    _h("CONFIGURATION SNAPSHOTS")
    if args.create:
        snap = app.create_snapshot(args.create, args.note or "")
        print(f"Snapshot '{snap.name}' created at {snap.timestamp}.")
        print("Contains only settings Phantom Tweeks manages:")
        for k, v in snap.values.items():
            print(f"  {k:<28}{v}")
        return 0
    snaps = app.snapshots()
    if not snaps:
        print("No snapshots yet. Create one with --create <name>.")
    for s in snaps:
        print(f"Snapshot: {s.name}   ({s.timestamp})")
    return 0


def cmd_latency(app: PhantomApp, args) -> int:
    _h("INPUT RESPONSIVENESS")
    stats = None
    if args.csv:
        from ..engine import frametime
        stats = frametime.import_csv(args.csv)
    r = app.input_latency(stats)
    print("Findings:")
    for f in r["findings"]:
        for line in _wrap(f"• {f}"):
            print(line)
    print("\nRecommended:")
    for x in r["recommendations"]:
        for line in _wrap(f"• {x}"):
            print(line)
    displays = app.displays()
    if displays:
        print("\nDisplays:")
        for d in displays:
            print(f"  {d.render()}")
    if r.get("note"):
        print()
        for line in _wrap(r["note"]):
            print(line)
    return 0


def cmd_export(app: PhantomApp, args) -> int:
    _h("EXPORT REPORT")
    stats = None
    if args.csv:
        from ..engine import frametime
        stats = frametime.import_csv(args.csv)
    app.scan()
    path = app.export_report(args.output, stats)
    print(f"Report written to:\n  {path}\n")
    print("Nothing was transmitted. The file contains no passwords or key material.")
    return 0


def cmd_watch(app: PhantomApp, args) -> int:
    """Live terminal telemetry — useful over RDP or while a game is running."""
    import time
    from ..hardware.monitor import MONITOR
    _h("LIVE MONITOR   (Ctrl+C to stop)")
    try:
        while True:
            cpu = MONITOR.cpu()
            mem = MONITOR.memory()
            gpus = MONITOR.gpus()
            gpu = next((g for g in gpus if g.utilization is not None), None)
            down, up = MONITOR.net_rates()

            def bar(v, width=22):
                if v is None:
                    return "n/a".ljust(width)
                filled = int(max(0, min(100, v)) / 100 * width)
                return "█" * filled + "░" * (width - filled)

            line = (f"CPU {bar(cpu.utilization)} "
                    f"{(f'{cpu.utilization:5.1f}%' if cpu.utilization is not None else '  n/a')}   "
                    f"GPU {bar(gpu.utilization if gpu else None)} "
                    f"{(f'{gpu.utilization:5.1f}%' if gpu and gpu.utilization is not None else '  n/a')}   "
                    f"RAM {(f'{mem.percent:5.1f}%' if mem.percent is not None else '  n/a')}   "
                    f"NET {(f'{down:.1f}' if down is not None else 'n/a')}↓ "
                    f"{(f'{up:.1f}' if up is not None else 'n/a')}↑ Mbps")
            print("\r" + line + " " * 4, end="", flush=True)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n\nStopped.")
    return 0


def cmd_maintenance(app: PhantomApp, args) -> int:
    """Maintenance Mode from the terminal."""
    from ..engine import maintenance

    if args.schedule:
        data = maintenance.save_schedule(args.schedule)
        print(f"Maintenance schedule set to: {data['schedule']}")
        return 0

    _h("MAINTENANCE")
    report = maintenance.run(allow_during_game=args.force)
    print(report.render())

    if not report.ran:
        print("\nUse --force to run anyway (not recommended mid-session).")
        return 0

    if args.clean:
        ids = [r.task_id for r in report.actionable]
        if not ids:
            print("\nNothing to clean.")
            return 0
        print(f"\nCleaning: {', '.join(ids)}")
        if not args.yes:
            print("Add --yes to actually delete. Showing a dry run instead.")
        result = maintenance.apply(ids, dry_run=not args.yes,
                                   allow_during_game=args.force)
        for a in result["applied"]:
            print(f"  {a['task']}: {a.get('removed', 0)} file(s), "
                  f"{a.get('freed_mb', 0):,.1f} MB")
            if a.get("note"):
                print(f"    {a['note']}")
        print(f"  Total: {result['freed_mb']:,.1f} MB"
              f"{' (dry run)' if result['dry_run'] else ''}")
    return 0


def cmd_trends(app: PhantomApp, args) -> int:
    """Show recorded performance history."""
    from ..engine import history

    if args.clear:
        n = history.clear(args.metric)
        print(f"Removed {n} entr{'y' if n == 1 else 'ies'}.")
        return 0

    _h("PERFORMANCE TRENDS")
    data = history.summary()
    if not data["metrics"]:
        print("No measurements recorded yet.")
        print("Run 'benchmark', 'network-test' or 'scan' to start tracking.")
        return 0
    print(f"Retention: {data['retention']}\n")
    for t in data["trends"]:
        if args.metric and t.metric != args.metric:
            continue
        print(t.render())
        print()
    if data.get("note"):
        print(data["note"])
    return 0


def cmd_features(app: PhantomApp, args) -> int:
    """List every feature and whether it is free or Premium."""
    from ..core import features

    data = features.summary()
    _h("FEATURES")
    print(data["promise"])
    print()
    print(f"FREE ({data['free_count']})")
    for f in features.free_features():
        print(f"  [free]    {f.name}")
        print(f"            {f.summary}")
    print()
    mark = "unlocked" if data["active"] else "locked"
    print(f"PREMIUM ({data['premium_count']}) - {mark}")
    for f in features.premium_features():
        print(f"  [premium] {f.name}")
        print(f"            {f.summary}")
    print()
    print(data["payment_note"])
    return 0


def cmd_watchgame(app: PhantomApp, args) -> int:
    """Watch for games starting and stopping, live."""
    import time as _time
    from ..core import gamewatch

    _h("GAME WATCH")
    print("Watching for games. Press Ctrl+C to stop.")
    print("Detection is observation only - no process is ever modified.\n")

    def started(g):
        print(f"  [{_time.strftime('%H:%M:%S')}] STARTED  {g.name} (PID {g.pid})")
        if g.anti_cheat:
            print(f"              anti-cheat: {g.anti_cheat} - protected")

    def stopped(g):
        print(f"  [{_time.strftime('%H:%M:%S')}] STOPPED  {g.name}")

    w = gamewatch.GameWatcher(interval=args.interval,
                              on_start=started, on_stop=stopped)
    state = w.poll_once()
    print(state.render())
    print()
    w.start()
    try:
        while True:
            _time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopped watching.")
    finally:
        w.stop()
    return 0


def cmd_doctor(app: PhantomApp, args) -> int:
    """Self-diagnostic: prove the installation is intact."""
    from ..core import selftest
    _h("SELF-TEST")
    report = selftest.run()
    print(report.render())
    print()
    print("This output is safe to paste into a bug report. It contains no "
          "personal information.")
    return 0 if report.healthy else 1


def cmd_update(app: PhantomApp, args) -> int:
    """Check for a newer release, and optionally download it."""
    from ..core import updates
    from ..branding import VERSION as _V

    _h("UPDATE CHECK")
    print(f"Installed version: {_V}")
    print(f"Checking {args.host} ...")
    info = updates.check(args.host)
    if info is None:
        print("\nNo update available. You are on the latest version, or no")
        print("release has been published yet.")
        return 0

    print()
    print(info.render())

    if not args.download:
        print("\nRun with --download to fetch it. The file is verified against")
        print("its published SHA-256 and is never run automatically.")
        return 0

    asset = info.installer
    print(f"\nDownloading {asset['name']} ...")

    last = [0]

    def progress(done, total):
        if total and done - last[0] > total / 20:
            last[0] = done
            print(f"  {done * 100 // total}%", end="\r", flush=True)

    ok, message, path = updates.download_and_verify(info, asset,
                                                    progress=progress)
    print()
    print(message)
    return 0 if ok else 1


def cmd_premium(app: PhantomApp, args) -> int:
    c = premium.page_content()
    _h(c["title"])
    print(f"{c['status']}\n\n{c['blurb']}\n\nPlanned:")
    for f in c["planned"]:
        print(f"  ✓ {f}")
    print(f"\n{c['note']}")
    if args.notify:
        ok, msg = premium.register_interest(args.notify)
        print(f"\n{msg}")
    return 0


def cmd_expert(app: PhantomApp, args) -> int:
    _h("EXPERT MODE DUMP")
    data = app.expert_dump()
    print(json.dumps(data, indent=2, default=str))
    return 0


def cmd_config(app: PhantomApp, args) -> int:
    _h("CONFIGURATION")
    if args.set:
        key, _, value = args.set.partition("=")
        if key not in app.config.data:
            print(f"Unknown setting '{key}'.")
            return 1
        parsed: object = value
        if value.lower() in ("true", "false"):
            parsed = value.lower() == "true"
        elif value.isdigit():
            parsed = int(value)
        if key == "auto_apply_high_confidence" and parsed is True:
            print("Automatic optimization will apply high-confidence, low-risk,")
            print("reversible changes without asking each time. Backups are still")
            print("created for every change.\n")
            if not _confirm("Enable automatic optimization?", args.yes):
                print("Cancelled.")
                return 1
        app.config.set(key, parsed)
        print(f"{key} = {parsed}")
        return 0
    for k, v in sorted(app.config.data.items()):
        print(f"  {k:<34}{v}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=f"{APP_SLUG}.exe",
        description=f"{APP_NAME} — advanced Windows performance optimization.",
        epilog=GOLDEN_RULE,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--json", action="store_true", help="emit machine-readable output where supported")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("version", help="show version and platform support").set_defaults(fn=cmd_version)
    sub.add_parser("hardware", help="show detected hardware and live telemetry").set_defaults(fn=cmd_hardware)
    sub.add_parser("shield", help="show Phantom Shield status").set_defaults(fn=cmd_shield)

    s = sub.add_parser("power", help="the Phantom custom power plan")
    s.add_argument("--create", action="store_true", help="create/update the plan")
    s.add_argument("--remove", action="store_true", help="delete the plan")
    s.add_argument("--no-activate", action="store_true",
                   help="create without switching to it")
    s.set_defaults(fn=cmd_power)

    s = sub.add_parser("license", help="show, activate or remove a license key")
    s.add_argument("--activate", metavar="KEY", help="activate a license key")
    s.add_argument("--remove", action="store_true", help="remove the license")
    s.set_defaults(fn=cmd_license)

    s = sub.add_parser("presets", help="list optimization presets, or preview one")
    s.add_argument("name", nargs="?", help="preset id to preview")
    s.set_defaults(fn=cmd_presets)

    s = sub.add_parser("scan", help="full system scan and recommendations")
    s.add_argument("--network", action="store_true", help="include network tests")
    s.set_defaults(fn=cmd_scan)

    sub.add_parser("score", help="Phantom Performance Score with explanations").set_defaults(fn=cmd_score)

    s = sub.add_parser("bottleneck", help="detect what is actually limiting performance")
    s.add_argument("--seconds", type=float, default=5.0)
    s.set_defaults(fn=cmd_bottleneck)

    s = sub.add_parser("network-test", help="run the Phantom Network Lab")
    s.add_argument("--full", action="store_true", help="longer, more accurate test")
    s.add_argument("--trace", action="store_true", help="include route diagnostics")
    s.set_defaults(fn=cmd_network)

    s = sub.add_parser("network-history", help="graph stored ping history")
    s.add_argument("--days", type=int, default=7)
    s.set_defaults(fn=cmd_history)

    s = sub.add_parser("optimize", help="apply approved optimizations (requires confirmation)")
    s.add_argument("ids", nargs="*", help="specific optimization ids; default is all applicable")
    s.add_argument("--auto", action="store_true", help="high-confidence items only")
    s.add_argument("--title", help="label for the backup entry")
    s.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")
    s.set_defaults(fn=cmd_optimize)

    s = sub.add_parser("benchmark", help="capture and analyze frame times")
    s.add_argument("--seconds", type=int, default=30)
    s.add_argument("--label", default="benchmark")
    s.add_argument("--csv", help="analyze an existing PresentMon/CapFrameX CSV instead")
    s.set_defaults(fn=cmd_benchmark)

    s = sub.add_parser("compare", help="before/after performance report")
    s.add_argument("before"); s.add_argument("after")
    s.set_defaults(fn=cmd_compare)

    s = sub.add_parser("restore", help="roll back Phantom Tweeks changes")
    s.add_argument("--id", help="restore a specific backup")
    s.add_argument("--last", action="store_true", help="restore the most recent run")
    s.add_argument("--all", action="store_true", help="RESTORE EVERYTHING")
    s.add_argument("-y", "--yes", action="store_true")
    s.set_defaults(fn=cmd_restore)

    sub.add_parser("games", help="list detected games").set_defaults(fn=cmd_games)
    sub.add_parser("background", help="analyze background resource usage").set_defaults(fn=cmd_background)
    sub.add_parser("startup", help="list startup applications").set_defaults(fn=cmd_startup)
    sub.add_parser("drivers", help="driver center report").set_defaults(fn=cmd_drivers)
    sub.add_parser("storage", help="storage lab report").set_defaults(fn=cmd_storage)
    sub.add_parser("health", help="system health center").set_defaults(fn=cmd_health)
    sub.add_parser("profiles", help="list game optimization profiles").set_defaults(fn=cmd_profiles)

    s = sub.add_parser("maintenance", help="run safe maintenance checks")
    s.add_argument("--clean", action="store_true",
                   help="also clean up regenerable caches")
    s.add_argument("--yes", action="store_true",
                   help="actually delete (otherwise a dry run)")
    s.add_argument("--force", action="store_true",
                   help="run even while a game is detected (not recommended)")
    s.add_argument("--schedule", choices=["off", "weekly", "monthly"],
                   help="set the maintenance schedule and exit")
    s.set_defaults(fn=cmd_maintenance)

    s = sub.add_parser("trends", help="performance history over time")
    s.add_argument("--metric", help="show only this metric")
    s.add_argument("--clear", action="store_true", help="delete stored history")
    s.set_defaults(fn=cmd_trends)

    sub.add_parser("features", help="list free and Premium features"
                   ).set_defaults(fn=cmd_features)

    sub.add_parser("doctor", help="check the installation and report problems"
                   ).set_defaults(fn=cmd_doctor)

    s = sub.add_parser("update", help="check for a newer version")
    s.add_argument("--download", action="store_true",
                   help="download and verify the update (never runs it)")
    s.add_argument("--host", default=__import__("phantom_tweeks.core.updates",
                   fromlist=["x"]).DEFAULT_UPDATE_HOST,
                   help="update host (defaults to the official site)")
    s.set_defaults(fn=cmd_update)

    s = sub.add_parser("watch-game", help="live game start/stop detection")
    s.add_argument("--interval", type=float, default=3.0,
                   help="seconds between checks (default 3)")
    s.set_defaults(fn=cmd_watchgame)

    s = sub.add_parser("snapshot", help="configuration snapshots")
    s.add_argument("--create", metavar="NAME")
    s.add_argument("--note", default="")
    s.set_defaults(fn=cmd_snapshot)

    s = sub.add_parser("premium", help="Phantom Premium information")
    s.add_argument("--notify", metavar="EMAIL", help="register interest locally")
    s.set_defaults(fn=cmd_premium)

    s = sub.add_parser("latency", help="input responsiveness analysis")
    s.add_argument("--csv", help="include FPS analysis from a frame-time CSV")
    s.set_defaults(fn=cmd_latency)

    s = sub.add_parser("export", help="write a full diagnostic report to a file")
    s.add_argument("-o", "--output", default="PhantomTweeks-Report.txt")
    s.add_argument("--csv", help="include frame-time data from a CSV")
    s.set_defaults(fn=cmd_export)

    s = sub.add_parser("watch", help="live terminal telemetry")
    s.add_argument("--interval", type=float, default=1.0)
    s.set_defaults(fn=cmd_watch)

    sub.add_parser("expert", help="expert-mode technical dump").set_defaults(fn=cmd_expert)

    s = sub.add_parser("config", help="view or change settings")
    s.add_argument("--set", metavar="KEY=VALUE")
    s.add_argument("-y", "--yes", action="store_true")
    s.set_defaults(fn=cmd_config)

    s = sub.add_parser("gui", help="launch the graphical interface")
    s.set_defaults(fn=lambda app, args: __import__(
        "phantom_tweeks.gui.app_window", fromlist=["launch"]).launch())
    return p


def run(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    app = PhantomApp()
    try:
        return args.fn(app, args)
    except KeyboardInterrupt:
        print("\nInterrupted. No partial changes were left applied.")
        return 130
    except PermissionError as e:
        print(f"\nBlocked: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(run())
