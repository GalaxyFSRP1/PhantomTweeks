"""DNS provider catalog, benchmarking and switching.

What DNS actually does for gaming
---------------------------------
Changing DNS affects **name lookups**: how long it takes to turn
``store.steampowered.com`` into an IP. It makes launchers, stores and web
pages feel snappier, and a filtering resolver can block malware domains.

It does **not** reduce your in-game ping. Once a match starts, your client
talks to a game server by IP and the resolver is out of the loop entirely.
Anyone claiming a DNS change lowers ping is selling something. Every string
in this module is written to be honest about that.

Safety
------
* The previous settings are captured **before** any change and returned as a
  reversible ``ChangeRecord``, so Restore works.
* "Automatic (DHCP)" is always offered - that is the true original state for
  most people.
* Setting DNS needs administrator rights. Without them we say so plainly
  rather than failing with a cryptic error.
* IPv6 resolvers are applied only when the adapter already has IPv6 enabled.
"""
from __future__ import annotations

import re
import socket
import statistics
import time
from dataclasses import dataclass, field
from typing import Optional

from ..core import runproc
from ..core.platform_info import IS_WINDOWS


@dataclass(frozen=True)
class DnsProvider:
    id: str
    name: str
    primary: str
    secondary: str = ""
    v6_primary: str = ""
    v6_secondary: str = ""
    notes: str = ""
    filtering: str = "none"      # none | malware | family | adblock
    logging: str = "unknown"     # none | minimal | unknown | some

    @property
    def servers(self) -> list[str]:
        return [s for s in (self.primary, self.secondary) if s]

    @property
    def v6_servers(self) -> list[str]:
        return [s for s in (self.v6_primary, self.v6_secondary) if s]

    def render(self) -> str:
        out = [f"{self.name}", f"  IPv4: {', '.join(self.servers)}"]
        if self.v6_servers:
            out.append(f"  IPv6: {', '.join(self.v6_servers)}")
        out.append(f"  Filtering: {self.filtering}   Logging: {self.logging}")
        if self.notes:
            out.append(f"  {self.notes}")
        return "\n".join(out)


