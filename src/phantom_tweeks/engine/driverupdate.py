"""Real driver update checking against vendor sources.

What this does
--------------
Reads the installed GPU driver version and compares it against the version
NVIDIA, AMD or Intel currently publishes, then links to the official download.

What it deliberately does not do
--------------------------------
**It never downloads or installs a driver.** Driver installers touch kernel
code; a wrong or interrupted one produces a machine that will not display
anything. Every "driver updater" utility that automates this is either
scareware or a support-call generator, and several are known malware vectors.

Phantom Tweeks tells you a newer version exists and sends you to the vendor's
own page. You install it deliberately, from the source, with the vendor's
installer - which can also clean up the previous version properly.

Sources
-------
NVIDIA publishes a public driver lookup API used by GeForce Experience. AMD
and Intel do not offer an equivalent open endpoint, so for those we report the
installed version and link to the official download page rather than inventing
a comparison we cannot actually make.
"""
from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

TIMEOUT = 15

NVIDIA_LOOKUP = ("https://gfwsl.geforce.com/services_toolkit/services/com/"
                 "nvidia/services/AjaxDriverService.php")
NVIDIA_DOWNLOADS = "https://www.nvidia.com/Download/index.aspx"
AMD_DOWNLOADS = "https://www.amd.com/en/support"
INTEL_DOWNLOADS = "https://www.intel.com/content/www/us/en/download-center/home.html"


@dataclass
class DriverStatus:
    vendor: str = ""
    device: str = ""
    installed: str = ""
    latest: str = ""
    download_url: str = ""
    checked: bool = False
    up_to_date: Optional[bool] = None
    message: str = ""

    def render(self) -> str:
        out = [f"{self.vendor or 'Unknown'} - {self.device or 'GPU'}"]
        out.append(f"  Installed  {self.installed or 'not detected'}")
        if self.checked and self.latest:
            out.append(f"  Latest     {self.latest}")
            if self.up_to_date:
                out.append("  Status     up to date")
            else:
                out.append("  Status     a newer driver is available")
        else:
            out.append("  Latest     not checked")
        if self.message:
            out.append(f"  {self.message}")
        if self.download_url:
            out.append(f"  Download   {self.download_url}")
        return "\n".join(out)


def _version_tuple(text: str) -> tuple:
    """Driver versions are dotted numbers; compare them numerically."""
    parts = re.findall(r"\d+", text or "")
    return tuple(int(p) for p in parts[:4]) or (0,)


def _short_nvidia_version(raw: str) -> str:
    """Windows reports 31.0.15.6603; NVIDIA calls that 566.03.

    The last five digits of the Windows version are the marketing version.
    """
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) >= 5:
        tail = digits[-5:]
        return f"{tail[:3]}.{tail[3:]}"
    return raw or ""


def _get(url: str, timeout: int = TIMEOUT) -> str:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "PhantomTweeks"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read().decode("utf-8", errors="replace")


def check_nvidia(installed_raw: str = "", device: str = "") -> DriverStatus:
    """Compare the installed NVIDIA driver against the published one."""
    status = DriverStatus(vendor="NVIDIA", device=device,
                          download_url=NVIDIA_DOWNLOADS)
    status.installed = _short_nvidia_version(installed_raw) or installed_raw

    # psid/pfid select the product family. 101/815 is the GeForce desktop
    # line, which covers the overwhelming majority of gaming machines.
    query = urllib.parse.urlencode({
        "func": "DriverManualLookup", "psid": "101", "pfid": "815",
        "osID": "57", "languageCode": "1033", "isWHQL": "1",
        "dch": "1", "sort1": "0", "numberOfResults": "1",
    })
    try:
        raw = _get(f"{NVIDIA_LOOKUP}?{query}")
        data = json.loads(raw)
        infos = data.get("IDS") or []
        if not infos:
            status.message = ("NVIDIA's lookup returned no driver for this "
                              "product family.")
            return status
        info = infos[0].get("downloadInfo", {})
        status.latest = str(info.get("Version") or "")
        status.checked = bool(status.latest)
    except urllib.error.HTTPError as exc:
        status.message = f"NVIDIA's driver service returned HTTP {exc.code}."
        return status
    except Exception as exc:
        status.message = (f"Could not reach NVIDIA's driver service "
                          f"({type(exc).__name__}). Check manually.")
        return status

    if status.checked and status.installed:
        status.up_to_date = (_version_tuple(status.installed)
                             >= _version_tuple(status.latest))
        if not status.up_to_date:
            status.message = (
                "Driver updates deliver genuine, sometimes double-digit gains "
                "in new titles. Occasionally one regresses - Phantom Tweeks "
                "records benchmark history so you can see it if it happens.")
    return status


def check_amd(installed: str = "", device: str = "") -> DriverStatus:
    """AMD publishes no open version endpoint, so report and link."""
    return DriverStatus(
        vendor="AMD", device=device, installed=installed,
        download_url=AMD_DOWNLOADS, checked=False,
        message=("AMD does not publish an open driver-version API, so "
                 "Phantom Tweeks cannot compare automatically without "
                 "guessing. Adrenalin's own updater is reliable, or use the "
                 "link below."))


def check_intel(installed: str = "", device: str = "") -> DriverStatus:
    return DriverStatus(
        vendor="Intel", device=device, installed=installed,
        download_url=INTEL_DOWNLOADS, checked=False,
        message=("Intel does not publish an open driver-version API. The "
                 "Intel Driver & Support Assistant checks automatically, or "
                 "use the link below."))


def check_all() -> list:
    """Check every detected GPU. Never raises."""
    results = []
    try:
        from ..hardware.monitor import MONITOR
        gpus = MONITOR.gpus()
    except Exception:
        gpus = []

    if not gpus:
        return [DriverStatus(
            vendor="", device="", checked=False,
            message=("No GPU was detected, so no driver could be checked. "
                     "This needs WMI on Windows."))]

    for gpu in gpus:
        vendor = (gpu.vendor or "").upper()
        version = gpu.driver_version or ""
        try:
            if "NVIDIA" in vendor:
                results.append(check_nvidia(version, gpu.model or ""))
            elif "AMD" in vendor or "ATI" in vendor or "RADEON" in vendor:
                results.append(check_amd(version, gpu.model or ""))
            elif "INTEL" in vendor:
                results.append(check_intel(version, gpu.model or ""))
            else:
                results.append(DriverStatus(
                    vendor=gpu.vendor or "Unknown", device=gpu.model or "",
                    installed=version, checked=False,
                    message="Unrecognised GPU vendor; check manually."))
        except Exception as exc:                      # pragma: no cover
            results.append(DriverStatus(
                vendor=gpu.vendor or "", device=gpu.model or "",
                installed=version,
                message=f"Check failed: {type(exc).__name__}"))
    return results


def report() -> str:
    out = ["GPU DRIVER STATUS", ""]
    statuses = check_all()
    for status in statuses:
        out += [status.render(), ""]
    out += [
        "-" * 60, "",
        "Phantom Tweeks never downloads or installs a driver.",
        "",
        "Driver installers load kernel code. A wrong or interrupted one",
        "leaves a machine that will not display anything, and automated",
        "'driver updater' tools are a well-known malware vector. Install",
        "from the vendor's own page, with their installer, which also",
        "removes the previous version properly.",
        "",
        "If a new driver makes things worse, Display Driver Uninstaller",
        "(DDU) in safe mode is the reliable way back.",
    ]
    return "\n".join(out)


def outdated() -> list:
    """Only the drivers we could confirm are behind."""
    return [s for s in check_all() if s.checked and s.up_to_date is False]
