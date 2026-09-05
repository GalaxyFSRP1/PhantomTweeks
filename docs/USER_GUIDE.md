# Phantom Tweeks — User Guide

## Starting the application

**From a built release:** run `PhantomTweeks.exe`, or launch it from the Start menu.

**From source:** from inside the `phantom-tweeks` folder run

```
python run.py            GUI
python run.py scan       a CLI command
python run.py --help     all commands
```

On Windows, double-clicking `PhantomTweeks.bat` does the same thing.

> `python -m phantom_tweeks` only works after `pip install -e .`, because the project uses a
> `src/` layout. `run.py` works without installing anything.

## First run

Phantom Tweeks opens on the **Dashboard** with live telemetry already sampling. Nothing has been
changed on your system, and nothing will be until you approve it.

A good first session:

1. **Dashboard → Calculate Score** — a baseline, with every sub-score explaining its formula.
2. **Phantom Scan → Run Phantom Scan** — see what actually applies to your hardware.
3. **Network Lab → Run Tests** — establish whether your connection is the real problem.
4. **System Health** — check for warnings, each of which states its reason.

Read the recommendations before applying anything. Several will likely say *"No change
recommended"* — that means your system is already configured correctly for that item.

---

## Understanding recommendations

Every recommendation carries a **confidence rating**:

| Rating | Meaning |
|---|---|
| **HIGH CONFIDENCE** | Likely beneficial for this configuration |
| **MEDIUM CONFIDENCE** | May help depending on workload |
| **LOW CONFIDENCE** | Limited evidence |
| **NOT RECOMMENDED** | No meaningful benefit expected |

…and a **category**: Safe, Recommended, Optional, Advanced, or Not recommended.

Click the **ⓘ** button on any item to see its purpose, expected effect, risk level, supported
Windows versions and whether it is reversible.

### Applying changes

Tick the items you want, then **Review & Apply Selected**. Phantom Tweeks will:

1. Show you exactly what will change
2. Create and verify a backup
3. Apply only the approved items
4. Report what succeeded, what was skipped and why

Advanced items require a **two-step confirmation** and include recovery instructions.

If anything fails mid-run, every change from that run is reverted immediately. A partial state
is never left behind.

---

## Phantom Shield

The Shield page lists every protected process currently running. Protected applications are
never killed, suspended, reprioritised, re-affinitised or injected into — by any mode,
including Expert Mode.

**Manage Protected Apps** lets you add your own executables (wildcards supported). Built-in
protections cannot be removed.

---

## Gaming Mode

Enable it from the Dashboard. When a game launches, Phantom Tweeks:

* Extends Shield across the game's entire process tree
* Detects the launcher and anti-cheat
* Selects a matching profile
* Records session performance and monitors network stability

It does **not** close Discord, Steam, Epic or your game, and it does not terminate background
applications. If automatic optimization is enabled *and* the profile allows it, only
high-confidence low-risk reversible items are applied — with a backup.

**Streaming Mode** and **Creator Mode** protect encoder and capture headroom instead of chasing
maximum game FPS.

---

## Frame-Time Analyzer

Average FPS hides stutter. This page shows what you actually feel:

* **Average / 1% low / 0.1% low** frame times
* **Frame pacing score** from consecutive-frame variance
* **Stutter count** — frames taking more than double the average
* A frame-time graph over the capture

### Getting frame data

Phantom Tweeks will not simulate FPS. You need a real source:

