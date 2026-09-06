"""Vercel function: GET /api/latest

Reports the newest published release so the website can show the real version,
file sizes and SHA-256 checksums instead of hard-coded values that go stale.

Works with a private repo via GITHUB_TOKEN (never exposed to the browser).
Returns only public-safe metadata: version, date, file names, sizes, checksums.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

API = "https://api.github.com"
TIMEOUT = 20
PUBLIC_FILES = {"PhantomTweeks-Setup.exe", "PhantomTweeks.exe",
                "PhantomTweeks-Portable.exe", "SHA256SUMS.txt"}


def _gh(url: str, token: str, accept: str):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "PhantomTweeks-Website",
    })
    return urllib.request.urlopen(req, timeout=TIMEOUT)


def _parse_sums(text: str) -> dict:
    """Parse 'hash  filename' lines into {filename: hash}."""
    out = {}
    for line in text.splitlines():
        m = re.match(r"^([0-9a-fA-F]{64})\s+\*?(\S+)\s*$", line.strip())
        if m:
            out[m.group(2)] = m.group(1).lower()
    return out


def latest_release(token: str, repo: str, gh=None) -> dict:
    """Return the newest release, INCLUDING pre-releases.

    GitHub's /releases/latest endpoint deliberately skips pre-releases and
    drafts. Every 0.x build is published as a pre-release, so that endpoint
    404s and the website reports "no release published yet" even though one
    exists. Listing releases and taking the newest non-draft is the only way
    to see them.
    """
    gh = gh or _gh
    try:
        with gh(f"{API}/repos/{repo}/releases?per_page=20", token,
                "application/vnd.github+json") as r:
            releases = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError:
        raise
    if not isinstance(releases, list):
        raise urllib.error.HTTPError(repo, 404, "Not Found", {}, None)
    live = [x for x in releases if isinstance(x, dict) and not x.get("draft")]
    if not live:
        raise urllib.error.HTTPError(repo, 404, "Not Found", {}, None)
    # The API already returns newest-first by creation date.
    return live[0]


def build_payload(token: str, repo: str) -> tuple[int, dict]:
    if not token:
        return 503, {"available": False,
                     "message": "Downloads are not configured yet."}
    try:
        rel = latest_release(token, repo)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # Not an error: the site is live before the first release exists.
            # Returning 404 made the browser console show a scary red error
            # for an entirely normal state, so answer 200 with available=false.
            return 200, {"available": False,
                         "reason": "no_release",
                         "message": ("No release has been published yet. "
                                     "Push a version tag to build and "
                                     "publish one.")}
        return 502, {"available": False,
                     "message": f"GitHub returned {e.code}."}
    except Exception:
        return 502, {"available": False, "message": "Could not reach GitHub."}

    assets = {a["name"]: a for a in rel.get("assets", [])
              if a.get("name") in PUBLIC_FILES}

    checksums = {}
    if "SHA256SUMS.txt" in assets:
        try:
            with _gh(f"{API}/repos/{repo}/releases/assets/"
                     f"{assets['SHA256SUMS.txt']['id']}", token,
                     "application/octet-stream") as r:
                checksums = _parse_sums(r.read().decode("utf-8", "replace"))
        except Exception:
            checksums = {}

    files = []
    for name, a in sorted(assets.items()):
        if name == "SHA256SUMS.txt":
            continue
        files.append({
            "name": name,
            "size": a.get("size", 0),
            "size_mb": round(a.get("size", 0) / 1048576, 1),
            "sha256": checksums.get(name, ""),
            "url": "/api/download?file=" + urllib.parse.quote(name),
        })

    tag = rel.get("tag_name", "")
    return 200, {
        "available": bool(files),
        "version": tag.lstrip("v"),
        "tag": tag,
        "published": (rel.get("published_at") or "")[:10],
        "prerelease": bool(rel.get("prerelease")),
        "files": files,
        "checksums_url": "/api/download?file=checksums",
        "signed": False,
        "note": ("These binaries are not code-signed yet, so SmartScreen will "
                 "warn on first run. Verify the SHA-256 before allowing it."),
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):                                    # noqa: N802
        token = (os.environ.get("GITHUB_TOKEN")
                 or os.environ.get("GH_TOKEN") or "").strip()
        repo = os.environ.get("GITHUB_REPO", "GalaxyFSRP1/PhantomTweeks").strip()
        code, payload = build_payload(token, repo)
        raw = json.dumps(payload, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "public, max-age=300")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)
