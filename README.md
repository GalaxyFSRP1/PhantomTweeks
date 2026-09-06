# Phantom Tweeks

**Optimize Smarter. Game Better.**

Advanced Windows 10/11 gaming and performance optimization suite built around *real system
data*. Phantom Tweeks measures your machine, explains what is actually limiting it, changes
only what you approve, and gives you a one-click way back.

This is a working application, not a mockup — but it is deliberately **not** a one-click FPS
booster. If a tweak will not help your specific hardware, Phantom Tweeks tells you so.

---

## The Golden Rule

> Phantom Tweeks must never break the user's PC in an attempt to make it faster.

* Potential +2 FPS vs. possible instability → **stability**
* Claiming an optimization worked vs. honestly reporting no measurable change → **honesty**
* Closing Discord/Steam/the game vs. leaving them running → **leave them running**

---

## The pipeline

```
SCAN → ANALYZE → RECOMMEND → BACKUP → APPROVE → OPTIMIZE → BENCHMARK → COMPARE → RESTORE IF NECESSARY
```

Nothing is written to your system until a **verified backup exists** and you have **explicitly
approved** the change. Automatic optimization is off by default and, even when enabled, only
ever applies high-confidence, low-risk, reversible, non-advanced items.

---

## Quick start

### Run from source

```bash
pip install -r requirements.txt

python run.py            # launches the GUI
python run.py scan       # or use the CLI
python run.py --help     # all commands
```

On Windows you can also just double-click **`PhantomTweeks.bat`**.

> **`No module named phantom_tweeks`?**
> This project uses a `src/` layout, so `python -m phantom_tweeks` only works once the
> package is installed. Use `python run.py` instead, or install it first:
>
> ```bash
> pip install -e .
> python -m phantom_tweeks     # now works from anywhere
> ```

### Build Windows binaries

```powershell
.\build.ps1
```

Produces in `dist/`:

| File | Description |
|---|---|
| `PhantomTweeks.exe` | Main application |
| `PhantomTweeks-Portable.exe` | Single-file portable build |
| `PhantomTweeks-Setup.exe` | Installer (requires Inno Setup 6) |
| `SHA256SUMS.txt` | Checksums for every artefact |

Useful flags: `-SkipTests`, `-SkipInstaller`, `-Clean`, `-Sign -CertThumbprint <hash>`.

> **Sign your releases.** `build.ps1` warns loudly when producing unsigned binaries. Users
> cannot verify an unsigned executable, and SmartScreen will block it.

---

## CLI

```
PhantomTweeks.exe scan              full system scan and recommendations
PhantomTweeks.exe optimize          apply approved optimizations (requires confirmation)
PhantomTweeks.exe benchmark         capture and analyze frame times
PhantomTweeks.exe network-test      run the Phantom Network Lab
PhantomTweeks.exe restore           roll back changes (--id / --last / --all)
PhantomTweeks.exe hardware          hardware inventory and live telemetry
PhantomTweeks.exe version           version and platform support
```

Plus: `shield`, `score`, `bottleneck`, `network-history`, `compare`, `games`, `background`,
`startup`, `drivers`, `storage`, `health`, `profiles`, `snapshot`, `premium`, `expert`,
`config`, `gui`.

Commands that change the system require `--yes` or an interactive confirmation, and report
clearly when they need elevation.

---

## Features

### Safety
* **Phantom Shield** — a hard deny-list wired into every process-touching code path. Games,
  launchers, anti-cheat, voice chat, capture software, GPU services, input software and
  essential Windows processes can never be killed, suspended, reprioritised, re-affinitised
  or injected into. Not by any mode, including Expert Mode.
* **Security deny-list** — Defender, Firewall, Windows Update, security mitigations and
  anti-cheat services are refused at the registry-write API, not merely hidden in the UI.
* **Backup vault** — every change records its exact prior value; a sentinel marks values that
  did not previously exist so restore deletes rather than guesses.
