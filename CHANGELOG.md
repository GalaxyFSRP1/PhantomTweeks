# Changelog

All notable changes to Phantom Tweeks. Versions follow
[semantic versioning](https://semver.org). While the major version is `0`,
releases are published as pre-releases: the software is usable but the
interfaces may still change.

## 0.2.9 — 2026-09-06

### Added
- **A second, all-out power plan: "Phantom Tweeks Maximum".**
  17 settings against the Gaming plan's
  8. No idle states, no core parking, no
  PCIe link power management, aggressive boost, instant clock ramp-up and a
  slow ramp-down so the CPU does not drop speed between frames. Display,
  sleep, disk and hibernate timeouts all disabled on AC.
- The Gaming plan remains the default and the recommendation. Both are offered
  side by side, and the confirmation lists every setting before it applies
  anything.

### Honest notes
- **Maximum pins the CPU at 100%, which the Gaming plan deliberately avoids.**
  That is the point of having two tiers - but it costs power and heat for a
  gain you will mostly see in 1% lows, and on a thermally limited machine it
  can reduce sustained clocks.
- **On a laptop the app warns before creating it and asks twice.** A pinned
  CPU reaches its thermal limit sooner, and a throttled chip runs slower than
  one allowed to idle between frames. The warning says exactly that.
- Battery values stay conservative in both profiles. An "everything maximum"
  plan that flattens a laptop in forty minutes is not a feature.
- Still no overclocking, undervolting or voltage changes in either profile.
  These are Windows power-plan settings only.

### Fixed
- Two settings in the new profile had one-line justifications. Every setting
  in every profile now explains itself, enforced by a test.

## 0.2.8 — 2026-09-06

### Fixed
- **Your tweak selections are now saved.** Nineteen toggles could not read
  their state back from Windows - a powercfg sub-setting, a scheduled task, an
  adapter property the driver does not expose. They reported OFF
  unconditionally, so every switch you flipped appeared off again on the next
  launch, and there was no way to tell "off" from "cannot tell".
- Tweaks that cannot be read now declare that explicitly, and the app records
  what you chose. Verified end to end across two separate processes: apply,
  quit, relaunch, still on.
- **Where Windows CAN read a setting, the machine still wins.** The saved
  record never overrides reality - it only fills the gap. If the two disagree,
  the app says "changed outside Phantom Tweeks", which is what you see after
  Windows Update or a driver reinstall reverts something.
- **Re-apply my saved tweaks** button for exactly that case.

### Added
- **Latency tweaks: 54 to 64** - now **10 CPU** and **13 NVIDIA**.
  New CPU: aggressive boost policy, faster clock ramp-up, slower ramp-down,
  unparked cores, timer resolution and timer distribution. New NVIDIA: G-Sync
  fullscreen, Ansel/overlay hooks, Dynamic Boost and 3D PowerMizer level.
- **Network tweaks: 48 to 54.** Wi-Fi transmit power, MIMO power
  saving, wake-on-LAN packet matching, IPv4 preference, hosts-file resolution
  priority and SMB bandwidth throttling.
- `run.py saved`, `--reapply`, `--clear`.

### Honest notes
- The IPv4 preference tweak changes *preference only*. It does not disable
  IPv6, which Microsoft explicitly advises against and which breaks parts of
  Windows.
- SMB bandwidth throttling says plainly that it has no effect on game traffic.
- The high-resolution timer tweak says it is far narrower than older guides
  claim, because since Windows 10 2004 the request applies per process.

## 0.2.7 — 2026-09-06

### Added
- **Real driver update checking.** Queries NVIDIA's own public driver service
  and compares it against what is installed. Verified live: it translates the
  Windows driver version `31.0.15.6603` into NVIDIA's `566.03` - comparing the
  raw strings would report every driver as outdated - and correctly found
  `582.66` published.
- AMD and Intel publish no open version API, so those are reported honestly as
  "cannot compare automatically" with a link, rather than inventing a result.
- **Phantom Tweeks never downloads or installs a driver.** Those load kernel
  code, and automated driver updaters are a well-known malware vector. A test
  fails the build if this module ever gains a download or execute call.
- **Network tweaks: 41 to 48.** TCP Fast Open, dead gateway
  detection, path MTU discovery, selective acknowledgements, receive and
  transmit buffers, and task offload.
- **Latency tweaks: 42 to 54**, with a new **CPU category**: idle
  state floor, minimum processor state, boost policy, performance-core
  preference and interrupt steering. Plus four more NVIDIA settings - texture
  filtering, threaded optimization, pre-rendered frame limit and driver
  V-Sync.
- The minimum processor state deliberately sets 50%, not 100%. Pinning a
  modern CPU at full clock removes the thermal headroom single-core boost
  depends on, so 100% often *lowers* peak performance.

### Fixed
- An info button on the NVIDIA page clipped at 1000x640 because the settings
  card and the report panel competed for height.
- The anti-overclocking test was grepping for the word "voltage" and flagged
  a description that says the tweak does *not* touch voltages. It now parses
  the AST and checks what the code actually calls. Verified it still catches
  a real `nvidia-smi -lgc` clock-lock call.

## 0.2.6 — 2026-09-06

### Fixed
- **The power plan really does create now.** The remaining cause was that
  `/duplicatescheme` copies from Balanced - and many OEM machines ship without
  it. Dell, HP and Lenovo all replace Balanced with their own profile, so
  powercfg returned "the system cannot find the file specified", which reads
  as a permissions error and is not. Creation now falls back to your active
  scheme, then to any scheme present, and says which one it copied. When
  group policy genuinely blocks every scheme it says that instead of blaming
  administrator rights.
- The plan is verified findable after creation, so a silent rename failure is
  reported rather than leaving an unmanageable duplicate.

### Added
- **CPU page with Intel and AMD specific guidance.** Generic tweak lists give
  both vendors the same answer, which is how people end up disabling SMT on a
  Ryzen or setting manual affinity on a hybrid Intel chip.
- Detects hybrid Intel layouts (P-cores and E-cores) and Ryzen chiplet counts.
  A 12700K resolves to 8 P-cores + 4 E-cores; a 7950X to 2 CCDs.
- **AMD** leads with EXPO/DOCP, because Ryzen scales with memory speed more
  than any other consumer platform - the Infinity Fabric runs in step with it.
- **Intel 12th gen and newer** leads with "do not set CPU affinity manually",
  because Thread Director places threads and overriding it can pin your game
  to efficiency cores.
- Neither vendor is told to disable SMT. A test enforces that.

### Changed
- **The NVIDIA toggles moved onto the NVIDIA GPU page** instead of being
  buried in the Latency Tweaks list.

## 0.2.5 — 2026-09-06

### Added
- **Bufferbloat test.** This is the one that actually matters for ping. Idle
  ping is what speed tests report and it barely predicts anything; what ruins
  a match is latency *while the connection is busy*. The test pings
  continuously while idle, during a download and during an upload, and grades
  the difference A+ to F.
- Unlike most items in this app, bufferbloat has a **real fix** - SQM on the
  router, or capping bulk downloads - and the report names it rather than
  suggesting a registry change that cannot help.
- Upload is measured separately because home connections are asymmetric and
  upstream saturates far sooner. An asymmetric result is called out.
- **Network tweaks: 35 to 41.** Steam download throttling, metered
  connection, Proportional Rate Reduction, minimum retransmit timeout, Wi-Fi
  maximum performance and background scan reduction - several aimed squarely
  at the saturation that causes bufferbloat.

### Fixed
- **The bufferbloat test could invent a perfect score.** On a machine where
  ICMP is blocked every ping timed out, and the first implementation
  substituted the timeout value for all three phases. They matched, the
  difference was zero, and it reported **grade A+ on a connection it had
  never once successfully pinged**. It now refuses to grade without real
  replies and explains that ICMP is probably blocked. A test locks this down.

## 0.2.4 — 2026-09-06

### Fixed
- **The power plan, properly this time.** The plan name contained an em dash.
  powercfg runs on a cp1252 console, so Windows stored the name mangled and
  `find_phantom_plan()` could never match it again. The plan WAS being created
  every single time - it just became invisible to the app, so every run made
  another duplicate and "Remove" found nothing to remove. The name is now pure
  ASCII, the whole module is ASCII-only, and a test fails the build if a
  non-ASCII character is ever reintroduced.
- Existing mangled plans from earlier versions are recognised and adopted
  instead of duplicated, and a **"Clean up duplicates"** button removes the
  extras a previous version left behind.

### Added
- **Network tweaks: 26 to 35.** TCP initial RTO, SYN retry count,
  keep-alive interval, network interrupt priority, DNS-over-HTTPS, Wi-Fi
  roaming aggressiveness, 5 GHz band preference, packet coalescing and ARP
  cache lifetime.
- **Latency tweaks: 32 to 42**, including a new **NVIDIA
  category**: Low Latency Mode, prefer maximum performance, a larger shader
  cache, driver telemetry, and G-Sync in windowed mode. Plus timer interrupt
  distribution, MMCSS storage I/O priority, DWM throttling and hibernation.
- The shader cache tweak is worth singling out: it directly reduces
  shader-compilation stutter, which is one of the most common causes of
  hitching in modern games, and costs nothing but disk space.

### Honest notes
- The NVIDIA "GPU priority" tweak is included at Microsoft's **documented**
  value, not the inflated one guides suggest. The Tweak Encyclopedia rates the
  popular version as placebo and that assessment has not changed.
- DNS-over-HTTPS is described as a privacy and reliability improvement, not a
  speed one - it adds a small handshake overhead.

## 0.2.3 — 2026-09-06

### Fixed
- **Confirmation dialogs could push their buttons off-screen.** The window was
  a fixed 540x330 with the message in a plain label, so a long list - "turn on
  30 tweaks" - moved Confirm below the bottom edge where it could not be
  clicked. The dialog now packs its buttons against the bottom first, puts the
  message in a scrolling area, sizes itself to its content and caps that at
  85% of screen height. Verified with a 200-item message: the window settles
  at 511px with both buttons fully visible and at full height.

### Added
- **Administrator elevation at startup.** The app requests rights through the
  standard UAC prompt, because most of what it does needs them - HKLM writes,
  power plans, adapter settings, restore points. Declining is respected: it
  continues with reduced capability and lists exactly what is unavailable.
  Controlled by "Ask for administrator rights when the app starts".
- The relaunch passes a marker argument so a declined prompt can never loop,
  and CLI commands never trigger UAC - asking for a report should not prompt.
- **35 settings**, up from 20, in four new tabs: Startup, Safety,
  Interface and expanded Diagnostics. Restore point before tweaks, confirm
  every tweak, double confirmation for high-risk changes, backup retention,
  compact layout, risk badges, auto-refresh intervals and hardware query
  timeouts.
- A test now fails the build if any setting exists in config but is not
  reachable from the Settings page.

### Changed
- **The NVIDIA page moved from Dashboard to Tweaks**, where it belongs
  alongside the other tweak pages.

## 0.2.2 — 2026-09-06

### Added
- **Network tweaks: 15 to 26.** New: TCP timestamps, ECN, Receive
  Segment Coalescing, auto-tuning heuristics, the CTCP congestion provider,
  ephemeral port range, default TTL, negative DNS caching, the QoS bandwidth
  reservation, NetBIOS over TCP/IP and LLMNR.
- **Latency tweaks: 17 to 32.** New: mouse and keyboard input
  buffers, USB selective suspend, a flattened pointer acceleration curve,
  fullscreen optimizations, Multi-Plane Overlay, foreground priority
  separation, svchost grouping, the network usage driver, NTFS last-access
  timestamps, boot-only prefetch, core parking, USB hub power, the
  compatibility appraiser, background Store apps and Widgets.
- **Registry page** listing all 19 values the app can change,
  each with its current state, the Windows default, what it means and which
  toggle sets it. Search by name, path or meaning; filter to only what differs
  from default.

### Honest notes
- Two new network tweaks are included because people expect them and say so
  plainly: **default TTL** and the **QoS 20% reservation** myth both state
  "expect no measurable change" in their own description.
- The registry page is deliberately **not** a general editor. Regedit does that
  better, and a full editor inside an optimizer invites blind copy-paste from
  forum posts. Manual writes require explicit confirmation and are refused for
  any path outside the managed set.

### Fixed
- **A toggle that did nothing.** `pointer_precision_off` wrote the same value
  whether switched on or off. Replaced with a real flattened-curve tweak, and
  a test now fails the build if any of the 58
  toggles writes identical values in both directions.

## 0.2.1 — 2026-09-06

### Added
- **17 latency and performance tweaks as toggles**, grouped into
  Input, Display, System, Power and Background. Same contract as the network
  tweaks: flip on to apply, flip off to restore the Windows default exactly.
  Mouse acceleration and its thresholds, keyboard repeat, Filter Keys, Sticky
  Keys, Game DVR, Game Bar tips, menu delay, transparency, animations, HAGS,
  CPU power throttling, paging executive, MMCSS Games profile, search
  indexing, tips, and startup delay.
- **NVIDIA GPU page.** Graphics, memory and SM clocks against their maximums,
  power draw against both the current limit and the card's rated ceiling,
  temperature against the slowdown target, fan speed, and PCIe link width.
- **"What is limiting my clocks?"** reads the card's own throttle reasons from
  NVML. Instead of guessing, it tells you whether you are power-capped,
  thermally capped, or hitting a hardware protection - and what actually
  fixes each.
- **PCIe downgrade detection.** A card negotiating Gen 3 x8 when it should be
  Gen 4 x16 is a real, findable fault that costs measurable performance, and
  most tools never surface it.

### Deliberately not added
- **No overclocking or undervolting.** Clocks are reported, never set. Silicon
  quality varies between individual chips: a preset stable on one card causes
  artifacts, driver timeouts or silent corruption on another, usually hours
  later. Tests fail the build if this module ever gains a clock-setting call.

## 0.2.0 — 2026-09-06

### Added
- **15 network tweaks as one-click toggles** — no analysis step, no
  scanning. Flip a switch and it applies; flip it back and the Windows default
  is restored exactly. Covers Nagle batching, delayed ACK, interrupt
  moderation, Energy Efficient Ethernet, Green Ethernet, adapter power-saving,
  flow control, RSS and RSS queues, the multimedia network throttle, MMCSS
  reserved CPU, DNS resolver, DNS flush, Delivery Optimization uploads, and
  TCP auto-tuning.
- **Honest wording throughout.** These reduce delay your *own PC* adds:
  packet batching, adapter wake-up time, name lookups, background uploads.
  They do not change the distance to a game server, which is what ping
  measures. A test fails the build if any wording claims otherwise.
- **Caution notes on the two that can backfire.** Interrupt moderation raises
  CPU use; adapter power-saving costs laptop battery. Everything else is a
  plain toggle. "Turn on the safe ones" applies only the unflagged tweaks.
- **Developer unlock** for Premium. Stored as a SHA-256 hash rather than a
  plaintext string, and reported everywhere as a developer unlock — it is not
  a licence, is not transferable, and nothing was purchased.
- `run.py nettweaks`, `--on <id>`, `--on all`, `--off all`.

## 0.1.9 — 2026-09-06

### Added
- **Windows System Restore integration.** Phantom Tweeks already journals every
  change and reverts them individually, but that needs Phantom Tweeks to run.
  A restore point is the OS's own net: it can be rolled back from Windows
  Recovery even if the PC will not boot. Create one from History & Restore or
  `run.py restore-point --create`.
- Every failure mode gets a specific explanation rather than a generic error:
  System Protection disabled (common on OEM Windows 11), missing admin rights,
  or the 24-hour rate limit Windows enforces. A user who believes they have a
  restore point and does not is worse off than one who knows they do not.
- **Phantom Tweeks never enables System Protection itself** — it reserves disk
  space and changes system configuration, so it shows you the command instead.
- **Diagnostic report export** in HTML, Markdown, JSON, CSV or plain text.
  The HTML is fully self-contained, so it renders correctly when emailed or
  opened offline. `run.py report -o report.html`.
- **Usernames are stripped automatically** before anything is written. A
  screenshot of a report is the easiest way to leak your own name into a forum
  post.

### Fixed
- The username scrubber turned `C:\Users\user` into `C:\<user>s\<user>` when
  the account was literally named "user". It now matches on word boundaries.
- `export_reports` was advertised on the Premium page but never built. It is
  real now, and its link points at a page that exists.

## 0.1.8 — 2026-09-06

### Fixed
- **The uninstaller and updater were missing from the build.** The packaging
  files lived in a directory named `build/`, which the workspace snapshot
  system excludes by name - so `installer.iss`, the PyInstaller specs and the
  WiX source silently disappeared between sessions and were never in the
  archive you received. They now live in `packaging/`, which persists.
- Removed a duplicate uninstall shortcut that would have made Inno Setup
  refuse to compile.

### Added
- **Update.exe** — a standalone updater built as its own binary. It has to be
  separate: Windows locks a running executable, so an in-app updater cannot
  replace the app it is running inside. Same verified path as the in-app
  check: HTTPS only, SHA-256 verified, installer staged and never executed
  for you.
- **Uninstall shortcut** in the Start menu, so removing the app does not mean
  hunting through Add/Remove Programs.
- **Performance page** — one view of every measurable component: each CPU core,
  every GPU, memory speed, **every attached drive** (not just C:), network
  adapters with error counts, and the heaviest processes. Auto-refresh and a
  copy button for help threads.
- Per-drive SMART status, temperature and throughput. A drive reporting a
  non-healthy status is called out as hardware failure that no software
  setting will fix.
- `python run.py perf`, with `--watch` for continuous monitoring.

## 0.1.7 — 2026-09-06

### Added
- **Tweaks page** — every optimization with its own checkbox, risk level and
  info button. "Analyse my system" scores each one against your hardware and
  shows the reasoning inline; "Select recommended" ticks only what suits this
  PC, and deliberately never selects anything rated NOT RECOMMENDED, high
  risk, or irreversible.
- **Three top-level tabs** — Dashboard, Tweaks, Settings. 22 pages in one flat
  list was a wall of text; each tab now shows only its own pages.
- **Liquid-glass surfaces** — layered tones with a bright specular top edge.
  Tk has no backdrop blur, so this is built from flat layers rather than faked
  with stipple patterns, which looked muddy at these sizes.
- **One-click "Fix input latency" and "Fix network lag"** on the dashboard.
  Both analyse first, list only what applies, and still ask before changing
  anything. The network one states plainly that it will not reduce your ping.
- **Start-menu shortcuts** for Check for Updates, Self-Test and Restore
  Everything, installed alongside the app.

### Fixed
- **The "Download PresentMon" button did not exist.** The frame-time error
  message told users to press it. It is now there, next to "Open tools folder".
- **The Settings tab opened Premium**, because Premium came first in the nav
  order — it looked like a sales-page ambush. Each tab now has an explicit
  landing page.
- **Disabled buttons were unreadable** — the accent fill greyed out but the
  dark text stayed at full contrast, so "Apply selected" looked broken rather
  than disabled.

## 0.1.6 — 2026-09-06

### Fixed
- **The website had no styling at all.** `.vercelignore` contained a bare
  `assets/` line to exclude the desktop app's icon folder. Without a leading
  slash that pattern also matched `website/assets/`, so `style.css` was never
  deployed and the live site served raw unstyled HTML. All patterns are now
  anchored with `/`.
- **The MSI was stale at every release.** `build.ps1` hard-coded
  `$Version = "0.1.2"`, so a v0.1.4 release shipped an asset named
  `PhantomTweeks-0.1.2.msi` - an installer three versions out of date. The
  build now reads VERSION from `branding.py`, the single source of truth.
- **The nav Download button was nearly illegible** - `.nav-links a` overrode
  `.btn-primary`, rendering muted grey text on the teal background.

### Added
- **Critical CSS inlined into every page.** If the external stylesheet ever
  fails to load again, pages still render as a readable dark document instead
  of unstyled white HTML.
- Tests that catch all three regressions: an unanchored `assets/` pattern, a
  hard-coded version in `build.ps1`, and a missing inline fallback.

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
