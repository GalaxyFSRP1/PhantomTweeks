"""Bufferbloat: measuring latency while the connection is busy.

Why this matters more than anything else in the app
---------------------------------------------------
Idle ping is what every speed test reports, and it is close to useless for
gaming. What actually ruins a match is **latency under load**: someone starts
a download, your router's transmit queue fills with large packets, and your
game's small packets sit behind them. Idle ping of 20 ms becomes 300 ms while
a single Steam download runs.

That is bufferbloat, and unlike almost every registry tweak people try, it has
a real fix - SQM/fq_codel on the router, or simply capping bulk downloads.

What this module does
---------------------
Measures ping three times: idle, during a download, and during an upload. The
difference is the bufferbloat figure. Upload is measured separately because
home connections are asymmetric and upstream saturates far sooner - a cloud
backup or game upload is the usual culprit.

Honesty
-------
* The load is generated against public endpoints and is deliberately modest.
  A test that saturates your line for a minute is itself disruptive.
* This measures the path from your PC to the internet. A bad result may be
  your router, your ISP, or Wi-Fi. The report says which is most likely
  rather than blaming something it cannot see.
* No result is invented. If a phase fails it is reported as not measured.
"""
from __future__ import annotations

import socket
import statistics
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

from . import lab

# Public endpoints used to generate load. Cloudflare's speed endpoints are
# purpose-built for this and are not someone's unwitting web server.
_DOWNLOAD_URL = "https://speed.cloudflare.com/__down?bytes=25000000"
_UPLOAD_URL = "https://speed.cloudflare.com/__up"
_PING_TARGET = "1.1.1.1"

# Grades follow the widely used bufferbloat scale (added latency in ms).
_GRADES = ((5, "A+"), (30, "A"), (60, "B"), (200, "C"), (400, "D"))


def grade_for(added_ms: Optional[float]) -> str:
    if added_ms is None:
        return "?"
    for limit, letter in _GRADES:
        if added_ms < limit:
            return letter
    return "F"


@dataclass
class Phase:
    label: str
    median_ms: Optional[float] = None
    worst_ms: Optional[float] = None
    samples: int = 0
    lost: int = 0
    error: str = ""

    def render(self) -> str:
        if self.median_ms is None:
            return f"  {self.label:<22} not measured" + (
                f"  ({self.error})" if self.error else "")
        line = (f"  {self.label:<22} {self.median_ms:6.1f} ms median"
                f"   worst {self.worst_ms:.0f} ms   ({self.samples} samples)")
        if self.lost:
            line += f"   {self.lost} lost"
        return line


@dataclass
class BufferbloatResult:
    idle: Phase = field(default_factory=lambda: Phase("Idle"))
    download: Phase = field(default_factory=lambda: Phase("While downloading"))
    upload: Phase = field(default_factory=lambda: Phase("While uploading"))
    notes: list = field(default_factory=list)

    @property
    def download_added(self) -> Optional[float]:
        if self.idle.median_ms is None or self.download.median_ms is None:
            return None
        return max(0.0, self.download.median_ms - self.idle.median_ms)

    @property
    def upload_added(self) -> Optional[float]:
        if self.idle.median_ms is None or self.upload.median_ms is None:
            return None
        return max(0.0, self.upload.median_ms - self.idle.median_ms)

    @property
    def worst_added(self) -> Optional[float]:
        vals = [v for v in (self.download_added, self.upload_added)
                if v is not None]
        return max(vals) if vals else None

    @property
    def measured(self) -> bool:
        """True only when idle AND at least one load phase produced data."""
        return (self.idle.median_ms is not None
                and (self.download.median_ms is not None
                     or self.upload.median_ms is not None))

    @property
    def grade(self) -> str:
        return grade_for(self.worst_added) if self.measured else "not measured"

    def verdict(self) -> list:
        """What the numbers mean, and what to do about them."""
        if not self.measured:
            reasons = [p.error for p in (self.idle, self.download, self.upload)
                       if p.error]
            out = ["This test could not measure your connection, so there is "
                   "no result to report."]
            if reasons:
                out.append(f"Reason: {reasons[0]}.")
            out += ["",
                    "Many networks and VPNs block the ICMP pings this test "
                    "relies on. That is a configuration choice, not a fault, "
                    "and it does not mean your connection is bad.",
                    "",
                    "Phantom Tweeks will not guess a grade from data it does "
                    "not have."]
            return out

        added = self.worst_added
        if added is None:
            return ["Not enough data to judge. Check your connection and "
                    "try again."]

        out = []
        if added < 30:
            out.append(
                "Your connection holds up well under load. A download running "
                "in the background will not noticeably affect your game.")
            return out

        if added < 60:
            out.append(
                f"Latency rises about {added:.0f} ms when the line is busy. "
                "Mild, but you would feel it in a fast-paced game while "
                "something is downloading.")
        elif added < 200:
            out.append(
                f"Latency rises about {added:.0f} ms under load. This is "
                "real bufferbloat and it is almost certainly what you notice "
                "as lag spikes when someone else is streaming or a game is "
                "updating.")
        else:
            out.append(
                f"Latency rises about {added:.0f} ms under load. That is "
                "severe. Any background transfer will make an online game "
                "essentially unplayable, and no registry tweak on this PC can "
                "fix it - the queue is in your router or at your ISP.")

        out.append("")
        out.append("What actually fixes this, in order of effect:")
        out.append("  1. Enable SQM or Smart Queue Management on your router "
                   "(sometimes called QoS, fq_codel or cake). This is the "
                   "real fix and often eliminates the problem entirely.")
        out.append("  2. Cap your download speed to about 85-90% of your "
                   "line rate, in the router or in Steam. Bufferbloat only "
                   "occurs when the link is saturated.")
        out.append("  3. Pause background downloads while you play. Phantom "
                   "Tweeks can show you what is using the connection.")

        if (self.upload_added or 0) > (self.download_added or 0) * 1.5:
            out.append("")
            out.append("Your upload is noticeably worse than your download. "
                       "That is typical of cable and DSL connections, where "
                       "upstream is a fraction of downstream and saturates "
                       "far sooner. Cloud backup and game uploads are the "
                       "usual cause.")
        return out

    def render(self) -> str:
        out = ["BUFFERBLOAT TEST", "",
               "Idle ping is what speed tests report. What ruins a game is",
               "latency while the connection is busy - this measures both.",
               "",
               self.idle.render(),
               self.download.render(),
               self.upload.render(),
               ""]
        if self.download_added is not None:
            out.append(f"  Added by download:  +{self.download_added:.0f} ms "
                       f"({grade_for(self.download_added)})")
        if self.upload_added is not None:
            out.append(f"  Added by upload:    +{self.upload_added:.0f} ms "
                       f"({grade_for(self.upload_added)})")
        out += ["", f"  Bufferbloat grade:  {self.grade}", ""]
        out += self.verdict()
        if self.notes:
            out += [""] + [f"  Note: {n}" for n in self.notes]
        return "\n".join(out)


