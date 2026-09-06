"""Driver Center.

Reports what is installed and how old it is, then links to the official vendor
page. Phantom Tweeks never downloads or installs drivers automatically — that
is the single fastest way to break a working PC.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..hardware.monitor import _wmi_query

VENDOR_LINKS = {
    "NVIDIA": "https://www.nvidia.com/Download/index.aspx",
    "AMD": "https://www.amd.com/en/support",
    "Intel": "https://www.intel.com/content/www/us/en/download-center/home.html",
    "Realtek": "https://www.realtek.com/downloads",
}
STALE_DAYS = 365


@dataclass
class Driver:
    category: str
    device: str
    version: Optional[str] = None
    date: Optional[str] = None
    vendor: Optional[str] = None

    @property
    def age_days(self) -> Optional[int]:
        if not self.date:
            return None
        raw = str(self.date)
        for fmt in ("%Y%m%d", "%m/%d/%Y", "%Y-%m-%d"):
            try:
                return (datetime.now() - datetime.strptime(raw[:len(fmt.replace('%','')) + 4], fmt)).days
            except ValueError:
                continue
        try:  # WMI CIM_DATETIME e.g. 20240115000000.000000-000
            return (datetime.now() - datetime.strptime(raw[:8], "%Y%m%d")).days
        except ValueError:
            return None

    @property
    def status(self) -> str:
        age = self.age_days
        if age is None:
            return "Unknown"
        return "Outdated" if age > STALE_DAYS else "Current"

    @property
    def link(self) -> Optional[str]:
        for key, url in VENDOR_LINKS.items():
            if self.vendor and key.lower() in self.vendor.lower():
                return url
            if key.lower() in self.device.lower():
                return url
        return None

    def render(self) -> str:
        return (f"{self.category}: {self.device}\n"
                f"  Version: {self.version or 'Unknown'}\n"
                f"  Date:    {str(self.date)[:10] if self.date else 'Unknown'}\n"
                f"  Status:  {self.status}"
                + (f"\n  Update:  {self.link}" if self.status == 'Outdated' and self.link else ""))


def _fmt(raw) -> Optional[str]:
    if not raw:
        return None
    s = str(raw)
    if len(s) >= 8 and s[:8].isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return s[:10]


def _collect(pnp_class: str, category: str) -> list[Driver]:
    rows = _wmi_query(
        "root/cimv2",
        f"SELECT DeviceName,DriverVersion,DriverDate,Manufacturer FROM "
        f"Win32_PnPSignedDriver WHERE DeviceClass='{pnp_class}'",
        ["DeviceName", "DriverVersion", "DriverDate", "Manufacturer"])
    out = []
    for r in rows:
        if not r.get("DeviceName"):
            continue
        out.append(Driver(category, r["DeviceName"], r.get("DriverVersion"),
                          _fmt(r.get("DriverDate")), r.get("Manufacturer")))
    return out


def scan() -> list[Driver]:
    drivers: list[Driver] = []
    for cls, cat in (("DISPLAY", "GPU"), ("NET", "Network"), ("MEDIA", "Audio"),
                     ("SYSTEM", "Chipset")):
        drivers.extend(_collect(cls, cat))
    # Chipset is noisy; keep the informative entries only.
    drivers = [d for d in drivers
               if d.category != "Chipset"
               or any(k in d.device.lower() for k in ("chipset", "smbus", "pci express root", "amd", "intel"))]
    return drivers[:40]


def report() -> dict:
    ds = scan()
    outdated = [d for d in ds if d.status == "Outdated"]
    return {
        "drivers": ds,
        "outdated": outdated,
        "summary": ("All detected drivers are less than a year old."
                    if not outdated else
                    f"{len(outdated)} driver(s) are over a year old. Phantom Tweeks "
                    "will not install drivers for you — use the official vendor link."),
    }
