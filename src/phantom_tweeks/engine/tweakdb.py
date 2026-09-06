"""The Tweak Encyclopedia - every popular "gaming tweak", with a verdict.

Why this exists
---------------
Sites like miztweakz, risxntweaks and hone.gg, plus countless YouTube guides
and .reg files, circulate the same list of Windows tweaks. Some are genuinely
useful. Several do nothing measurable. A few are actively harmful, and two of
the most widely shared will get you banned from competitive games or leave
your PC exposed to known CPU vulnerabilities.

Phantom Tweeks catalogues all of them - including the ones it refuses to
apply - because "we won't do that, and here is exactly why" is far more useful
to a user than silently omitting it and leaving them to find the .reg file
somewhere worse.

Worth noting: Hone, the largest commercial product in this space, explicitly
states it cannot guarantee more FPS or lower latency, and backs up registry
values before changing them. The honest position is also the mainstream one.
Marketing that promises a fixed FPS number is the outlier.

Verdicts
--------
SAFE        Real, understood benefit. Reversible. Phantom Tweeks can apply it.
SITUATIONAL Helps in specific cases only. Applied only when detection says so.
PLACEBO     No measurable effect on modern Windows. Documented, never applied.
HARMFUL     Causes instability, security exposure or bans. Never applied.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

SAFE = "SAFE"
SITUATIONAL = "SITUATIONAL"
PLACEBO = "PLACEBO"
HARMFUL = "HARMFUL"

_ORDER = {SAFE: 0, SITUATIONAL: 1, PLACEBO: 2, HARMFUL: 3}


@dataclass(frozen=True)
class Tweak:
    id: str
    name: str
    verdict: str
    summary: str
    detail: str
    registry: str = ""
    also_known_as: tuple = ()
    evidence: str = ""
    # Only set for tweaks Phantom Tweeks implements; links to catalog.py.
    catalog_id: str = ""

    @property
    def applied_by_us(self) -> bool:
        return bool(self.catalog_id)

    def render(self) -> str:
        out = [f"[{self.verdict}] {self.name}", f"  {self.summary}"]
        if self.registry:
            out.append(f"  Registry: {self.registry}")
        if self.also_known_as:
            out.append(f"  Also called: {', '.join(self.also_known_as)}")
        out.append(f"  {self.detail}")
        if self.evidence:
            out.append(f"  Evidence: {self.evidence}")
        out.append("  Phantom Tweeks: " + (
            f"implements this ({self.catalog_id})" if self.catalog_id
            else "documents this but does not apply it"))
        return "\n".join(out)


TWEAKS: tuple[Tweak, ...] = (

    # ------------------------------------------------------------ SAFE
    Tweak(
        "game_mode", "Windows Game Mode", SAFE,
        "Defers background scheduling and Windows Update while a game runs.",
        "A supported Microsoft feature, not a hack. Helps frame-time "
        "consistency more than average FPS. Costs nothing and is trivially "
        "reversible.",
        registry=r"HKCU\Software\Microsoft\GameBar\AllowAutoGameMode",
        catalog_id="win.game_mode"),

    Tweak(
        "gpu_preference", "High-performance GPU preference", SAFE,
        "Pins a game to the discrete GPU instead of integrated graphics.",
        "On laptops a game can silently run on the iGPU, which costs far more "
        "performance than every registry tweak on this page combined. This is "
        "one of the few changes that can genuinely double your frame rate - "
        "but only if the problem existed in the first place.",
        registry=r"HKCU\Software\Microsoft\DirectX\UserGpuPreferences",
        catalog_id="gfx.gpu_preference"),

    Tweak(
        "disable_gamedvr", "Disable Game DVR / background recording", SAFE,
        "Stops Xbox Game Bar continuously recording gameplay.",
        "Background capture costs real GPU time and memory bandwidth. If you "
        "do not use clip recording there is no reason to pay for it. This is "
        "one of the more defensible items on the usual tweak lists.",
        registry=r"HKCU\System\GameConfigStore\GameDVR_Enabled",
        also_known_as=("Disable Xbox Game Bar", "GameDVR off"),
        catalog_id="win.game_dvr"),

    Tweak(
        "visual_effects", "Reduce Windows animations", SAFE,
        "Turns off window animations and transparency.",
        "Frees a small amount of GPU and compositor work. The desktop feels "
        "snappier. It will not change in-game FPS - the desktop compositor is "
        "already idle while a fullscreen game is running.",
        registry=r"HKCU\Control Panel\Desktop\UserPreferencesMask",
        catalog_id="win.visual_effects"),

    Tweak(
        "mouse_accel", "Disable mouse acceleration", SAFE,
        "Makes mouse movement 1:1 with hand movement.",
        "Not a performance tweak at all - it is a consistency one. Enhanced "
        "Pointer Precision makes the same physical movement produce different "
        "cursor distances depending on speed, which fights muscle memory in "
        "aim-based games.",
        registry=r"HKCU\Control Panel\Mouse\MouseSpeed",
        also_known_as=("Enhanced Pointer Precision off", "Raw input"),
        catalog_id="input.mouse_accel"),

    Tweak(
        "high_perf_power", "High performance power plan", SAFE,
        "Stops the CPU dropping to low clock speeds between frames.",
        "Genuinely helps on desktops, especially for 1% lows, because "
        "aggressive core parking adds latency when load spikes. On a laptop "
        "on battery it will cost you runtime and may cause thermal "
        "throttling, which is why Phantom Tweeks detects the machine type "
        "first.",
        catalog_id="power.high_performance"),

    Tweak(
        "storage_sense", "Disable Storage Sense during play", SAFE,
        "Prevents automatic cleanup running mid-session.",
        "Disk cleanup competing with a game for I/O is a real cause of "
        "stutter. Postponing it is sensible; disabling it forever is not.",
        registry=r"HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\StorageSense",
        catalog_id="storage.storage_sense"),

    # ----------------------------------------------------- SITUATIONAL
    Tweak(
        "hags", "Hardware-Accelerated GPU Scheduling", SITUATIONAL,
        "Lets the GPU manage its own frame queue instead of the CPU.",
        "Removes one buffering stage. Measurably helps on some driver and "
        "title combinations and measurably hurts on others - it is genuinely "
        "hardware-dependent. Requires a reboot. Benchmark before and after "
        "rather than assuming.",
        registry=r"HKLM\System\CurrentControlSet\Control\GraphicsDrivers\HwSchMode",
        catalog_id="gfx.hags"),

    Tweak(
        "nagle", "Disable Nagle's algorithm", SITUATIONAL,
        "Sends small TCP packets immediately instead of batching them.",
        "Real and well understood, but narrower than the guides claim. Most "
        "competitive games use UDP, which Nagle never touches. It can help "
        "TCP-based titles and chat, and costs a little bandwidth efficiency. "
        "It does not lower your ping to the game server.",
        registry=r"HKLM\SYSTEM\...\Tcpip\Parameters\Interfaces\{GUID}\TcpAckFrequency",
        also_known_as=("TcpAckFrequency", "TCPNoDelay", "TcpDelAckTicks"),
        evidence="Nagle applies to TCP only; most game traffic is UDP."),

    Tweak(
        "network_throttling", "NetworkThrottlingIndex = ffffffff", SITUATIONAL,
        "Removes the MMCSS limit on non-multimedia network packets.",
        "A legacy Vista-era throttle of 10 packets/ms for non-multimedia "
        "traffic. Disabling it can help on very high-throughput links but is "
        "irrelevant to typical game traffic volumes. Widely presented as a "
        "ping fix; it is not one.",
        registry=r"HKLM\SOFTWARE\...\Multimedia\SystemProfile\NetworkThrottlingIndex",
        evidence="Documented by Microsoft as a multimedia scheduling limit, "
                 "not a latency control."),

    Tweak(
        "fullscreen_optimizations", "Disable fullscreen optimizations", SITUATIONAL,
        "Forces true exclusive fullscreen instead of borderless emulation.",
        "Can reduce latency by one frame in older titles. On modern Windows "
        "the flip-model path is usually as fast or faster, and disabling it "
        "may break alt-tab, HDR and overlays. Test per game.",
        registry=r"HKCU\System\GameConfigStore\GameDVR_FSEBehaviorMode"),

    Tweak(
        "prefetch_superfetch", "Disable Prefetch / SysMain", SITUATIONAL,
        "Stops Windows preloading frequently used data into RAM.",
        "Made sense on mechanical drives with 4 GB of RAM. On an SSD with "
        "16 GB it typically makes launches slower, because SysMain was "
        "helping. Only consider it if you have measured a specific problem.",
        registry=r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management\PrefetchParameters",
        also_known_as=("Disable SysMain", "Disable Superfetch")),

    # --------------------------------------------------------- PLACEBO
    Tweak(
        "system_responsiveness", "SystemResponsiveness = 0", PLACEBO,
        "Claims to reserve 100% of CPU for foreground games.",
        "The value sets the percentage of CPU that MMCSS reserves for "
        "low-priority work. Windows clamps very low values and does not hand "
        "the remainder to your game. Present on essentially every tweak list; "
        "no controlled benchmark shows a consistent gain.",
        registry=r"HKLM\SOFTWARE\...\Multimedia\SystemProfile\SystemResponsiveness",
        evidence="MMCSS clamps the value; it governs multimedia scheduling, "
                 "not game rendering."),

    Tweak(
        "mmcss_gpu_priority", "GPU Priority = 8, Priority = 6", PLACEBO,
        "Claims to raise your game's GPU scheduling priority.",
        "These are MMCSS task-profile values, not Windows process priorities. "
        "They apply to threads that register with MMCSS - which games "
        "generally do not for rendering. Setting 'GPU Priority' to 8 does not "
        "make the GPU serve your game first.",
        registry=r"HKLM\SOFTWARE\...\Multimedia\SystemProfile\Tasks\Games",
        also_known_as=("SFIO Priority", "Scheduling Category High"),
        evidence="MMCSS task profiles affect registered multimedia threads "
                 "only, not the D3D present path."),

    Tweak(
        "win32_priority", "Win32PrioritySeparation = 26 (hex)", PLACEBO,
        "Claims to give the foreground application maximum CPU attention.",
        "It does adjust quantum length and foreground boost, but the effect "
        "on a fullscreen game that is already the foreground process is "
        "negligible. Some values actively hurt by shortening quanta and "
        "increasing context switching. 0x26 is cargo-culted, not derived.",
        registry=r"HKLM\SYSTEM\CurrentControlSet\Control\PriorityControl"),

    Tweak(
        "timer_resolution", "Force 0.5 ms timer resolution", PLACEBO,
        "Claims lower timer resolution reduces input latency.",
        "Windows 10 2004+ changed timer behaviour so per-process requests no "
        "longer apply globally. Games that need a high-resolution timer "
        "already request one. Forcing it system-wide raises power draw and "
        "can increase DPC latency.",
        also_known_as=("TimerResolution", "ISLC", "GlobalTimerResolutionRequests")),

    Tweak(
        "disable_hpet", "Disable HPET", PLACEBO,
        "Claims disabling the High Precision Event Timer boosts FPS.",
        "Was a real fix for specific AMD chipset bugs around 2017. On modern "
        "hardware Windows chooses its timer source sensibly and forcing it "
        "can make latency worse or cause boot problems. There is no supported "
        "registry setting that reliably disables it.",
        evidence="Chipset-specific historical issue; no longer generally "
                 "applicable."),

    Tweak(
        "clear_standby_memory", "RAM cleaners / clear standby list", PLACEBO,
        "Claims to 'free' memory for your game.",
        "Standby memory is cached data that Windows discards instantly when "
        "an application needs it. Flushing it does not free anything that was "
        "not already available - it just throws away a cache you paid to "
        "build, making the next load slower.",
        also_known_as=("Memory optimizer", "RAM booster", "Empty working set")),

    Tweak(
        "disable_pagefile", "Disable the pagefile", PLACEBO,
        "Claims that with enough RAM the pagefile only slows you down.",
        "Windows uses the pagefile for committed memory even when RAM is "
        "free, and some games allocate more commit than they touch. Disabling "
        "it causes out-of-memory crashes in exactly the titles that need the "
        "most memory. Leave it system-managed.",
        evidence="Commit charge is not the same as physical memory use."),

    Tweak(
        "msi_mode", "Force MSI mode on the GPU", PLACEBO,
        "Claims message-signalled interrupts reduce DPC latency.",
        "Modern GPU drivers already enable MSI where it helps. Forcing it on "
        "devices that do not support it properly causes device failures, and "
        "the tools that do this write directly to PCI configuration space.",
        also_known_as=("MSI Utility", "Interrupt affinity")),

    # --------------------------------------------------------- HARMFUL
    Tweak(
        "disable_defender", "Disable Windows Defender", HARMFUL,
        "Claims real-time scanning costs FPS.",
        "Real-time protection has a measurable but small cost, typically "
        "1-2% and mostly during file access rather than gameplay. Disabling "
        "it leaves you running untrusted game mods and cheat-adjacent "
        "downloads with no protection at all. Add a game folder exclusion "
        "instead - same benefit, none of the exposure. Phantom Tweeks will "
        "never disable security software.",
        registry=r"HKLM\SOFTWARE\Policies\Microsoft\Windows Defender\DisableAntiSpyware"),

    Tweak(
        "disable_mitigations", "Disable Spectre/Meltdown mitigations", HARMFUL,
        "Claims CPU security mitigations cost 5-15% performance.",
        "The performance claim was true on 2018-era CPUs and is largely "
        "obsolete on current hardware with in-silicon fixes. What remains is "
        "the cost: you re-expose your machine to speculative-execution "
        "attacks that read memory across process boundaries - including your "
        "browser's saved passwords. Never worth it.",
        registry=r"HKLM\SYSTEM\...\Memory Management\FeatureSettingsOverride",
        also_known_as=("FeatureSettingsOverride", "Disable Spectre patches")),

    Tweak(
        "disable_uac", "Disable User Account Control", HARMFUL,
        "Claims UAC prompts add overhead.",
        "UAC costs nothing while a game is running - it only acts at "
        "elevation time. Disabling it means every program you launch, "
        "including malware, runs with full administrative rights silently. "
        "This one appears on tweak lists purely because it stops a dialog "
        "the author found annoying.",
        registry=r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System\EnableLUA"),

    Tweak(
        "disable_core_isolation", "Disable Core Isolation / VBS / HVCI", HARMFUL,
        "Claims virtualisation-based security costs 5-10% FPS.",
        "The performance claim has some truth on older CPUs. But several "
        "anti-cheat systems now REQUIRE VBS or memory integrity - Valorant's "
        "Vanguard notably enforces Secure Boot and TPM. Disabling it can "
        "leave you unable to launch the game you were trying to optimise, and "
        "removes a meaningful defence against kernel-level malware.",
        also_known_as=("Memory Integrity off", "Disable VBS", "Disable HVCI")),

    Tweak(
        "delete_services", "Delete Windows services (sc delete)", HARMFUL,
        "Claims removing services frees resources permanently.",
        "Disabling a service is reversible. **Deleting** one is not - it "
        "cannot be restored without repairing or reinstalling Windows, and "
        "Windows Update will often fail afterwards. Several widely shared "
        "scripts delete DiagTrack and dmwappushservice this way. A stopped "
        "service consumes no CPU, so there is no benefit to deleting it.",
        also_known_as=("sc delete DiagTrack", "Service ripper")),

    Tweak(
        "remove_defender_folder", "Remove Defender / Windows Update files", HARMFUL,
        "Claims deleting the files stops them consuming resources.",
        "Corrupts the Windows servicing stack. Updates then fail with opaque "
        "errors and the usual repair paths (DISM, SFC) cannot fix it because "
        "the components they restore from are gone.",
        also_known_as=("Windows debloat script", "Remove WinSxS")),

    Tweak(
        "cpu_affinity_game", "Force CPU affinity / disable cores", HARMFUL,
        "Claims pinning a game to specific cores stops scheduler thrashing.",
        "The Windows scheduler already understands your CPU topology, "
        "including which cores are preferred and which are E-cores. Manual "
        "affinity commonly makes things worse by preventing threads from "
        "migrating off a busy core - and on hybrid CPUs it can pin a game to "
        "efficiency cores. Some anti-cheat systems also flag processes that "
        "manipulate another process's affinity.",
        also_known_as=("Core parking off", "Disable E-cores", "Affinity mask")),

    Tweak(
        "registry_cleaner", "Registry cleaners", HARMFUL,
        "Claims a smaller registry loads faster.",
        "The registry is a memory-mapped database; a few thousand orphaned "
        "keys cost nothing measurable. Microsoft has stated it does not "
        "support registry cleaning tools. The downside - a cleaner removing "
        "a key some application actually needed - is real and hard to "
        "diagnose.",
        evidence="Microsoft does not support registry cleaning utilities."),

    Tweak(
        "auto_overclock", "One-click overclocking / undervolting", HARMFUL,
        "Claims free performance from higher clocks.",
        "Silicon quality varies between individual chips. A setting that is "
        "stable on the developer's CPU can cause silent data corruption on "
        "yours, and the failure mode is subtle: crashes hours later, "
        "corrupted saves, an unbootable system. Phantom Tweeks will never "
        "auto-overclock. If you want to overclock, do it deliberately in your "
        "BIOS with proper stability testing.",
        also_known_as=("Auto OC", "Curve optimizer", "One-click undervolt")),
)

BY_ID = {t.id: t for t in TWEAKS}


def by_verdict(verdict: str) -> list[Tweak]:
    return [t for t in TWEAKS if t.verdict == verdict]


def counts() -> dict:
    return {v: len(by_verdict(v)) for v in (SAFE, SITUATIONAL, PLACEBO, HARMFUL)}


def search(term: str) -> list[Tweak]:
    """Find a tweak by name, alias or registry path.

    Lets someone paste a value they saw in a YouTube guide and get a straight
    answer about whether it does anything.
    """
    needle = (term or "").strip().lower()
    if not needle:
        return []
    hits = []
    for t in TWEAKS:
        haystack = " ".join((t.id, t.name, t.summary, t.detail, t.registry,
                             " ".join(t.also_known_as))).lower()
        if needle in haystack:
            hits.append(t)
    return sorted(hits, key=lambda t: _ORDER[t.verdict])


def report() -> str:
    n = counts()
    out = [
        "THE TWEAK ENCYCLOPEDIA",
        "",
        f"{len(TWEAKS)} popular Windows gaming tweaks, each with a verdict.",
        f"  {n[SAFE]} safe   {n[SITUATIONAL]} situational   "
        f"{n[PLACEBO]} placebo   {n[HARMFUL]} harmful",
        "",
        "Phantom Tweeks implements the safe and situational ones. The rest are",
        "listed so you know they were considered and rejected, and why - which",
        "is more useful than pretending they do not exist.",
        "",
    ]
    for verdict in (SAFE, SITUATIONAL, PLACEBO, HARMFUL):
        out += [f"{'=' * 62}", f"{verdict}", f"{'=' * 62}", ""]
        for t in by_verdict(verdict):
            out += [t.render(), ""]
    return "\n".join(out)
