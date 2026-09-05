"""Live hardware telemetry.

Rule: never fabricate a reading. Anything unavailable on this machine is
returned as None and the UI renders it as "n/a" rather than inventing a value.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Optional

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore

from ..core.platform_info import IS_WINDOWS
from ..core import runproc


def _wmi_query(namespace: str, query: str, props: list[str]) -> list[dict]:
    """Query WMI via PowerShell. Returns [] when unavailable — never raises."""
    if not IS_WINDOWS or not shutil.which("powershell"):
        return []
    sel = ",".join(props)
    ps = (
        f"Get-CimInstance -Namespace {namespace} -Query \"{query}\" -ErrorAction "
        f"SilentlyContinue | Select-Object {sel} | ConvertTo-Json -Compress -Depth 3"
    )
    try:
        out = runproc.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=20,
        ).stdout.strip()
        if not out:
            return []
        import json
        data = json.loads(out)
        return data if isinstance(data, list) else [data]
    except Exception:
        return []


@dataclass
class CPUInfo:
    model: Optional[str] = None
    physical_cores: Optional[int] = None
    logical_cores: Optional[int] = None
    architecture: Optional[str] = None
    current_mhz: Optional[float] = None
    max_mhz: Optional[float] = None
    utilization: Optional[float] = None
    per_core: list[float] = field(default_factory=list)
    temperature_c: Optional[float] = None
    power_plan: Optional[str] = None


@dataclass
class GPUInfo:
    vendor: Optional[str] = None
    model: Optional[str] = None
    driver_version: Optional[str] = None
    driver_date: Optional[str] = None
    vram_total_mb: Optional[float] = None
    vram_used_mb: Optional[float] = None
    utilization: Optional[float] = None
    temperature_c: Optional[float] = None
    clock_mhz: Optional[float] = None
    power_w: Optional[float] = None


@dataclass
class MemoryInfo:
    total_gb: Optional[float] = None
    used_gb: Optional[float] = None
    available_gb: Optional[float] = None
    percent: Optional[float] = None
    speed_mhz: Optional[int] = None
    modules: Optional[int] = None


@dataclass
class DiskInfo:
    device: str = ""
    mountpoint: str = ""
    media_type: Optional[str] = None    # HDD / SATA SSD / NVMe SSD
    total_gb: Optional[float] = None
    free_gb: Optional[float] = None
    percent_used: Optional[float] = None
    health: Optional[str] = None
    temperature_c: Optional[float] = None
    read_mb_s: Optional[float] = None
    write_mb_s: Optional[float] = None


class HardwareMonitor:
    """Samples hardware. Expensive identity lookups are cached; rates are sampled."""

    def __init__(self) -> None:
        self._cpu_static: dict = {}
        self._gpu_static: list[dict] = []
        self._disk_static: dict = {}
        self._last_disk_io = None
        self._last_net_io = None
        if psutil:
            psutil.cpu_percent(interval=None)  # prime the counter

    # ---------------- CPU ----------------
    def cpu(self) -> CPUInfo:
        info = CPUInfo()
        if not psutil:
            return info
        info.logical_cores = psutil.cpu_count(logical=True)
        info.physical_cores = psutil.cpu_count(logical=False)
        info.utilization = psutil.cpu_percent(interval=None)
        try:
            info.per_core = psutil.cpu_percent(interval=None, percpu=True)
        except Exception:
            info.per_core = []
        try:
            freq = psutil.cpu_freq()
            if freq:
                info.current_mhz, info.max_mhz = freq.current, freq.max or None
        except Exception:
            pass
        import platform
        info.architecture = platform.machine()
        if not self._cpu_static:
            rows = _wmi_query("root/cimv2", "SELECT Name,MaxClockSpeed FROM Win32_Processor", ["Name", "MaxClockSpeed"])
            self._cpu_static = rows[0] if rows else {"Name": platform.processor() or None}
        info.model = self._cpu_static.get("Name") or platform.processor() or None
        info.temperature_c = self._cpu_temperature()
        info.power_plan = self._power_plan()
        return info

    def _cpu_temperature(self) -> Optional[float]:
        # Linux/dev path
        if psutil and hasattr(psutil, "sensors_temperatures"):
            try:
                temps = psutil.sensors_temperatures()
                for key in ("coretemp", "k10temp", "zenpower", "acpitz"):
                    if temps.get(key):
                        return round(float(temps[key][0].current), 1)
            except Exception:
                pass
        # Windows: only the ACPI thermal zone is available without a driver.
        rows = _wmi_query("root/wmi",
                          "SELECT CurrentTemperature FROM MSAcpi_ThermalZoneTemperature",
                          ["CurrentTemperature"])
        if rows:
            try:
                return round(float(rows[0]["CurrentTemperature"]) / 10.0 - 273.15, 1)
            except Exception:
                return None
        return None  # honest: most desktops need a kernel driver we won't install

    def _power_plan(self) -> Optional[str]:
        if not IS_WINDOWS or not shutil.which("powercfg"):
            return None
        try:
            out = runproc.run(["powercfg", "/getactivescheme"],
                                 capture_output=True, text=True, timeout=10).stdout
            if "(" in out:
                return out.split("(")[-1].split(")")[0]
        except Exception:
            pass
        return None

    # ---------------- GPU ----------------
    def gpus(self) -> list[GPUInfo]:
        results: list[GPUInfo] = []
        nv = self._nvidia_smi()
        if nv:
            return nv
        if not self._gpu_static:
            self._gpu_static = _wmi_query(
                "root/cimv2",
                "SELECT Name,DriverVersion,DriverDate,AdapterRAM FROM Win32_VideoController",
                ["Name", "DriverVersion", "DriverDate", "AdapterRAM"],
            )
        for row in self._gpu_static:
            name = row.get("Name") or "Unknown GPU"
            low = name.lower()
            vendor = ("NVIDIA" if "nvidia" in low or "geforce" in low or "rtx" in low
                      else "AMD" if "amd" in low or "radeon" in low
                      else "Intel" if "intel" in low or "arc" in low else "Unknown")
            ram = row.get("AdapterRAM")
            results.append(GPUInfo(
                vendor=vendor, model=name,
                driver_version=row.get("DriverVersion"),
                driver_date=str(row.get("DriverDate") or "") or None,
                # AdapterRAM is a signed 32-bit field: unreliable above 4 GB.
                vram_total_mb=round(ram / 1024 / 1024, 0) if isinstance(ram, (int, float)) and 0 < ram < 2**31 else None,
            ))
        return results

    def _nvidia_smi(self) -> list[GPUInfo]:
        exe = shutil.which("nvidia-smi")
        if not exe:
            return []
        fields = ("name,driver_version,memory.total,memory.used,utilization.gpu,"
                  "temperature.gpu,clocks.current.graphics,power.draw")
        try:
            out = runproc.run(
                [exe, f"--query-gpu={fields}", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=15).stdout.strip()
        except Exception:
            return []

        def num(v: str) -> Optional[float]:
            v = v.strip()
            try:
                return float(v)
            except ValueError:
                return None

        gpus = []
        for line in out.splitlines():
            p = [c.strip() for c in line.split(",")]
            if len(p) < 8:
                continue
            gpus.append(GPUInfo(
                vendor="NVIDIA", model=p[0], driver_version=p[1],
                vram_total_mb=num(p[2]), vram_used_mb=num(p[3]),
                utilization=num(p[4]), temperature_c=num(p[5]),
                clock_mhz=num(p[6]), power_w=num(p[7]),
            ))
        return gpus

    # ---------------- Memory ----------------
    def memory(self) -> MemoryInfo:
        info = MemoryInfo()
        if not psutil:
            return info
        vm = psutil.virtual_memory()
        g = 1024 ** 3
        info.total_gb = round(vm.total / g, 2)
        info.used_gb = round((vm.total - vm.available) / g, 2)
        info.available_gb = round(vm.available / g, 2)
        info.percent = vm.percent
        rows = _wmi_query("root/cimv2", "SELECT Speed FROM Win32_PhysicalMemory", ["Speed"])
        if rows:
            speeds = [r.get("Speed") for r in rows if r.get("Speed")]
            if speeds:
                info.speed_mhz = int(max(speeds))
            info.modules = len(rows)
        return info

    # ---------------- Storage ----------------
    def disks(self) -> list[DiskInfo]:
        out: list[DiskInfo] = []
        if not psutil:
            return out
        media = self._media_types()
        for part in psutil.disk_partitions(all=False):
            if "cdrom" in part.opts or not part.fstype:
                continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError):
                continue
            g = 1024 ** 3
            out.append(DiskInfo(
                device=part.device, mountpoint=part.mountpoint,
                media_type=media.get(part.device[:2].upper()),
                total_gb=round(usage.total / g, 1),
                free_gb=round(usage.free / g, 1),
                percent_used=usage.percent,
            ))
        return out

    def _media_types(self) -> dict[str, str]:
        if self._disk_static:
            return self._disk_static
        mapping: dict[str, str] = {}
        rows = _wmi_query("root/microsoft/windows/storage",
                          "SELECT MediaType,BusType,Size,HealthStatus,FriendlyName FROM MSFT_PhysicalDisk",
                          ["MediaType", "BusType", "FriendlyName", "HealthStatus"])
        for r in rows:
            mt = {3: "HDD", 4: "SSD", 5: "SCM"}.get(r.get("MediaType"), "Unknown")
            bus = r.get("BusType")
            if mt == "SSD":
                mt = "NVMe SSD" if bus == 17 else "SATA SSD"
            mapping[str(r.get("FriendlyName"))] = mt
        self._disk_static = mapping
        return mapping

    def disk_rates(self) -> tuple[Optional[float], Optional[float]]:
        """Returns (read MB/s, write MB/s) between consecutive calls."""
        if not psutil:
            return (None, None)
        import time
        io = psutil.disk_io_counters()
        now = time.monotonic()
        if not io:
            return (None, None)
        prev = self._last_disk_io
        self._last_disk_io = (now, io.read_bytes, io.write_bytes)
        if not prev:
            return (None, None)
        dt = now - prev[0]
        if dt <= 0:
            return (None, None)
        mb = 1024 ** 2
        return (round((io.read_bytes - prev[1]) / dt / mb, 2),
                round((io.write_bytes - prev[2]) / dt / mb, 2))

    def net_rates(self) -> tuple[Optional[float], Optional[float]]:
        """Returns (down Mbps, up Mbps)."""
        if not psutil:
            return (None, None)
        import time
        io = psutil.net_io_counters()
        now = time.monotonic()
        prev = self._last_net_io
        self._last_net_io = (now, io.bytes_recv, io.bytes_sent)
        if not prev:
            return (None, None)
        dt = now - prev[0]
        if dt <= 0:
            return (None, None)
        return (round((io.bytes_recv - prev[1]) * 8 / dt / 1e6, 2),
                round((io.bytes_sent - prev[2]) * 8 / dt / 1e6, 2))

    def snapshot(self) -> dict:
        cpu, mem = self.cpu(), self.memory()
        gpus = self.gpus()
        r, w = self.disk_rates()
        down, up = self.net_rates()
        return {
            "cpu": cpu, "memory": mem, "gpus": gpus, "disks": self.disks(),
            "disk_read_mb_s": r, "disk_write_mb_s": w,
            "net_down_mbps": down, "net_up_mbps": up,
        }


MONITOR = HardwareMonitor()
