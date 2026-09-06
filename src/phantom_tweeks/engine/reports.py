"""Export a full diagnostic report as HTML, JSON, CSV or Markdown.

What this is for
----------------
Two real situations: posting a help thread where people need to see your
actual hardware, and keeping a record before and after a change so you can
prove to yourself whether it did anything.

Privacy
-------
Reports are written to a file you choose. Nothing is uploaded. The username is
stripped from any path that contains it, because a screenshot of a report is
the most likely way someone leaks their own name into a forum post.
"""
from __future__ import annotations

import getpass
import html
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..branding import APP_NAME, VERSION

FORMATS = ("html", "json", "csv", "md", "txt")


def _scrub(text: str) -> str:
    """Remove the local username from anything we are about to write out."""
    if not text:
        return text
    try:
        user = getpass.getuser()
    except Exception:
        user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    if user and len(user) > 2:
        # Word boundaries matter: a plain replace turns "C:\\Users\\user"
        # into "C:\\<user>s\\<user>" when the account is literally named
        # "user", which corrupts the path and looks like a bug in the report.
        import re as _re
        text = _re.sub(rf"(?<![A-Za-z0-9]){_re.escape(user)}(?![A-Za-z0-9])",
                       "<user>", text, flags=_re.IGNORECASE)
    return text


