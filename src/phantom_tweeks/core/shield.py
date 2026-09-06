"""Phantom Shield — the absolute safety system.

Shield is a *deny* list for automation, not a UI decoration. Any code path in
Phantom Tweeks that could touch a process must call `guard()` first. Guarded
processes are never killed, suspended, re-prioritised, re-affinitised, injected
into, or have their services stopped — by any mode, including Expert Mode.
"""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from typing import Iterable

# --- Built-in protection groups -------------------------------------------
# Matched case-insensitively against the process image name.

LAUNCHERS = {
    "steam.exe": "Steam",
    "steamwebhelper.exe": "Steam",
    "steamservice.exe": "Steam",
    "epicgameslauncher.exe": "Epic Games Launcher",
    "epicwebhelper.exe": "Epic Games Launcher",
    "battle.net.exe": "Battle.net",
    "agent.exe": "Battle.net Agent",
    "riotclientservices.exe": "Riot Client",
    "riotclientux.exe": "Riot Client",
    "eadesktop.exe": "EA App",
    "eabackgroundservice.exe": "EA App",
    "origin.exe": "EA / Origin",
    "upc.exe": "Ubisoft Connect",
    "ubisoftconnect.exe": "Ubisoft Connect",
    "ubisoftgamelauncher.exe": "Ubisoft Connect",
    "gamingservices.exe": "Xbox / Game Pass",
    "gamingservicesnet.exe": "Xbox / Game Pass",
    "xboxpcapp.exe": "Xbox / Game Pass",
    "xbox.exe": "Xbox / Game Pass",
    "galaxyclient.exe": "GOG Galaxy",
    "itch.exe": "itch.io",
    "rockstarservice.exe": "Rockstar Launcher",
    "playgameservices.exe": "Rockstar Launcher",
}

ANTI_CHEAT = {
    "easyanticheat.exe": "Easy Anti-Cheat",
    "easyanticheat_eos.exe": "Easy Anti-Cheat",
    "battleye.exe": "BattlEye",
    "beservice.exe": "BattlEye",
    "vgtray.exe": "Vanguard",
    "vgc.exe": "Vanguard",
    "faceitservice.exe": "FACEIT AC",
    "esea.exe": "ESEA AC",
    "mhyprot*.exe": "mhyprot",
}

COMMS_AND_CAPTURE = {
    "discord.exe": "Discord",
    "discordptb.exe": "Discord",
    "discordcanary.exe": "Discord",
    "teamspeak3.exe": "TeamSpeak",
    "ts3client_win64.exe": "TeamSpeak",
    "mumble.exe": "Mumble",
    "obs64.exe": "OBS Studio",
    "obs32.exe": "OBS Studio",
    "streamlabs obs.exe": "Streamlabs",
    "xsplit.core.exe": "XSplit",
    "ms-teams.exe": "Microsoft Teams",
    "zoom.exe": "Zoom",
}

GPU_AND_INPUT = {
    "nvcontainer.exe": "NVIDIA driver service",
    "nvdisplay.container.exe": "NVIDIA display container",
    "nvidia share.exe": "NVIDIA overlay",
    "nvidia web helper.exe": "NVIDIA helper",
    "radeonsoftware.exe": "AMD Radeon Software",
    "amddvr.exe": "AMD ReLive",
    "cncmd.exe": "AMD service",
    "igfxem.exe": "Intel Graphics",
    "igfxcuiservice.exe": "Intel Graphics",
    "steelseriesengine.exe": "SteelSeries Engine",
    "logioptionsplus_agent.exe": "Logitech Options+",
    "lghub.exe": "Logitech G HUB",
    "lghub_agent.exe": "Logitech G HUB",
    "razer synapse service.exe": "Razer Synapse",
    "rzsdkservice.exe": "Razer Synapse",
    "corsair.service.exe": "iCUE",
    "icue.exe": "iCUE",
    "wootility.exe": "Wooting",
    "xboxgameoverlay.exe": "Xbox overlay",
    "controllercompanion.exe": "Controller software",
}

WINDOWS_ESSENTIAL = {
    "system", "system idle process", "registry", "memory compression",
    "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe",
    "lsass.exe", "svchost.exe", "fontdrvhost.exe", "dwm.exe", "explorer.exe",
    "sihost.exe", "ctfmon.exe", "taskhostw.exe", "runtimebroker.exe",
    "shellexperiencehost.exe", "searchhost.exe", "startmenuexperiencehost.exe",
    "audiodg.exe", "spoolsv.exe", "conhost.exe", "wudfhost.exe",
    "msmpeng.exe", "nissrv.exe", "securityhealthservice.exe",
    "securityhealthsystray.exe", "mpdefendercoreservice.exe",
    "mpcmdrun.exe", "wscsvc.exe", "trustedinstaller.exe", "tiworker.exe",
}

