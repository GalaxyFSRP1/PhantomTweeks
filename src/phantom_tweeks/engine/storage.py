"""Storage Lab.

Reports drive type, capacity, health and safe cleanup candidates.
Personal files are never enumerated for deletion and never deleted automatically.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..hardware.monitor import MONITOR, _wmi_query

# Only well-known, regenerable caches. No Documents, Downloads, Desktop, Pictures.
CLEANUP_TARGETS = [
    ("Windows temporary files", "%TEMP%"),
    ("System temporary files", r"%SystemRoot%\Temp"),
    ("Windows Update cache", r"%SystemRoot%\SoftwareDistribution\Download"),
    ("Delivery Optimization cache", r"%SystemRoot%\SoftwareDistribution\DeliveryOptimization"),
    ("Crash dumps", r"%LOCALAPPDATA%\CrashDumps"),
    ("DirectX shader cache", r"%LOCALAPPDATA%\D3DSCache"),
    ("NVIDIA shader cache", r"%LOCALAPPDATA%\NVIDIA\DXCache"),
    ("Thumbnail cache", r"%LOCALAPPDATA%\Microsoft\Windows\Explorer"),
]


@dataclass
class CleanupCandidate:
    label: str
    path: str
    size_mb: float
    note: str = ""


@dataclass
class StorageReport:
    disks: list = field(default_factory=list)
    physical: list = field(default_factory=list)
    candidates: list[CleanupCandidate] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    @property
    def reclaimable_mb(self) -> float:
        return round(sum(c.size_mb for c in self.candidates), 1)


def _dir_size_mb(path: Path, cap_files: int = 20000) -> float:
    total = 0
    count = 0
    try:
        for root, _dirs, files in os.walk(path):
            for f in files:
                try:
                    total += (Path(root) / f).stat().st_size
                except OSError:
                    continue
                count += 1
                if count > cap_files:
                    return round(total / 1024 / 1024, 1)
    except (OSError, PermissionError):
        pass
    return round(total / 1024 / 1024, 1)


def physical_disks() -> list[dict]:
    rows = _wmi_query("root/microsoft/windows/storage",
                      "SELECT FriendlyName,MediaType,BusType,Size,HealthStatus,"
                      "Temperature FROM MSFT_PhysicalDisk",
                      ["FriendlyName", "MediaType", "BusType", "Size",
                       "HealthStatus", "Temperature"])
    out = []
    for r in rows:
        mt = {3: "HDD", 4: "SSD", 5: "SCM"}.get(r.get("MediaType"), "Unknown")
        if mt == "SSD":
            mt = "NVMe SSD" if r.get("BusType") == 17 else "SATA SSD"
        health = {0: "Healthy", 1: "Warning", 2: "Unhealthy"}.get(r.get("HealthStatus"), None)
        out.append({
            "name": r.get("FriendlyName"), "media_type": mt, "health": health,
            "size_gb": round(r["Size"] / 1024**3, 1) if r.get("Size") else None,
            "temperature_c": r.get("Temperature") or None,
        })
    return out


def scan() -> StorageReport:
    rep = StorageReport(disks=MONITOR.disks(), physical=physical_disks())
    for label, raw in CLEANUP_TARGETS:
        path = Path(os.path.expandvars(raw))
        if not path.exists() or "%" in str(path):
            continue
        size = _dir_size_mb(path)
        if size >= 50:
            note = ("Shader caches regenerate automatically; clearing them causes "
                    "brief stutter on first launch." if "shader" in label.lower() else "")
            rep.candidates.append(CleanupCandidate(label, str(path), size, note))
    rep.candidates.sort(key=lambda c: c.size_mb, reverse=True)

    for d in rep.disks:
        if d.total_gb and d.free_gb is not None:
            pct = d.free_gb / d.total_gb * 100
            if pct < 10:
                rep.recommendations.append(
                    f"{d.mountpoint} is {100-pct:.0f}% full. Below 10% free, SSD write "
                    "performance degrades and Windows loses paging headroom.")
            elif pct < 20:
                rep.recommendations.append(
                    f"{d.mountpoint} has {pct:.0f}% free. Consider freeing space soon.")
    for p in rep.physical:
        if p.get("health") and p["health"] != "Healthy":
            rep.recommendations.append(
                f"{p['name']} reports health status '{p['health']}'. Back up your data "
                "and investigate with the manufacturer's tool.")
        if p.get("media_type") == "HDD":
            rep.recommendations.append(
                f"{p['name']} is a mechanical hard drive. Moving your most-played game "
                "to an SSD is the single largest real-world improvement available on "
                "this system — far more than any software tweak.")
    if not rep.recommendations:
        rep.recommendations.append("No change recommended. Storage looks healthy.")
    return rep
