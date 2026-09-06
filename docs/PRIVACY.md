# Phantom Tweeks — Privacy Policy

**Last updated:** 5 September 2026 · **Applies to:** Phantom Tweeks 0.1.5

## Summary

Phantom Tweeks collects **nothing**, transmits **nothing**, and sells **nothing**.
It runs entirely on your computer. There is no analytics endpoint compiled into the
application, no account requirement, and no background network activity other than the
diagnostic tests you explicitly run and the optional update check.

## What we collect

Nothing. There is no user account, no device fingerprint sent anywhere, and no hidden
analytics.

## What stays on your device

Stored locally in `%LOCALAPPDATA%\PhantomTweeks` (or beside the executable in the portable
build):

* **Hardware information** — CPU, GPU, memory, storage, driver details (for recommendations)
* **Game information** — installed and running games detected from launcher manifests
* **Performance data** — benchmark captures, frame-time statistics, session samples
* **Network results** — latency, jitter and packet-loss history from tests you run
* **Configuration and backups** — your settings and the prior value of every change made
* **Logs and crash reports** — application activity and stack traces

Deleting that folder removes every trace of your data.

## Network activity

Exactly two circumstances:

1. **Diagnostic tests you start.** ICMP echo requests to your gateway, public addresses such as
   1.1.1.1, and DNS resolvers you selected. These are ping packets and carry no personal data.
2. **Update checks.** If enabled, an HTTPS request for a version manifest. Disable in
   Settings → Updates.

## Crash reports

Written locally to `logs\crash\`. Contains the stack trace, application version and basic
system information (OS build, architecture). Contains no personal files, no credentials, no
game data. **Never uploaded automatically** — sharing is a deliberate action you take.

## Optional sharing settings

`telemetry`, `share_hardware_info` and `share_game_info` exist in Settings → Privacy. All three
default to **off**, and there is currently no endpoint for them to send data to. They exist so
that if such a feature is ever added, it is opt-in by construction rather than opt-out by
apology.

## Third parties

No analytics, advertising or tracking SDKs are bundled. No social platform integration.
Optional frame-time capture uses Intel PresentMon only if you install it yourself — a local
process, not a service.

## Children

A system utility not directed at children, collecting no information from anyone.

## Future changes

Any future data collection will be opt-in, disclosed here before release, and clearly presented
in the application. Silent introduction of telemetry would contradict the reason this product
exists.

## Your rights

Because no data is collected, there is nothing to request, correct or delete on our side. Your
data is on your disk, in a plain folder you can inspect and remove at any time.