# Services that must never be stopped or disabled by automation.
PROTECTED_SERVICES = {
    "windefend", "wscsvc", "securityhealthservice", "mpssvc", "wuauserv",
    "bfe", "eventlog", "rpcss", "dcomlaunch", "audiosrv", "audioendpointbuilder",
    "gamingservices", "gamingservicesnet", "steamservice", "easyanticheat",
    "beservice", "vgc", "nvdisplay.containerlocalsystem", "amdexternalevents",
    "dhcp", "dnscache", "nsi", "netprofm", "power", "profsvc", "themes",
}

CATEGORY_ORDER = [
    "Current Game",
    "Game Launchers",
    "Anti-Cheat",
    "Voice & Capture",
    "GPU & Input",
    "Windows Essential",
    "User Protected",
]


@dataclass
class ProtectedProcess:
    pid: int
    name: str
    label: str
    category: str


@dataclass
class ShieldDecision:
    allowed: bool
    reason: str
    label: str = ""
    category: str = ""


@dataclass
class PhantomShield:
    """Evaluates whether automation may touch a given process."""

    user_protected: set[str] = field(default_factory=set)
    game_processes: set[str] = field(default_factory=set)  # lowercase image names
    active: bool = True

    # -- registration ------------------------------------------------------
    def add_user_protected(self, name: str) -> None:
        if name.strip():
            self.user_protected.add(name.strip().lower())

    def remove_user_protected(self, name: str) -> None:
        self.user_protected.discard(name.strip().lower())

    def set_game_processes(self, names: Iterable[str]) -> None:
        self.game_processes = {n.lower() for n in names if n}

    # -- classification ----------------------------------------------------
    def classify(self, process_name: str | None) -> tuple[str, str] | None:
        """Return (category, label) when protected, else None."""
        if not process_name:
            # Unknown identity: refuse to act. Fail closed.
            return ("Windows Essential", "Unidentified process")
        n = process_name.lower()
        if n in self.game_processes:
            return ("Current Game", process_name)
        for table, category in (
            (LAUNCHERS, "Game Launchers"),
            (ANTI_CHEAT, "Anti-Cheat"),
            (COMMS_AND_CAPTURE, "Voice & Capture"),
            (GPU_AND_INPUT, "GPU & Input"),
        ):
            for pattern, label in table.items():
                if n == pattern or fnmatch.fnmatch(n, pattern):
                    return (category, label)
        if n in WINDOWS_ESSENTIAL:
            return ("Windows Essential", process_name)
        for pattern in self.user_protected:
            if n == pattern or fnmatch.fnmatch(n, pattern):
                return ("User Protected", process_name)
        return None

    def is_protected(self, process_name: str | None) -> bool:
        return self.classify(process_name) is not None

    # -- the gate ----------------------------------------------------------
    def guard(self, process_name: str | None, action: str) -> ShieldDecision:
        """The single choke point. Deny by default for protected processes."""
        hit = self.classify(process_name)
        if hit:
            category, label = hit
            return ShieldDecision(
                allowed=False,
                reason=(
                    f"Phantom Shield blocked '{action}' on {process_name}: "
                    f"protected as {label} ({category}). Phantom Tweeks reports "
                    f"resource usage instead of interfering."
                ),
                label=label,
                category=category,
            )
        return ShieldDecision(True, f"'{action}' permitted for {process_name}.")

    def guard_service(self, service_name: str, action: str) -> ShieldDecision:
        if service_name.lower() in PROTECTED_SERVICES:
            return ShieldDecision(
                False,
                f"Phantom Shield blocked '{action}' on service '{service_name}': "
                "security, audio, gaming and driver services are never touched.",
                label=service_name,
                category="Protected Service",
            )
        return ShieldDecision(True, f"'{action}' permitted for service {service_name}.")

    # -- dashboard ---------------------------------------------------------
    def scan_running(self) -> list[ProtectedProcess]:
        try:
            import psutil
        except ImportError:
            return []
        found: list[ProtectedProcess] = []
        for proc in psutil.process_iter(["pid", "name"]):
            name = proc.info.get("name") or ""
            hit = self.classify(name)
            if hit and not (hit[0] == "Windows Essential" and name.lower() not in WINDOWS_ESSENTIAL):
                found.append(ProtectedProcess(proc.info["pid"], name, hit[1], hit[0]))
        return found

    def dashboard(self) -> dict:
        procs = self.scan_running()
        groups: dict[str, list[str]] = {}
        for p in procs:
            groups.setdefault(p.category, [])
            if p.label not in groups[p.category]:
                groups[p.category].append(p.label)
        return {
            "status": "ACTIVE" if self.active else "INACTIVE",
            "protected_count": len(procs),
            "groups": {c: sorted(groups[c]) for c in CATEGORY_ORDER if c in groups},
            "user_protected": sorted(self.user_protected),
        }


SHIELD = PhantomShield()