* **One-click restore** — reverts only what Phantom Tweeks recorded.
* **Multi-step confirmation** for advanced changes, with a stated recovery plan.

### Analysis
* Live dashboard (CPU/GPU/VRAM/RAM/disk/network) — unavailable sensors read `n/a`, never faked
* Transparent 8-part Performance Score, each sub-score showing its formula and inputs
* Phantom Scan across 10 subsystems with confidence-rated recommendations
* Bottleneck detection: GPU-bound / CPU-bound / memory / network / balanced
* Frame-Time Analyzer: 1% and 0.1% lows, pacing score, stutter detection
* Background Analyzer that reports heavy processes and closes nothing

### Hardware & system
* Vendor-aware CPU and GPU analysis (NVIDIA / AMD / Intel)
* Driver Center with staleness detection and official vendor links — installs nothing
* Storage Lab with HDD/SATA/NVMe detection, health and safe cleanup candidates
* Startup Manager with impact, publisher and reversible disable
* System Health Center where every warning carries its reason

### Network
* Gateway and internet tested separately so local faults aren't blamed on the ISP
* Jitter (mean consecutive delta), packet loss, DNS benchmark, route diagnostics
* Sustained stability testing and locally stored ping history

### Workflow
* Game detection across Steam, Epic, Xbox/Game Pass, Battle.net, Riot, EA, Ubisoft, GOG
* Profiles: Competitive, Balanced, Quality, Streaming, Creator + custom
* Gaming / Streaming / Creator modes — monitoring only
* Configuration snapshots containing only settings we manage
* Before/after comparison with automatic regression rollback

---

## What Phantom Tweeks will never do

* Close, suspend or reprioritise your game, Steam, Discord, Epic, OBS or anti-cheat
* Disable Windows Defender, Firewall, Windows Update or CPU security mitigations
* Modify game files, executables or anti-cheat
* Delete personal files
* Overclock, undervolt or disable CPU cores
* Download and execute arbitrary files
* Send telemetry (there is no endpoint in the build)
* Claim an improvement it did not measure

---

## Project layout

```
phantom-tweeks/
├── src/phantom_tweeks/
│   ├── app.py              facade shared by GUI and CLI
│   ├── branding.py         single source of brand truth
│   ├── core/               shield, config, games, paths, premium, updates, notifications
│   ├── engine/             optimizer, catalog, backup, winsettings, bottleneck,
│   │                       frametime, comparison, score, profiles, health, drivers,
│   │                       storage, startup, background, gaming_mode
│   ├── hardware/monitor.py telemetry (never fabricated)
│   ├── network/lab.py      Network Lab
│   ├── gui/                Tkinter dark-theme interface
│   └── cli/main.py         command-line interface
├── website/                9-page official site
├── tests/                  129 tests, safety-focused
├── docs/                   privacy, security, architecture, user guide
├── build/                  PyInstaller spec + Inno Setup script
├── assets/                 icon set
└── build.ps1               Windows build script
```

