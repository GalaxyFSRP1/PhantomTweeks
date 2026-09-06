# Phantom Tweeks — Security & Safety Model

This document describes the guarantees Phantom Tweeks makes, and — more importantly — how they
are *enforced in code* rather than promised in documentation.

---

## 1. Threat model

Phantom Tweeks is a privileged local utility. The realistic risks are not attackers; they are:

| Risk | Mitigation |
|---|---|
| Breaking a working PC while "optimizing" it | Backup-first writes, verified backups, one-click restore, conservative catalog |
| Killing a process the user needed (game, voice chat, anti-cheat) | Phantom Shield deny-list; no termination code path exists |
| Weakening system security for performance | Registry deny-list refuses Defender/Firewall/Update/mitigation writes at the API |
| Triggering an anti-cheat false positive | No injection, no hooking, no game-file access; documented Windows APIs only |
| Silently exfiltrating user data | No telemetry endpoint compiled in; all data local |
| Executing a tampered update | HTTPS-only, checksum + Authenticode verification, discard-on-failure |
| Users trusting fabricated numbers | Unmeasurable values return `None` and render as `n/a` |

---

## 2. Phantom Shield

`core/shield.py` is the single choke point for anything that could touch a process.

### Protected categories
Current game (and its whole process tree) · Game launchers (Steam, Epic, Xbox/Game Pass,
Battle.net, Riot, EA, Ubisoft, GOG, itch, Rockstar) · Anti-cheat (EAC, BattlEye, Vanguard,
FACEIT, ESEA) · Voice & capture (Discord, TeamSpeak, Mumble, OBS, Streamlabs, XSplit, Teams,
Zoom) · GPU & input software (NVIDIA, AMD, Intel, Logitech, Razer, Corsair, SteelSeries,
Wooting) · Essential Windows processes · User-defined additions.

### Enforcement properties

1. **Deny by default for anything protected.** `guard(name, action)` returns a refusal with a
   human-readable reason for *every* action verb — terminate, suspend, set_priority,
   set_affinity, inject, modify_files, stop_service.
2. **Fails closed on unknown identity.** `guard(None, ...)` and `guard("", ...)` are refused.
   A process that cannot be identified is never actioned.
3. **Case-insensitive with wildcard support**, so `STEAM.EXE` and `mhyprot3.exe` both match.
4. **No termination code path exists.** `engine/background.py::request_close()` always returns
   `False`. There is no function in the codebase that kills a process — the capability is
   absent, not merely gated.
5. **Expert Mode grants no destructive power.** It exposes more *information* only.
   `app.expert_dump()` reports `"shield_bypass_possible": False`.
6. **Protected services** (Defender, firewall, audio, gaming services, anti-cheat, GPU driver
   services, networking core) cannot be stopped or disabled.

Verified by `tests/test_shield.py` — every protected process against every dangerous action.

---

## 3. Registry deny-list

`engine/winsettings.py::_check_allowed()` raises `ForbiddenSetting` before any write to:

* `SOFTWARE\Microsoft\Windows Defender` and its policy keys
* `SYSTEM\CurrentControlSet\Services\WinDefend` / `MpsSvc` (firewall) / `wuauserv`
* `SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate`
* `...\Memory Management\FeatureSettings` (Spectre/Meltdown mitigations)
* `SYSTEM\CurrentControlSet\Services\EasyAntiCheat` / `BEService` / `vgc`

This is enforced in the *write primitive itself*, so no future feature, profile, snapshot or
Expert Mode path can route around it.

---

## 4. Backup and restore

Every mutating primitive returns a `ChangeRecord` capturing `kind`, `target`, `name`,
`previous`, `applied` and `value_type` **before** writing.

* **`ABSENT` sentinel** — when a value did not exist, restore *deletes* the key Phantom Tweeks
  created rather than inventing a "default".
* **Pre-flight verification** — `BackupVault.verify()` rejects empty backups, missing files and
  records without a prior value. Required before advanced changes.
* **Atomic writes** — config, backups and history are written to `.tmp` and renamed.
* **Partial-failure rollback** — if any optimization in a run raises, every change already made
  in that run is reverted immediately. A partial state is never left behind.
* **Scoped restore** — restore replays only recorded `ChangeRecord`s. Unrelated user changes are
  structurally impossible to touch.
* **Unknown change kinds are refused**, not guessed.

---

## 5. Automatic optimization eligibility

Auto-apply is off by default. When explicitly enabled, an item must satisfy **all** of:

```
evaluation.applicable
  AND confidence == HIGH
  AND category in (SAFE, RECOMMENDED)
  AND reversible
  AND NOT advanced
  AND apply is not None
  AND (not requires_admin OR is_admin())
```

Verified by `tests/test_safety.py`: irreversible, advanced, and medium/low-confidence items are
provably never auto-applicable.

---

## 6. Honest measurement

Fabricating data is treated as a safety defect, because users make hardware purchases based on
these numbers.

* Every telemetry field is `Optional`; unavailable readings are `None` → rendered `n/a`.
* CPU temperature returns `None` when no sensor is readable rather than installing a kernel
  driver or estimating.
* `AdapterRAM` above 2³¹ is discarded as unreliable rather than reported.
* Frame-time analysis **requires a real capture source** (PresentMon or an imported CSV) and
  refuses to estimate FPS from hardware specifications.
* Bottleneck detection returns `UNKNOWN` when GPU utilisation is unmeasurable instead of
  guessing from CPU data alone.
* Comparison deltas under 2% are labelled measurement noise.
* "No measurable improvement was detected" is an explicit, expected output.

---

## 7. Update integrity

`core/updates.py`:

1. Non-HTTPS manifest or payload URLs are **refused outright**.
2. TLS certificate validation is on (`ssl.create_default_context()`).
3. Downloads stage to `.part`; SHA-256 is verified against the manifest.
4. Authenticode signature must report `Valid` — unsigned or tampered packages are deleted.
5. Only on passing both checks is the file renamed into place. **Nothing is ever executed by
   the updater.**
6. Any failure is non-fatal and logged; the application continues on the current version.

---

## 8. Privilege handling

* The application does **not** request blanket elevation (`uac_admin=False` in the spec).
* Most functionality — all monitoring, diagnostics, benchmarking, network testing — works as a
  standard user.
* Items requiring HKLM writes are individually marked `requires_admin` and are skipped with a
  clear explanation rather than failing obscurely.

---

## 9. Privacy as a security property

* No analytics endpoint is compiled into the build.
* `telemetry`, `share_hardware_info` and `share_game_info` all default to `False`, asserted by
  test.
* Crash reports are local-only and contain no personal files or credentials.
* No API keys or licence secrets are embedded in the client. Premium licence validation is
  designed as a server-side responsibility precisely because a self-validating client is
  trivially patchable — and shipping one would be security theatre.

---

## 10. Reporting a vulnerability

Report security issues privately through the Support page rather than in a public tracker.
Please include reproduction steps and the relevant portion of
`%LOCALAPPDATA%\PhantomTweeks\logs\phantomtweeks.log`.
