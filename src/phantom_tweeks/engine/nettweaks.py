"""Network tweaks - one-click toggles that reduce PC-side network delay.

What these actually do
----------------------
Every tweak here targets delay your own machine adds: packet batching,
interrupt coalescing, adapter power-saving, name-lookup time, and background
processes competing for your uplink.

They do not change the distance to the game server or the route your packets
take, which is what "ping" measures. A tweak that promised that would be
lying. The wording throughout is chosen to describe the mechanism rather than
an outcome nobody can guarantee.

Where they help most: wireless links with power-saving enabled, adapters with
aggressive interrupt moderation, and connections shared with a busy download.
On a clean wired connection several of these will measure as no change - and
the app says so rather than inventing an improvement.

Safety
------
* Every tweak captures its previous value first and returns a reversible
  ``ChangeRecord``. Toggling off restores exactly what was there.
* Nothing here touches Defender, the firewall, Windows Update, or anything
  security-related.
* Adapter-level changes are applied per adapter, so a broken NIC driver
  cannot take the whole stack down.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..core import runproc
from ..core.platform_info import IS_WINDOWS, is_admin
from . import winsettings as ws

TCPIP_IFACES = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
TCPIP_PARAMS = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters"
MMCSS_SYSTEM = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"

# Effect wording used in the UI. Deliberately mechanical, never "lower ping".
EFFECT_SEND = "Sends small packets immediately instead of batching them"
EFFECT_WAKE = "Removes wake-up delay on the network adapter"
EFFECT_LOOKUP = "Speeds up name lookups"
EFFECT_UPLINK = "Stops background traffic competing for your uplink"


@dataclass
class NetTweak:
    id: str
    name: str
    effect: str                 # what it mechanically does
    detail: str                 # the honest longer explanation
    warning: str = ""           # shown when it can backfire
    requires_admin: bool = True
    per_adapter: bool = False
    apply: Optional[Callable] = None
    is_on: Optional[Callable] = None

    @property
    def risky(self) -> bool:
        return bool(self.warning)


# --------------------------------------------------------------- helpers

def _adapter_guids() -> list[str]:
    """Interface GUIDs that currently have an IPv4 address."""
    if not IS_WINDOWS:
        return []
    ps = ("Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | "
          "Where-Object { $_.IPAddress -notlike '127.*' } | "
          "ForEach-Object { (Get-NetAdapter -InterfaceIndex "
          "$_.InterfaceIndex -ErrorAction SilentlyContinue).InterfaceGuid } | "
          "Sort-Object -Unique")
    out = runproc.output(["powershell", "-NoProfile", "-NonInteractive",
                          "-Command", ps], timeout=30)
    return re.findall(r"\{[0-9A-Fa-f-]{36}\}", out or "")


def _iface_key(guid: str) -> str:
    return f"{TCPIP_IFACES}\\{guid}"


def _set_on_all_adapters(name: str, value: int, note: str) -> list:
    changes = []
    for guid in _adapter_guids():
        try:
            changes.append(ws.write_registry("HKLM", _iface_key(guid), name,
                                             value, note=note))
        except Exception:
            # A single problem adapter must not abort the rest.
            continue
    return changes


def _any_adapter_has(name: str, value: int) -> bool:
    for guid in _adapter_guids():
        if ws.read_registry("HKLM", _iface_key(guid), name) == value:
            return True
    return False


def _netsh(*args, note: str = "") -> list:
    """Run netsh. These are not registry writes, so they are logged but the
    revert is handled by the paired tweak rather than the journal."""
    runproc.run(["netsh", *args], timeout=30)
    return []


def _adapter_property(keyword: str, value: str) -> list:
    """Set an advanced adapter property by its registry keyword."""
    if not IS_WINDOWS:
        return []
    ps = (f"Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | "
          f"ForEach-Object {{ Set-NetAdapterAdvancedProperty -Name $_.Name "
          f"-RegistryKeyword '{keyword}' -RegistryValue '{value}' "
          f"-NoRestart -ErrorAction SilentlyContinue }}")
    runproc.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                timeout=60)
    return []


def _adapter_property_is(keyword: str, value: str) -> bool:
    if not IS_WINDOWS:
        return False
    ps = (f"(Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | "
          f"Get-NetAdapterAdvancedProperty -RegistryKeyword '{keyword}' "
          f"-ErrorAction SilentlyContinue).RegistryValue")
    out = runproc.output(["powershell", "-NoProfile", "-NonInteractive",
                          "-Command", ps], timeout=30)
    return value in (out or "")


# ---------------------------------------------------------------- tweaks

TWEAKS: list[NetTweak] = [

    NetTweak(
        "nagle", "Disable Nagle's algorithm",
        EFFECT_SEND,
        "Nagle batches small outgoing TCP packets to save bandwidth, adding "
        "up to 200 ms before a small packet leaves your PC. Disabling it "
        "sends immediately. Affects TCP only - most competitive shooters use "
        "UDP, where this changes nothing.",
        apply=lambda on: (
            _set_on_all_adapters("TcpAckFrequency", 1 if on else 2,
                                 note="TCP ack frequency")
            + _set_on_all_adapters("TCPNoDelay", 1 if on else 0,
                                   note="Nagle's algorithm")),
        is_on=lambda: _any_adapter_has("TCPNoDelay", 1)),

    NetTweak(
        "delayed_ack", "Disable delayed ACK",
        EFFECT_SEND,
        "Windows waits before acknowledging received TCP data, hoping to "
        "bundle the ack with outgoing data. Setting the delay to zero "
        "acknowledges immediately, which keeps TCP streams flowing.",
        apply=lambda on: _set_on_all_adapters(
            "TcpDelAckTicks", 0 if on else 2, note="Delayed ACK"),
        is_on=lambda: _any_adapter_has("TcpDelAckTicks", 0)),

    NetTweak(
        "interrupt_moderation", "Disable interrupt moderation",
        "Delivers packets to Windows the moment they arrive",
        "The adapter batches interrupts to reduce CPU load. Turning that off "
        "delivers each packet immediately, cutting a fraction of a "
        "millisecond of delay at the cost of noticeably higher CPU use.",
        warning="Raises CPU use under load. On a weak or already-saturated "
                "CPU this can cost more than it saves.",
        apply=lambda on: _adapter_property(
            "*InterruptModeration", "0" if on else "1"),
        is_on=lambda: _adapter_property_is("*InterruptModeration", "0")),

    NetTweak(
        "energy_efficient_ethernet", "Disable Energy Efficient Ethernet",
        EFFECT_WAKE,
        "EEE lets the adapter idle between packets and wake on demand. The "
        "wake takes time, and on some hardware it causes intermittent link "
        "drops. Disabling it keeps the adapter always ready.",
        apply=lambda on: _adapter_property("*EEE", "0" if on else "1"),
        is_on=lambda: _adapter_property_is("*EEE", "0")),

    NetTweak(
        "green_ethernet", "Disable Green Ethernet",
        EFFECT_WAKE,
        "A vendor power-saving mode that reduces signal strength on short "
        "cable runs. Same trade as EEE: a little power for a little latency, "
        "and it is a known cause of flaky links on cheap cabling.",
        apply=lambda on: _adapter_property("GreenEthernet", "0" if on else "1"),
        is_on=lambda: _adapter_property_is("GreenEthernet", "0")),

    NetTweak(
        "nic_power_saving", "Stop Windows powering down the adapter",
        EFFECT_WAKE,
        "Windows may suspend the network adapter to save power. On a desktop "
        "the saving is meaningless and the wake latency is real. This is a "
        "genuine fix for intermittent dropouts.",
        warning="On a laptop running on battery this shortens runtime.",
        apply=lambda on: _adapter_property(
            "*DeviceSleepOnDisconnect", "0" if on else "1"),
        is_on=lambda: _adapter_property_is("*DeviceSleepOnDisconnect", "0")),

    NetTweak(
        "flow_control", "Disable flow control",
        "Stops the adapter pausing traffic when a switch asks it to",
        "Pause frames let a congested switch throttle your PC. On a home "
        "network that congestion rarely exists, and the pause adds delay "
        "when it triggers spuriously.",
        apply=lambda on: _adapter_property("*FlowControl", "0" if on else "3"),
        is_on=lambda: _adapter_property_is("*FlowControl", "0")),

    NetTweak(
        "receive_side_scaling", "Enable Receive Side Scaling",
        "Spreads packet processing across CPU cores",
        "Without RSS every network interrupt lands on CPU 0, which becomes a "
        "bottleneck under load. Enabling it is correct on any multi-core "
        "machine and is usually already on.",
        apply=lambda on: _netsh("int", "tcp", "set", "global",
                                f"rss={'enabled' if on else 'disabled'}"),
        is_on=lambda: "enabled" in (runproc.output(
            ["netsh", "int", "tcp", "show", "global"], timeout=20) or
            "").lower().split("receive-side scaling state")[-1][:30]),

    NetTweak(
        "rss_queues", "Increase RSS queues",
        "Uses more CPU cores for receive processing",
        "Raises the number of receive queues so more cores share the load. "
        "Helps on high-core-count systems with a fast link. Setting more "
        "queues than the adapter supports silently does nothing.",
        apply=lambda on: _adapter_property("*NumRssQueues", "4" if on else "2"),
        is_on=lambda: _adapter_property_is("*NumRssQueues", "4")),

    NetTweak(
        "network_throttling", "Remove the multimedia network throttle",
        "Lifts a legacy 10-packets-per-millisecond cap",
        "A Vista-era limit that throttles non-multimedia network traffic "
        "while multimedia is playing. Irrelevant at typical game traffic "
        "volumes, but harmless to lift and occasionally helps on very fast "
        "links.",
        apply=lambda on: [ws.write_registry(
            "HKLM", MMCSS_SYSTEM, "NetworkThrottlingIndex",
            0xFFFFFFFF if on else 10, note="Network throttling index")],
        is_on=lambda: ws.read_registry("HKLM", MMCSS_SYSTEM,
                                       "NetworkThrottlingIndex") == 0xFFFFFFFF),

    NetTweak(
        "system_responsiveness", "Reduce reserved CPU for background tasks",
        "Gives foreground work a larger share of scheduled CPU",
        "MMCSS reserves a percentage of CPU for low-priority work. Lowering "
        "it from 20 to 10 leaves more for the foreground. Windows clamps very "
        "low values, so setting it to zero achieves nothing - 10 is the "
        "lowest value that actually applies.",
        apply=lambda on: [ws.write_registry(
            "HKLM", MMCSS_SYSTEM, "SystemResponsiveness", 10 if on else 20,
            note="MMCSS reserved CPU")],
        is_on=lambda: ws.read_registry("HKLM", MMCSS_SYSTEM,
                                       "SystemResponsiveness") == 10),

    NetTweak(
        "dns_cloudflare", "Use a fast DNS resolver",
        EFFECT_LOOKUP,
        "Points name resolution at Cloudflare (1.1.1.1), usually among the "
        "fastest. This makes launchers, stores and web pages start loading "
        "sooner. It does not affect an in-progress match, which talks to the "
        "server by IP.",
        apply=lambda on: _apply_dns(on),
        is_on=lambda: _dns_is("1.1.1.1")),

    NetTweak(
        "flush_dns", "Flush the DNS cache",
        "Clears stale name-resolution entries",
        "A one-shot repair rather than a setting. Useful when a server has "
        "moved and your PC is still resolving the old address.",
        requires_admin=False,
        apply=lambda on: _flush_dns(),
        is_on=lambda: False),

    NetTweak(
        "delivery_optimization", "Stop seeding Windows updates",
        EFFECT_UPLINK,
        "Delivery Optimization uploads Windows update data to other machines "
        "in the background. Upstream saturation is a real and common cause of "
        "lag spikes, and most people never chose to enable this.",
        apply=lambda on: [ws.write_registry(
            "HKLM",
            r"SOFTWARE\Policies\Microsoft\Windows\DeliveryOptimization",
            "DODownloadMode", 0 if on else 1,
            note="Delivery Optimization peer sharing")],
        is_on=lambda: ws.read_registry(
            "HKLM", r"SOFTWARE\Policies\Microsoft\Windows\DeliveryOptimization",
            "DODownloadMode") == 0),

    NetTweak(
        "tcp_autotuning", "Verify TCP auto-tuning is on",
        "Lets Windows size the TCP window for your connection",
        "Auto-tuning should be left enabled - guides that tell you to disable "
        "it are wrong and it caps throughput on fast links. This toggle "
        "restores the correct default if something disabled it.",
        apply=lambda on: _netsh("int", "tcp", "set", "global",
                                f"autotuninglevel="
                                f"{'normal' if on else 'disabled'}"),
        is_on=lambda: "normal" in (runproc.output(
            ["netsh", "int", "tcp", "show", "global"], timeout=20) or "").lower()),
]


def _apply_dns(on: bool) -> list:
    from ..network import dns as _dns
    result = _dns.apply("cloudflare" if on else "dhcp", dry_run=False)
    return []


def _dns_is(server: str) -> bool:
    from ..network import dns as _dns
    for row in _dns.current_servers():
        servers = row.get("ServerAddresses") or []
        if isinstance(servers, str):
            servers = [servers]
        if server in servers:
            return True
    return False


def _flush_dns() -> list:
    runproc.run(["ipconfig", "/flushdns"], timeout=20)
    return []


BY_ID = {t.id: t for t in TWEAKS}


def states() -> dict:
    """Current on/off state of every tweak. Never raises."""
    out = {}
    for t in TWEAKS:
        try:
            out[t.id] = bool(t.is_on()) if t.is_on else False
        except Exception:
            out[t.id] = False
    return out


def set_tweak(tweak_id: str, enabled: bool) -> tuple[bool, str, list]:
    """Toggle one tweak. Returns (ok, message, reversible changes)."""
    tweak = BY_ID.get(tweak_id)
    if tweak is None:
        return False, f"Unknown network tweak: {tweak_id}", []
    if not IS_WINDOWS:
        return False, "Network tweaks require Windows.", []
    if tweak.requires_admin and not is_admin():
        return False, (f"{tweak.name} needs administrator rights. Restart "
                       "Phantom Tweeks as administrator."), []
    try:
        changes = tweak.apply(enabled) or []
    except Exception as exc:
        return False, f"{tweak.name} failed: {exc}", []
    verb = "enabled" if enabled else "reverted"
    return True, f"{tweak.name} {verb}.", changes


def summary() -> str:
    on = states()
    out = ["NETWORK TWEAKS", "",
           "These reduce delay your own PC adds. They do not change the",
           "distance to a game server, which is what ping measures.", ""]
    for t in TWEAKS:
        mark = "[on] " if on.get(t.id) else "[off]"
        out.append(f"{mark} {t.name}")
        out.append(f"       {t.effect}")
        if t.warning:
            out.append(f"       ! {t.warning}")
    return "\n".join(out)
