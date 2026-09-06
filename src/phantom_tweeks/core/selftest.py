"""Self-diagnostic - proves the installation is intact and working.

Why this exists
---------------
A user reported ``ImportError: attempted relative import with no known parent
package`` from a packaged build. They had no way to tell whether the problem
was their PC, their antivirus, or our packaging - and neither did we, from a
one-line traceback.

``python run.py doctor`` (or the Help menu) answers that. It checks every
subsystem, reports what works and what does not, and states plainly whether a
failure is the app's fault or the environment's. Output is safe to paste into
a bug report: it contains no personal paths beyond the install location and no
identifying information.
"""
from __future__ import annotations

import importlib
import os
import platform
import sys
from dataclasses import dataclass, field
from typing import Optional

OK = "OK"
WARN = "WARN"
FAIL = "FAIL"


@dataclass
class Check:
    name: str
    status: str = OK
    detail: str = ""
    fix: str = ""
    ours: Optional[bool] = None      # True = our bug, False = environment

    def render(self) -> str:
        line = f"  [{self.status:4}] {self.name}"
        if self.detail:
            line += f"\n         {self.detail}"
        if self.fix:
            line += f"\n         Fix: {self.fix}"
        return line


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.status == FAIL]

    @property
    def warnings(self) -> list[Check]:
        return [c for c in self.checks if c.status == WARN]

    @property
    def healthy(self) -> bool:
        return not self.failures

    def render(self) -> str:
        out = ["PHANTOM TWEEKS SELF-TEST", ""]
        out += [c.render() for c in self.checks]
        out.append("")
        if self.healthy and not self.warnings:
            out.append("Everything checks out. The installation is healthy.")
        elif self.healthy:
            out.append(f"Working, with {len(self.warnings)} limitation(s) noted "
                       "above. These reduce what can be measured but do not "
                       "stop the app running.")
        else:
            ours = [c for c in self.failures if c.ours]
            out.append(f"{len(self.failures)} problem(s) found.")
            if ours:
                out.append("At least one is a bug in Phantom Tweeks, not your "
                           "PC. Please report the output above.")
        return "\n".join(out)


# Import name -> what breaks without it.
_SUBSYSTEMS = [
    ("phantom_tweeks.core.paths", "data storage"),
    ("phantom_tweeks.core.config", "settings"),
    ("phantom_tweeks.core.shield", "Phantom Shield"),
    ("phantom_tweeks.core.games", "game detection"),
    ("phantom_tweeks.core.gamewatch", "live game watching"),
    ("phantom_tweeks.core.features", "feature gating"),
    ("phantom_tweeks.core.runproc", "external commands"),
    ("phantom_tweeks.engine.catalog", "the optimization catalog"),
    ("phantom_tweeks.engine.optimizer", "applying optimizations"),
    ("phantom_tweeks.engine.backup", "backup and restore"),
    ("phantom_tweeks.engine.maintenance", "maintenance mode"),
    ("phantom_tweeks.engine.history", "performance history"),
    ("phantom_tweeks.hardware.monitor", "hardware monitoring"),
    ("phantom_tweeks.network.lab", "the network lab"),
    ("phantom_tweeks.licensing.keys", "license validation"),
]


def run() -> Report:
    rep = Report()

    # --- runtime -------------------------------------------------------
    frozen = getattr(sys, "frozen", False)
    rep.checks.append(Check(
        "Runtime",
        detail=(f"Python {platform.python_version()} on "
                f"{platform.system()} {platform.release()}"
                f"{' (packaged build)' if frozen else ' (from source)'}")))

    # --- imports -------------------------------------------------------
    broken = []
    for module, purpose in _SUBSYSTEMS:
        try:
            importlib.import_module(module)
        except Exception as exc:
            broken.append((module, purpose, exc))

    if broken:
        for module, purpose, exc in broken:
            relative = "no known parent package" in str(exc)
            rep.checks.append(Check(
                f"Module: {purpose}", FAIL,
                detail=f"{module} failed to load: {type(exc).__name__}: {exc}",
                fix=("This is a packaging fault in this build. Reinstall from "
                     "the official release, and report it if it persists."
                     if relative else
                     "Reinstall Phantom Tweeks. If it persists, report this."),
                ours=True))
    else:
        rep.checks.append(Check(
            "Modules", detail=f"All {len(_SUBSYSTEMS)} subsystems loaded."))

    # --- GUI toolkit ---------------------------------------------------
    try:
        import tkinter                                    # noqa: F401
        rep.checks.append(Check("Interface toolkit",
                                detail="Tkinter available."))
    except Exception as exc:
        rep.checks.append(Check(
            "Interface toolkit", FAIL,
            detail=f"Tkinter is missing: {exc}",
            fix="Reinstall using the official installer, which bundles it.",
            ours=True))

    # --- writable data directory ---------------------------------------
    try:
        from phantom_tweeks.core import paths
        paths.ensure_dirs()
        probe = paths.ROOT / ".selftest"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        rep.checks.append(Check("Data folder", detail=str(paths.ROOT)))
    except Exception as exc:
        rep.checks.append(Check(
            "Data folder", FAIL, detail=str(exc),
            fix=("Check permissions on the folder above, or run the portable "
                 "build from a writable location."),
            ours=False))

    # --- optional dependency -------------------------------------------
    try:
        import psutil                                     # noqa: F401
        rep.checks.append(Check("Process monitoring",
                                detail="psutil available."))
    except ImportError:
        rep.checks.append(Check(
            "Process monitoring", WARN,
            detail="psutil is not installed.",
            fix="pip install psutil  (bundled in the packaged build)",
            ours=False))

    # --- external tooling ----------------------------------------------
    from phantom_tweeks.core import runproc
    if runproc.IS_WINDOWS:
        for tool, purpose in (("powercfg", "power plans"),
                              ("ping", "network measurements")):
            out = runproc.output([tool, "/?"], timeout=10)
            if out:
                rep.checks.append(Check(f"Windows tool: {tool}",
                                        detail=f"Available for {purpose}."))
            else:
                rep.checks.append(Check(
                    f"Windows tool: {tool}", WARN,
                    detail=f"Could not run {tool}; {purpose} will be limited.",
                    ours=False))
    else:
        rep.checks.append(Check(
            "Platform", WARN,
            detail=("Not running on Windows. Phantom Tweeks optimizes "
                    "Windows 10/11; most measurements are unavailable here."),
            ours=False))

    # --- admin rights ---------------------------------------------------
    try:
        from phantom_tweeks.core.platform_info import is_admin
        if is_admin():
            rep.checks.append(Check("Privileges", detail="Running as admin."))
        else:
            rep.checks.append(Check(
                "Privileges", WARN,
                detail="Not running as administrator.",
                fix=("Some optimizations need admin rights. Scanning and "
                     "reporting work fine without them."),
                ours=False))
    except Exception:
        pass

    # --- licensing integrity --------------------------------------------
    try:
        from phantom_tweeks.licensing import keys
        key = getattr(keys, "ISSUER_PUBLIC_KEY_B64", "")
        placeholder = (not key) or key.startswith("PLACEHOLDER")
        rep.checks.append(Check(
            "Licensing", WARN if placeholder else OK,
            detail=("No publisher key is embedded in this build, so Premium "
                    "keys cannot be validated." if placeholder else
                    "Publisher key present; keys verify offline."),
            ours=False))
    except Exception as exc:
        rep.checks.append(Check("Licensing", WARN, detail=str(exc)))

    return rep
