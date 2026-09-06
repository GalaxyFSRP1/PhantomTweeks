# Changelog

All notable changes to Phantom Tweeks. Versions follow
[semantic versioning](https://semver.org). While the major version is `0`,
releases are published as pre-releases: the software is usable but the
interfaces may still change.

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