* **PresentMon** (Intel, free) — place `PresentMon.exe` on PATH or in
  `%LOCALAPPDATA%\PhantomTweeks\tools\`, then use **Capture 30s**
* **Import CSV** — any PresentMon or CapFrameX capture you already have

### Comparing before and after

**Compare Two Captures** produces the performance report: FPS, 1% lows, frame time, pacing and
network deltas. Changes under 2% are labelled measurement noise.

If a meaningful regression is detected, Phantom Tweeks says so and offers to restore the
previous configuration immediately.

---

## Network Lab

Tests your **gateway** and the **internet** separately, which is what makes the results useful:

* Loss/jitter to your own router → Wi-Fi interference, bad cable, or the router
* Clean local hop, dirty internet hop → ISP or upstream routing

Also included: DNS benchmark, route diagnostics, sustained stability testing, and locally
stored ping history graphed by day.

> DNS response time is **not** game-server ping. A faster resolver speeds up name lookups, not
> gameplay. Phantom Tweeks does not promise ping reduction.

---

## Restoring changes

Three levels, all on the **History & Restore** page:

| Action | Scope |
|---|---|
| **Restore Selected** | One optimization run |
| **RESTORE EVERYTHING** | Every change Phantom Tweeks ever made |
| CLI `restore --all --yes` | Same, works from Safe Mode |

Restore only reverts changes Phantom Tweeks recorded. Settings you changed yourself are never
touched. Some changes (notably GPU scheduling) need a reboot to fully revert.

### Snapshots

Save named configurations — Competitive Gaming, Streaming, Everyday, Maximum Performance,
Default Windows. A snapshot can only contain settings Phantom Tweeks manages.

---

## Other pages

* **Background Analyzer** — ranks resource consumers and tells you if closing something would
  help. It will never close it for you.
* **Startup Manager** — impact, publisher, path, status. Critical Windows components and
  protected apps cannot be disabled. All changes reversible.
* **Driver Center** — versions, dates, staleness, and official vendor links. Installs nothing.
* **Storage Lab** — drive type, health, free space, safe cleanup candidates. Never touches
  personal files.
* **System Health** — CPU, GPU, RAM, Storage, Network, Drivers, Windows, with explanations.

---

## Settings

Notable options (all safe defaults):

| Setting | Default | Effect |
|---|---|---|
| Automatic optimization | **Off** | Applies high-confidence safe items without asking each time |
| Expert Mode | **Off** | Shows registry values, power config, process telemetry. Does **not** bypass Shield |
| Telemetry | **Off** | No endpoint exists in this build |
| Check for updates | On | HTTPS, checksum and signature verified |

---

## Command line

```
PhantomTweeks.exe scan                  recommendations
PhantomTweeks.exe scan --network        include network tests
PhantomTweeks.exe optimize --auto       high-confidence items only
PhantomTweeks.exe optimize -y           apply all applicable, no prompt
PhantomTweeks.exe benchmark --csv f.csv analyze an existing capture
PhantomTweeks.exe compare a.csv b.csv   before/after report
PhantomTweeks.exe restore --all --yes   restore everything
PhantomTweeks.exe health                system health
PhantomTweeks.exe config --set expert_mode=true --yes
```

Run `PhantomTweeks.exe --help` for the full list.

---

## Troubleshooting

**Something broke after an optimization** → RESTORE EVERYTHING, or from Safe Mode:
`PhantomTweeks.exe restore --all --yes`

**GPU temperature shows n/a** → live GPU telemetry needs vendor tooling (nvidia-smi ships with
the NVIDIA driver). Phantom Tweeks shows `n/a` rather than an estimate.

**An item requires administrator rights** → right-click Phantom Tweeks → Run as administrator.
Everything else works as a standard user.

**Network tests show 100% loss** → your firewall or network blocks ICMP. Common on corporate
networks and some VPNs.

**The app crashed** → a local crash log is in `%LOCALAPPDATA%\PhantomTweeks\logs\crash\`.
Nothing was uploaded.

---

## Navigating: scrolling and selecting

**Scrolling.** Every long page scrolls. Use the mouse wheel over any panel,
drag the scrollbar on the right, or use the keyboard: **Page Up / Page Down**
to move a screen at a time and **Home / End** to jump to the top or bottom.
The scrollbar hides itself automatically when a page already fits on screen,
so if you don't see one, there is nothing below the fold.

**Selecting recommendations.** After a scan, each recommendation is a card.
**Click anywhere on the card** to select or deselect it — the whole row is the
target, not just the little checkbox. The cursor turns into a hand over
anything clickable. A selected card is outlined in the accent colour.

Above the list there are three shortcuts:

| Chip | What it does |
| --- | --- |
| Select all | Ticks every listed recommendation |
| Select none | Clears the list |
| Recommended only | Ticks only HIGH and MEDIUM confidence items |

The counter beside them always reads **"N of M selected"**, so you know exactly
how much you are about to change before you press Apply. Items marked
**NOT RECOMMENDED** are never included by "Recommended only" and must be
ticked deliberately, one at a time.

## Keyboard shortcuts

| Key | Action |
| --- | --- |
| `Ctrl+S` | Run a system scan |
| `Ctrl+N` | Open Network Lab |
| `Ctrl+R` / `F5` | Refresh the current page |
| `Ctrl+E` | Export a diagnostic report |
| `Ctrl+1`…`Ctrl+9` | Jump to the Nth page in the sidebar |
| `F1` | Show this shortcut list |
| `Ctrl+Q` | Quit |

## Input Latency

The Input Latency page looks for the causes of "the game feels sluggish" that
can actually be measured:

- a high-refresh monitor that Windows is currently driving at 60 Hz
- a frame rate far below your refresh rate
- GPU or CPU saturation during play
- mouse acceleration ("Enhance pointer precision") altering your aim

It reports what it can measure and says so plainly when it cannot measure
something. It will not claim to have removed milliseconds it never observed.

## Export Report

**Ctrl+E**, or the Export Report button, writes a plain-text diagnostic report
covering your hardware, current settings, scan findings and recent changes.
The file is written **only to the folder you choose**. Nothing is uploaded, and
the report contains no passwords or key material. It is meant for your own
records or for pasting into a support thread when *you* decide to.

## Command line

In addition to the GUI, `python run.py <command>` offers:

| Command | Purpose |
| --- | --- |
| `latency [--csv FILE]` | Input-latency analysis, optionally against a frame-time CSV |
| `export [-o FILE] [--csv FILE]` | Write the diagnostic report to a file |
| `watch [--interval N]` | Live CPU/GPU/RAM telemetry as bar graphs in the terminal |

Run `python run.py --help` for the full list of commands.

## Optimization presets

Picking through a dozen individual tweaks is a chore, so the scan page has a
**Preset** dropdown. A preset is a *filter over what your scan actually found* —
never a fixed list of changes forced onto the machine. If the scan says
something is already correct or does not apply to your hardware, no preset can
resurrect it.

| Preset | What it selects |
| --- | --- |
| **Safe** (default) | High-confidence, low-risk, reversible changes only |
| **Balanced** | Safe, plus medium-confidence items with small, explained tradeoffs |
| **Competitive** | Input, scheduling and frame pacing; ignores storage housekeeping |
| **Quiet / Laptop** | Never switches your power plan, so battery and fan noise are untouched |
| **Housekeeping** | Storage only; cannot affect how games run |

Three guarantees hold for every preset, and are enforced by the test suite:

1. A preset will **never** tick a NOT RECOMMENDED or LOW confidence item.
2. A preset will **never** tick an advisory-only entry (one with no automatic
   applier), because "applying" it would be a lie.
3. A preset will **never** tick something already optimal or inapplicable.

If a preset selects **nothing**, that is a good result, not a failure — it means
everything in its remit is already set correctly. Selecting a preset only ticks
boxes; nothing is applied until you press **Review & Apply Selected**, and you
still get the confirmation and backup step.

From the terminal: `python run.py presets` lists them, and
`python run.py presets competitive` previews exactly what that preset would
select on this machine without changing anything.

## When a restore only partly succeeds

Restore is the one feature that has to work when everything else has gone
wrong, so it is deliberately cautious.

Changes are undone **newest first**, and each one is recorded as it completes.
If a change cannot be reverted — most often because it needs administrator
rights — Phantom Tweeks does **not** abandon the rest. It carries on, then
tells you exactly how many changes came back:

```
✓ Restored HKCU\...\GameDVR_Enabled
✗ Access denied: HKLM\...\GraphicsDrivers\HwSchMode
✓ Restored power plan

