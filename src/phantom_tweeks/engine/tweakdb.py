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



# ----------------------------------------------------------------------
# Extended catalogue. Same rules as above: what it claims, what it
# actually does, and why it earned its verdict.
# ----------------------------------------------------------------------

_EXTENDED = (
    Tweak(
        "menu_show_delay", "MenuShowDelay = 0", SAFE,
        "Removes the 400 ms delay before submenus open.",
        "A genuine responsiveness win for the desktop, and completely "
        "harmless. It changes how quickly menus appear, nothing else. It "
        "will not affect anything inside a game.",
        registry=r"HKCU\\Control Panel\\Desktop\\MenuShowDelay",
    ),
    Tweak(
        "startup_delay", "Remove Explorer startup delay", SAFE,
        "Stops Windows deliberately delaying startup apps after login.",
        "Windows staggers startup programs so the desktop appears "
        "responsive first. Removing the delay makes everything load at "
        "once - faster overall, briefly busier at login.",
        registry=r"HKCU\\...\\Explorer\\Serialize\\StartupDelayInMSec",
    ),
    Tweak(
        "taskbar_animations", "Disable taskbar animations", SAFE,
        "Turns off taskbar and Start menu animation.",
        "Small compositor saving on the desktop. No in-game effect, "
        "because a fullscreen game is not compositing the taskbar.",
        registry=r"HKCU\\...\\Explorer\\Advanced\\TaskbarAnimations",
    ),
    Tweak(
        "transparency", "Disable transparency effects", SAFE,
        "Removes acrylic and blur from Start, taskbar and window chrome.",
        "Blur is genuinely GPU work on the desktop. Measurable on low-end "
        "integrated graphics; irrelevant while a game owns the screen.",
        registry=r"HKCU\\...\\Themes\\Personalize\\EnableTransparency",
    ),
    Tweak(
        "show_seconds", "Show seconds in the clock", PLACEBO,
        "Cosmetic only.",
        "Appears on tweak lists as a 'performance' item. It adds a "
        "per-second redraw of the clock. It is a preference, not an "
        "optimization, and the cost is unmeasurable either way.",
        registry=r"HKCU\\...\\Advanced\\ShowSecondsInSystemClock",
    ),
    Tweak(
        "verbose_status", "Verbose startup messages", PLACEBO,
        "Shows detailed boot and shutdown status text.",
        "A diagnostic aid, useful for finding what stalls a slow "
        "shutdown. It makes nothing faster and is often listed as if it "
        "did.",
        registry=r"HKLM\\...\\Policies\\System\\VerboseStatus",
    ),
    Tweak(
        "fast_startup", "Disable Fast Startup", SITUATIONAL,
        "Makes shutdown a true shutdown instead of a partial hibernate.",
        "Fast Startup shortens boot time but leaves kernel state stale, "
        "which causes odd driver behaviour and is a common cause of 'a "
        "reboot fixed it' problems. Disabling it trades a few seconds of "
        "boot for a genuinely clean start. Worth doing if you see "
        "unexplained device issues.",
        registry=r"HKLM\\SYSTEM\\...\\Power\\HiberbootEnabled",
        also_known_as=('Hiberboot',),
    ),
    Tweak(
        "hibernate_off", "Disable hibernation", SITUATIONAL,
        "Frees disk space equal to a large part of your RAM.",
        "Deletes hiberfil.sys - useful on a small SSD. It does not make "
        "anything faster, and it disables Fast Startup and "
        "resume-from-sleep as a side effect.",
        registry=r"powercfg /hibernate off",
    ),
    Tweak(
        "disable_uac_prompt_dim", "Disable the UAC secure desktop dim", SITUATIONAL,
        "Stops the screen dimming for elevation prompts.",
        "Removes an annoyance and a brief compositor transition. Unlike "
        "disabling UAC entirely this keeps the prompt, so you still "
        "approve elevation. Mildly weakens protection against "
        "prompt-spoofing.",
        registry=r"HKLM\\...\\Policies\\System\\PromptOnSecureDesktop",
    ),
    Tweak(
        "telemetry_min", "Set telemetry to the minimum", SAFE,
        "Reduces diagnostic data to Security/Required level.",
        "A supported Group Policy setting, not a hack. Fewer background "
        "uploads and less disk logging. The effect on FPS is essentially "
        "zero; the privacy benefit is real, which is the honest reason to "
        "do it.",
        registry=r"HKLM\\...\\DataCollection\\AllowTelemetry",
    ),
    Tweak(
        "disable_diagtrack", "Disable the DiagTrack service", SITUATIONAL,
        "Stops the Connected User Experiences and Telemetry service.",
        "Disabling is fine and reversible. It uses little CPU but does "
        "periodic disk and network work. Note the difference from "
        "DELETING it, which is listed separately as harmful.",
        registry=r"services.msc > DiagTrack",
        also_known_as=('Connected User Experiences',),
    ),
    Tweak(
        "disable_cortana", "Disable Cortana", SITUATIONAL,
        "Removes the assistant and its background indexing.",
        "Frees some memory on systems where it still runs. Largely moot "
        "on current Windows 11, where Cortana is already unbundled.",
        registry=r"HKLM\\...\\Windows Search\\AllowCortana",
    ),
    Tweak(
        "disable_tips", "Disable Windows tips and suggestions", SAFE,
        "Stops suggestion notifications and Start menu ads.",
        "Removes interruptions - which matters mid-game more than the "
        "negligible CPU it saves.",
        registry=r"HKCU\\...\\ContentDeliveryManager\\SubscribedContent-338389Enabled",
    ),
    Tweak(
        "disable_background_apps", "Disable background UWP apps", SITUATIONAL,
        "Stops Store apps running when closed.",
        "Real memory and CPU savings if you have many Store apps "
        "installed. Nothing to gain if you do not use them. Breaks live "
        "tiles and background notifications for the apps affected.",
        registry=r"HKCU\\...\\BackgroundAccessApplications\\GlobalUserDisabled",
    ),
    Tweak(
        "disable_widgets", "Disable Windows 11 Widgets", SAFE,
        "Removes the widgets panel and its background process.",
        "Widgets runs a WebView2 process that consumes real memory and "
        "periodically fetches content. Removing it is a genuine saving on "
        "8 GB machines.",
        registry=r"HKLM\\...\\Dsh\\AllowNewsAndInterests",
        also_known_as=('News and Interests',),
    ),
    Tweak(
        "disable_search_index", "Disable Windows Search indexing", SITUATIONAL,
        "Stops the indexer scanning your drives.",
        "Indexing causes real disk activity, which can stutter a game "
        "mid-session. But it runs at low priority and mostly when idle, "
        "and disabling it makes Start menu search almost useless. Better "
        "to exclude your game folders than disable it wholesale.",
        registry=r"services.msc > WSearch",
    ),
    Tweak(
        "disable_sysmain", "Disable SysMain", SITUATIONAL,
        "Stops Windows preloading frequently used applications.",
        "Was worth doing on mechanical drives. On an SSD SysMain is "
        "generally helping, and disabling it makes launches slower. "
        "Consider it only if you observe sustained disk activity you can "
        "trace to it.",
        registry=r"services.msc > SysMain",
        also_known_as=('Superfetch',),
    ),
    Tweak(
        "disable_print_spooler", "Disable the Print Spooler", SITUATIONAL,
        "Stops the printing service.",
        "Sensible if you genuinely never print, and it has a long history "
        "of security vulnerabilities (PrintNightmare). Zero performance "
        "benefit - it is idle when not printing.",
        registry=r"services.msc > Spooler",
    ),
    Tweak(
        "disable_fax", "Disable the Fax service", PLACEBO,
        "Stops a service almost nobody has running.",
        "Already disabled or absent on essentially every modern system. "
        "Listed for completeness; there is nothing to gain.",
        registry=r"services.msc > Fax",
    ),
    Tweak(
        "disable_remote_registry", "Disable Remote Registry", SAFE,
        "Prevents remote modification of your registry.",
        "A security improvement, not a performance one. It is already "
        "disabled by default on Windows 10/11 Home. Worth confirming "
        "rather than assuming.",
        registry=r"services.msc > RemoteRegistry",
    ),
    Tweak(
        "disable_wer", "Disable Windows Error Reporting", SITUATIONAL,
        "Stops crash dump collection and upload.",
        "Saves disk writes after a crash. It also removes the diagnostic "
        "data you would need to work out WHY something crashed - a poor "
        "trade if you are troubleshooting.",
        registry=r"HKLM\\...\\Windows Error Reporting\\Disabled",
    ),
    Tweak(
        "disable_sticky_keys", "Disable Sticky Keys prompt", SAFE,
        "Stops the five-shift-presses accessibility popup.",
        "Purely an anti-annoyance fix, but a real one: the prompt can "
        "steal focus mid-game. No performance claim attached.",
        registry=r"HKCU\\Control Panel\\Accessibility\\StickyKeys\\Flags",
    ),
    Tweak(
        "disable_gamebar_tips", "Disable Game Bar tips", SAFE,
        "Prevents an overlay prompt appearing over your game, which can steal focus. Small and real, with no downside and nothing to lose by turning it off.",
        "Prevents an overlay prompt appearing over your game, which can "
        "steal focus mid-match. Small and real, with nothing to lose by "
        "turning it off.",
        registry=r"HKCU\\Software\\Microsoft\\GameBar\\ShowStartupPanel",
    ),
    Tweak(
        "disable_notifications_game", "Suppress notifications while gaming", SAFE,
        "Enables Focus Assist during fullscreen play.",
        "A supported Windows feature. Stops a notification stealing focus "
        "or causing an alt-tab in a fullscreen game - a real cause of "
        "lost rounds, not a frame-rate change.",
        registry=r"Settings > Focus Assist > When playing a game",
        also_known_as=('Do Not Disturb',),
    ),
    Tweak(
        "tcp_autotuning_off", "Disable TCP auto-tuning", HARMFUL,
        "Claims a fixed receive window is faster.",
        "Auto-tuning sizes the TCP receive window to your actual "
        "connection. Disabling it caps throughput on fast links - people "
        "who do this often report their download speed dropping by half "
        "and never connect it to the tweak. Windows has handled this "
        "correctly since Vista.",
        registry=r"netsh int tcp set global autotuninglevel=disabled",
    ),
    Tweak(
        "tcp_chimney", "Enable TCP Chimney Offload", PLACEBO,
        "Claims to offload TCP processing to the network card.",
        "Removed from Windows in 8.1 and later. The netsh command still "
        "appears to succeed on modern Windows, which is why it survives "
        "on tweak lists, but nothing happens.",
        registry=r"netsh int tcp set global chimney=enabled",
    ),
    Tweak(
        "rss_enable", "Enable Receive Side Scaling", SAFE,
        "Spreads network interrupt processing across CPU cores.",
        "Genuinely useful and already enabled by default on modern "
        "adapters. Worth verifying rather than assuming; if a driver "
        "disabled it, enabling it helps under load.",
        registry=r"netsh int tcp set global rss=enabled",
    ),
    Tweak(
        "disable_rss", "Disable Receive Side Scaling", HARMFUL,
        "Claims pinning network work to one core reduces jitter.",
        "The opposite of the truth. RSS exists so a single core does not "
        "become the bottleneck for interrupts. Disabling it concentrates "
        "all network interrupt load on CPU 0, which is exactly the core "
        "most likely to already be busy.",
        registry=r"netsh int tcp set global rss=disabled",
    ),
    Tweak(
        "disable_lso", "Disable Large Send Offload", SITUATIONAL,
        "Moves TCP segmentation from the NIC to the CPU.",
        "Occasionally fixes real problems with buggy NIC firmware, at the "
        "cost of more CPU per packet. Only do this if you have diagnosed "
        "a specific offload bug - not as a general tweak.",
        registry=r"Device Manager > NIC > Advanced > LSO",
    ),
    Tweak(
        "interrupt_moderation_off", "Disable interrupt moderation", SITUATIONAL,
        "Delivers packets immediately instead of batching interrupts.",
        "Can shave a fraction of a millisecond of latency at the cost of "
        "noticeably higher CPU use under load. Measurable with the right "
        "tools; imperceptible in most games. A defensible choice for "
        "competitive play on a strong CPU.",
        registry=r"Device Manager > NIC > Advanced > Interrupt Moderation",
    ),
    Tweak(
        "energy_efficient_ethernet", "Disable Energy Efficient Ethernet", SITUATIONAL,
        "Stops the NIC entering low-power states between packets.",
        "EEE can add sub-millisecond wake latency and, on some hardware, "
        "causes link drops. Disabling it is low-risk and occasionally "
        "fixes real intermittent disconnects.",
        registry=r"Device Manager > NIC > Advanced > EEE",
        also_known_as=('Green Ethernet',),
    ),
    Tweak(
        "flow_control_off", "Disable flow control", SITUATIONAL,
        "Stops the NIC sending pause frames.",
        "Only relevant on congested switched networks. Harmless to "
        "change, rarely does anything at home.",
        registry=r"Device Manager > NIC > Advanced > Flow Control",
    ),
    Tweak(
        "jumbo_frames", "Enable jumbo frames", HARMFUL,
        "Claims larger packets reduce overhead.",
        "Only works if every device on the path supports the same MTU. "
        "Enable it on one machine and you get silent packet loss, broken "
        "file transfers and connection failures that are extremely hard "
        "to diagnose. Irrelevant to internet traffic, which is limited to "
        "1500 bytes anyway.",
        registry=r"Device Manager > NIC > Advanced > Jumbo Frame",
        also_known_as=('MTU 9000',),
    ),
    Tweak(
        "qos_reserve", "Set reservable bandwidth to 0", PLACEBO,
        "Claims Windows reserves 20% of your bandwidth.",
        "The most persistent networking myth on the internet. The 20% "
        "limit only applies to applications that explicitly request QoS "
        "reservation, and only when the link is saturated. Microsoft has "
        "published this repeatedly. Setting it to 0 changes nothing for "
        "normal traffic.",
        registry=r"HKLM\\...\\Psched\\NonBestEffortLimit",
        also_known_as=('Psched limit',),
        evidence="Microsoft documented that the reserve applies only to QoS-aware apps.",
    ),
    Tweak(
        "dns_cache_size", "Increase the DNS cache size", PLACEBO,
        "Claims a bigger resolver cache speeds up browsing.",
        "The default cache is already far larger than a normal machine "
        "needs. The registry values quoted in most guides were for "
        "Windows 2000 and are ignored on modern builds.",
        registry=r"HKLM\\...\\Dnscache\\Parameters\\CacheHashTableSize",
    ),
    Tweak(
        "disable_ipv6", "Disable IPv6", HARMFUL,
        "Claims IPv6 adds overhead or causes latency.",
        "Microsoft explicitly does not recommend disabling IPv6 - parts "
        "of Windows assume it is present, and disabling it can break "
        "Homegroup, some VPNs and Exchange connectivity. Modern games and "
        "CDNs increasingly prefer IPv6 routes, which are often shorter.",
        registry=r"HKLM\\SYSTEM\\...\\Tcpip6\\Parameters\\DisabledComponents",
        evidence="Microsoft advises against disabling IPv6.",
    ),
    Tweak(
        "teredo_off", "Disable Teredo", SITUATIONAL,
        "Turns off IPv6-over-IPv4 tunnelling.",
        "Genuinely obsolete for most people. But some peer-to-peer games "
        "and Xbox multiplayer still rely on it, and disabling it is a "
        "known cause of 'cannot connect to party' problems.",
        registry=r"netsh interface teredo set state disabled",
    ),
    Tweak(
        "nic_power_save_off", "Stop Windows powering down the NIC", SAFE,
        "Prevents the adapter sleeping to save power.",
        "A real fix for intermittent disconnects on desktops, where the "
        "power saving is pointless anyway. On a laptop it costs battery "
        "life.",
        registry=r"Device Manager > NIC > Power Management",
    ),
    Tweak(
        "max_user_port", "Increase MaxUserPort", PLACEBO,
        "Claims more ephemeral ports improve connectivity.",
        "The default range was widened to about 16,000 ports in Vista. "
        "Exhausting it requires thousands of simultaneous connections - a "
        "server workload, not a gaming one.",
        registry=r"HKLM\\SYSTEM\\...\\Tcpip\\Parameters\\MaxUserPort",
    ),
    Tweak(
        "tcp_window_hardcode", "Hard-code the TCP window size", HARMFUL,
        "Claims a manually tuned window is faster than auto-tuning.",
        "The values circulated in guides were calculated for early-2000s "
        "broadband. Applying them to a modern connection caps throughput "
        "badly. This is auto-tuning's job and it does it well.",
        registry=r"HKLM\\SYSTEM\\...\\Tcpip\\Parameters\\TcpWindowSize",
    ),
    Tweak(
        "disable_nagle_udp", "Disable Nagle for UDP games", PLACEBO,
        "Claims it lowers ping in UDP titles.",
        "Nagle's algorithm is part of TCP. It has no effect whatsoever on "
        "UDP traffic, which is what most competitive games use. The tweak "
        "is real; applying it for a UDP game is not.",
        registry=r"TcpAckFrequency",
        evidence="Nagle is defined in the TCP specification only.",
    ),
    Tweak(
        "network_adapter_rss_queues", "Increase RSS queues", SITUATIONAL,
        "Distributes receive processing across more cores.",
        "Helpful on high-core-count systems with a fast link and a "
        "capable NIC. Setting more queues than the adapter supports "
        "silently does nothing.",
        registry=r"Device Manager > NIC > Advanced > RSS Queues",
    ),
    Tweak(
        "smb_tweaks", "SMB / LanmanWorkstation tweaks", PLACEBO,
        "Claims to improve file-sharing throughput.",
        "Affects Windows network file shares only. It has no relationship "
        "to game traffic and appears on gaming lists purely through "
        "copy-paste.",
        registry=r"HKLM\\SYSTEM\\...\\LanmanWorkstation\\Parameters",
    ),
    Tweak(
        "shader_cache_size", "Increase the driver shader cache", SAFE,
        "Lets the GPU driver keep more compiled shaders on disk.",
        "Directly reduces shader-compilation stutter in titles that "
        "compile at runtime, which is a very common cause of hitching in "
        "modern games. Costs disk space. One of the more genuinely useful "
        "items on this page.",
        registry=r"NVIDIA Control Panel / AMD Adrenalin > Shader Cache Size",
    ),
    Tweak(
        "power_management_prefer_max", "GPU power mode: prefer maximum performance", SITUATIONAL,
        "Stops the GPU dropping clocks between frames.",
        "Helps 1% lows in games that do not load the GPU heavily enough "
        "to trigger a clock boost. Increases idle power and temperature, "
        "so it is a poor default for laptops.",
        registry=r"NVIDIA Control Panel > Power Management Mode",
    ),
    Tweak(
        "low_latency_mode", "NVIDIA Low Latency / AMD Anti-Lag", SITUATIONAL,
        "Limits how many frames the CPU may queue ahead of the GPU.",
        "A real, measurable latency reduction when you are GPU-bound. "
        "When you are CPU-bound it does nothing, and 'Ultra' can cost a "
        "little average FPS. Reflex, where a game supports it, is better "
        "than either.",
        registry=r"NVIDIA Control Panel > Low Latency Mode",
        also_known_as=('Anti-Lag', 'Ultra Low Latency'),
    ),
    Tweak(
        "texture_filtering_perf", "Texture filtering: high performance", SITUATIONAL,
        "Trades texture sharpness for frame rate.",
        "A genuine trade, not a free win: it lowers image quality. "
        "Reasonable on weak hardware, pointless on a card that is not "
        "texture-limited.",
        registry=r"NVIDIA Control Panel > Texture Filtering Quality",
    ),
    Tweak(
        "disable_vsync_globally", "Force V-Sync off globally", SITUATIONAL,
        "Removes the frame-rate cap imposed by your refresh rate.",
        "Lowers latency at the cost of tearing. If you have a "
        "variable-refresh display, forcing V-Sync off globally actually "
        "breaks G-Sync/FreeSync operation - the recommended configuration "
        "is V-Sync on with a frame cap just below refresh.",
        registry=r"NVIDIA Control Panel > Vertical Sync",
    ),
    Tweak(
        "mpo_disable", "Disable Multi-Plane Overlay", SITUATIONAL,
        "Works around flickering and stutter in windowed mode.",
        "A documented fix for real MPO bugs that Microsoft and NVIDIA "
        "have both acknowledged. Not a performance tweak - only apply it "
        "if you actually see flickering or windowed-mode stutter.",
        registry=r"HKLM\\...\\GraphicsDrivers\\OverlayTestMode",
        also_known_as=('MPO fix',),
    ),
    Tweak(
        "gpu_overclock_msi", "One-click GPU overclock presets", HARMFUL,
        "Claims free performance from a vendor preset.",
        "Every chip is different. A preset stable on the developer's card "
        "can cause driver timeouts, artifacts or crashes on yours. The "
        "failure mode is often intermittent, so people blame the game. "
        "Overclock deliberately with your own stability testing or not at "
        "all.",
        registry=r"MSI Afterburner OC Scanner",
    ),
    Tweak(
        "disable_hdcp", "Disable HDCP", PLACEBO,
        "Claims removing copy protection frees GPU work.",
        "HDCP encryption happens in dedicated display-output hardware, "
        "not the shaders that render your game. Disabling it does not "
        "free any rendering capacity, and it breaks Netflix and other "
        "protected playback.",
        registry=r"NVIDIA Control Panel",
    ),
    Tweak(
        "disable_gpu_preemption", "Disable GPU preemption", HARMFUL,
        "Claims uninterrupted GPU tasks are faster.",
        "Preemption exists so a long-running task cannot lock up the "
        "display. Disabling it is a direct route to TDR timeouts, black "
        "screens and driver recovery mid-game. There is no supported way "
        "to do this and the registry values quoted are guesses.",
        registry=r"HKLM\\...\\GraphicsDrivers\\DisablePreemption",
    ),
    Tweak(
        "core_parking_off", "Disable core parking", SITUATIONAL,
        "Keeps all cores awake instead of parking idle ones.",
        "Parking adds a small wake latency when load spikes, which can "
        "show up in 1% lows. The High Performance power plan already "
        "unparks everything, so the registry hack is usually redundant. "
        "Costs idle power.",
        registry=r"HKLM\\SYSTEM\\...\\Power\\PowerSettings\\...\\ValueMax",
    ),
    Tweak(
        "disable_power_throttling", "Disable CPU power throttling", SITUATIONAL,
        "Stops Windows throttling background-classified processes.",
        "Power throttling targets background work, and a foreground game "
        "is already exempt. Helps in the specific case where a game's "
        "helper process is misclassified. Costs battery life on laptops.",
        registry=r"HKLM\\SYSTEM\\...\\Power\\PowerThrottling\\PowerThrottlingOff",
    ),
    Tweak(
        "min_processor_state_100", "Minimum processor state 100%", SITUATIONAL,
        "Prevents the CPU downclocking at all.",
        "Eliminates clock-ramp latency, at the cost of running hot and "
        "loud permanently. On a laptop this can cause thermal throttling "
        "that makes performance WORSE than leaving it alone. Reasonable "
        "on a well-cooled desktop.",
        registry=r"powercfg > Processor power management > Minimum processor state",
    ),
    Tweak(
        "disable_c_states", "Disable CPU C-states", HARMFUL,
        "Claims idle states add latency when waking.",
        "C-state exit latency is measured in microseconds. Disabling them "
        "raises idle temperature significantly, and on modern CPUs it "
        "prevents the thermal headroom that single-core boost depends on "
        "- so peak clocks can drop. Often makes gaming performance worse.",
        registry=r"BIOS > Advanced > CPU C-State Control",
    ),
    Tweak(
        "disable_smt", "Disable SMT / Hyper-Threading", HARMFUL,
        "Claims fewer logical cores reduces scheduling overhead.",
        "Halves your thread count. Modern games use 8+ threads and lose "
        "substantial performance. This advice originates from a handful "
        "of 2015-era titles with genuine SMT bugs, and has been wrong for "
        "years.",
        registry=r"BIOS > CPU Configuration > SMT",
        also_known_as=('Disable Hyper-Threading',),
    ),
    Tweak(
        "bios_xmp", "Enable XMP / EXPO memory profile", SAFE,
        "Runs your RAM at its advertised speed.",
        "One of the few changes with a large, consistent, measurable "
        "effect - RAM shipped at 6000 MT/s runs at 4800 until you enable "
        "this. Particularly significant for AMD Ryzen 1% lows. It is a "
        "BIOS setting, so Phantom Tweeks reports it rather than applying "
        "it.",
        registry=r"BIOS > Memory > XMP / EXPO / DOCP",
        also_known_as=('DOCP', 'A-XMP'),
    ),
    Tweak(
        "disable_spread_spectrum", "Disable spread spectrum", PLACEBO,
        "Claims cleaner clocks improve stability.",
        "Reduces electromagnetic interference by modulating the clock "
        "very slightly. It has no measurable effect on performance and "
        "only matters for overclockers chasing the last few MHz.",
        registry=r"BIOS > Advanced > Spread Spectrum",
    ),
    Tweak(
        "cpu_affinity_background", "Set background app affinity manually", HARMFUL,
        "Claims confining background apps frees cores for the game.",
        "The scheduler already deprioritises idle background work. Manual "
        "affinity prevents threads migrating off busy cores and, on "
        "hybrid Intel CPUs, can pin things to E-cores. Some anti-cheats "
        "also flag processes that modify another process's affinity.",
        registry=r"Task Manager > Set Affinity",
    ),
    Tweak(
        "realtime_priority", "Set a game to Realtime priority", HARMFUL,
        "Claims maximum priority means maximum FPS.",
        "Realtime outranks kernel threads including input and disk I/O. "
        "The classic result is a completely frozen system that requires a "
        "hard reset. Even High priority can starve the very audio and "
        "input threads your game needs. Windows already boosts the "
        "foreground process.",
        registry=r"Task Manager > Set Priority > Realtime",
    ),
    Tweak(
        "bcdedit_useplatformclock", "bcdedit useplatformclock true", HARMFUL,
        "Claims forcing the HPET timer improves consistency.",
        "Forces Windows onto the High Precision Event Timer, which is "
        "SLOWER to read than the invariant TSC modern CPUs use. This "
        "measurably increases DPC latency and reduces FPS on most "
        "systems. It is one of the most damaging pieces of widely "
        "repeated tweak advice.",
        registry=r"bcdedit /set useplatformclock true",
    ),
    Tweak(
        "bcdedit_disable_dynamic_tick", "bcdedit disabledynamictick yes", SITUATIONAL,
        "Stops the kernel skipping timer ticks when idle.",
        "Occasionally reduces timer jitter on specific hardware. "
        "Increases power draw and, on many systems, changes nothing "
        "measurable. Benchmark rather than assume.",
        registry=r"bcdedit /set disabledynamictick yes",
    ),
    Tweak(
        "bcdedit_numproc", "bcdedit set numproc", HARMFUL,
        "Claims limiting cores at boot improves scheduling.",
        "Actively removes CPU capacity from Windows. There is no scenario "
        "where a gaming PC benefits from having fewer usable cores, and a "
        "mistyped value can leave the machine unbootable.",
        registry=r"bcdedit /set numproc",
    ),
    Tweak(
        "trim_enabled", "Verify TRIM is enabled", SAFE,
        "Confirms Windows is issuing TRIM to your SSD.",
        "Enabled by default, but genuinely worth checking: without it an "
        "SSD slows down significantly as it fills. Read-only verification "
        "with a real consequence.",
        registry=r"fsutil behavior query DisableDeleteNotify",
    ),
    Tweak(
        "disable_defrag_ssd", "Do not defragment an SSD", SAFE,
        "Prevents scheduled defragmentation of flash storage.",
        "Windows already detects SSDs and runs TRIM instead of defrag. "
        "Third-party 'optimizers' often do not, and defragmenting flash "
        "writes gigabytes for no benefit while consuming write endurance.",
        registry=r"dfrgui > Change settings",
    ),
    Tweak(
        "disable_last_access", "Disable last-access timestamps", SITUATIONAL,
        "Stops NTFS writing a timestamp on every file read.",
        "Removes a small write amplification. Already disabled by default "
        "on modern Windows, and some backup and indexing tools depend on "
        "it.",
        registry=r"fsutil behavior set disablelastaccess 1",
    ),
    Tweak(
        "disable_8dot3", "Disable 8.3 filename creation", SITUATIONAL,
        "Stops NTFS maintaining legacy short names.",
        "A measurable improvement on volumes with very many files in one "
        "directory. Breaks a small number of legacy installers that still "
        "reference short paths.",
        registry=r"fsutil behavior set disable8dot3 1",
    ),
    Tweak(
        "ntfs_memory_usage", "Increase NTFS memory usage", PLACEBO,
        "Claims more paged-pool memory speeds up the filesystem.",
        "A Windows XP-era tuning knob for servers with heavy file loads. "
        "On a modern desktop the cache is already sized dynamically and "
        "this changes nothing you can measure.",
        registry=r"fsutil behavior set memoryusage 2",
    ),
    Tweak(
        "disable_pagefile_ssd", "Move the pagefile off the SSD", PLACEBO,
        "Claims paging wears out the SSD.",
        "Modern SSD endurance is measured in hundreds of terabytes "
        "written; pagefile activity is a rounding error. Moving it to a "
        "mechanical drive makes the rare paging event dramatically "
        "slower.",
        registry=r"System Properties > Virtual Memory",
    ),
    Tweak(
        "game_folder_exclusion", "Add a Defender exclusion for game folders", SAFE,
        "Stops real-time scanning of files your game reads constantly.",
        "This is the correct alternative to disabling Defender. You keep "
        "full protection everywhere else and remove the scanning overhead "
        "where it actually costs you - shader caches and asset streaming. "
        "Only exclude folders you trust.",
        registry=r"Windows Security > Exclusions",
    ),
    Tweak(
        "storage_driver_write_cache", "Enable write caching", SITUATIONAL,
        "Lets the drive acknowledge writes before they hit media.",
        "Enabled by default and generally correct. The related 'turn off "
        "Windows write-cache buffer flushing' option risks data loss on "
        "power failure and should stay off without a UPS.",
        registry=r"Device Manager > Disk > Policies",
    ),
    Tweak(
        "keyboard_repeat", "Fastest keyboard repeat rate", SAFE,
        "Reduces the delay and interval for held keys.",
        "A preference with a real feel difference in menus and chat. No "
        "effect on in-game input polling.",
        registry=r"HKCU\\Control Panel\\Keyboard\\KeyboardDelay",
    ),
    Tweak(
        "mouse_data_queue", "Reduce the mouse data queue size", PLACEBO,
        "Claims a smaller queue reduces input latency.",
        "The queue is a buffer for input packets, sized in entries not "
        "time. It never fills at normal polling rates, so shrinking it "
        "changes nothing. Setting it too low can drop input during a "
        "stall.",
        registry=r"HKLM\\SYSTEM\\...\\mouclass\\Parameters\\MouseDataQueueSize",
    ),
    Tweak(
        "usb_selective_suspend_off", "Disable USB selective suspend", SITUATIONAL,
        "Stops Windows powering down idle USB devices.",
        "A genuine fix for peripherals that briefly stop responding after "
        "inactivity - a real and irritating problem with some mice and "
        "controllers. Costs a little power. Not an FPS tweak.",
        registry=r"powercfg > USB settings > USB selective suspend",
    ),
    Tweak(
        "polling_rate_override", "Force a 1000 Hz mouse polling rate", SITUATIONAL,
        "Increases how often the mouse reports position.",
        "Real and worthwhile if your mouse defaults to 125 Hz. Beyond "
        "1000 Hz the returns are extremely small and very high rates "
        "measurably increase CPU interrupt load. Use the manufacturer's "
        "software rather than a registry hack.",
        registry=r"Manufacturer software / HKLM\\SYSTEM\\...\\HidUsb",
    ),
    Tweak(
        "filter_keys_off", "Disable Filter Keys", SAFE,
        "Stops Windows ignoring rapid repeated keystrokes.",
        "If Filter Keys is accidentally enabled it genuinely drops fast "
        "inputs - a real, if uncommon, cause of 'my keyboard is missing "
        "presses' in games.",
        registry=r"HKCU\\Control Panel\\Accessibility\\Keyboard Response",
    ),
    Tweak(
        "disable_pointer_precision", "Disable Enhanced Pointer Precision", SAFE,
        "Removes acceleration so movement is 1:1.",
        "Distinct from raw input: this is the OS-level acceleration "
        "curve. Turning it off is near-universal advice among competitive "
        "players because it makes muscle memory reliable.",
        registry=r"HKCU\\Control Panel\\Mouse\\MouseSpeed",
        also_known_as=('Mouse acceleration off',),
    ),
    Tweak(
        "remove_edge", "Force-remove Microsoft Edge", HARMFUL,
        "Claims Edge runs in the background wasting resources.",
        "Edge is a servicing component: WebView2 backs Widgets, Outlook, "
        "Teams and many installers. Forced removal scripts break those "
        "and cause update failures. Edge does not run unless launched. "
        "Set a different default browser instead.",
        registry=r"setup.exe --uninstall --force-uninstall",
    ),
    Tweak(
        "remove_defender_fully", "Defender removal tools", HARMFUL,
        "Claims fully removing Defender frees resources.",
        "These tools disable tamper protection and delete a security "
        "component. Windows Update then repeatedly tries and fails to "
        "restore it. You are left unprotected and with a broken servicing "
        "stack, and the performance gain is 1-2%.",
        registry=r"Third-party Defender removers",
    ),
    Tweak(
        "debloat_script_all", "Run-everything debloat scripts", HARMFUL,
        "Claims one script removes all unnecessary Windows components.",
        "The popular scripts bundle sensible items with genuinely "
        "destructive ones - deleting services, removing Edge, disabling "
        "mitigations - behind a single button. You cannot review what "
        "applied, and there is no undo. Apply changes individually, "
        "understanding each one.",
        registry=r"Various .bat and .ps1 scripts",
        also_known_as=('Windows debloater',),
    ),
    Tweak(
        "remove_store", "Remove the Microsoft Store", HARMFUL,
        "Claims the Store is bloat.",
        "Game Pass, Xbox app and many games depend on it, and it cannot "
        "be cleanly reinstalled once removed. It consumes nothing when "
        "not running.",
        registry=r"Get-AppxPackage *WindowsStore* | Remove-AppxPackage",
    ),
    Tweak(
        "remove_xbox_apps", "Remove Xbox apps", SITUATIONAL,
        "Frees a small amount of disk and background activity.",
        "Fine if you do not use Game Pass. If you do, removing the Gaming "
        "Services component breaks game launches in ways that are hard to "
        "diagnose. Reversible via the Store, but awkward.",
        registry=r"Get-AppxPackage *Xbox* | Remove-AppxPackage",
    ),
    Tweak(
        "remove_onedrive", "Uninstall OneDrive", SITUATIONAL,
        "Stops continuous file synchronisation.",
        "A real saving if unused: OneDrive does constant disk and network "
        "work. Make sure nothing is stored only in the cloud before "
        "removing it.",
        registry=r"OneDriveSetup.exe /uninstall",
    ),
    Tweak(
        "disable_defender_realtime_temp", "Temporarily disable real-time protection", HARMFUL,
        "Claims it is safe if you turn it back on afterwards.",
        "Tamper Protection blocks this anyway on current Windows, and it "
        "usually re-enables itself. People typically do this to run "
        "something Defender flagged - which is exactly when they should "
        "not. Use an exclusion for a specific trusted folder.",
        registry=r"Set-MpPreference -DisableRealtimeMonitoring $true",
    ),
    Tweak(
        "disable_smartscreen", "Disable SmartScreen", HARMFUL,
        "Claims SmartScreen slows program launches.",
        "It performs a reputation check on first launch only, taking "
        "milliseconds. Disabling it removes your last defence against a "
        "trojanised game mod or cheat installer - the exact download "
        "profile of someone applying gaming tweaks.",
        registry=r"HKLM\\...\\Explorer\\SmartScreenEnabled",
    ),
    Tweak(
        "disable_windows_update", "Disable Windows Update", HARMFUL,
        "Claims updates interrupt gaming.",
        "You stop receiving security patches for known, actively "
        "exploited vulnerabilities. Use Active Hours and Pause Updates "
        "instead - both supported and both solve the actual complaint.",
        registry=r"services.msc > wuauserv",
    ),
    Tweak(
        "disable_tamper_protection", "Disable Tamper Protection", HARMFUL,
        "Required first step in most 'disable Defender' guides.",
        "Tamper Protection exists specifically to stop malware disabling "
        "your antivirus. Turning it off to make other tweaks possible is "
        "a strong signal those tweaks should not be applied.",
        registry=r"Windows Security > Tamper Protection",
    ),
    Tweak(
        "process_lasso", "Process Lasso ProBalance", SITUATIONAL,
        "Automatically deprioritises background processes.",
        "A well-regarded tool that does dynamic priority adjustment more "
        "carefully than a static registry tweak. The benefit is mostly on "
        "CPU-constrained systems. It is another background process "
        "itself.",
        registry=r"Third-party utility",
    ),
    Tweak(
        "game_mode_third_party", "Third-party 'game booster' one-click modes", PLACEBO,
        "Claims to free resources by closing background apps.",
        "Most simply terminate processes and clear the standby list. "
        "Killing Explorer or a launcher mid-session causes more problems "
        "than the RAM it frees. The measurable benefit in reviews is "
        "consistently near zero.",
        registry=r"Various boosters",
        also_known_as=('Razer Cortex', 'Game Fire'),
    ),
    Tweak(
        "timer_resolution_tool", "ISLC / TimerResolution utilities", PLACEBO,
        "Claims to hold a 0.5 ms timer for smoother frames.",
        "Since Windows 10 2004 a process requesting a high-resolution "
        "timer affects only itself. These tools also 'clear standby "
        "memory' on a schedule, which throws away a useful cache. The "
        "measured effect on frame pacing is not distinguishable from "
        "noise.",
        registry=r"ISLC",
        also_known_as=('Intelligent Standby List Cleaner',),
    ),
    Tweak(
        "disable_prefetch_boot", "Disable boot prefetching", HARMFUL,
        "Claims it speeds up startup.",
        "Boot prefetch exists specifically to make startup faster by "
        "reading files in optimal order. Disabling it measurably slows "
        "boot. The tweak is a misreading of the application prefetch "
        "discussion.",
        registry=r"HKLM\\SYSTEM\\...\\PrefetchParameters\\EnablePrefetcher",
    ),
    Tweak(
        "clear_temp_startup", "Clear temp files on every boot", SITUATIONAL,
        "Frees disk space automatically.",
        "Harmless if it only targets %TEMP%. Many scripts also clear "
        "browser caches and Windows Update downloads, which just forces "
        "everything to be re-downloaded.",
        registry=r"Scheduled task",
    ),
    Tweak(
        "disable_superfetch_ssd", "Disable SysMain specifically on SSDs", PLACEBO,
        "Claims SysMain is only useful for mechanical drives.",
        "SysMain already detects SSDs and adjusts its behaviour. "
        "Disabling it on a modern system typically makes application "
        "launches slower, not faster.",
        registry=r"services.msc > SysMain",
    ),
    Tweak(
        "high_performance_visuals", "Adjust for best performance", SITUATIONAL,
        "Turns off every visual effect at once.",
        "Genuinely helps on old integrated graphics. On modern hardware "
        "it mostly makes Windows look dated for no measurable in-game "
        "gain, since the compositor is idle during fullscreen play.",
        registry=r"System Properties > Performance Options",
    ),
    Tweak(
        "disable_dwm", "Disable the Desktop Window Manager", HARMFUL,
        "Claims removing the compositor eliminates a frame of latency.",
        "DWM cannot be disabled on Windows 8 and later - it is "
        "fundamental to how the desktop renders. Scripts that attempt it "
        "produce a broken, unusable desktop. Exclusive fullscreen already "
        "bypasses the compositor.",
        registry=r"services.msc > DWM",
    ),
    Tweak(
        "wpr_latency_check", "Measure DPC latency before tweaking", SAFE,
        "Identifies which driver is actually causing stutter.",
        "The correct first step, and the one almost every guide skips. "
        "LatencyMon or WPR will name the offending driver - usually "
        "network, audio or storage - so you can fix the real cause "
        "instead of applying twenty unrelated registry edits.",
        registry=r"LatencyMon / Windows Performance Recorder",
    ),
    Tweak(
        "clean_gpu_driver_install", "Clean GPU driver install with DDU", SITUATIONAL,
        "Removes all traces of previous drivers before installing.",
        "A genuine fix for problems caused by layered driver upgrades, "
        "and standard advice when troubleshooting. Not something to do "
        "routinely - a normal driver update is fine when nothing is "
        "wrong.",
        registry=r"Display Driver Uninstaller",
        also_known_as=('DDU',),
    ),
    Tweak(
        "undervolt_cpu", "Undervolt the CPU", SITUATIONAL,
        "Lowers voltage to reduce heat and sustain boost clocks.",
        "Can genuinely improve sustained performance on thermally limited "
        "laptops by allowing higher boost within the same thermal budget. "
        "It is also silicon-specific and unstable settings cause crashes "
        "hours later. Requires patient stability testing - never a "
        "one-click preset.",
        registry=r"BIOS / ThrottleStop / Ryzen Master",
    ),
    Tweak(
        "disable_fullscreen_opt_global", "Disable fullscreen optimizations for every exe", SITUATIONAL,
        "Applies the compatibility flag system-wide.",
        "Occasionally helps older DX9 and DX11 titles. On modern games "
        "the flip model is usually faster, and this breaks HDR, alt-tab "
        "and overlays. Apply per game after testing, not globally.",
        registry=r"Compatibility tab > Disable fullscreen optimisations",
    ),
    Tweak(
        "registry_defrag", "Defragment the registry", PLACEBO,
        "Claims a compacted registry loads faster.",
        "The registry hives are memory-mapped and paged on demand. "
        "Compaction saves a few megabytes and no measurable time. The "
        "tools that do it operate on live system files, which carries "
        "real risk for no reward.",
        registry=r"Third-party registry defragmenters",
    ),
    Tweak(
        "disable_audio_enhancements", "Disable audio enhancements", SITUATIONAL,
        "Removes DSP effects from the audio path.",
        "Genuinely reduces audio latency by a few milliseconds and can "
        "fix crackling. Matters for competitive audio cues; you lose "
        "spatial effects if you used them.",
        registry=r"Sound > Device Properties > Enhancements",
    ),
    Tweak(
        "exclusive_audio_mode", "Allow exclusive audio mode", SITUATIONAL,
        "Lets an application take direct control of the device.",
        "Lower latency for the app that grabs it, but it then blocks all "
        "other audio - including Discord. Rarely the right trade for "
        "gaming with voice chat.",
        registry=r"Sound > Device Properties > Advanced",
    ),
    Tweak(
        "disable_startup_programs", "Trim startup programs", SAFE,
        "Stops unnecessary applications launching at login.",
        "One of the few changes with a large, consistent effect - not on "
        "FPS, but on boot time and idle memory. Reversible, visible, and "
        "you decide each entry individually.",
        registry=r"Task Manager > Startup",
    ),
    Tweak(
        "set_game_high_priority", "Set a game to High priority", SITUATIONAL,
        "Raises the game above normal background processes.",
        "Less dangerous than Realtime but still able to starve audio and "
        "input threads on a CPU-limited system. Windows already applies a "
        "foreground boost, so the gain is usually small. Never persist it "
        "automatically.",
        registry=r"Task Manager > Set Priority > High",
    ),
    Tweak(
        "refresh_rate_max", "Set the display to its maximum refresh rate", SAFE,
        "Ensures Windows is not running a 144 Hz panel at 60 Hz.",
        "Windows frequently defaults to 60 Hz after a driver update or "
        "cable change. This is one of the highest-impact checks on the "
        "whole list, and a surprising number of people play for months "
        "without noticing.",
        registry=r"Settings > Display > Advanced display",
    ),
    Tweak(
        "gsync_freesync_on", "Enable G-Sync / FreeSync", SAFE,
        "Matches display refresh to the rendered frame rate.",
        "Eliminates tearing without V-Sync's latency penalty. A genuine "
        "improvement in perceived smoothness. Best combined with a frame "
        "cap a few FPS below your refresh rate.",
        registry=r"NVIDIA Control Panel > Set up G-SYNC",
        also_known_as=('VRR', 'Adaptive Sync'),
    ),
    Tweak(
        "frame_cap_below_refresh", "Cap FPS just below refresh rate", SAFE,
        "Keeps the frame rate inside the variable-refresh window.",
        "The standard configuration for VRR displays. Prevents falling "
        "back to V-Sync behaviour at the top of the range, which is where "
        "latency spikes. Small, specific and well understood.",
        registry=r"NVIDIA Control Panel > Max Frame Rate",
        also_known_as=('RTSS cap',),
    ),
    Tweak(
        "hdr_toggle", "Disable HDR when not using it", SITUATIONAL,
        "Avoids the tone-mapping cost and washed-out SDR content.",
        "HDR left on in Windows makes SDR content look grey and costs a "
        "little GPU. If your display and game both support it properly, "
        "leave it on.",
        registry=r"Settings > Display > Use HDR",
    ),
    Tweak(
        "display_scaling_gpu", "Perform display scaling on the GPU", SITUATIONAL,
        "Moves scaling from the monitor to the graphics card.",
        "Usually lower latency than the monitor's own scaler. Only "
        "relevant when running below native resolution.",
        registry=r"NVIDIA Control Panel > Adjust desktop size and position",
    ),
    Tweak(
        "disable_second_monitor", "Disable secondary monitors while gaming", SITUATIONAL,
        "Stops the GPU compositing additional desktops.",
        "A real but small saving, and it can prevent mixed-refresh-rate "
        "stutter on older drivers. Modern drivers handle mixed refresh "
        "far better than they did, so test before adopting it as a habit.",
        registry=r"Win+P > PC screen only",
    ),
    Tweak(
        "integer_scaling", "Enable integer scaling", SITUATIONAL,
        "Scales low resolutions without blurring.",
        "An image-quality choice for retro or low-res play, not a "
        "performance one. No frame-rate effect.",
        registry=r"NVIDIA/AMD control panel",
    ),
    Tweak(
        "color_depth_8bit", "Force 8-bit colour depth", PLACEBO,
        "Claims lower colour depth means more bandwidth for frames.",
        "Display bandwidth only limits the maximum resolution and refresh "
        "combination. If your current mode works, reducing colour depth "
        "frees nothing and visibly worsens gradients.",
        registry=r"NVIDIA Control Panel > Change resolution",
    ),
    Tweak(
        "clear_pagefile_shutdown", "Clear the pagefile at shutdown", HARMFUL,
        "Claims a clean pagefile improves the next boot.",
        "Zeroes a multi-gigabyte file on every shutdown, adding minutes "
        "to it. A security feature for shared machines, catastrophic as a "
        "performance tweak.",
        registry=r"HKLM\\SYSTEM\\...\\Memory Management\\ClearPageFileAtShutdown",
    ),
    Tweak(
        "large_system_cache", "Enable LargeSystemCache", HARMFUL,
        "Claims prioritising the file cache speeds up games.",
        "Designed for file servers. On a desktop it lets the cache grow "
        "at the expense of application memory, causing paging in exactly "
        "the memory-hungry games it is supposed to help.",
        registry=r"HKLM\\SYSTEM\\...\\Memory Management\\LargeSystemCache",
    ),
    Tweak(
        "disable_paging_executive", "DisablePagingExecutive = 1", SITUATIONAL,
        "Keeps kernel drivers resident in RAM.",
        "Prevents kernel code being paged out, which can reduce rare "
        "latency spikes. Costs a few hundred megabytes. Defensible with "
        "32 GB, wasteful with 8 GB.",
        registry=r"HKLM\\SYSTEM\\...\\Memory Management\\DisablePagingExecutive",
    ),
    Tweak(
        "pagefile_fixed_size", "Set a fixed pagefile size", SITUATIONAL,
        "Stops the pagefile growing and fragmenting.",
        "Reasonable on a mechanical drive where fragmentation matters. On "
        "an SSD it makes no measurable difference, and setting it too "
        "small causes crashes in memory-hungry titles.",
        registry=r"System Properties > Virtual Memory",
    ),
    Tweak(
        "ram_timings_manual", "Manually tune RAM sub-timings", SITUATIONAL,
        "Squeezes extra latency out of memory.",
        "A genuine improvement for Ryzen 1% lows in the hands of someone "
        "who tests thoroughly. Unstable timings cause data corruption "
        "that looks like random crashes. Not a one-click item and Phantom "
        "Tweeks will not automate it.",
        registry=r"BIOS > Memory timings",
    ),
    Tweak(
        "memory_compression_off", "Disable memory compression", SITUATIONAL,
        "Stops Windows compressing pages instead of paging out.",
        "Trades CPU for RAM. Disabling it can help on a high-core-count "
        "machine with plenty of memory, and hurts badly on 8 GB systems "
        "where compression is preventing disk paging.",
        registry=r"Disable-MMAgent -mc",
    ),
    Tweak(
        "steam_disable_overlay", "Disable the Steam overlay", SITUATIONAL,
        "Removes Steam's in-game hooks.",
        "The overlay injects into the game and costs a small amount of "
        "performance. It also provides Shift+Tab, screenshots and "
        "browser. Disable per game rather than globally if you want the "
        "feature elsewhere.",
        registry=r"Steam > Settings > In Game",
    ),
    Tweak(
        "steam_disable_broadcast", "Disable Steam broadcasting", SAFE,
        "Stops Steam encoding your gameplay for viewers.",
        "If enabled, this is genuine continuous encoding work. Most "
        "people never intended to turn it on.",
        registry=r"Steam > Settings > Broadcast",
    ),
    Tweak(
        "discord_hardware_accel", "Toggle Discord hardware acceleration", SITUATIONAL,
        "Moves Discord rendering between GPU and CPU.",
        "GPU acceleration makes Discord smoother but competes with your "
        "game for GPU time. Turning it off shifts that to the CPU. Which "
        "is better depends on whether you are GPU-bound or CPU-bound - so "
        "measure.",
        registry=r"Discord > Settings > Advanced",
    ),
    Tweak(
        "disable_discord_overlay", "Disable the Discord overlay", SITUATIONAL,
        "Removes Discord's injection into the game.",
        "A known cause of stutter and crashes in some titles, and it is "
        "another hook in your process. Phantom Tweeks never closes "
        "Discord itself - this is a setting you change inside Discord.",
        registry=r"Discord > Settings > Game Overlay",
    ),
    Tweak(
        "epic_disable_cloud", "Disable Epic cloud saves during play", PLACEBO,
        "Claims background sync causes stutter.",
        "Cloud saves sync at launch and exit, not during gameplay. There "
        "is nothing running mid-session to disable.",
        registry=r"Epic Games Launcher > Settings",
    ),
    Tweak(
        "nvidia_overlay_off", "Disable the NVIDIA overlay", SITUATIONAL,
        "Removes the GeForce Experience in-game hook.",
        "Another injected overlay with a small cost. It also provides "
        "ShadowPlay - which is genuinely efficient hardware encoding, so "
        "weigh the loss.",
        registry=r"GeForce Experience > In-Game Overlay",
    ),
    Tweak(
        "disable_instant_replay", "Disable Instant Replay / background capture", SITUATIONAL,
        "Stops continuous rolling-buffer recording.",
        "This one is worth checking: continuous capture uses real GPU "
        "encode capacity and disk bandwidth the entire time you play, and "
        "many people leave it on without realising.",
        registry=r"GeForce Experience > Instant Replay",
        also_known_as=('ShadowPlay',),
    ),
    Tweak(
        "disable_vanguard_boot", "Stop Vanguard loading at boot", SITUATIONAL,
        "Prevents Riot's kernel driver starting with Windows.",
        "It only needs to be running for Riot games. Stopping it at boot "
        "means you must reboot before playing Valorant. A legitimate "
        "choice; not a performance tweak.",
        registry=r"Vanguard system tray > Exit",
    ),
    Tweak(
        "tamper_anticheat", "Modify or block anti-cheat drivers", HARMFUL,
        "Claims anti-cheat drivers cost performance.",
        "Interfering with EAC, BattlEye or Vanguard is indistinguishable "
        "from cheating as far as their detection is concerned, and "
        "results in hardware bans that are not appealable. Phantom Tweeks "
        "explicitly protects these processes.",
        registry=r"Various",
    ),
    Tweak(
        "disable_secure_boot", "Disable Secure Boot", HARMFUL,
        "Claims Secure Boot adds boot overhead.",
        "Costs nothing after boot. Valorant and several other titles now "
        "REQUIRE it - disabling it means the game will not launch at all. "
        "It also removes protection against bootkits.",
        registry=r"BIOS > Secure Boot",
    ),
    Tweak(
        "disable_tpm", "Disable the TPM", HARMFUL,
        "Claims TPM is unnecessary overhead.",
        "Required by Windows 11 and by some anti-cheat systems. Disabling "
        "it can lock BitLocker-encrypted drives and prevent games "
        "launching. No performance benefit exists.",
        registry=r"BIOS > TPM / fTPM",
    ),
    Tweak(
        "disable_rgb_software", "Close RGB control software while gaming", SITUATIONAL,
        "Removes vendor utilities that poll hardware constantly.",
        "iCUE, Armoury Crate, Synapse and similar are frequently among "
        "the heaviest idle background processes on a gaming PC, and "
        "several are known DPC-latency offenders. A real saving - but "
        "they also control your fan curves, so do not simply delete them.",
        registry=r"Task Manager",
        also_known_as=('iCUE', 'Armoury Crate', 'Synapse'),
    ),
    Tweak(
        "msi_afterburner_osd", "Disable the Afterburner on-screen display", SITUATIONAL,
        "Removes the RivaTuner overlay hook.",
        "RTSS injects into every game. Its overhead is small and it is "
        "very useful for measurement - keep it while benchmarking, drop "
        "it if you are chasing the last frame.",
        registry=r"RivaTuner Statistics Server",
        also_known_as=('RTSS',),
    ),
    Tweak(
        "disable_telemetry_gpu", "Disable GPU driver telemetry", SAFE,
        "Stops NVIDIA/AMD usage reporting tasks.",
        "Scheduled tasks that phone home periodically. Disabling them is "
        "a privacy improvement with a negligible performance effect - "
        "which is the honest way to describe it.",
        registry=r"Task Scheduler > NvTmRep",
    ),
    Tweak(
        "hwinfo_polling", "Reduce hardware monitoring poll rate", SITUATIONAL,
        "Lowers how often sensors are read.",
        "Aggressive sensor polling genuinely causes DPC latency spikes on "
        "some motherboards, because SMBus reads stall. If you monitor "
        "while playing, a 2-second interval is plenty.",
        registry=r"HWiNFO > Settings > Polling Period",
    ),
    Tweak(
        "game_settings_shadows", "Lower shadow quality first", SAFE,
        "Shadows are usually the most expensive quality setting.",
        "In-game settings dwarf every registry tweak on this page. Shadow "
        "resolution and distance typically cost more frames than anything "
        "else and are among the least noticeable in motion.",
        registry=r"In-game graphics settings",
    ),
    Tweak(
        "game_settings_reflections", "Reduce reflection quality", SAFE,
        "Screen-space and ray-traced reflections are expensive.",
        "Often a large frame-rate gain for a change you will not notice "
        "during play. Real, measurable, and free.",
        registry=r"In-game graphics settings",
    ),
    Tweak(
        "game_settings_volumetrics", "Reduce volumetric fog and clouds", SAFE,
        "Volumetric effects are heavy and often subtle.",
        "Frequently one of the top three costs in modern engines. "
        "Lowering it is a much better first move than editing the "
        "registry.",
        registry=r"In-game graphics settings",
    ),
    Tweak(
        "render_scale", "Lower the render scale", SAFE,
        "Renders below native resolution and upscales.",
        "The single most effective performance control in any game. "
        "Scales almost linearly with GPU load. Costs sharpness - use "
        "DLSS/FSR quality modes instead where available.",
        registry=r"In-game graphics settings",
        also_known_as=('Resolution scale',),
    ),
    Tweak(
        "dlss_fsr_upscaling", "Enable DLSS / FSR / XeSS", SAFE,
        "Renders at a lower resolution and reconstructs detail.",
        "Genuine large gains with far less quality loss than plain render "
        "scaling. Quality mode is usually near-indistinguishable. The "
        "most effective real optimization available in modern titles.",
        registry=r"In-game graphics settings",
        also_known_as=('Super resolution',),
    ),
    Tweak(
        "frame_generation", "Frame generation", SITUATIONAL,
        "Inserts interpolated frames between rendered ones.",
        "Raises the FPS counter substantially but does not reduce input "
        "latency - it slightly increases it. Good for smoothness in "
        "single-player, generally wrong for competitive shooters. The "
        "distinction matters and is often glossed over.",
        registry=r"In-game graphics settings",
        also_known_as=('DLSS 3 FG', 'FSR 3 FG'),
    ),
    Tweak(
        "disable_motion_blur", "Disable motion blur", SAFE,
        "Removes per-object and camera blur.",
        "Small performance gain and a clarity improvement most "
        "competitive players prefer. Purely subjective beyond the frame "
        "cost.",
        registry=r"In-game graphics settings",
    ),
    Tweak(
        "disable_depth_of_field", "Disable depth of field", SAFE,
        "Removes background blurring.",
        "Cheap to disable, improves visibility of distant targets. A "
        "reasonable default for competitive play.",
        registry=r"In-game graphics settings",
    ),
    Tweak(
        "texture_quality_vram", "Match texture quality to VRAM", SAFE,
        "Prevents texture streaming from exceeding video memory.",
        "Exceeding VRAM causes severe stutter as textures stream over "
        "PCIe. Reducing texture quality one step often eliminates "
        "hitching entirely with minimal visual loss.",
        registry=r"In-game graphics settings",
    ),
    Tweak(
        "exclusive_fullscreen", "Use exclusive fullscreen", SITUATIONAL,
        "Bypasses the desktop compositor.",
        "Historically a clear latency win. With flip-model presentation "
        "the gap has largely closed, and borderless keeps alt-tab fast. "
        "Test rather than assuming the old advice still holds.",
        registry=r"In-game display mode",
    ),
    Tweak(
        "disable_ingame_vsync", "Disable in-game V-Sync", SITUATIONAL,
        "Removes the refresh-rate frame cap.",
        "Lower latency, at the cost of tearing. Wrong if you use "
        "G-Sync/FreeSync, where the recommended setup keeps V-Sync on "
        "with a frame cap below refresh.",
        registry=r"In-game graphics settings",
    ),
    Tweak(
        "reduce_view_distance", "Lower view distance", SITUATIONAL,
        "Reduces how far the engine draws detailed geometry.",
        "A large CPU saving in open-world games. In competitive titles it "
        "can hide distant players, which is a tactical loss - so it is a "
        "genuine trade rather than a free win.",
        registry=r"In-game graphics settings",
    ),
    Tweak(
        "disable_ambient_occlusion", "Disable ambient occlusion", SAFE,
        "Removes contact shadowing.",
        "Moderate gain for mild visual flattening. A safe early choice "
        "when you need frames back without editing the registry.",
        registry=r"In-game graphics settings",
        also_known_as=('SSAO', 'HBAO'),
    ),
    Tweak(
        "config_file_edits", "Edit game config files directly", SITUATIONAL,
        "Exposes settings below the in-game minimums.",
        "Can genuinely unlock lower settings than the menu allows. But "
        "some anti-cheat systems flag modified config files, and a syntax "
        "error can make the game refuse to start. Back up the file first.",
        registry=r"Game config .ini / .cfg",
    ),
    Tweak(
        "launch_options_highpri", "Launch options: -high", SITUATIONAL,
        "Starts the game at High priority.",
        "Same caveats as setting priority manually - can starve audio and "
        "input on a constrained CPU. At least it is scoped to that launch "
        "rather than persisted.",
        registry=r"Steam > Launch Options",
    ),
    Tweak(
        "launch_options_novid", "Launch options: -novid", SAFE,
        "Skips intro videos.",
        "Saves you several seconds every launch. No performance claim, "
        "just a genuine quality-of-life improvement.",
        registry=r"Steam > Launch Options",
    ),
    Tweak(
        "launch_options_threads", "Launch options: -threads N", PLACEBO,
        "Claims to tell the engine how many cores to use.",
        "Most modern engines detect core count correctly. Setting it "
        "manually usually does nothing and occasionally caps the engine "
        "below your actual capability.",
        registry=r"Steam > Launch Options",
    ),
    Tweak(
        "disable_steam_input", "Disable Steam Input when unused", SITUATIONAL,
        "Stops Steam's controller abstraction layer.",
        "Removes an input translation layer. Only relevant if you use a "
        "controller; disabling it can break controller support entirely "
        "in some games.",
        registry=r"Steam > Controller settings",
    ),
    Tweak(
        "windowed_borderless_alt_tab", "Borderless for fast alt-tab", SAFE,
        "Trades a tiny amount of latency for instant switching.",
        "A legitimate preference, especially with multiple monitors. The "
        "latency difference on modern Windows is much smaller than older "
        "guides claim.",
        registry=r"In-game display mode",
    ),
    Tweak(
        "verify_game_files", "Verify game file integrity", SAFE,
        "Repairs corrupted or partially downloaded assets.",
        "A real fix for stutter and crashes caused by bad files, and it "
        "is completely safe. Worth doing before any registry tweaking - "
        "it addresses an actual cause rather than a theoretical one.",
        registry=r"Steam > Properties > Installed Files",
    ),
    Tweak(
        "move_game_to_ssd", "Move the game to an SSD", SAFE,
        "Eliminates mechanical seek times for asset streaming.",
        "For anyone still on a hard drive this produces a far larger "
        "real-world improvement than every software tweak combined - "
        "loading times, texture pop-in and traversal stutter all improve.",
        registry=r"Steam > Properties > Move install folder",
    ),
    Tweak(
        "close_browser_tabs", "Close the browser while playing", SAFE,
        "Frees memory and background CPU.",
        "Chrome with thirty tabs and hardware acceleration is a genuine "
        "competitor for GPU and RAM. Unglamorous, and more effective than "
        "most of the registry tweaks people try first.",
        registry=r"N/A",
    ),
    Tweak(
        "disable_browser_hw_accel", "Disable browser hardware acceleration", SITUATIONAL,
        "Stops the browser using the GPU while you game.",
        "Frees GPU time and video memory. Makes the browser itself "
        "noticeably less smooth, so it depends on whether you alt-tab "
        "often.",
        registry=r"Browser > Settings > System",
    ),
    Tweak(
        "update_gpu_drivers", "Keep GPU drivers current", SAFE,
        "Game-ready drivers include real per-title optimizations.",
        "Driver updates deliver genuine, sometimes double-digit gains in "
        "new releases. Occasionally a release regresses - which is why "
        "Phantom Tweeks records benchmark history so you can see it.",
        registry=r"GeForce Experience / AMD Adrenalin",
    ),
    Tweak(
        "chipset_drivers", "Install chipset drivers", SAFE,
        "Provides the correct power and scheduling behaviour.",
        "Particularly important on AMD, where the chipset driver supplies "
        "the power plan and CCX-aware scheduling. Frequently overlooked "
        "after a fresh Windows install and a real cause of "
        "underperformance.",
        registry=r"Motherboard vendor site",
    ),
    Tweak(
        "clean_dust_thermals", "Clean dust and check thermals", SAFE,
        "Restores cooling capacity so boost clocks are sustained.",
        "A thermally throttled CPU or GPU loses far more performance than "
        "any tweak on this page can recover. The least glamorous and most "
        "effective item here.",
        registry=r"Physical maintenance",
    ),
    Tweak(
        "repaste_thermal", "Replace thermal paste", SITUATIONAL,
        "Restores heat transfer on an older machine.",
        "Genuinely effective on laptops and systems more than three or "
        "four years old. Carries a real risk of physical damage if done "
        "carelessly, and may void a warranty.",
        registry=r"Physical maintenance",
    ),
    Tweak(
        "check_psu_headroom", "Check power supply headroom", SAFE,
        "An overloaded PSU causes crashes under load.",
        "Diagnostic rather than an optimization: sudden shutdowns during "
        "gaming are frequently power delivery, not software. Worth ruling "
        "out before tweaking anything.",
        registry=r"Hardware inspection",
    ),
    Tweak(
        "bios_update", "Update the motherboard BIOS", SITUATIONAL,
        "Improves CPU compatibility, memory stability and boost behaviour.",
        "Can deliver real gains, especially AGESA updates on AMD. A "
        "failed flash can also brick the board, so only do it for a "
        "specific documented fix.",
        registry=r"Motherboard vendor site",
    ),
    Tweak(
        "resizable_bar", "Enable Resizable BAR", SITUATIONAL,
        "Lets the CPU access the whole GPU frame buffer at once.",
        "Measurable gains in some titles, small losses in others - it is "
        "genuinely per-game. Both NVIDIA and AMD maintain per-title "
        "profiles for exactly this reason.",
        registry=r"BIOS > Above 4G Decoding / ReBAR",
        also_known_as=('Smart Access Memory',),
    ),
    Tweak(
        "disable_ndu", "Disable the Ndu network usage driver", SITUATIONAL,
        "Stops the network data usage monitor.",
        "Had a genuine memory-leak bug in early Windows 10 builds. Long "
        "fixed. Disabling it now removes Task Manager's per-app network "
        "figures for no measurable gain.",
        registry=r"HKLM\\SYSTEM\\...\\Services\\Ndu\\Start",
    ),
    Tweak(
        "svchost_split_threshold", "Raise SvcHostSplitThresholdInKB", SITUATIONAL,
        "Groups services into fewer svchost processes.",
        "Windows splits services into separate processes above 3.5 GB RAM "
        "for reliability and security isolation. Grouping them saves a "
        "little memory overhead and loses that isolation - one crashing "
        "service can take others with it.",
        registry=r"HKLM\\SYSTEM\\CurrentControlSet\\Control\\SvcHostSplitThresholdInKB",
    ),
    Tweak(
        "io_page_lock_limit", "IoPageLockLimit", PLACEBO,
        "Claims to increase I/O throughput.",
        "A Windows NT 4 tuning value. Ignored entirely by modern kernels. "
        "It survives on tweak lists purely through copying.",
        registry=r"HKLM\\SYSTEM\\...\\Memory Management\\IoPageLockLimit",
    ),
    Tweak(
        "second_level_cache", "SecondLevelDataCache", PLACEBO,
        "Claims telling Windows your L2 cache size improves scheduling.",
        "Windows reads cache size from the CPU directly. The value is "
        "only used if the firmware fails to report it, which has not "
        "happened on consumer hardware in decades.",
        registry=r"HKLM\\SYSTEM\\...\\Memory Management\\SecondLevelDataCache",
    ),
    Tweak(
        "disable_ntfs_compression", "Disable NTFS compression on game folders", SITUATIONAL,
        "Stops the CPU decompressing files on every read.",
        "Only relevant if compression was enabled, which is rare and "
        "usually accidental. When it is on, disabling it genuinely helps "
        "load times.",
        registry=r"Folder Properties > Advanced",
    ),
    Tweak(
        "win32_priority_2a", "Win32PrioritySeparation = 2A hex", PLACEBO,
        "An alternative magic value to 26.",
        "Different guides quote 26, 2A, 24 and 38 with equal confidence "
        "and no measurements. The variation itself is the tell: these are "
        "copied, not derived.",
        registry=r"HKLM\\SYSTEM\\...\\PriorityControl\\Win32PrioritySeparation",
    ),
    Tweak(
        "disable_dynamic_fair_share", "Disable Dynamic Fair Share Scheduling", PLACEBO,
        "Claims DFSS steals CPU from foreground apps.",
        "DFSS only applies to Remote Desktop sessions, balancing CPU "
        "between multiple logged-in users. It has no effect on a "
        "single-user desktop.",
        registry=r"HKLM\\SYSTEM\\...\\Session Manager\\Quota System\\EnableCpuQuota",
    ),
    Tweak(
        "disable_gamedvr_policy", "Disable Game DVR via policy", SAFE,
        "Machine-wide equivalent of the per-user Game DVR toggle.",
        "The same real benefit as the per-user setting, applied for every "
        "account on the machine. Fully reversible at any time.",
        registry=r"HKLM\\...\\PolicyManager\\default\\ApplicationManagement\\AllowGameDVR",
    ),
    Tweak(
        "disable_mouse_smoothing_reg", "Remove mouse smoothing curves", SAFE,
        "Zeroes the acceleration threshold values.",
        "The registry counterpart of turning off Enhanced Pointer "
        "Precision. Same real benefit for aim consistency.",
        registry=r"HKCU\\Control Panel\\Mouse\\MouseThreshold1",
    ),
    Tweak(
        "network_binding_order", "Change the network binding order", PLACEBO,
        "Claims prioritising an adapter reduces latency.",
        "Binding order affects which adapter Windows prefers for name "
        "resolution, not packet routing. The routing table decides where "
        "traffic goes, and it is metric-based.",
        registry=r"Network Connections > Advanced Settings",
    ),
    Tweak(
        "disable_wifi_when_wired", "Disable Wi-Fi when using Ethernet", SAFE,
        "Removes an unnecessary interface.",
        "Prevents traffic occasionally routing over the slower link, and "
        "removes a source of interference. Small, real, easily undone.",
        registry=r"Network Connections",
    ),
    Tweak(
        "set_dns_manually", "Set DNS manually rather than DHCP", SITUATIONAL,
        "Uses a chosen resolver instead of your ISP's.",
        "Can genuinely speed up name lookups, which affects launcher and "
        "web responsiveness. It does not change in-game ping. Phantom "
        "Tweeks measures this properly in the DNS Lab.",
        registry=r"Network adapter > IPv4 properties",
    ),
    Tweak(
        "disable_netbios", "Disable NetBIOS over TCP/IP", SITUATIONAL,
        "Removes legacy name-resolution broadcasts.",
        "Slightly reduces broadcast chatter and closes an old attack "
        "surface. Can break discovery of older network shares and "
        "printers.",
        registry=r"IPv4 > Advanced > WINS",
    ),
    Tweak(
        "disable_llmnr", "Disable LLMNR", SAFE,
        "Stops link-local multicast name resolution.",
        "A genuine security improvement - LLMNR is routinely abused for "
        "credential relay attacks. Negligible performance impact either "
        "way, which is how it should be described.",
        registry=r"HKLM\\...\\DNSClient\\EnableMulticast",
    ),
    Tweak(
        "mtu_tuning", "Manually tune the MTU", SITUATIONAL,
        "Matches packet size to the path to avoid fragmentation.",
        "Occasionally fixes real problems on PPPoE or VPN connections "
        "where the effective MTU is below 1500. Setting it wrongly causes "
        "silent packet loss that is very hard to diagnose.",
        registry=r"netsh interface ipv4 set subinterface",
    ),
    Tweak(
        "disable_auto_disconnect", "Disable idle session auto-disconnect", PLACEBO,
        "Claims to keep game connections alive.",
        "Applies to SMB file-sharing sessions only. It has nothing to do "
        "with game server connections.",
        registry=r"HKLM\\SYSTEM\\...\\LanmanServer\\Parameters\\autodisconnect",
    ),
    Tweak(
        "gaming_vpn", "Gaming VPNs for lower ping", SITUATIONAL,
        "Routes traffic through an alternative path to the server.",
        "Genuinely helps in the specific case where your ISP's default "
        "route is poor - it can shorten the path. It cannot beat physics: "
        "if the direct route is already good, adding a hop makes latency "
        "worse. Test both.",
        registry=r"Third-party service",
        also_known_as=('ExitLag', 'WTFast'),
    ),
    Tweak(
        "router_qos", "Enable QoS on the router", SITUATIONAL,
        "Prioritises game traffic over bulk downloads.",
        "Real and effective when someone else on the network is "
        "saturating the connection. Does nothing when the link is idle, "
        "which is when most people test it and conclude it failed.",
        registry=r"Router admin > QoS",
    ),
    Tweak(
        "ethernet_over_wifi", "Use Ethernet instead of Wi-Fi", SAFE,
        "Removes wireless interference and retransmission jitter.",
        "One of the largest genuine latency improvements available, and "
        "far more effective than any registry tweak. Wi-Fi jitter is "
        "frequently the actual cause of the problem people are trying to "
        "tweak away.",
        registry=r"Physical connection",
    ),
    Tweak(
        "disable_bandwidth_hogs", "Pause background downloads while gaming", SAFE,
        "Stops Steam, Windows Update and cloud sync competing for bandwidth.",
        "Directly addresses a real and common cause of lag spikes. "
        "Phantom Tweeks reports heavy consumers rather than killing them.",
        registry=r"Steam > Downloads > Throttle",
    ),
    Tweak(
        "disable_delivery_optimization", "Disable Delivery Optimization uploads", SAFE,
        "Stops your PC seeding Windows updates to other machines.",
        "Genuinely uses upload bandwidth in the background, which matters "
        "because upstream saturation causes latency spikes. A real, "
        "defensible change.",
        registry=r"Settings > Delivery Optimization",
    ),
    Tweak(
        "disable_maps_download", "Disable offline maps auto-update", SAFE,
        "Stops periodic background map downloads.",
        "Small, but real background disk and network activity for a "
        "feature almost nobody uses on a gaming PC.",
        registry=r"Settings > Apps > Offline maps",
    ),
    Tweak(
        "power_plan_ultimate", "Enable the Ultimate Performance plan", SITUATIONAL,
        "A hidden power plan with all savings disabled.",
        "Marginally more aggressive than High Performance. The measurable "
        "difference on a desktop is very small; on a laptop it is "
        "actively harmful to battery and thermals.",
        registry=r"powercfg -duplicatescheme e9a42b02-d5df-448d-aa00-03f14749eb61",
    ),
    Tweak(
        "disable_usb_power_saving", "Disable USB hub power saving", SITUATIONAL,
        "Stops Windows suspending USB root hubs.",
        "Fixes genuine peripheral dropouts. Slightly higher idle power. "
        "Not a frame-rate change - a reliability one.",
        registry=r"Device Manager > USB Root Hub > Power Management",
    ),
    Tweak(
        "disable_pcie_aspm", "Disable PCIe link power management", SITUATIONAL,
        "Keeps PCIe lanes at full power.",
        "Can reduce rare latency spikes from link state transitions, and "
        "occasionally fixes GPU or NVMe dropouts. Costs idle power. Only "
        "pursue it if you have measured a problem.",
        registry=r"powercfg > PCI Express > Link State Power Management",
        also_known_as=('ASPM',),
    ),
    Tweak(
        "disable_hpet_bios", "Disable HPET in BIOS", SITUATIONAL,
        "Removes the timer from the hardware table entirely.",
        "Distinct from the bcdedit tweak. On specific older AMD platforms "
        "this genuinely helped; on modern hardware Windows already "
        "prefers the invariant TSC, so the change is usually inert.",
        registry=r"BIOS > Advanced > HPET",
    ),
    Tweak(
        "cstate_c1e_only", "Allow C1E but disable deeper C-states", SITUATIONAL,
        "A middle ground between full C-states and none.",
        "More defensible than disabling all idle states: keeps most of "
        "the thermal headroom that boost depends on, while avoiding the "
        "deepest wake latencies. Still needs measurement to justify.",
        registry=r"BIOS > CPU C-State Control",
    ),
    Tweak(
        "disable_virtualization", "Disable virtualization (VT-x / SVM)", HARMFUL,
        "Claims virtualization support costs performance.",
        "It costs nothing when unused. Disabling it breaks WSL, Docker, "
        "Android emulators, Hyper-V and - critically - some anti-cheat "
        "systems that require virtualization-based security.",
        registry=r"BIOS > Virtualization Technology",
    ),
    Tweak(
        "windows_11_vbs_off", "Turn off VBS on Windows 11", SITUATIONAL,
        "Disables virtualization-based security.",
        "There is a measurable cost on older CPUs, so this is not pure "
        "myth. But it weakens kernel protection and several anti-cheats "
        "now require it. Listed as situational rather than safe because "
        "the trade is real in both directions.",
        registry=r"Settings > Core isolation > Memory integrity",
    ),
    Tweak(
        "game_bar_uninstall", "Uninstall the Xbox Game Bar", SITUATIONAL,
        "Removes the overlay entirely rather than disabling it.",
        "Fine if you never use it. Some games use its APIs for "
        "screenshots and recording, and Windows occasionally reinstalls "
        "it after updates.",
        registry=r"Get-AppxPackage *XboxGamingOverlay* | Remove-AppxPackage",
    ),
    Tweak(
        "disable_hyper_v", "Disable Hyper-V when unused", SITUATIONAL,
        "Removes the hypervisor layer Windows runs on top of.",
        "With Hyper-V enabled, Windows itself runs virtualised, which has "
        "a small measurable cost. Disabling it breaks WSL2, Docker, "
        "Windows Sandbox and some anti-cheat requirements. A real trade "
        "in both directions.",
        registry=r"bcdedit /set hypervisorlaunchtype off",
    ),
    Tweak(
        "disable_dep", "Disable Data Execution Prevention", HARMFUL,
        "Claims DEP adds overhead to code execution.",
        "DEP is enforced by the CPU's NX bit and costs essentially "
        "nothing. Disabling it re-enables an entire category of "
        "buffer-overflow exploits that have been mitigated since 2004.",
        registry=r"bcdedit /set nx AlwaysOff",
    ),
    Tweak(
        "disable_aslr", "Disable ASLR", HARMFUL,
        "Claims address randomisation slows module loading.",
        "The load-time cost is microseconds. ASLR is one of the core "
        "defences making memory-corruption exploits unreliable. Some "
        "cheat tools ask users to disable it, which should tell you what "
        "it is for.",
        registry=r"Exploit protection > Force randomization",
    ),
    Tweak(
        "disable_cfg", "Disable Control Flow Guard", HARMFUL,
        "Claims CFG checks cost CPU on every indirect call.",
        "The overhead is around 1%. CFG stops attackers redirecting "
        "execution to arbitrary code. Several games also enable it "
        "deliberately, and overriding it system-wide can make them fail "
        "to start.",
        registry=r"Exploit protection > Control flow guard",
    ),
    Tweak(
        "clear_dns_cache", "Flush the DNS cache", SAFE,
        "Clears stale name-resolution entries.",
        "A legitimate fix when a server has moved and you are still "
        "resolving the old address. Not a performance tweak - a "
        "troubleshooting step.",
        registry=r"ipconfig /flushdns",
    ),
    Tweak(
        "winsock_reset", "Reset the Winsock catalog", SITUATIONAL,
        "Restores the network stack to defaults.",
        "Genuinely fixes connectivity broken by badly behaved VPN or "
        "proxy software. Also undoes legitimate network configuration, so "
        "it is a repair action rather than an optimization.",
        registry=r"netsh winsock reset",
    ),
    Tweak(
        "disable_auto_tuning_wifi", "Disable Wi-Fi roaming aggressiveness", SITUATIONAL,
        "Stops the adapter hunting for a stronger access point.",
        "Prevents mid-game disconnects when two access points have "
        "similar signal strength. Only relevant on Wi-Fi, and it makes "
        "moving between rooms worse.",
        registry=r"Device Manager > Wi-Fi > Roaming Aggressiveness",
    ),
    Tweak(
        "preferred_band_5ghz", "Prefer the 5 GHz band", SAFE,
        "Avoids the congested 2.4 GHz spectrum.",
        "A real and significant latency and jitter improvement on Wi-Fi, "
        "because 2.4 GHz shares space with microwaves, Bluetooth and "
        "every neighbouring router.",
        registry=r"Device Manager > Wi-Fi > Preferred Band",
    ),
    Tweak(
        "disable_powershell_telemetry", "Disable PowerShell telemetry", SAFE,
        "Stops the shell reporting usage data.",
        "A privacy setting with no meaningful performance effect, and it "
        "should be described that way rather than as an optimization.",
        registry=r"POWERSHELL_TELEMETRY_OPTOUT=1",
    ),
    Tweak(
        "disable_activity_history", "Disable activity history", SAFE,
        "Stops Windows recording and syncing your app timeline.",
        "Removes periodic background writes and an upload. Privacy "
        "benefit is the honest justification; the performance effect is "
        "negligible.",
        registry=r"Settings > Privacy > Activity history",
    ),
    Tweak(
        "disable_location", "Disable location services", SAFE,
        "Stops the location provider polling.",
        "Small real saving if enabled, plus a privacy improvement. Breaks "
        "weather and Find My Device.",
        registry=r"Settings > Privacy > Location",
    ),
    Tweak(
        "disable_advertising_id", "Reset and disable the advertising ID", SAFE,
        "Stops cross-app ad tracking.",
        "Pure privacy. Zero performance impact, and any list claiming "
        "otherwise is padding.",
        registry=r"Settings > Privacy > General",
    ),
    Tweak(
        "disable_clipboard_history", "Disable clipboard history and sync", SITUATIONAL,
        "Worth doing if you ever copy passwords, since history retains them and cloud sync uploads them. The resource cost either way is trivial.",
        "Worth doing if you ever copy passwords, since history retains "
        "them and cloud sync uploads them. The resource cost either way "
        "is trivial.",
        registry=r"Settings > System > Clipboard",
    ),
    Tweak(
        "disable_recall", "Disable Windows Recall", SITUATIONAL,
        "Stops continuous screenshotting and indexing of your screen.",
        "Where present, Recall does genuinely continuous capture and "
        "on-device analysis - real CPU, disk and privacy cost. Disabling "
        "it is defensible on both grounds.",
        registry=r"Settings > Privacy > Recall",
    ),
    Tweak(
        "disable_copilot", "Disable Copilot", SITUATIONAL,
        "Removes the assistant and its background process.",
        "Frees some memory on systems where it is preloaded. Modest, "
        "real, easily reversed.",
        registry=r"HKCU\\...\\WindowsCopilot\\TurnOffWindowsCopilot",
    ),
    Tweak(
        "scheduled_task_cleanup", "Disable unnecessary scheduled tasks", SITUATIONAL,
        "Stops vendor telemetry and update-check tasks running.",
        "Real background activity, particularly the GPU vendor and OEM "
        "tasks. Disabling the wrong one can break driver updates, so "
        "review each rather than running a bulk script.",
        registry=r"Task Scheduler",
    ),
    Tweak(
        "disable_office_telemetry", "Disable Office telemetry tasks", SAFE,
        "Stops Office usage reporting.",
        "Same category as GPU telemetry: a privacy improvement with "
        "negligible performance effect.",
        registry=r"Task Scheduler > Microsoft Office",
    ),
    Tweak(
        "disable_compattelrunner", "Disable CompatTelRunner", SITUATIONAL,
        "Stops the application compatibility appraiser.",
        "This one genuinely does spike CPU and disk periodically, "
        "sometimes for minutes, and is a real cause of unexplained "
        "stutter. Disabling the scheduled task is reversible.",
        registry=r"Task Scheduler > Application Experience",
        also_known_as=('Microsoft Compatibility Appraiser',),
    ),
    Tweak(
        "disable_wsappx", "Reduce wsappx activity", PLACEBO,
        "Claims wsappx constantly consumes CPU.",
        "wsappx only runs while Store apps are installing or updating. It "
        "idles otherwise. It cannot be disabled without breaking Store "
        "apps, and there is nothing to reclaim.",
        registry=r"services.msc > AppXSvc",
    ),
    Tweak(
        "nvidia_debug_mode", "Enable NVIDIA debug mode", SITUATIONAL,
        "Resets a factory-overclocked card to reference clocks.",
        "Useful for diagnosing instability on a factory-OC card - if the "
        "crash disappears, the overclock was the cause. Slightly lower "
        "performance while enabled. A diagnostic, not an optimization.",
        registry=r"NVIDIA Control Panel > Help > Debug Mode",
    ),
    Tweak(
        "disable_nvidia_telemetry", "Disable NVIDIA telemetry", SAFE,
        "Stops the driver's usage reporting components.",
        "Privacy improvement, negligible performance effect. Honest "
        "framing matters here because several tweak sites present it as "
        "an FPS gain.",
        registry=r"Task Scheduler > NvTmRep",
    ),
    Tweak(
        "amd_disable_metrics", "Disable AMD user experience reporting", SAFE,
        "Same as the NVIDIA equivalent: this is a privacy setting, not a performance one, and any list presenting it as an FPS gain is padding.",
        "Same as the NVIDIA equivalent: this is a privacy setting and not "
        "a performance one. Any list presenting it as an FPS gain is "
        "padding.",
        registry=r"AMD Adrenalin > Preferences",
    ),
    Tweak(
        "disable_game_bar_capture", "Disable background capture in Game Bar", SAFE,
        "Stops the 'record the last 30 seconds' buffer.",
        "This is continuous encoding whenever it is enabled - a genuine, "
        "ongoing GPU and disk cost that many people leave on without "
        "realising.",
        registry=r"Settings > Gaming > Captures",
    ),
    Tweak(
        "audio_sample_rate_match", "Match the audio sample rate to your content", SITUATIONAL,
        "Avoids real-time resampling.",
        "Removes a small amount of DSP work and can fix crackling. "
        "Inaudible in most setups, but harmless to set correctly.",
        registry=r"Sound > Device Properties > Advanced",
    ),
    Tweak(
        "disable_spatial_audio", "Disable spatial audio processing", SITUATIONAL,
        "Removes virtual surround processing.",
        "Reduces audio latency slightly. You lose positional cues that "
        "some competitive players rely on, so it is a genuine trade.",
        registry=r"Sound > Spatial sound",
    ),
    Tweak(
        "increase_audio_buffer", "Increase the audio buffer", SITUATIONAL,
        "Trades latency for stability.",
        "The correct fix for crackling under load, and the opposite of "
        "what most 'low latency' guides recommend. Which is right depends "
        "on whether you have dropouts or delay.",
        registry=r"Audio driver control panel",
    ),
    Tweak(
        "disable_onboard_audio", "Disable unused onboard audio devices", SAFE,
        "Removes idle audio endpoints.",
        "Stops Windows enumerating devices you never use, and prevents "
        "applications defaulting to the wrong output - a real and common "
        "annoyance.",
        registry=r"Device Manager > Sound devices",
    ),
    Tweak(
        "check_cable_quality", "Check the display cable specification", SAFE,
        "An inadequate cable silently caps refresh rate.",
        "A genuinely common cause of a 144 Hz monitor running at 60 Hz. "
        "Costs nothing to verify, and the fix is a cable rather than a "
        "tweak.",
        registry=r"Physical inspection",
    ),
    Tweak(
        "monitor_overdrive", "Tune monitor overdrive", SITUATIONAL,
        "Reduces pixel response time and ghosting.",
        "A real image-quality improvement at the right setting. Too "
        "aggressive and you get inverse ghosting, which is worse than the "
        "smearing it fixes.",
        registry=r"Monitor OSD > Overdrive / Response Time",
    ),
    Tweak(
        "disable_monitor_power_save", "Disable display power saving while gaming", PLACEBO,
        "Claims the display sleeping mid-game causes stutter.",
        "The display only sleeps after a period with no input. During "
        "gameplay there is constant input, so the timer never fires.",
        registry=r"powercfg > Turn off display",
    ),
)

TWEAKS = TWEAKS + _EXTENDED
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
