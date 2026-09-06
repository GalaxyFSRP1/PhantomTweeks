"""Phantom Network Lab.

Honest measurement only. Phantom Tweeks does not claim to reduce your ping — it
measures your connection so you can find the actual cause of instability.
DNS resolver response time is NOT the same as game-server ping; the report says
so explicitly.
"""
from __future__ import annotations

import json
import re
import socket
import statistics
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional

from ..core import paths
from ..core.platform_info import IS_WINDOWS
from ..core import runproc

DNS_PROVIDERS = [
    ("Cloudflare", "1.1.1.1"),
    ("Google", "8.8.8.8"),
    ("Quad9", "9.9.9.9"),
    ("OpenDNS", "208.67.222.222"),
]


@dataclass
class PingResult:
    target: str
    label: str = ""
    sent: int = 0
    received: int = 0
    latency_ms: Optional[float] = None
    min_ms: Optional[float] = None
    max_ms: Optional[float] = None
    jitter_ms: Optional[float] = None
    packet_loss_pct: Optional[float] = None
    samples: list[float] = field(default_factory=list)
    error: Optional[str] = None

    def as_dict(self) -> dict:
        return asdict(self)


def _ping_cmd(target: str, count: int, timeout_ms: int) -> list[str]:
    if IS_WINDOWS:
        return ["ping", "-n", str(count), "-w", str(timeout_ms), target]
    return ["ping", "-c", str(count), "-W", str(max(1, timeout_ms // 1000)), target]


_RTT = re.compile(r"time[=<]\s*([\d.]+)\s*ms", re.IGNORECASE)


def ping(target: str, count: int = 10, timeout_ms: int = 2000,
         label: str = "") -> PingResult:
    """Run a ping series and compute latency, jitter and packet loss."""
    res = PingResult(target=target, label=label or target, sent=count)
    try:
        out = runproc.run(_ping_cmd(target, count, timeout_ms),
                             capture_output=True, text=True,
                             timeout=count * (timeout_ms / 1000) + 15).stdout
    except FileNotFoundError:
        res.error = "The system 'ping' utility is unavailable."
        return res
    except subprocess.TimeoutExpired:
        res.error = "Ping timed out."
        return res

    samples = [float(m) for m in _RTT.findall(out)]
    res.samples = samples
    res.received = len(samples)
    res.packet_loss_pct = round((count - len(samples)) / count * 100, 1)
    if samples:
        res.latency_ms = round(statistics.fmean(samples), 1)
        res.min_ms, res.max_ms = round(min(samples), 1), round(max(samples), 1)
        if len(samples) > 1:
            # Mean absolute consecutive difference — the RFC 3550 style jitter
            # gamers actually feel, not standard deviation.
            deltas = [abs(b - a) for a, b in zip(samples, samples[1:])]
            res.jitter_ms = round(statistics.fmean(deltas), 1)
        else:
            res.jitter_ms = 0.0
    else:
        res.error = "No replies received. The host may block ICMP."
    return res


def default_gateway() -> Optional[str]:
    try:
        if IS_WINDOWS:
            out = runproc.run(["ipconfig"], capture_output=True, text=True,
                                 timeout=15).stdout
            for line in out.splitlines():
                if "Default Gateway" in line:
                    cand = line.split(":")[-1].strip()
                    if cand and cand.count(".") == 3:
                        return cand
        else:
            out = runproc.run(["ip", "route"], capture_output=True, text=True,
                                 timeout=10).stdout
            m = re.search(r"default via ([\d.]+)", out)
            if m:
                return m.group(1)
    except Exception:
        return None
    return None


def connection_type() -> str:
    """Ethernet vs Wi-Fi — matters more for stability than any software tweak."""
    try:
        import psutil
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
        for name, st in stats.items():
            if not st.isup or name.lower().startswith(("lo", "loopback")):
                continue
            has_ip = any(a.family == socket.AF_INET and not a.address.startswith("127.")
                         for a in addrs.get(name, []))
            if not has_ip:
                continue
            low = name.lower()
            if any(k in low for k in ("wi-fi", "wifi", "wlan", "wireless")):
                return f"Wi-Fi ({name})"
            if any(k in low for k in ("ethernet", "eth", "enp", "lan")):
                return f"Ethernet ({name})"
        return "Unknown"
    except Exception:
        return "Unknown"


def dns_benchmark(providers=None) -> list[dict]:
    """Measure resolver response time. NOT game ping."""
    providers = providers or DNS_PROVIDERS
    results = []
    for name, ip in providers:
        r = ping(ip, count=5, label=name)
        results.append({
            "provider": name, "address": ip,
            "response_ms": r.latency_ms, "packet_loss_pct": r.packet_loss_pct,
            "error": r.error,
        })
    return sorted(results, key=lambda d: (d["response_ms"] is None, d["response_ms"] or 0))


def traceroute(target: str = "1.1.1.1", max_hops: int = 15) -> list[str]:
    cmd = (["tracert", "-d", "-h", str(max_hops), "-w", "1000", target] if IS_WINDOWS
           else ["traceroute", "-n", "-m", str(max_hops), "-w", "1", target])
    try:
        out = runproc.run(cmd, capture_output=True, text=True, timeout=90).stdout
        return [l.rstrip() for l in out.splitlines() if l.strip()]
    except Exception as e:
        return [f"Route diagnostics unavailable: {e}"]


def stability_test(target: str = "1.1.1.1", seconds: int = 30) -> dict:
    """Sustained sampling — catches intermittent drops a 4-packet ping misses."""
    start = time.monotonic()
    samples: list[float] = []
    lost = 0
    while time.monotonic() - start < seconds:
        r = ping(target, count=1, timeout_ms=1000)
        if r.samples:
            samples.extend(r.samples)
        else:
            lost += 1
        time.sleep(0.2)
    total = len(samples) + lost
    out = {
        "target": target, "duration_s": seconds, "probes": total,
        "packet_loss_pct": round(lost / total * 100, 1) if total else None,
        "avg_ms": round(statistics.fmean(samples), 1) if samples else None,
        "max_ms": round(max(samples), 1) if samples else None,
        "jitter_ms": None, "spikes": 0,
    }
    if len(samples) > 1:
        deltas = [abs(b - a) for a, b in zip(samples, samples[1:])]
        out["jitter_ms"] = round(statistics.fmean(deltas), 1)
        avg = out["avg_ms"] or 0
        out["spikes"] = sum(1 for s in samples if s > avg * 2 + 10)
    return out


def full_lab(quick: bool = True) -> dict:
    gw = default_gateway()
    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "connection": connection_type(),
        "gateway": None,
        "internet": None,
        "dns": [],
        "notes": [
            "DNS response time is not the same as game-server ping. A faster "
            "resolver speeds up name lookups, not gameplay latency.",
            "Phantom Tweeks does not promise ping reduction. Latency is dominated "
            "by physical distance and your ISP's routing.",
        ],
    }
    count = 6 if quick else 20
    if gw:
        report["gateway"] = ping(gw, count=count, label="Gateway").as_dict()
    report["internet"] = ping("1.1.1.1", count=count, label="Internet").as_dict()
    report["dns"] = dns_benchmark()
    report["diagnosis"] = diagnose(report)
    return report


def diagnose(report: dict) -> dict:
    """Turn measurements into an honest verdict."""
    internet = report.get("internet") or {}
    gateway = report.get("gateway") or {}
    loss = internet.get("packet_loss_pct")
    jitter = internet.get("jitter_ms")
    gw_loss = gateway.get("packet_loss_pct")
    gw_jitter = gateway.get("jitter_ms")
    issues, recs = [], []

    if gw_loss and gw_loss > 0.5:
        issues.append(f"Packet loss to your own router: {gw_loss}%")
        recs.append("Loss on the local hop points at Wi-Fi interference, a bad "
                    "cable, or the router itself — not your ISP.")
    if loss and loss > 1:
        issues.append(f"Internet packet loss: {loss}%")
        recs.append("Investigate ISP routing; run the test on Ethernet to rule out Wi-Fi.")
    if jitter and jitter > 10:
        issues.append(f"High jitter: {jitter} ms")
        recs.append("Jitter this high causes rubber-banding. Check for other devices "
                    "saturating the connection, and prefer a wired connection.")
    if "Wi-Fi" in report.get("connection", "") and (jitter or 0) > 5:
        recs.append("You are on Wi-Fi. An Ethernet connection is the single most "
                    "effective change for online stability.")
    if gw_jitter is not None and jitter is not None and gw_jitter < 2 and jitter > 15:
        recs.append("Your local network is clean but the path to the internet is not: "
                    "this is an ISP or upstream routing problem, not a PC setting.")

    if not issues:
        return {
            "status": "STABLE",
            "summary": "No network instability detected in this test.",
            "recommendations": ["No change recommended."],
        }
    return {
        "status": "UNSTABLE",
        "summary": "NETWORK ISSUE DETECTED\n" + "\n".join(f"• {i}" for i in issues),
        "recommendations": recs + [
            "Changing DNS will not fix packet loss or jitter."],
    }


# ---------------- history ----------------

def record_history(report: dict) -> None:
    paths.ensure_dirs()
    hist = load_history()
    internet = report.get("internet") or {}
    hist.append({
        "timestamp": report.get("timestamp"),
        "latency_ms": internet.get("latency_ms"),
        "jitter_ms": internet.get("jitter_ms"),
        "packet_loss_pct": internet.get("packet_loss_pct"),
        "connection": report.get("connection"),
    })
    tmp = paths.NETWORK_HISTORY.with_suffix(".tmp")
    tmp.write_text(json.dumps(hist[-500:], indent=2), encoding="utf-8")
    tmp.replace(paths.NETWORK_HISTORY)


def load_history() -> list[dict]:
    if not paths.NETWORK_HISTORY.exists():
        return []
    try:
        return json.loads(paths.NETWORK_HISTORY.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def daily_summary(days: int = 7) -> list[dict]:
    """Collapse history into per-day averages for the PING HISTORY graph."""
    from collections import defaultdict
    buckets: dict[str, list[float]] = defaultdict(list)
    for row in load_history():
        ts, lat = row.get("timestamp"), row.get("latency_ms")
        if ts and lat is not None:
            buckets[ts[:10]].append(lat)
    rows = [{"date": d, "avg_ms": round(statistics.fmean(v), 1), "samples": len(v)}
            for d, v in sorted(buckets.items())]
    return rows[-days:]
