# Changelog

All notable changes to Phantom Tweeks. Versions follow
[semantic versioning](https://semver.org). While the major version is `0`,
releases are published as pre-releases: the software is usable but the
interfaces may still change.

## 0.1.5 — 2026-09-06

### Fixed
- **The MSI download link 404'd.** The release asset is named
  `PhantomTweeks-<version>.msi`, but `api/download.py` matched against a static
  allowlist containing only fixed filenames — so no `.msi` could ever be
  served, at any version. The endpoint now resolves the MSI from the release's
  own asset list, so it stays correct for every future version without another
  code change. Path traversal and lookalike names are still rejected.
- `?file=msi` now works, alongside `setup`, `portable`, `app` and `checksums`.

### Added
- **Tweak Encyclopedia expanded to 253 entries** —
  73 safe, 102 situational, 37 placebo,
  41 harmful. Covers Windows, network, GPU, CPU, power, storage,
  input, display, memory, launchers, anti-cheat, audio, in-game settings and
  physical maintenance.
- Notable additions: `bcdedit useplatformclock true` is **harmful** — it forces
  the slower HPET timer and measurably increases DPC latency, the opposite of
  its claim. The "Windows reserves 20% of your bandwidth" QoS myth is
  **placebo** — the reserve only applies to QoS-aware applications.
  Disabling SMT/Hyper-Threading is **harmful** on modern multi-threaded games.
- The highest-impact entries are deliberately unglamorous: check your refresh
  rate is not stuck at 60 Hz, enable XMP/EXPO, move the game to an SSD, use
  Ethernet, and clean the dust. These beat every registry tweak combined.

## 0.1.4 — 2026-09-06

### Added
- **Tweak Encyclopedia** — 29 popular Windows gaming tweaks from
  the lists circulated by sites like miztweakz, risxntweaks and hone.gg, each
  with a verdict and the reasoning behind it: **7 safe**,
  **5 situational**, **8 placebo**,
  **9 harmful**. Searchable by name or registry value, so you can
  paste something from a YouTube guide and get a straight answer.
- Phantom Tweeks implements the safe and situational ones. The rest are
  documented rather than hidden — telling you *why* a tweak was rejected is
  more useful than pretending it does not exist, because otherwise you will
  find the .reg file somewhere with no warning attached.
- `python run.py tweaks`, `--search TERM`, `--verdict safe|situational|placebo|harmful`.

### Notable verdicts
- **`SystemResponsiveness = 0`** and **`GPU Priority = 8`** are placebo. They
  are MMCSS task-profile values that apply to threads registered with the
  multimedia scheduler — which games do not use for rendering.
- **Disabling Spectre/Meltdown mitigations** is harmful. The performance claim
  is largely obsolete on current CPUs; the security exposure is not.
- **Disabling Core Isolation/VBS** can leave you unable to launch the game you
  were optimising, since several anti-cheat systems now require it.
- **`sc delete`** on a Windows service is irreversible and breaks Windows
  Update. A stopped service already costs nothing.
- **RAM cleaners** discard a cache Windows built deliberately, making the next
  load slower.

## 0.1.3 — 2026-09-06

### Added
- **DNS Lab** — a new page listing 24 DNS providers with their filtering and
  logging policies. Benchmarks each with real UDP queries against six domains
  gamers actually resolve, then applies your choice in one click and records
  the previous servers so it can be undone. Runs in parallel (25s for the full
  catalog; it was 45s serially for half the samples).
- **Automatic updates** — a once-a-day background check against the release
  API, with a dismissible banner offering "skip this version" or "remind me
  later". Downloads are verified against their published SHA-256 and staged
  for you to install.
- **Maintenance Mode** — seven safe health checks with weekly or monthly
  scheduling.
- **Performance Trends** — benchmark history stored locally, with trend
  analysis.
- **Live game auto-detection** — a background watcher with debouncing.
- **Help & Diagnostics** — a self-test reporting subsystem health.
- **Assisted PresentMon install** — downloads Intel's official build.
- **Quick Actions** on the dashboard.
- **`/api/activate`** — device activation and limits for the licensing
  backend. Fails open so a valid customer is never locked out.
- **CLI** — `doctor`, `update`, `trends`, `maintenance`, `features`,
  `watch-game`, `config --init`.

### Fixed
- **Website reported "no release published yet" when one existed.** GitHub's
  `/releases/latest` endpoint skips pre-releases, and every 0.x build is a
  pre-release. Both API endpoints now list releases and take the newest
  non-draft.
- **Power plan creation failed with a cryptic error** without administrator
  rights. It now says exactly what to do, and reports powercfg's real error
  otherwise.
- **Console windows flashed during monitoring.** All 14 external commands now
  run hidden. The hardware monitor polls on a timer, so this was a black box
  appearing every few seconds, able to steal focus from a fullscreen game.
- **`hardware` appeared to hang.** Every WMI query launched a PowerShell
  process with no caching. Results are now cached for the process lifetime,
  with a per-query timeout and a global budget.
- **`ImportError: attempted relative import with no known parent package`** in
  the packaged build.
- **Sidebar overflowed** at 19+ pages, making Settings and Help unreachable.
  It is now scrollable, with the action buttons pinned.
- Seven navigation icons rendered as missing-glyph boxes on Windows.
- A duplicate `_refresh_premium` silently shadowed the real one, leaving the
  licence status stuck on "Checking…".
- `Permissions-Policy` no longer sends the dead `interest-cohort` token.
- The installer creates `%LOCALAPPDATA%\PhantomTweeks` and seeds default
  settings, preserving existing settings on reinstall.

### Changed
- Frame-time capture accepts any `PresentMon*.exe` in the tools folder.
- Website: keyboard focus rings, `prefers-reduced-motion`, skip links.
- App: themed notebook tabs, dark scrollbars, accent progress bars.

## 0.1.2 — 2026-09-05

Initial release. Phantom Shield, the optimization engine with confidence
ratings, the backup vault with per-change rollback, Frame-Time Analyzer,
Network Lab, bottleneck detection, Driver Center, Storage Lab, Startup
Manager, System Health, game detection across eight launchers, a full CLI,
and the inert Premium architecture.
