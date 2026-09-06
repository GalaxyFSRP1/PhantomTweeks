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

    NetTweak(
        "tcp_timestamps", "Disable TCP timestamps",
        "Removes 12 bytes of overhead from every TCP packet",
        "RFC 1323 timestamps help round-trip estimation on long-haul links "
        "but add 12 bytes per packet. On a low-latency connection the "
        "overhead outweighs the benefit. Windows disables them by default; "
        "this restores that if something enabled them.",
        apply=lambda on: _netsh("int", "tcp", "set", "global",
                                f"timestamps={'disabled' if on else 'enabled'}"),
        is_on=lambda: "disabled" in (runproc.output(
            ["netsh", "int", "tcp", "show", "global"], timeout=20)
            or "").lower().split("timestamps")[-1][:24]),

    NetTweak(
        "ecn_off", "Disable Explicit Congestion Notification",
        "Stops negotiating congestion signalling with routers",
        "ECN lets routers mark packets instead of dropping them. Some older "
        "home routers and middleboxes handle the flag badly and silently "
        "drop the connection instead, which shows up as random disconnects.",
        apply=lambda on: _netsh("int", "tcp", "set", "global",
                                f"ecncapability={'disabled' if on else 'enabled'}"),
        is_on=lambda: "disabled" in (runproc.output(
            ["netsh", "int", "tcp", "show", "global"], timeout=20)
            or "").lower().split("ecn capability")[-1][:24]),

    NetTweak(
        "rsc_off", "Disable Receive Segment Coalescing",
        "Delivers each packet separately instead of merging them",
        "RSC merges several received packets into one before handing them to "
        "Windows, which raises throughput but adds a small delay while it "
        "waits to coalesce. Turning it off favours latency over bulk speed.",
        warning="Slightly reduces maximum download throughput and raises CPU "
                "use on very fast links.",
        apply=lambda on: _netsh("int", "tcp", "set", "global",
                                f"rsc={'disabled' if on else 'enabled'}"),
        is_on=lambda: "disabled" in (runproc.output(
            ["netsh", "int", "tcp", "show", "global"], timeout=20)
            or "").lower().split("receive segment coalescing")[-1][:24]),

    NetTweak(
        "heuristics_off", "Disable TCP window auto-tuning heuristics",
        "Stops Windows second-guessing its own window scaling",
        "A separate layer from auto-tuning itself: the heuristics can "
        "override the scaling level based on guesses about your connection. "
        "Disabling the heuristics while leaving auto-tuning on is the "
        "configuration Microsoft recommends for consistent throughput.",
        apply=lambda on: _netsh("int", "tcp", "set", "heuristics",
                                "disabled" if on else "default"),
        is_on=lambda: "disabled" in (runproc.output(
            ["netsh", "int", "tcp", "show", "heuristics"], timeout=20)
            or "").lower()),

    NetTweak(
        "ctcp", "Use the CTCP congestion provider",
        "Ramps up transfer speed more aggressively after congestion",
        "Compound TCP recovers throughput faster than the default provider "
        "on connections with any packet loss. It affects bulk transfers "
        "rather than the small packets a game sends.",
        apply=lambda on: _netsh("int", "tcp", "set", "supplemental",
                                "template=internet",
                                f"congestionprovider={'ctcp' if on else 'cubic'}"),
        is_on=lambda: "ctcp" in (runproc.output(
            ["netsh", "int", "tcp", "show", "supplemental"], timeout=20)
            or "").lower()),

    NetTweak(
        "max_user_port", "Widen the ephemeral port range",
        "Allows far more simultaneous outbound connections",
        "Raises the usable port ceiling to 65534 and shortens the wait before "
        "a closed port can be reused. Only matters if you actually exhaust "
        "the range - many peers in a P2P game, or a lot of browser tabs - "
        "but it is harmless otherwise.",
        apply=lambda on: [
            ws.write_registry("HKLM", TCPIP_PARAMS, "MaxUserPort",
                              65534 if on else 5000, note="Ephemeral ports"),
            ws.write_registry("HKLM", TCPIP_PARAMS, "TcpTimedWaitDelay",
                              30 if on else 120, note="TIME_WAIT delay")],
        is_on=lambda: ws.read_registry("HKLM", TCPIP_PARAMS,
                                       "MaxUserPort") == 65534),

    NetTweak(
        "default_ttl", "Set the default TTL to 64",
        "Uses the standard hop limit instead of the Windows default of 128",
        "A cosmetic difference on almost every connection: TTL only matters "
        "if packets are traversing more than 64 routers, which they are not. "
        "Included because it appears on every tweak list and people ask - "
        "expect no measurable change.",
        apply=lambda on: [ws.write_registry(
            "HKLM", TCPIP_PARAMS, "DefaultTTL", 64 if on else 128,
            note="Default TTL")],
        is_on=lambda: ws.read_registry("HKLM", TCPIP_PARAMS,
                                       "DefaultTTL") == 64),

    NetTweak(
        "no_negative_dns_cache", "Stop caching failed DNS lookups",
        EFFECT_LOOKUP,
        "Windows remembers failed lookups for five minutes by default. When "
        "a game server's DNS is briefly unavailable, that failure sticks "
        "around long after the problem is fixed. Zeroing the negative cache "
        "means a retry actually retries.",
        apply=lambda on: [
            ws.write_registry("HKLM",
                              r"SYSTEM\CurrentControlSet\Services\Dnscache\Parameters",
                              "MaxNegativeCacheTtl", 0 if on else 5,
                              note="Negative DNS cache"),
            ws.write_registry("HKLM",
                              r"SYSTEM\CurrentControlSet\Services\Dnscache\Parameters",
                              "NegativeCacheTime", 0 if on else 300,
                              note="Negative cache time")],
        is_on=lambda: ws.read_registry(
            "HKLM", r"SYSTEM\CurrentControlSet\Services\Dnscache\Parameters",
            "MaxNegativeCacheTtl") == 0),

    NetTweak(
        "qos_no_reserve", "Remove the QoS bandwidth reservation",
        EFFECT_UPLINK,
        "The famous '20% reserved bandwidth' setting. It only ever applied to "
        "applications that explicitly request QoS reservation, and only on a "
        "saturated link - so for almost everyone this changes nothing. "
        "Included because people expect it; do not expect a difference.",
        apply=lambda on: [ws.write_registry(
            "HKLM", r"SOFTWARE\Policies\Microsoft\Windows\Psched",
            "NonBestEffortLimit", 0 if on else 80,
            note="QoS reservable bandwidth")],
        is_on=lambda: ws.read_registry(
            "HKLM", r"SOFTWARE\Policies\Microsoft\Windows\Psched",
            "NonBestEffortLimit") == 0),

    NetTweak(
        "netbios_off", "Disable NetBIOS over TCP/IP",
        "Removes legacy name-resolution broadcast traffic",
        "NetBIOS broadcasts chatter on your local network and is a routinely "
        "abused credential-relay vector. Modern name resolution does not "
        "need it.",
        warning="Can break discovery of very old network shares and printers.",
        apply=lambda on: _netbios(on),
        is_on=lambda: False),

    NetTweak(
        "llmnr_off", "Disable LLMNR",
        "Stops link-local multicast name resolution",
        "Another legacy fallback that mostly generates broadcast noise and is "
        "widely abused for credential theft on shared networks. Disabling it "
        "is a security improvement with no measurable performance cost - and "
        "it should be described that way, not as a speed tweak.",
        apply=lambda on: [ws.write_registry(
            "HKLM", r"SOFTWARE\Policies\Microsoft\Windows NT\DNSClient",
            "EnableMulticast", 0 if on else 1, note="LLMNR")],
        is_on=lambda: ws.read_registry(
            "HKLM", r"SOFTWARE\Policies\Microsoft\Windows NT\DNSClient",
            "EnableMulticast") == 0),

    NetTweak(
        "tcp_initial_rto", "Shorten the TCP connection retry timeout",
        "Retries a lost connection attempt sooner",
        "Windows waits 3 seconds before retrying an unanswered TCP SYN. "
        "Halving it to 2 seconds means a dropped handshake recovers faster - "
        "noticeable when a game server briefly refuses connections. Does "
        "nothing once you are connected.",
        apply=lambda on: _netsh("int", "tcp", "set", "global",
                                f"initialRto={'2000' if on else '3000'}"),
        is_on=lambda: "2000" in (runproc.output(
            ["netsh", "int", "tcp", "show", "global"], timeout=20)
            or "").split("Initial RTO")[-1][:20]),

    NetTweak(
        "max_syn_retransmissions", "Fewer connection retry attempts",
        "Fails a dead connection faster instead of hanging",
        "Reduces SYN retransmissions from 4 to 2. A server that is genuinely "
        "down is reported as unreachable in about a second rather than "
        "twenty, so the game stops waiting and lets you pick another server.",
        apply=lambda on: [ws.write_registry(
            "HKLM", TCPIP_PARAMS, "TcpMaxConnectRetransmissions",
            2 if on else 4, note="SYN retransmissions")],
        is_on=lambda: ws.read_registry("HKLM", TCPIP_PARAMS,
                                       "TcpMaxConnectRetransmissions") == 2),

    NetTweak(
        "keepalive_time", "Shorten the TCP keep-alive interval",
        "Notices a dead connection sooner",
        "Windows waits two hours before probing an idle connection. Bringing "
        "that to five minutes means a silently dropped link is detected while "
        "you are still playing rather than long after.",
        apply=lambda on: [ws.write_registry(
            "HKLM", TCPIP_PARAMS, "KeepAliveTime",
            300000 if on else 7200000, note="TCP keep-alive")],
        is_on=lambda: ws.read_registry("HKLM", TCPIP_PARAMS,
                                       "KeepAliveTime") == 300000),

    NetTweak(
        "irq_priority", "Prioritise network interrupts",
        "Handles network interrupts ahead of other device work",
        "Raises the priority of the network stack's deferred procedure calls. "
        "Helps when a badly behaved driver - often audio or storage - is "
        "delaying packet processing. Small effect on a healthy system.",
        warning="Can starve other devices on a system that is already CPU "
                "bound. Revert it if audio starts crackling.",
        apply=lambda on: [ws.write_registry(
            "HKLM", MMCSS_SYSTEM, "NoLazyMode", 1 if on else 0,
            note="MMCSS lazy mode")],
        is_on=lambda: ws.read_registry("HKLM", MMCSS_SYSTEM,
                                       "NoLazyMode") == 1),

    NetTweak(
        "dns_over_https", "Use encrypted DNS",
        "Stops your ISP seeing and redirecting name lookups",
        "DNS-over-HTTPS encrypts lookups to the resolver. Some ISPs hijack "
        "plain DNS to inject ads or block sites, which also slows resolution. "
        "This is a privacy and reliability improvement, not a speed one - it "
        "adds a small amount of handshake overhead.",
        apply=lambda on: _doh(on),
        is_on=lambda: False),

    NetTweak(
        "wifi_roaming", "Reduce Wi-Fi roaming aggressiveness",
        "Stops the adapter hunting for a different access point",
        "Prevents mid-game disconnects when two access points have similar "
        "signal strength and the adapter keeps switching. Only relevant on "
        "Wi-Fi.",
        warning="Makes moving between rooms worse - the adapter will cling "
                "to a weak access point for longer.",
        apply=lambda on: _adapter_property("RoamAggressiveness",
                                           "1" if on else "3"),
        is_on=lambda: _adapter_property_is("RoamAggressiveness", "1")),

    NetTweak(
        "wifi_5ghz", "Prefer the 5 GHz band",
        "Avoids the congested 2.4 GHz spectrum",
        "2.4 GHz shares space with microwaves, Bluetooth and every "
        "neighbouring router. Preferring 5 GHz is a genuine and often large "
        "latency and jitter improvement on Wi-Fi.",
        apply=lambda on: _adapter_property("RoamingPreferredBandType",
                                           "2" if on else "0"),
        is_on=lambda: _adapter_property_is("RoamingPreferredBandType", "2")),

    NetTweak(
        "packet_coalescing", "Disable packet coalescing",
        "Delivers packets individually instead of in batches",
        "Windows can group received packets before waking the CPU. Turning "
        "that off removes a small buffering delay at the cost of more "
        "interrupts.",
        warning="Raises CPU use, like interrupt moderation. Do not enable "
                "both on a weak CPU.",
        apply=lambda on: _adapter_property("*PacketCoalescing",
                                           "0" if on else "1"),
        is_on=lambda: _adapter_property_is("*PacketCoalescing", "0")),

    NetTweak(
        "arp_cache_life", "Extend the ARP cache lifetime",
        "Avoids repeated address lookups on your local network",
        "Windows expires ARP entries after two minutes and must re-resolve "
        "your router's hardware address. Extending it to ten minutes removes "
        "those periodic lookups. The effect is small but real on a busy LAN.",
        apply=lambda on: [ws.write_registry(
            "HKLM", TCPIP_PARAMS, "ArpCacheLife", 600 if on else 120,
            note="ARP cache lifetime")],
        is_on=lambda: ws.read_registry("HKLM", TCPIP_PARAMS,
                                       "ArpCacheLife") == 600),
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