# ------------------------------------------------------------- measuring

def _ping_burst(seconds: float, target: str = _PING_TARGET) -> Phase:
    """Ping repeatedly for a period, returning median and worst."""
    phase = Phase("")
    times = []
    lost = 0
    end = time.time() + seconds
    while time.time() < end:
        result = lab.ping(target, count=1, timeout_ms=1500)
        if result.latency_ms is not None:
            times.append(result.latency_ms)
        else:
            lost += 1
        time.sleep(0.15)

    attempts = len(times) + lost
    # If nothing replied at all, ICMP is blocked or the target is
    # unreachable. Substituting the timeout value here would produce a
    # confident-looking number from no data - and because every phase would
    # get the same fake value, the test would cheerfully report grade A+ on
    # a connection it never measured. Report nothing instead.
    if not times:
        phase.error = ("no replies - ICMP is probably blocked"
                       if attempts else "no attempts made")
        return phase

    # Some loss under load IS the symptom, so count timeouts as bad samples,
    # but only when we have real replies to compare them against.
    times.extend([1500.0] * lost)
    phase.median_ms = round(statistics.median(times), 1)
    phase.worst_ms = round(max(times), 1)
    phase.samples = len(times)
    phase.lost = lost
    return phase


def _download_load(stop: threading.Event) -> None:
    """Pull data until told to stop. Errors are ignored - the load is the
    point, not the transfer."""
    try:
        req = urllib.request.Request(
            _DOWNLOAD_URL, headers={"User-Agent": "PhantomTweeks"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            while not stop.is_set():
                if not resp.read(65536):
                    break
    except Exception:
        pass


def _upload_load(stop: threading.Event) -> None:
    chunk = b"0" * 65536

    class Stream:
        def read(self, n=-1):
            return b"" if stop.is_set() else chunk

    try:
        req = urllib.request.Request(
            _UPLOAD_URL, data=Stream(), method="POST",
            headers={"User-Agent": "PhantomTweeks",
                     "Content-Type": "application/octet-stream"})
        urllib.request.urlopen(req, timeout=30)
    except Exception:
        pass


def run(seconds_per_phase: float = 6.0,
        progress=None) -> BufferbloatResult:
    """Measure idle, download and upload latency.

    Deliberately short. A test that saturates the line for a minute is itself
    disruptive, and six seconds is enough to fill a router queue.
    """
    result = BufferbloatResult()

    def say(msg):
        if progress:
            try:
                progress(msg)
            except Exception:
                pass

    say("Measuring idle latency...")
    result.idle = _ping_burst(seconds_per_phase)
    result.idle.label = "Idle"
    if result.idle.median_ms is None:
        result.notes.append(
            "Could not reach the ping target. Results are unavailable - this "
            "usually means outbound ICMP is blocked.")
        return result

    say("Measuring while downloading...")
    stop = threading.Event()
    workers = [threading.Thread(target=_download_load, args=(stop,),
                                daemon=True) for _ in range(4)]
    for w in workers:
        w.start()
    time.sleep(1.0)                    # let the queue actually fill
    result.download = _ping_burst(seconds_per_phase)
    result.download.label = "While downloading"
    stop.set()
    time.sleep(0.5)

    say("Measuring while uploading...")
    stop2 = threading.Event()
    ups = [threading.Thread(target=_upload_load, args=(stop2,), daemon=True)
           for _ in range(2)]
    for w in ups:
        w.start()
    time.sleep(1.0)
    result.upload = _ping_burst(seconds_per_phase)
    result.upload.label = "While uploading"
    stop2.set()

    if result.download.median_ms is None and result.upload.median_ms is None:
        result.notes.append(
            "Load phases failed, most likely because the test endpoints were "
            "unreachable. Only idle latency is shown.")
    return result


def quick_check() -> str:
    """A short summary for the dashboard."""
    result = run(seconds_per_phase=4.0)
    if not result.measured:
        return "Bufferbloat: not measured (ICMP may be blocked)"
    added = result.worst_added
    if added is None:
        return "Bufferbloat: not measured"
    return f"Bufferbloat: grade {result.grade} (+{added:.0f} ms under load)"
