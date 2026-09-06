# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Update.exe - the standalone updater.

A separate binary because Windows locks a running .exe: the updater cannot
replace the application while the application is running it.

console=True here, unlike the main app. This is a small tool that reports
what it found and asks before downloading; hiding its output would leave the
user staring at nothing.
"""
import os
import sys as _sys
from pathlib import Path

ROOT = Path(os.environ.get("PHANTOM_BUILD_ROOT", ".")).resolve()

_src = str(ROOT / "src")
if _src not in _sys.path:
    _sys.path.insert(0, _src)
from PyInstaller.utils.hooks import collect_submodules

hidden = collect_submodules("phantom_tweeks")
if not hidden:
    raise SystemExit(
        "Updater.spec: could not import 'phantom_tweeks' from "
        f"{_src}. Check PHANTOM_BUILD_ROOT is the repository root.")

a = Analysis(
    [str(ROOT / "packaging" / "updater_launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[],
    hiddenimports=hidden,
    hookspath=[],
    excludes=["numpy", "pandas", "matplotlib", "PIL", "scipy", "pytest",
              "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="Update",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=True,
    disable_windowed_traceback=False,
    icon=str(ROOT / "assets" / "phantom.ico"),
    version=str(ROOT / "version_info.txt"),
    uac_admin=False,
)