2 of 3 changes were reverted. The rest are still recorded and can be
retried — nothing was lost.
```

That entry then shows in History as **"Partially restored (2/3)"** rather than
pretending to be either finished or untouched. Restoring it again retries
**only the changes that are still outstanding**; the ones already undone are
skipped, so a retry can never double-apply anything. Restoring an entry that is
already complete is a harmless no-op.

Progress is written to disk after every individual change, so even if the
machine loses power midway through a restore, nothing is lost — reopen Phantom
Tweeks and restore that entry again to pick up where it stopped.

If you see a permissions failure, close Phantom Tweeks, right-click it and
choose **Run as administrator**, then restore again.

## The Phantom power plan

The **Power Plan** page creates a Windows power plan called
*"Phantom Tweeks — Gaming"*. It is a **copy of Balanced** with eight deliberate
changes; your existing plans are never edited, and removing it returns Windows
to Balanced.

What it changes, and why:

| Setting | Plugged in | On battery | Why |
| --- | --- | --- | --- |
| Minimum processor state | 20% | 5% | Balanced idles at 5%, so the CPU must ramp from near-idle when a frame suddenly needs work — a common stutter cause |
| Maximum processor state | 100% | 100% | Unchanged. We never cap your CPU |
| Core parking | all cores | 50% | Removes the delay while Windows wakes a parked core mid-frame |
| Boost mode | Aggressive | Enabled | Lets the CPU's own turbo engage promptly. Not an overclock |
| Turn off hard disk | never | 10 min | A disk waking mid-level causes a visible hitch |
| Hibernate after | never | 90 min | A long shader compile or download is never interrupted |
| PCIe link power management | off | max saving | ASPM can add latency to GPU and NVMe transfers |
| USB selective suspend | off | on | The usual cause of a mouse or controller responding late after idling |

**What it deliberately does NOT do.** It does not set minimum processor state to
100%. That is the most common "gaming power plan" mistake: it burns power and
adds fan noise without adding frames, and on a laptop it actively *reduces*
sustained performance by hitting thermal limits sooner. It also performs no
overclocking, undervolting, core disabling or voltage changes.

Laptops are detected automatically and the battery-side values stay
conservative, so your runtime is not sacrificed.

From the terminal:

```
python run.py power              # show status and the full explanation
python run.py power --create     # create and activate it
python run.py power --remove     # delete it, back to Balanced
```

## Premium licensing

Premium is unlocked with a license key on the **Premium** page.

- Keys are **cryptographically signed** (Ed25519). Editing a key by even one
  character makes it stop validating.
- Verification happens **on your PC**, so Premium works offline. If the
  licensing server is unreachable your key keeps working — you will never be
  locked out by an outage on our side.
- Phantom Tweeks contains **no payment processing** and will never ask for card
  details inside the app.
- If you gave an email at purchase, the key stores only a one-way hash of it.

```
python run.py license                       # show current status
python run.py license --activate PT-XXXX-…  # activate a key
python run.py license --remove              # remove it from this device
```

Removing a license only removes it from *this* device; the key stays valid and
can be entered again later or on another machine.

---

## Maintenance Mode

Routine housekeeping that keeps a gaming PC healthy. Open **Maintenance** in
the sidebar, or run `python run.py maintenance`.

**It never runs while you are playing.** If a game is detected, maintenance is
postponed and tells you so. Competing for CPU and disk mid-match is exactly the
kind of "help" that causes a stutter and loses you a round.

Seven checks run, each explaining why it matters:

| Check | What it looks at |
| --- | --- |
| Free disk space | Below ~10% free, Windows loses paging headroom and shader compilation stutters |
| Temporary files | Space only. Temp files do not slow a modern PC down |
| GPU shader caches | A corrupt cache causes stutter and artifacts |
| Pending restart | Half-applied updates cause odd, hard-to-reproduce problems |
| Drive type and health | Warns on unhealthy drives; never defragments an SSD |
| Backup coverage | Confirms your rollback points still exist |
| Log size | Local only, never uploaded |

Checks are **read-only**. Cleanup is a separate button that asks first, and
only ever removes regenerable caches. Documents, Downloads, Pictures, game
saves and the Recycle Bin are never touched, and files in use are skipped.

Set a **weekly** or **monthly** schedule if you want it to remind you. From the
CLI:

```powershell
python run.py maintenance --schedule weekly
python run.py maintenance --clean          # dry run, shows what it would free
python run.py maintenance --clean --yes    # actually clean
```

---

## Live game detection

Phantom Tweeks watches for games continuously. It notices a game that starts
**after** the app is already open, and a game that was **already running** when
you opened it. The sidebar shows the current game, and the app tells you when
anti-cheat is present so you know it is being left alone.

Detection is **observation only**. Phantom Tweeks never reprioritises,
suspends, kills or injects into a game process. A test enforces this.

```powershell
python run.py watch-game
```

If you have Premium and enable **"Apply my saved profile automatically when a
game starts"** in Settings, your saved profile is applied on launch. That
setting is **off by default** - nothing significant changes without you asking.

---

## Performance Trends

Every benchmark is recorded locally so you can answer the question that
normally goes unanswered: *did that driver update actually cost me frames?*

```powershell
python run.py trends
python run.py trends --metric avg_fps
python run.py trends --clear
```

**Trends will not flatter you.** A change smaller than the measured
run-to-run variation is reported as "within normal variation - no real change"
rather than presented as an improvement. Claiming a 2% win that is really noise
is the kind of dishonesty this project exists to avoid.

History is plain JSON in your data folder. Nothing is uploaded, ever.

---

## If something goes wrong

Open **Help & Diagnostics** in the sidebar and press **Run self-test**, or run:

```powershell
python run.py doctor
```

It checks every subsystem and states plainly whether a failure is a bug in
Phantom Tweeks or a limitation of your system. **Copy result** puts the report
on your clipboard; it contains no personal information and is safe to paste
into a bug report.

### "attempted relative import with no known parent package"

An early packaged build shipped with a broken entry point and failed with this
on launch. It is fixed. If you see it, you have an old build - download the
current release.

### Console windows flashing on screen

Also fixed. Phantom Tweeks runs external tools (`powercfg`, `ping`, WMI
queries) to read your system state, and in an early build each one briefly
opened a black console window. Every external command now runs hidden, so
nothing flashes and nothing steals focus from a fullscreen game.
