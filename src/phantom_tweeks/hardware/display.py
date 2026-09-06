"""Display and refresh-rate detection.

Feeds the Input Latency analysis: FPS relative to refresh rate is the single
most useful latency signal available without special hardware.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..core.platform_info import IS_WINDOWS
from .monitor import _wmi_query


@dataclass
class Display:
    name: str
    width: Optional[int] = None
    height: Optional[int] = None
    refresh_hz: Optional[int] = None
    primary: bool = False

    def render(self) -> str:
        res = (f"{self.width}x{self.height}" if self.width else "unknown resolution")
        hz = f"{self.refresh_hz} Hz" if self.refresh_hz else "refresh unknown"
        return f"{self.name}: {res} @ {hz}" + ("  (primary)" if self.primary else "")


def detect() -> list[Display]:
    """Enumerate displays. Uses the Win32 API directly — it is the only source
    that reports the *current* refresh rate rather than a capability list."""
    out: list[Display] = []
    if not IS_WINDOWS:
        return out
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()

        class DEVMODE(ctypes.Structure):
            _fields_ = [
                ("dmDeviceName", wintypes.WCHAR * 32),
                ("dmSpecVersion", wintypes.WORD),
                ("dmDriverVersion", wintypes.WORD),
                ("dmSize", wintypes.WORD),
                ("dmDriverExtra", wintypes.WORD),
                ("dmFields", wintypes.DWORD),
                ("dmPositionX", ctypes.c_long),
                ("dmPositionY", ctypes.c_long),
                ("dmDisplayOrientation", wintypes.DWORD),
                ("dmDisplayFixedOutput", wintypes.DWORD),
                ("dmColor", ctypes.c_short),
                ("dmDuplex", ctypes.c_short),
                ("dmYResolution", ctypes.c_short),
                ("dmTTOption", ctypes.c_short),
                ("dmCollate", ctypes.c_short),
                ("dmFormName", wintypes.WCHAR * 32),
                ("dmLogPixels", wintypes.WORD),
                ("dmBitsPerPel", wintypes.DWORD),
                ("dmPelsWidth", wintypes.DWORD),
                ("dmPelsHeight", wintypes.DWORD),
                ("dmDisplayFlags", wintypes.DWORD),
                ("dmDisplayFrequency", wintypes.DWORD),
                ("dmICMMethod", wintypes.DWORD),
                ("dmICMIntent", wintypes.DWORD),
                ("dmMediaType", wintypes.DWORD),
                ("dmDitherType", wintypes.DWORD),
                ("dmReserved1", wintypes.DWORD),
                ("dmReserved2", wintypes.DWORD),
                ("dmPanningWidth", wintypes.DWORD),
                ("dmPanningHeight", wintypes.DWORD),
            ]

        class DISPLAY_DEVICE(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("DeviceName", wintypes.WCHAR * 32),
                ("DeviceString", wintypes.WCHAR * 128),
                ("StateFlags", wintypes.DWORD),
                ("DeviceID", wintypes.WCHAR * 128),
                ("DeviceKey", wintypes.WCHAR * 128),
            ]

        ENUM_CURRENT_SETTINGS = -1
        ATTACHED = 0x00000001
        PRIMARY = 0x00000004

        i = 0
        while True:
            dd = DISPLAY_DEVICE()
            dd.cb = ctypes.sizeof(DISPLAY_DEVICE)
            if not user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
                break
            i += 1
            if not (dd.StateFlags & ATTACHED):
                continue
            dm = DEVMODE()
            dm.dmSize = ctypes.sizeof(DEVMODE)
            if user32.EnumDisplaySettingsW(dd.DeviceName, ENUM_CURRENT_SETTINGS,
                                           ctypes.byref(dm)):
                out.append(Display(
                    name=dd.DeviceString or dd.DeviceName,
                    width=int(dm.dmPelsWidth), height=int(dm.dmPelsHeight),
                    refresh_hz=int(dm.dmDisplayFrequency),
                    primary=bool(dd.StateFlags & PRIMARY),
                ))
    except Exception:
        return out
    return out


def primary() -> Optional[Display]:
    displays = detect()
    return next((d for d in displays if d.primary), displays[0] if displays else None)


def max_refresh_available(device_name: Optional[str] = None) -> Optional[int]:
    """Highest refresh rate the primary display supports at its current resolution.

    Used to detect the very common case of a 144 Hz monitor left running at 60 Hz.
    """
    if not IS_WINDOWS:
        return None
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        cur = primary()
        if not cur:
            return None

        class DEVMODE(ctypes.Structure):
            _fields_ = [("dmDeviceName", wintypes.WCHAR * 32),
                        ("dmSpecVersion", wintypes.WORD),
                        ("dmDriverVersion", wintypes.WORD),
                        ("dmSize", wintypes.WORD),
                        ("dmDriverExtra", wintypes.WORD),
                        ("dmFields", wintypes.DWORD),
                        ("dmPositionX", ctypes.c_long),
                        ("dmPositionY", ctypes.c_long),
                        ("dmDisplayOrientation", wintypes.DWORD),
                        ("dmDisplayFixedOutput", wintypes.DWORD),
                        ("dmColor", ctypes.c_short),
                        ("dmDuplex", ctypes.c_short),
                        ("dmYResolution", ctypes.c_short),
                        ("dmTTOption", ctypes.c_short),
                        ("dmCollate", ctypes.c_short),
                        ("dmFormName", wintypes.WCHAR * 32),
                        ("dmLogPixels", wintypes.WORD),
                        ("dmBitsPerPel", wintypes.DWORD),
                        ("dmPelsWidth", wintypes.DWORD),
                        ("dmPelsHeight", wintypes.DWORD),
                        ("dmDisplayFlags", wintypes.DWORD),
                        ("dmDisplayFrequency", wintypes.DWORD),
                        ("dmICMMethod", wintypes.DWORD),
                        ("dmICMIntent", wintypes.DWORD),
                        ("dmMediaType", wintypes.DWORD),
                        ("dmDitherType", wintypes.DWORD),
                        ("dmReserved1", wintypes.DWORD),
                        ("dmReserved2", wintypes.DWORD),
                        ("dmPanningWidth", wintypes.DWORD),
                        ("dmPanningHeight", wintypes.DWORD)]

        best = 0
        idx = 0
        while True:
            dm = DEVMODE()
            dm.dmSize = ctypes.sizeof(DEVMODE)
            if not user32.EnumDisplaySettingsW(None, idx, ctypes.byref(dm)):
                break
            idx += 1
            if (dm.dmPelsWidth == cur.width and dm.dmPelsHeight == cur.height
                    and dm.dmDisplayFrequency > best):
                best = int(dm.dmDisplayFrequency)
        return best or None
    except Exception:
        return None


def analyze_input_latency(avg_fps: Optional[float] = None,
                          gpu_util: Optional[float] = None,
                          cpu_util: Optional[float] = None) -> dict:
    """Honest input-responsiveness assessment.

    Deliberately makes no claim about removing milliseconds — it reports the
    measurable relationships that actually drive perceived latency.
    """
    disp = primary()
    max_hz = max_refresh_available()
    findings: list[str] = []
    recs: list[str] = []

    if disp is None:
        return {
            "display": None, "refresh_hz": None, "max_refresh_hz": None,
            "findings": ["Display information is unavailable on this platform."],
            "recommendations": ["Run Phantom Tweeks on Windows for display analysis."],
        }

    findings.append(disp.render())

    if disp.refresh_hz and max_hz and max_hz > disp.refresh_hz + 1:
        findings.append(
            f"Your display supports {max_hz} Hz but is running at {disp.refresh_hz} Hz.")
        recs.append(
            f"Set the refresh rate to {max_hz} Hz in Settings → System → Display → "
            f"Advanced display. This is one of the few changes that reliably reduces "
            f"perceived latency, and Phantom Tweeks will not change it for you.")

    if avg_fps and disp.refresh_hz:
        ratio = avg_fps / disp.refresh_hz
        if ratio < 0.85:
            findings.append(
                f"Average FPS ({avg_fps:.0f}) is below your refresh rate "
                f"({disp.refresh_hz} Hz).")
            recs.append("Frame rate is the limiting factor. Lowering graphics settings "
                        "will improve responsiveness more than any Windows tweak.")
        elif ratio > 1.15:
            findings.append(
                f"Average FPS ({avg_fps:.0f}) exceeds your refresh rate "
                f"({disp.refresh_hz} Hz).")
            recs.append(
                f"With VRR enabled, cap FPS a few frames below {disp.refresh_hz} to stay "
                "inside the variable-refresh window — this generally gives lower and more "
                "consistent latency than an uncapped frame rate.")

    if gpu_util is not None and gpu_util >= 97:
        findings.append(f"GPU utilisation is saturated at {gpu_util:.0f}%.")
        recs.append("Your GPU is consistently saturated. Reducing graphics settings may "
                    "improve responsiveness by increasing frame rate.")
    if cpu_util is not None and cpu_util >= 92:
        recs.append("CPU utilisation is very high, which adds frame-time variance. "
                    "Review the Background Analyzer before changing graphics settings.")

    if not recs:
        recs.append("No change recommended. Nothing measurable is limiting input "
                    "responsiveness right now.")

    return {
        "display": disp.render(),
        "refresh_hz": disp.refresh_hz,
        "max_refresh_hz": max_hz,
        "findings": findings,
        "recommendations": recs,
        "note": ("Phantom Tweeks measures the factors that influence latency. It does "
                 "not claim to remove milliseconds it has not measured."),
    }