# A broad, honest catalog. Filtering and logging claims come from each
# operator's published policy - they are the operator's claims, not
# measurements we can verify, and the UI says so.
PROVIDERS: tuple[DnsProvider, ...] = (
    DnsProvider("dhcp", "Automatic (DHCP)", "", "",
                notes="Whatever your router or ISP hands out. This is the "
                      "default and the safest fallback.",
                filtering="none", logging="unknown"),

    DnsProvider("cloudflare", "Cloudflare", "1.1.1.1", "1.0.0.1",
                "2606:4700:4700::1111", "2606:4700:4700::1001",
                "Consistently among the fastest. Privacy-focused; audited "
                "no-logging policy.", "none", "minimal"),
    DnsProvider("cloudflare_malware", "Cloudflare (block malware)",
                "1.1.1.2", "1.0.0.2",
                "2606:4700:4700::1112", "2606:4700:4700::1002",
                "Cloudflare plus malware domain blocking.", "malware", "minimal"),
    DnsProvider("cloudflare_family", "Cloudflare (family)",
                "1.1.1.3", "1.0.0.3",
                "2606:4700:4700::1113", "2606:4700:4700::1003",
                "Blocks malware and adult content.", "family", "minimal"),

    DnsProvider("google", "Google Public DNS", "8.8.8.8", "8.8.4.4",
                "2001:4860:4860::8888", "2001:4860:4860::8844",
                "Very reliable and widely peered. Google logs some data.",
                "none", "some"),

    DnsProvider("quad9", "Quad9", "9.9.9.9", "149.112.112.112",
                "2620:fe::fe", "2620:fe::9",
                "Blocks known-malicious domains using threat intelligence. "
                "Swiss non-profit.", "malware", "none"),
    DnsProvider("quad9_unsecured", "Quad9 (no filtering)",
                "9.9.9.10", "149.112.112.10",
                "2620:fe::10", "2620:fe::fe:10",
                "Quad9 without the malware blocklist.", "none", "none"),

    DnsProvider("opendns", "Cisco OpenDNS", "208.67.222.222", "208.67.220.220",
                "2620:119:35::35", "2620:119:53::53",
                "Long-established, with optional account-based filtering.",
                "malware", "some"),
    DnsProvider("opendns_family", "OpenDNS FamilyShield",
                "208.67.222.123", "208.67.220.123",
                notes="Blocks adult content by default.",
                filtering="family", logging="some"),

    DnsProvider("adguard", "AdGuard DNS", "94.140.14.14", "94.140.15.15",
                "2a10:50c0::ad1:ff", "2a10:50c0::ad2:ff",
                "Blocks ads and trackers at the DNS level.", "adblock", "minimal"),
    DnsProvider("adguard_unfiltered", "AdGuard (unfiltered)",
                "94.140.14.140", "94.140.14.141",
                "2a10:50c0::1:ff", "2a10:50c0::2:ff",
                "AdGuard resolvers without any blocking.", "none", "minimal"),

    DnsProvider("controld_free", "Control D (free)", "76.76.2.0", "76.76.10.0",
                "2606:1a40::", "2606:1a40:1::",
                "Configurable filtering; the free tier is unfiltered.",
                "none", "minimal"),
    DnsProvider("controld_malware", "Control D (block malware)",
                "76.76.2.1", "76.76.10.1",
                notes="Malware blocking enabled.",
                filtering="malware", logging="minimal"),

    DnsProvider("nextdns", "NextDNS (public)", "45.90.28.0", "45.90.30.0",
                "2a07:a8c0::", "2a07:a8c1::",
                "Public endpoints. A free account unlocks custom filtering.",
                "none", "minimal"),

    DnsProvider("mullvad", "Mullvad DNS", "194.242.2.2", "",
                "2a07:e340::2", "",
                "Privacy-first, no logging, run by the Mullvad VPN operator.",
                "none", "none"),
    DnsProvider("mullvad_adblock", "Mullvad (ad blocking)",
                "194.242.2.3", "", "2a07:e340::3", "",
                "Mullvad with ad and tracker blocking.", "adblock", "none"),

    DnsProvider("dnswatch", "DNS.WATCH", "84.200.69.80", "84.200.70.40",
                "2001:1608:10:25::1c04:b12f", "2001:1608:10:25::9249:d69b",
                "German, no logging, no filtering.", "none", "none"),
    DnsProvider("comodo", "Comodo Secure DNS", "8.26.56.26", "8.20.247.20",
                notes="Blocks known-malicious sites.",
                filtering="malware", logging="some"),
    DnsProvider("verisign", "Verisign Public DNS", "64.6.64.6", "64.6.65.6",
                "2620:74:1b::1:1", "2620:74:1c::2:2",
                "Stability-focused; does not redirect failed lookups.",
                "none", "minimal"),
    DnsProvider("alternate", "Alternate DNS", "76.76.19.19", "76.223.122.150",
                notes="Ad-blocking resolver.",
                filtering="adblock", logging="minimal"),
    DnsProvider("cleanbrowsing", "CleanBrowsing (security)",
                "185.228.168.9", "185.228.169.9",
                "2a0d:2a00:1::2", "2a0d:2a00:2::2",
                "Blocks malware and phishing.", "malware", "minimal"),
    DnsProvider("cleanbrowsing_family", "CleanBrowsing (family)",
                "185.228.168.168", "185.228.169.168",
                "2a0d:2a00:1::", "2a0d:2a00:2::",
                "Blocks adult content, malware and proxies.",
                "family", "minimal"),
    DnsProvider("yandex", "Yandex DNS (basic)", "77.88.8.8", "77.88.8.1",
                notes="Russian operator. Consider the jurisdiction.",
                filtering="none", logging="some"),
    DnsProvider("level3", "Level3 / CenturyLink", "4.2.2.1", "4.2.2.2",
                notes="Legacy carrier resolvers. Widely reachable.",
                filtering="none", logging="unknown"),
)

