"""Branded logging + crash handling. Logs stay local; nothing is uploaded."""
from __future__ import annotations

import logging
import sys
import traceback
from datetime import datetime
from logging.handlers import RotatingFileHandler

from ..branding import APP_NAME, VERSION
from . import paths

_configured = False


def get_logger(name: str = "phantom") -> logging.Logger:
    global _configured
    if not _configured:
        paths.ensure_dirs()
        root = logging.getLogger("phantom")
        root.setLevel(logging.DEBUG)
        fh = RotatingFileHandler(
            paths.LOGS / "phantomtweeks.log", maxBytes=2_000_000,
            backupCount=3, encoding="utf-8",
        )
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        root.addHandler(fh)
        sh = logging.StreamHandler(sys.stderr)
        sh.setLevel(logging.WARNING)
        sh.setFormatter(logging.Formatter(f"{APP_NAME}: %(levelname)s %(message)s"))
        root.addHandler(sh)
        _configured = True
    return logging.getLogger(f"phantom.{name}" if name != "phantom" else "phantom")


def write_crash_report(exc: BaseException) -> str:
    """Write a local crash log. Contains no personal files or credentials."""
    paths.ensure_dirs()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = paths.CRASH / f"crash-{stamp}.log"
    from .platform_info import summary
    lines = [
        f"{APP_NAME} {VERSION} crash report",
        f"Time: {datetime.now().isoformat(timespec='seconds')}",
        "System: " + ", ".join(f"{k}={v}" for k, v in summary().items()),
        "",
        "This report is stored locally only. Sharing it is optional.",
        "",
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    ]
    target.write_text("\n".join(lines), encoding="utf-8")
    return str(target)


def install_crash_handler() -> None:
    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        path = write_crash_report(exc)
        get_logger().critical("Unhandled exception; crash report at %s", path)
        print(f"\n{APP_NAME} hit an unexpected error.\n"
              f"A local crash log was saved to:\n  {path}\n"
              "Nothing was uploaded. You may share it voluntarily.", file=sys.stderr)
    sys.excepthook = hook
