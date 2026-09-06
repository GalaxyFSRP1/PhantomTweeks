# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Phantom Tweeks (installed build + portable build)."""
import os
from pathlib import Path

ROOT = Path(os.environ.get("PHANTOM_BUILD_ROOT", ".")).resolve()
PORTABLE = os.environ.get("PHANTOM_PORTABLE") == "1"

datas = [(str(ROOT / "assets"), "assets"), (str(ROOT / "docs"), "docs")]

# The portable build must actually BE portable at runtime, not just at build
# time. We bake a marker file into the bundle; core.paths looks for it and
# keeps all data next to the executable instead of in %LOCALAPPDATA%.
if PORTABLE:
    _marker = ROOT / "build" / "_work" / "portable.flag"
    _marker.parent.mkdir(parents=True, exist_ok=True)
    _marker.write_text(
        "This build stores its data next to the executable.\n", encoding="utf-8"
    )
    datas.append((str(_marker), "."))
hidden = ["psutil", "tkinter", "tkinter.ttk", "tkinter.filedialog"]

# The entry script lives outside the package, so PyInstaller cannot infer the
# submodules by following imports from it alone. Collect them explicitly.
# collect_submodules imports the package at spec-parse time, so src/ must be on
# sys.path *now* — pathex only affects the later analysis phase.
import sys as _sys
_src = str(ROOT / "src")
if _src not in _sys.path:
    _sys.path.insert(0, _src)
from PyInstaller.utils.hooks import collect_submodules
_collected = collect_submodules("phantom_tweeks")
if not _collected:
    raise SystemExit(
        "PhantomTweeks.spec: could not import 'phantom_tweeks' from "
        f"{_src}. Check PHANTOM_BUILD_ROOT is the repository root.")
hidden += _collected

a = Analysis(
    [str(ROOT / "build" / "phantom_launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    excludes=["numpy", "pandas", "matplotlib", "PIL", "scipy", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="PhantomTweeks-Portable" if PORTABLE else "PhantomTweeks",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False,                 # GUI by default; CLI still works via args
    disable_windowed_traceback=False,
    icon=str(ROOT / "assets" / "phantom.ico"),
    version=str(ROOT / "version_info.txt"),
    uac_admin=False,               # elevate on demand, never blanket-elevate
)
