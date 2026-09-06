"""Entry point for Update.exe - the standalone updater.

Why a separate executable
-------------------------
An updater that lives inside the application cannot replace the application
while it is running: Windows holds a lock on a running .exe. Shipping the
update check as its own small binary means it can be launched from the Start
menu, from a scheduled task, or by the main app just before it exits.

It uses exactly the same verified update path as the in-app checker - HTTPS
only, SHA-256 verified against the value published with the release, and the
installer is staged rather than executed. Nothing here runs a downloaded file
on your behalf.

Absolute imports only: PyInstaller runs an entry script as a top-level module
with no parent package, so a relative import would raise ImportError in the
frozen build.
"""
from __future__ import annotations

import os
import sys


def _bootstrap() -> None:
    if getattr(sys, "frozen", False):
        return
    here = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(os.path.dirname(here), "src")
    if os.path.isdir(src) and src not in sys.path:
        sys.path.insert(0, src)


def main() -> int:
    _bootstrap()
    try:
        from phantom_tweeks.branding import VERSION
        from phantom_tweeks.core import updates
    except ImportError as exc:
        sys.stderr.write(
            "Phantom Tweeks Update could not start because part of the "
            f"application is missing:\n  {exc}\n\n"
            "This is a packaging problem with this build, not a problem with "
            "your PC.\n")
        return 3

    print("Phantom Tweeks Updater")
    print(f"  Installed version: {VERSION}")
    print("  Checking for updates...")
    print()

    info = updates.check()
    if info is None:
        print("You are on the latest version.")
        print()
        print("(If no release has been published yet, there is nothing to")
        print(" download. This is not an error.)")
        _pause()
        return 0

    print(info.render())
    print()
    answer = input("Download this update now? [y/N] ").strip().lower()
    if answer not in ("y", "yes"):
        print("No changes made.")
        _pause()
        return 0

    last = [0]

    def progress(done: int, total: int) -> None:
        if total and done - last[0] > total / 20:
            last[0] = done
            pct = done * 100 // total
            print(f"  {pct}%", end="\r", flush=True)

    ok, message, path = updates.download_and_verify(info, progress=progress)
    print()
    print(message)
    if ok and path:
        print()
        print("Close Phantom Tweeks, then run the file above to install it.")
        print("Phantom Tweeks does not run installers for you.")
    _pause()
    return 0 if ok else 1


def _pause() -> None:
    """Keep the console open when double-clicked from Explorer."""
    if sys.stdout.isatty():
        try:
            input("\nPress Enter to close...")
        except (EOFError, KeyboardInterrupt):
            pass


if __name__ == "__main__":
    sys.exit(main())