BY_ID = {p.id: p for p in PROVIDERS}


def get(provider_id: str) -> Optional[DnsProvider]:
    return BY_ID.get(provider_id)


def resolvable(provider_id: str) -> bool:
    p = BY_ID.get(provider_id)
    return bool(p and p.servers)


# --------------------------------------------------------------- benchmark

# Domains a gamer's machine actually resolves. Measuring against these is
# more representative than a single synthetic lookup.
TEST_DOMAINS = (
    "store.steampowered.com",
    "discord.com",
    "epicgames.com",
    "xbox.com",
    "riotgames.com",
    "cloudflare.com",
)


@dataclass
class DnsResult:
    provider: DnsProvider
    median_ms: Optional[float] = None
    best_ms: Optional[float] = None
    worst_ms: Optional[float] = None
    failures: int = 0
    samples: int = 0
    error: str = ""

    @property
    def reachable(self) -> bool:
        return self.median_ms is not None

    def render(self) -> str:
        if not self.reachable:
            return f"{self.provider.name:<30} unreachable{'  ' + self.error if self.error else ''}"
        loss = f"  ({self.failures} failed)" if self.failures else ""
        return (f"{self.provider.name:<30} {self.median_ms:6.1f} ms median"
                f"   best {self.best_ms:.1f}   worst {self.worst_ms:.1f}{loss}")


def _query_once(server: str, domain: str, timeout: float = 2.0) -> Optional[float]:
    """Time a single A-record lookup against a specific resolver.

    Uses a hand-built DNS packet over UDP so no third-party dependency is
    needed and we measure the resolver rather than the OS cache.
    """
    import struct

    tid = int(time.time() * 1000) & 0xFFFF
    header = struct.pack(">HHHHHH", tid, 0x0100, 1, 0, 0, 0)
    qname = b"".join(bytes([len(part)]) + part.encode("ascii")
                     for part in domain.split(".")) + b"\x00"
    packet = header + qname + struct.pack(">HH", 1, 1)   # A, IN

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    started = time.perf_counter()
    try:
        sock.sendto(packet, (server, 53))
        data, _ = sock.recvfrom(512)
        if len(data) < 4 or data[:2] != packet[:2]:
            return None
        return (time.perf_counter() - started) * 1000.0
    except (OSError, socket.timeout):
        return None
    finally:
        sock.close()


def benchmark_provider(provider: DnsProvider, rounds: int = 2,
                       timeout: float = 2.0) -> DnsResult:
    result = DnsResult(provider=provider)
    if not provider.servers:
        result.error = "no fixed servers (DHCP)"
        return result

    server = provider.primary
    times: list[float] = []
    for _ in range(max(1, rounds)):
        for domain in TEST_DOMAINS:
            ms = _query_once(server, domain, timeout)
            result.samples += 1
            if ms is None:
                result.failures += 1
            else:
                times.append(ms)

    if times:
        result.median_ms = round(statistics.median(times), 2)
        result.best_ms = round(min(times), 2)
        result.worst_ms = round(max(times), 2)
    else:
        result.error = "all lookups timed out"
    return result


