"""Game detection across launchers.

Detection is read-only. Phantom Tweeks parses launcher manifests and inspects
running processes; it never writes to, patches, or launches game files.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore

from .platform_info import IS_WINDOWS
from .shield import ANTI_CHEAT, LAUNCHERS

LAUNCHER_OF_PROCESS = {
    "steam.exe": "Steam",
    "epicgameslauncher.exe": "Epic Games",
    "battle.net.exe": "Battle.net",
    "riotclientservices.exe": "Riot",
    "eadesktop.exe": "EA",
    "upc.exe": "Ubisoft Connect",
    "gamingservices.exe": "Xbox / Game Pass",
    "galaxyclient.exe": "GOG Galaxy",
}

# Executables that live in game folders but are not the game itself.
NON_GAME_HINTS = (
    "unitycrashhandler", "crashreport", "launcher", "setup", "installer",
    "redist", "vcredist", "dxsetup", "easyanticheat", "battleye", "uninstall",
)


@dataclass
class InstalledGame:
    name: str
    launcher: str
    install_dir: str
    app_id: Optional[str] = None
    executable_path: Optional[str] = None


@dataclass
class RunningGame:
    name: str
    pid: int
    executable: str
    executable_path: Optional[str]
    launcher: Optional[str] = None
    anti_cheat: Optional[str] = None
    process_tree: list[int] = field(default_factory=list)
    install_dir: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "name": self.name, "pid": self.pid, "executable": self.executable,
            "executable_path": self.executable_path, "launcher": self.launcher,
            "anti_cheat": self.anti_cheat, "install_dir": self.install_dir,
            "process_count": len(self.process_tree),
        }


# ---------------- library scanning ----------------

def _steam_roots() -> list[Path]:
    roots: list[Path] = []
    if IS_WINDOWS:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                roots.append(Path(winreg.QueryValueEx(k, "SteamPath")[0]))
        except Exception:
            pass
        for guess in (r"C:\Program Files (x86)\Steam", r"C:\Steam"):
            p = Path(guess)
            if p.exists():
                roots.append(p)
    return [r for r in dict.fromkeys(roots) if r.exists()]


def scan_steam() -> list[InstalledGame]:
    games: list[InstalledGame] = []
    for root in _steam_roots():
        libs = [root / "steamapps"]
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            try:
                for m in re.finditer(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="ignore")):
                    libs.append(Path(m.group(1).replace("\\\\", "\\")) / "steamapps")
            except OSError:
                pass
        for lib in dict.fromkeys(libs):
            if not lib.exists():
                continue
            for manifest in lib.glob("appmanifest_*.acf"):
                try:
                    text = manifest.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                name = re.search(r'"name"\s+"([^"]+)"', text)
                appid = re.search(r'"appid"\s+"([^"]+)"', text)
                folder = re.search(r'"installdir"\s+"([^"]+)"', text)
                if name and folder:
                    games.append(InstalledGame(
                        name.group(1), "Steam",
                        str(lib / "common" / folder.group(1)),
                        appid.group(1) if appid else None))
    return games


def scan_epic() -> list[InstalledGame]:
    games: list[InstalledGame] = []
    base = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "Epic/EpicGamesLauncher/Data/Manifests"
    if not base.exists():
        return games
    import json
    for item in base.glob("*.item"):
        try:
            d = json.loads(item.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
        if d.get("DisplayName") and d.get("InstallLocation"):
            games.append(InstalledGame(
                d["DisplayName"], "Epic Games", d["InstallLocation"],
                d.get("AppName"),
                str(Path(d["InstallLocation"]) / d["LaunchExecutable"])
                if d.get("LaunchExecutable") else None))
    return games


def scan_xbox() -> list[InstalledGame]:
    games: list[InstalledGame] = []
    if not IS_WINDOWS:
        return games
    for drive in "CDEFG":
        p = Path(f"{drive}:/XboxGames")
        if p.exists():
            for child in p.iterdir():
                if child.is_dir():
                    games.append(InstalledGame(child.name, "Xbox / Game Pass", str(child)))
    return games


def scan_generic_registry() -> list[InstalledGame]:
    """Battle.net / EA / Ubisoft / GOG / standalone via uninstall entries."""
    games: list[InstalledGame] = []
    if not IS_WINDOWS:
        return games
    import winreg
    keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    vendor_map = {
        "blizzard": "Battle.net", "battle.net": "Battle.net",
        "riot": "Riot", "electronic arts": "EA", "ea games": "EA",
        "ubisoft": "Ubisoft Connect", "gog.com": "GOG Galaxy",
    }
    for hive, path in keys:
        try:
            with winreg.OpenKey(hive, path) as root:
                for i in range(winreg.QueryInfoKey(root)[0]):
                    try:
                        sub = winreg.EnumKey(root, i)
                        with winreg.OpenKey(root, sub) as k:
                            name = winreg.QueryValueEx(k, "DisplayName")[0]
                            loc = winreg.QueryValueEx(k, "InstallLocation")[0]
                            pub = ""
                            try:
                                pub = str(winreg.QueryValueEx(k, "Publisher")[0]).lower()
                            except OSError:
                                pass
                            launcher = next((v for kk, v in vendor_map.items() if kk in pub), None)
                            if launcher and loc:
                                games.append(InstalledGame(name, launcher, loc))
                    except OSError:
                        continue
        except OSError:
            continue
    return games


def scan_library() -> list[InstalledGame]:
    seen: dict[str, InstalledGame] = {}
    for fn in (scan_steam, scan_epic, scan_xbox, scan_generic_registry):
        try:
            for g in fn():
                seen.setdefault(g.name.lower(), g)
        except Exception:
            continue
    return sorted(seen.values(), key=lambda g: g.name.lower())


# ---------------- running game detection ----------------

def _looks_like_game(proc, install_dirs: dict[str, InstalledGame]) -> Optional[InstalledGame]:
    try:
        exe = proc.info.get("exe") or ""
        name = (proc.info.get("name") or "").lower()
    except Exception:
        return None
    if not exe or any(h in name for h in NON_GAME_HINTS):
        return None
    if name in LAUNCHERS or name in ANTI_CHEAT:
        return None
    low = exe.lower().replace("/", "\\")
    for d, game in install_dirs.items():
        if low.startswith(d):
            return game
    return None


def detect_running_game(library: Optional[list[InstalledGame]] = None) -> Optional[RunningGame]:
    """Identify the active game via installed-library path matching."""
    if not psutil:
        return None
    library = library if library is not None else scan_library()
    dirs = {g.install_dir.lower().replace("/", "\\").rstrip("\\") + "\\": g
            for g in library if g.install_dir}
    best = None
    best_mem = 0
    for proc in psutil.process_iter(["pid", "name", "exe", "memory_info"]):
        game = _looks_like_game(proc, dirs)
        if not game:
            continue
        try:
            mem = proc.info["memory_info"].rss
        except Exception:
            mem = 0
        if mem > best_mem:   # the game itself is the heaviest process in its folder
            best_mem, best = mem, (proc, game)
    if not best:
        return None
    proc, game = best
    running = RunningGame(
        name=game.name, pid=proc.info["pid"],
        executable=proc.info.get("name") or "",
        executable_path=proc.info.get("exe"),
        launcher=game.launcher, install_dir=game.install_dir,
    )
    running.process_tree = _related_pids(proc)
    running.anti_cheat = _detect_anti_cheat(game.install_dir)
    return running


def _related_pids(proc) -> list[int]:
    pids = [proc.pid]
    try:
        for child in proc.children(recursive=True):
            pids.append(child.pid)
        parent = proc.parent()
        if parent and (parent.name() or "").lower() in LAUNCHERS:
            pids.append(parent.pid)
    except Exception:
        pass
    return pids


def _detect_anti_cheat(install_dir: Optional[str]) -> Optional[str]:
    if psutil:
        for p in psutil.process_iter(["name"]):
            n = (p.info.get("name") or "").lower()
            for pattern, label in ANTI_CHEAT.items():
                if n == pattern:
                    return label
    if install_dir and Path(install_dir).exists():
        try:
            for entry in Path(install_dir).rglob("*"):
                low = entry.name.lower()
                if "easyanticheat" in low:
                    return "Easy Anti-Cheat"
                if "battleye" in low:
                    return "BattlEye"
        except (OSError, PermissionError):
            pass
    return None


def game_process_names(game: RunningGame) -> set[str]:
    """Image names Phantom Shield must protect for this game session."""
    names = {game.executable.lower()} if game.executable else set()
    if not psutil:
        return names
    for pid in game.process_tree:
        try:
            names.add(psutil.Process(pid).name().lower())
        except Exception:
            continue
    return names