---

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q        # 129 tests
```

The test suite deliberately over-indexes on safety invariants: Shield coverage across every
dangerous action, the security deny-list, "no change recommended" outcomes, auto-apply
eligibility rules, backup/restore round-trips, regression detection and honest reporting.

**Non-Windows platforms** run in analysis-only mode: monitoring, network diagnostics and
reporting all work, while every mutating operation refuses politely instead of guessing.

---

## Documentation

* [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) — using the application
* [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how it is built and why
* [`docs/SECURITY.md`](docs/SECURITY.md) — the safety model in detail
* [`docs/PRIVACY.md`](docs/PRIVACY.md) — privacy policy
* [`docs/BUILDING.md`](docs/BUILDING.md) — build and distribution guide

---

© 2026 Phantom Tweeks. Windows is a trademark of Microsoft Corporation. Phantom Tweeks is not
affiliated with Microsoft, Valve, Epic Games, NVIDIA, AMD, Intel or any game publisher.

### What's in 0.1.3

- **DNS Lab** — 24 providers, benchmarked with real UDP queries from your
  machine. One-click switching with a recorded undo. Says plainly that DNS
  affects name lookups, not in-game ping.
- **Automatic updates** — daily background check against the release API.
  Downloads are verified against their published SHA-256 and staged; nothing
  is ever executed automatically and checks never run during a game.
- **Maintenance Mode** — scheduled housekeeping that refuses to run mid-game
  and never touches personal files.
- **Performance Trends** — local history with a conservative noise floor, so
  a change smaller than run-to-run variation is reported as "no real change".
- **Live game auto-detection** — notices games started after the app.
- **Help & Diagnostics** — self-test that distinguishes our bugs from
  environment problems.
- **Assisted PresentMon install** — fetches Intel's official build.
- **Fixes** — power plans explain the need for administrator rights instead
  of failing silently; external commands no longer flash console windows; the
  installer creates `%LOCALAPPDATA%\PhantomTweeks` up front; the website now
  sees pre-releases.

### What's in 0.1.2

- **Input Latency page** — finds high-refresh monitors stuck at 60 Hz, frame
  rate/refresh mismatches, GPU/CPU saturation and mouse acceleration.
- **Export Report** (`Ctrl+E`) — a local plain-text diagnostic report. Nothing
  is uploaded.
- **12 optimizations**, including mouse acceleration, MMCSS gaming scheduling,
  network throttling index, Windows Search indexing and Storage Sense.
- **Full mouse-wheel and keyboard scrolling** on every page, and
  click-anywhere recommendation cards with select-all / recommended-only chips
  and a live selection counter.
- **Optimization presets** — Safe / Balanced / Competitive / Quiet / Housekeeping,
  as a filter over your real scan results. Presets can never select a
  NOT RECOMMENDED, low-confidence or advisory-only item.
- **Resumable restore** — a restore that partly fails is recorded as
  "Partially restored (N/M)", retries only the outstanding changes, and
  survives a crash or power loss mid-restore.
- **Phantom power plan** — a Balanced-derived Windows power plan with eight
  justified changes. Never pins the CPU at 100% minimum state, detects laptops,
  and leaves your existing plans untouched.
- **Real premium licensing** — Ed25519-signed keys verified offline, an admin
  CLI for issuing/revoking them, and a Vercel serverless validation API.
- **Live game auto-detection** - a background watcher notices a game starting
  or stopping even if it was launched after Phantom Tweeks, or was already
  running when the app opened. Detection is observation only: no process is
  ever reprioritised, suspended or killed.
- **Maintenance Mode** - routine health checks and safe cleanup, with a weekly
  or monthly schedule. Never runs while a game is detected, and never deletes
  anything personal.
- **Performance Trends** - benchmarks are recorded locally over time so you can
  see whether a driver update actually cost you frames. Changes smaller than
  the measured run-to-run noise are reported as "no real change" rather than
  spun as a win.
- **Real Premium tier** - 9 implemented Premium features and 14 free ones, with
  enforced gating. Safety features (scan, Shield, backup, restore, every
  warning) are free forever.
- **Quick Actions** on the dashboard - scan, maintenance, health and
  self-test are one click from launch.
- **Automatic updates** - a daily background check against the release API,
  with a dismissible banner. Downloads are verified against their published
  SHA-256 and staged for you to install; nothing is ever executed
  automatically, and checks never run during a game.
- **Self-diagnostic** - `python run.py doctor`, or Help & Diagnostics in the
  app. Reports which subsystems are healthy and whether a failure is our bug
  or an environment limitation.
- **No console flashes** - every external command runs hidden, so nothing
  steals focus from a fullscreen game.
- **MSI package** for managed deployment (Group Policy / Intune / `msiexec`),
  alongside the normal `.exe` installer.
- **New CLI commands**: `latency`, `export`, `watch`, `presets`, `power`, `license`.