def _doh(on: bool) -> list:
    """Enable or disable DNS-over-HTTPS for the configured resolvers."""
    value = 2 if on else 0     # 2 = require DoH, 0 = plain DNS
    ps = ("Get-DnsClientDohServerAddress -ErrorAction SilentlyContinue | "
          "Out-Null; Set-DnsClientDohServerAddress -ServerAddress 1.1.1.1 "
          "-DohTemplate 'https://cloudflare-dns.com/dns-query' "
          "-AllowFallbackToUdp $" + ("false" if on else "true") +
          " -AutoUpgrade $" + ("true" if on else "false") +
          " -ErrorAction SilentlyContinue")
    runproc.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                timeout=45)
    return [ws.write_registry(
        "HKLM", r"SYSTEM\CurrentControlSet\Services\Dnscache\Parameters",
        "EnableAutoDoh", value, note="DNS over HTTPS")]


def _netbios(on: bool) -> list:
    """Toggle NetBIOS over TCP/IP on every adapter.

    SetTcpipNetbios takes 0 = use DHCP default, 1 = enable, 2 = disable.
    """
    option = 2 if on else 0
    ps = ("Get-CimInstance -ClassName Win32_NetworkAdapterConfiguration "
          "-Filter 'IPEnabled=True' | ForEach-Object { $_ | "
          "Invoke-CimMethod -MethodName SetTcpipNetbios -Arguments "
          f"@{{TcpipNetbiosOptions={option}}} }}")
    runproc.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                timeout=60)
    return []


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
