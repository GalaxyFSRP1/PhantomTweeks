# Phantom Tweeks — Architecture

## Design principles

1. **One facade, two frontends.** `app.PhantomApp` is the only entry point for both GUI and
   CLI, so they cannot drift into different safety behaviour.
2. **Safety at the primitive, not the UI.** Deny-lists live inside the write functions. No
   feature added later can route around them by not asking.
3. **Honest by construction.** Every measurement is `Optional`. There is no code path that
   substitutes a plausible value for a missing one.
4. **Reversible by construction.** Mutating primitives *return* a `ChangeRecord`. Applying a
   change without producing a rollback record is not expressible in the API.
5. **Graceful platform degradation.** Off Windows the app runs analysis-only; every mutating
   call raises `UnsupportedPlatform` rather than guessing.

## Layers

```
                      ┌──────────────┐   ┌──────────────┐
                      │  gui/        │   │  cli/main.py │
                      │  app_window  │   │              │
                      └──────┬───────┘   └──────┬───────┘
                             └────────┬─────────┘
                              ┌───────▼────────┐
                              │  app.PhantomApp │  facade
                              └───────┬────────┘
        ┌───────────────┬─────────────┼─────────────┬───────────────┐
   ┌────▼────┐    ┌─────▼─────┐  ┌────▼─────┐  ┌────▼────┐   ┌──────▼──────┐
   │ engine/ │    │ hardware/ │  │ network/ │  │  core/  │   │ engine/     │
   │optimizer│    │  monitor  │  │   lab    │  │ shield  │   │ gaming_mode │
   └────┬────┘    └───────────┘  └──────────┘  └─────────┘   └─────────────┘
        │
   ┌────▼─────────────────────────────────────┐
   │ catalog → evaluate() → Evaluation        │
   │ catalog → apply()    → [ChangeRecord]    │
   │ winsettings (deny-list enforced here)    │
   │ backup.BackupVault (journal + restore)   │
   └──────────────────────────────────────────┘
```

## Key modules

| Module | Responsibility |
|---|---|
| `core/shield.py` | Phantom Shield deny-list; the single `guard()` choke point |
| `core/config.py` | Settings with safe defaults; corrupt config never blocks startup |
| `core/games.py` | Read-only launcher manifest parsing and running-game identification |
| `core/premium.py` | Inert licensing seam; `PREMIUM_AVAILABLE = False` |
| `core/updates.py` | HTTPS + checksum + Authenticode verification, discard on failure |
| `core/platform_info.py` | Windows gating; `require_windows()` for mutating ops |
| `engine/catalog.py` | Optimization definitions: purpose, risk, evaluator, applier |
| `engine/optimizer.py` | The SCAN→APPROVE→APPLY pipeline and restore orchestration |
| `engine/winsettings.py` | The only code allowed to mutate; registry deny-list lives here |
| `engine/backup.py` | `ChangeRecord` journal, `ABSENT` sentinel, verification |
| `engine/frametime.py` | Real frame capture/import; 1% and 0.1% lows; pacing score |
| `engine/comparison.py` | Before/after deltas, noise threshold, regression detection |
| `engine/score.py` | Eight transparent sub-scores, each with its formula |
| `engine/bottleneck.py` | Windowed sampling → GPU/CPU/memory/network verdict |
| `hardware/monitor.py` | Telemetry; `None` for anything unmeasurable |
| `network/lab.py` | Gateway/internet isolation, jitter, loss, DNS, history |

## The optimization contract

Each `Optimization` carries:

* `purpose` / `expected_effect` / `risk` / `supported` / `reversible` — the info card
* `evaluate(ctx) -> Evaluation` — inspects the *live system*, may return
  `applicable=False, confidence=NOT_RECOMMENDED` ("No change recommended") which is a
  first-class success
* `apply(ctx) -> list[ChangeRecord]` — optional; advisory items have `apply=None`

Adding an optimization without a justification, a real evaluator, or a rollback record fails
the test suite.

## Concurrency

* The GUI never blocks: work runs on daemon threads and results return through a
  `queue.Queue` drained on the Tk main loop.
* A failing worker thread posts its exception rather than killing the UI.
* Gaming Mode polls on its own daemon thread with a `threading.Event` stop signal.

## Data locations

```
%LOCALAPPDATA%\PhantomTweeks\
├── config.json          settings
├── backups\             one JSON per optimization run
├── snapshots\           named configuration snapshots
├── profiles\            user game profiles
├── benchmarks\          frame-time captures and results
├── history\             optimization + network history
├── logs\                rotating log, crash\ subfolder
└── tools\               user-supplied PresentMon.exe (optional)
```

Portable builds set `PHANTOM_TWEEKS_HOME` beside the executable.

## Extension points

* **New optimization** — add an `Optimization` to `catalog.CATALOG` with an evaluator and an
  applier built from `winsettings` primitives. Backup and restore come free.
* **New setting kind** — add a primitive to `winsettings` returning a `ChangeRecord`, and a
  branch in `winsettings.revert()`.
* **Premium** — implement `core.premium.LicenseValidator` server-side and flip
  `PREMIUM_AVAILABLE`.

## Added modules

| Module | Responsibility |
| --- | --- |
| `core/gamewatch.py` | Background polling for game start/stop, with debouncing |
| `core/features.py` | Feature catalog and Premium gating |
| `engine/maintenance.py` | Maintenance checks, cleanup and scheduling |
| `engine/history.py` | Local performance history and trend analysis |

### Why the game watcher debounces

Launchers spawn short-lived helper processes during startup. A naive detector
flips between "game running" and "no game" several times before settling, which
would spam notifications and could trigger a profile apply/revert loop. The
watcher therefore requires N consecutive sightings of the *same PID* before
declaring a start (`confirm_polls`, default 2).

Callbacks fire on the watcher thread. GUI code must marshal back to the Tk main
loop with `after(0, ...)`; touching widgets from the watcher thread is a
crash waiting to happen.

### Why the trend noise floor is generous

`history._noise_floor()` returns two standard deviations of the observed
samples, clamped to 3-15%. Anything smaller than that is reported as no real
change. This deliberately under-claims: missing a small real improvement is a
far better failure than inventing one, and inventing one is precisely what
makes optimizer software untrustworthy.

### Feature gating fails open

`features.check()` allows unknown feature ids. A typo in a feature name must
never silently disable something that should work. Only an explicit `premium`
entry in the catalog can lock a feature, and `FREE_FOREVER` names the safety
features that a test forbids from ever becoming Premium.