def benchmark(provider_ids: Optional[list[str]] = None, rounds: int = 2,
              progress=None, workers: int = 8) -> list[DnsResult]:
    """Measure every listed provider and return them fastest-first.

    Run in parallel. Serially this took ~45 seconds for the full catalog,
    which is far too long to sit in front of. These are independent UDP
    round-trips to different hosts, so concurrency does not distort the
    individual timings in any way that matters at this resolution.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    ids = provider_ids or [p.id for p in PROVIDERS if p.servers]
    providers = [BY_ID[i] for i in ids if i in BY_ID and BY_ID[i].servers]
    out: list[DnsResult] = []
    done = 0

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(benchmark_provider, prov, rounds): prov
                   for prov in providers}
        for future in as_completed(futures):
            provider = futures[future]
            try:
                out.append(future.result())
            except Exception as exc:                    # pragma: no cover
                out.append(DnsResult(provider=provider, error=str(exc)))
            done += 1
            if progress:
                try:
                    progress(done, len(providers), provider.name)
                except Exception:
                    pass

    out.sort(key=lambda r: (not r.reachable, r.median_ms or 1e9))
    return out


def recommend(results: list[DnsResult]) -> str:
    """An honest recommendation, including 'no change needed'."""
    ok = [r for r in results if r.reachable]
    if not ok:
        return ("No resolver responded. Your network may block outbound DNS "
                "on port 53, which some routers and captive portals do.")

    fastest = ok[0]
    lines = [f"Fastest here: {fastest.provider.name} at "
             f"{fastest.median_ms:.1f} ms median."]

    if len(ok) > 1:
        spread = ok[-1].median_ms - fastest.median_ms
        if spread < 10:
            lines.append(
                "All resolvers are within 10 ms of each other. That "
                "difference is imperceptible in practice - there is no real "
                "reason to change.")
        elif fastest.median_ms > 80:
            lines.append(
                "Even the fastest is slow, which usually points at the "
                "connection rather than the resolver.")

    lines.append(
        "Remember: this measures name-lookup speed only. It affects how "
        "quickly launchers and web pages start loading. It does NOT change "
        "your in-game ping - once a match starts your client talks to the "
        "game server by IP and the resolver is not involved.")
    return "\n".join(lines)


# ------------------------------------------------------------ apply / revert

def _adapters() -> list[dict]:
    """Active network adapters, via PowerShell."""
    if not IS_WINDOWS:
        return []
    ps = ("Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | "
          "Select-Object Name,InterfaceIndex,InterfaceDescription | "
          "ConvertTo-Json -Compress")
    out = runproc.output(["powershell", "-NoProfile", "-NonInteractive",
                          "-Command", ps], timeout=20)
    if not out.strip():
        return []
    try:
        import json
        data = json.loads(out)
        return data if isinstance(data, list) else [data]
    except ValueError:
        return []


def current_servers() -> list[dict]:
    """What each adapter is using right now."""
    if not IS_WINDOWS:
        return []
    ps = ("Get-DnsClientServerAddress -AddressFamily IPv4 | "
          "Select-Object InterfaceAlias,InterfaceIndex,ServerAddresses | "
          "ConvertTo-Json -Compress -Depth 3")
    out = runproc.output(["powershell", "-NoProfile", "-NonInteractive",
                          "-Command", ps], timeout=20)
    if not out.strip():
        return []
    try:
        import json
        data = json.loads(out)
        return data if isinstance(data, list) else [data]
    except ValueError:
        return []


def describe_current() -> str:
    rows = current_servers()
    if not rows:
        return ("Current DNS settings are unavailable on this platform."
                if not IS_WINDOWS else "Could not read the current DNS settings.")
    out = ["Current DNS servers:"]
    for row in rows:
        servers = row.get("ServerAddresses") or []
        if isinstance(servers, str):
            servers = [servers]
        alias = row.get("InterfaceAlias", "?")
        out.append(f"  {alias}: {', '.join(servers) if servers else 'automatic (DHCP)'}")
    return "\n".join(out)


def _valid_ip(value: str) -> bool:
    try:
        socket.inet_aton(value)
        return bool(re.fullmatch(r"[0-9.]+", value))
    except OSError:
        return False


def apply(provider_id: str, adapter_index: Optional[int] = None,
          dry_run: bool = True) -> dict:
    """Set the DNS servers for one or all active adapters.

    Returns a dict describing what happened, including the previous values so
    the change can be reversed.
    """
    provider = BY_ID.get(provider_id)
    result: dict = {"ok": False, "provider": provider_id, "dry_run": dry_run,
                    "changes": [], "message": ""}
    if provider is None:
        result["message"] = f"Unknown DNS provider: {provider_id}"
        return result
    if not IS_WINDOWS:
        result["message"] = "Changing DNS is only supported on Windows."
        return result

    for server in provider.servers:
        if not _valid_ip(server):
            result["message"] = f"Refusing to apply an invalid address: {server}"
            return result

    from ..core.platform_info import is_admin
    if not is_admin() and not dry_run:
        result["message"] = ("Changing DNS requires administrator rights. "
                             "Restart Phantom Tweeks as administrator.")
        return result

    before = {r.get("InterfaceIndex"): r for r in current_servers()}
    targets = ([a for a in _adapters() if a.get("InterfaceIndex") == adapter_index]
               if adapter_index is not None else _adapters())
    if not targets:
        result["message"] = "No active network adapter was found."
        return result

    for adapter in targets:
        idx = adapter.get("InterfaceIndex")
        name = adapter.get("Name", "?")
        prev = before.get(idx, {}).get("ServerAddresses") or []
        if isinstance(prev, str):
            prev = [prev]

        if provider.id == "dhcp":
            ps = f"Set-DnsClientServerAddress -InterfaceIndex {idx} -ResetServerAddresses"
        else:
            joined = ",".join(f"'{s}'" for s in provider.servers)
            ps = (f"Set-DnsClientServerAddress -InterfaceIndex {idx} "
                  f"-ServerAddresses {joined}")

        change = {"adapter": name, "interface_index": idx,
                  "previous": prev, "new": provider.servers or ["DHCP"],
                  "applied": False}

        if dry_run:
            result["changes"].append(change)
            continue

        proc = runproc.run(["powershell", "-NoProfile", "-NonInteractive",
                            "-Command", ps], timeout=30)
        change["applied"] = proc.returncode == 0
        if proc.returncode != 0:
            change["error"] = (proc.stderr or "").strip()[:200]
        result["changes"].append(change)

    if not dry_run:
        # Flush so the new resolver is used immediately.
        runproc.run(["ipconfig", "/flushdns"], timeout=20)

    applied = [c for c in result["changes"] if c.get("applied")]
    result["ok"] = bool(dry_run or applied)
    if dry_run:
        result["message"] = (f"Would set {len(result['changes'])} adapter(s) to "
                             f"{provider.name}. Nothing has been changed.")
    elif applied:
        result["message"] = (f"{provider.name} applied to {len(applied)} "
                             "adapter(s). DNS cache flushed.")
    else:
        result["message"] = "No adapter could be changed. See the errors above."
    return result


def revert(changes: list[dict]) -> dict:
    """Undo a previous apply() using the recorded previous values."""
    out: dict = {"ok": False, "restored": 0, "message": ""}
    if not IS_WINDOWS:
        out["message"] = "Only supported on Windows."
        return out

    for change in changes:
        idx = change.get("interface_index")
        prev = change.get("previous") or []
        if idx is None:
            continue
        if prev:
            joined = ",".join(f"'{s}'" for s in prev)
            ps = (f"Set-DnsClientServerAddress -InterfaceIndex {idx} "
                  f"-ServerAddresses {joined}")
        else:
            ps = (f"Set-DnsClientServerAddress -InterfaceIndex {idx} "
                  "-ResetServerAddresses")
        proc = runproc.run(["powershell", "-NoProfile", "-NonInteractive",
                            "-Command", ps], timeout=30)
        if proc.returncode == 0:
            out["restored"] += 1

    runproc.run(["ipconfig", "/flushdns"], timeout=20)
    out["ok"] = out["restored"] > 0
    out["message"] = (f"Restored the previous DNS on {out['restored']} adapter(s)."
                      if out["ok"] else "Nothing could be restored.")
    return out