@dataclass
class Report:
    title: str
    sections: list          # list[(heading, list[(key, value)])]
    generated: float

    def to_txt(self) -> str:
        out = [self.title, "=" * len(self.title),
               f"{APP_NAME} {VERSION}",
               time.strftime("%Y-%m-%d %H:%M", time.localtime(self.generated)),
               ""]
        for heading, rows in self.sections:
            out += [heading, "-" * len(heading)]
            for key, value in rows:
                out.append(f"  {key:<28} {value}")
            out.append("")
        out += ["", "Generated locally. Nothing was uploaded.",
                "Usernames are removed automatically."]
        return _scrub("\n".join(out))

    def to_md(self) -> str:
        out = [f"# {self.title}", "",
               f"**{APP_NAME} {VERSION}** - "
               f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(self.generated))}",
               ""]
        for heading, rows in self.sections:
            out += [f"## {heading}", "", "| Item | Value |", "| --- | --- |"]
            for key, value in rows:
                safe = str(value).replace("|", "\\|").replace("\n", " ")
                out.append(f"| {key} | {safe} |")
            out.append("")
        out += ["---", "", "_Generated locally. Nothing was uploaded._"]
        return _scrub("\n".join(out))

    def to_json(self) -> str:
        payload = {
            "app": APP_NAME,
            "version": VERSION,
            "generated": time.strftime("%Y-%m-%dT%H:%M:%S",
                                       time.localtime(self.generated)),
            "title": self.title,
            "sections": [
                {"heading": h, "items": {k: str(v) for k, v in rows}}
                for h, rows in self.sections
            ],
        }
        return _scrub(json.dumps(payload, indent=2))

    def to_csv(self) -> str:
        import csv
        import io
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["section", "item", "value"])
        for heading, rows in self.sections:
            for key, value in rows:
                w.writerow([heading, key, str(value).replace("\n", " ")])
        return _scrub(buf.getvalue())

    def to_html(self) -> str:
        """Self-contained HTML - no external CSS, so it renders anywhere."""
        rows_html = []
        for heading, rows in self.sections:
            body = "".join(
                f"<tr><td>{html.escape(str(k))}</td>"
                f"<td>{html.escape(str(v))}</td></tr>"
                for k, v in rows)
            rows_html.append(
                f"<h2>{html.escape(heading)}</h2><table>{body}</table>")
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(self.generated))
        doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{html.escape(self.title)}</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ background:#0a0d14; color:#e6ecf7; margin:0; padding:40px;
         font:15px/1.6 "Segoe UI",system-ui,sans-serif; }}
  .wrap {{ max-width:900px; margin:0 auto; }}
  h1 {{ color:#00e5c0; letter-spacing:-.02em; margin:0 0 6px; }}
  h2 {{ color:#00e5c0; font-size:15px; letter-spacing:.1em;
        text-transform:uppercase; margin:34px 0 10px; }}
  .meta {{ color:#8493ad; font-size:13.5px; margin-bottom:8px; }}
  table {{ width:100%; border-collapse:collapse;
           background:#111725; border:1px solid #222e47; border-radius:10px;
           overflow:hidden; }}
  td {{ padding:10px 14px; border-bottom:1px solid #222e47;
        vertical-align:top; }}
  td:first-child {{ color:#8493ad; width:34%; }}
  tr:last-child td {{ border-bottom:0; }}
  footer {{ margin-top:36px; color:#8493ad; font-size:13px;
            border-top:1px solid #222e47; padding-top:18px; }}
</style></head><body><div class="wrap">
<h1>{html.escape(self.title)}</h1>
<div class="meta">{html.escape(APP_NAME)} {html.escape(VERSION)} &middot; {when}</div>
{''.join(rows_html)}
<footer>Generated locally by {html.escape(APP_NAME)}. Nothing was uploaded.
Usernames are removed automatically before writing.</footer>
</div></body></html>"""
        return _scrub(doc)

    def render(self, fmt: str) -> str:
        fmt = (fmt or "txt").lower().lstrip(".")
        if fmt not in FORMATS:
            raise ValueError(f"Unsupported format: {fmt}. Use one of "
                             + ", ".join(FORMATS))
        return getattr(self, f"to_{fmt}")()


# ------------------------------------------------------------- gathering

def _rows_from_perf() -> list:
    from . import perfview
    out = []
    for section in perfview.build().sections:
        rows = []
        for r in section.readings:
            value = r.detail or ""
            if r.value is not None:
                value = f"{r.value}{r.unit}" + (f" - {r.detail}" if r.detail else "")
            rows.append((r.label, value or "not measured"))
        if section.note:
            rows.append(("Note", section.note))
        out.append((section.title, rows))
    return out


def build(include_tweaks: bool = True, include_history: bool = True) -> Report:
    """Assemble everything worth putting in a bug report."""
    sections = list(_rows_from_perf())

    try:
        from ..core import platform_info
        sections.insert(0, ("SYSTEM", [
            ("Operating system", platform_info.windows_release()),
            ("Administrator", "yes" if platform_info.is_admin() else "no"),
            ("Phantom Tweeks", VERSION),
        ]))
    except Exception:
        pass

    if include_tweaks:
        try:
            from . import catalog
            rows = []
            for opt in catalog.CATALOG:
                rows.append((opt.title,
                             f"{opt.area} - {opt.risk.value} risk - "
                             + ("reversible" if opt.reversible
                                else "NOT reversible")))
            sections.append(("AVAILABLE OPTIMIZATIONS", rows))
        except Exception:
            pass

    if include_history:
        try:
            from .backup import BackupVault
            entries = BackupVault().list_all()
            rows = [(e.id, f"{e.title} - {e.change_count} change(s)")
                    for e in entries[:20]]
            sections.append(("BACKUP HISTORY",
                             rows or [("None", "No changes applied yet")]))
        except Exception:
            pass

    return Report(title="Phantom Tweeks Diagnostic Report",
                  sections=sections, generated=time.time())


def save(path: str | Path, fmt: Optional[str] = None,
         report: Optional[Report] = None) -> tuple[bool, str]:
    """Write a report. The format follows the file extension unless given."""
    target = Path(path)
    fmt = (fmt or target.suffix or "txt").lstrip(".").lower()
    if fmt not in FORMATS:
        return False, (f"Unsupported format '{fmt}'. Use one of: "
                       + ", ".join(FORMATS))
    try:
        data = (report or build()).render(fmt)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(data, encoding="utf-8")
    except OSError as exc:
        return False, f"Could not write {target}: {exc}"
    return True, (f"Report saved to {target}\n\n"
                  "It contains no usernames and was not uploaded anywhere.")
