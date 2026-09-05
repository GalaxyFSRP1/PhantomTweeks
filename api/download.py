"""Vercel function: GET /api/download?file=setup

Streams a release asset from a PRIVATE GitHub repo to the public.

Why this exists
---------------
GitHub Release assets on a private repo are NOT publicly downloadable. A plain
link to github.com/.../releases/download/... returns 404 for anyone who is not
signed in with access. This endpoint uses a server-side token (never exposed to
the browser) to fetch the asset and stream it back, so the website can offer a
normal download link without making the repository public.

Environment variables
---------------------
GITHUB_TOKEN   fine-grained PAT with **Contents: read** on this repo only.
GITHUB_REPO    "GalaxyFSRP1/PhantomTweeks" (owner/name).
RELEASE_TAG    optional; defaults to the latest release.

If GITHUB_TOKEN is absent the endpoint explains the situation instead of
failing obscurely.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

API = "https://api.github.com"
TIMEOUT = 25

# Friendly name -> asset filename
ALIASES = {
    "setup": "PhantomTweeks-Setup.exe",
    "installer": "PhantomTweeks-Setup.exe",
    "app": "PhantomTweeks.exe",
    "exe": "PhantomTweeks.exe",
    "portable": "PhantomTweeks-Portable.exe",
    "checksums": "SHA256SUMS.txt",
    "sha256": "SHA256SUMS.txt",
}

# Only these may ever be served. Prevents this endpoint being turned into a
# generic proxy for arbitrary repository contents.
ALLOWED = {
    "PhantomTweeks-Setup.exe",
    "PhantomTweeks.exe",
    "PhantomTweeks-Portable.exe",
    "SHA256SUMS.txt",
}


def _token() -> str:
    return (os.environ.get("GITHUB_TOKEN")
            or os.environ.get("GH_TOKEN") or "").strip()


def _repo() -> str:
    return os.environ.get("GITHUB_REPO", "GalaxyFSRP1/PhantomTweeks").strip()


def _gh(url: str, token: str, accept: str):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "PhantomTweeks-Website",
    })
    return urllib.request.urlopen(req, timeout=TIMEOUT)


def resolve_asset(filename: str, token: str, repo: str, tag: str = ""):
    """Return (asset_id, size, content_type) for a release asset."""
    url = (f"{API}/repos/{repo}/releases/tags/{urllib.parse.quote(tag)}"
           if tag else f"{API}/repos/{repo}/releases/latest")
    with _gh(url, token, "application/vnd.github+json") as r:
        release = json.loads(r.read().decode("utf-8"))
    for asset in release.get("assets", []):
        if asset.get("name") == filename:
            return asset["id"], asset.get("size", 0), release.get("tag_name", "")
    return None, 0, release.get("tag_name", "")


class handler(BaseHTTPRequestHandler):
    def _json(self, code: int, body: dict) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):                                    # noqa: N802
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        want = (params.get("file", ["setup"])[0] or "setup").strip()
        filename = ALIASES.get(want.lower(), want)

        if filename not in ALLOWED:
            self._json(400, {
                "error": "unknown_file",
                "message": f"'{want}' is not a downloadable file.",
                "available": sorted(ALIASES),
            })
            return

        token = _token()
        if not token:
            self._json(503, {
                "error": "not_configured",
                "message": ("Downloads are not configured yet. Set GITHUB_TOKEN "
                            "in the Vercel project settings (fine-grained PAT "
                            "with Contents: read)."),
            })
            return

        tag = os.environ.get("RELEASE_TAG", "").strip()
        try:
            asset_id, size, tag_name = resolve_asset(filename, token, _repo(), tag)
        except urllib.error.HTTPError as e:
            self._json(502, {
                "error": "github_error",
                "message": f"GitHub returned {e.code} while looking up the release.",
            })
            return
        except Exception:
            self._json(502, {"error": "github_unreachable",
                             "message": "Could not reach GitHub."})
            return

        if asset_id is None:
            self._json(404, {
                "error": "asset_missing",
                "message": (f"'{filename}' is not attached to release "
                            f"'{tag_name or 'latest'}'. Push a version tag to "
                            "build and publish it."),
            })
            return

        try:
            upstream = _gh(f"{API}/repos/{_repo()}/releases/assets/{asset_id}",
                           token, "application/octet-stream")
        except Exception:
            self._json(502, {"error": "download_failed",
                             "message": "Could not fetch the file from GitHub."})
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition",
                         f'attachment; filename="{filename}"')
        if size:
            self.send_header("Content-Length", str(size))
        # Releases are immutable once published; let the CDN cache them.
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()

        try:
            while True:
                chunk = upstream.read(64 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass                                  # user cancelled the download
        finally:
            upstream.close()
