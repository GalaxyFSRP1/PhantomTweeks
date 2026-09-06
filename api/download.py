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
import re
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler
from typing import Optional

API = "https://api.github.com"
TIMEOUT = 25

# Friendly name -> asset filename
ALIASES = {
    "setup": "PhantomTweeks-Setup.exe",
    "setup-exe": "PhantomTweeks-Setup.exe",
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

# The MSI carries the version in its filename (PhantomTweeks-0.1.4.msi), so it
# can never match a static allowlist. An earlier version of this file simply
# rejected every .msi request, which is why the download link 404'd.
#
# Rather than hard-coding a version - which would break on the next release -
# match the shape and let the release itself decide the exact name. The
# pattern is deliberately tight: digits and dots only, no path separators.
MSI_PATTERN = re.compile(r"^PhantomTweeks-\d+(?:\.\d+){1,3}\.msi$")


def is_allowed(filename: str) -> bool:
    """True if this exact filename may be served."""
    if "/" in filename or "\\" in filename or ".." in filename:
        return False
    return filename in ALLOWED or bool(MSI_PATTERN.match(filename))


def resolve_name(want: str, release: Optional[dict] = None) -> Optional[str]:
    """Turn a friendly alias into the real asset name for THIS release.

    "msi" has no fixed filename, so when a release is supplied we look through
    its assets for the one that matches. That keeps the endpoint correct for
    every future version without another code change.
    """
    key = (want or "").strip()
    mapped = ALIASES.get(key.lower())
    if mapped:
        return mapped

    if key.lower() in ("msi", "installer-msi", "package"):
        if release:
            for asset in release.get("assets", []):
                name = asset.get("name", "")
                if MSI_PATTERN.match(name):
                    return name
            return None
        return "msi"          # resolved later, once the release is known

    return key if is_allowed(key) else None


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


def resolve_asset(filename: str, token: str, repo: str, tag: str = ""):
    """Return (asset_id, size, content_type) for a release asset."""
    if tag:
        url = f"{API}/repos/{repo}/releases/tags/{urllib.parse.quote(tag)}"
        with _gh(url, token, "application/vnd.github+json") as r:
            release = json.loads(r.read().decode("utf-8"))
    else:
        # Includes pre-releases; /releases/latest would skip every 0.x build.
        release = latest_release(token, repo)
    # "msi" is deferred until here, because only the release knows the exact
    # versioned filename (PhantomTweeks-0.1.4.msi and so on).
    if filename == "msi":
        resolved = resolve_name("msi", release)
        if not resolved:
            return None, 0, release.get("tag_name", "")
        filename = resolved

    if not is_allowed(filename):
        return None, 0, release.get("tag_name", "")

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
        # A function that raises is killed by the platform and the visitor
        # sees an opaque "502 Bad Gateway". Catch everything and explain.
        try:
            self._handle()
        except Exception as exc:                        # pragma: no cover
            try:
                self._json(500, {
                    "error": "unexpected",
                    "message": ("The download service hit an unexpected error. "
                                "This is a bug on our side, not your PC."),
                    "detail": type(exc).__name__,
                })
            except Exception:
                pass

    def _handle(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        want = (params.get("file", ["setup"])[0] or "setup").strip()
        filename = resolve_name(want)

        if filename is None:
            self._json(400, {
                "error": "unknown_file",
                "message": f"'{want}' is not a downloadable file.",
                "available": sorted(set(ALIASES) | {"msi"}),
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
            if filename == "msi" and asset_id is not None:
                # Report the real filename in the download headers.
                filename = f"PhantomTweeks-{(tag_name or '').lstrip('v')}.msi"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                # The overwhelmingly common cause: no release published yet.
                # This used to surface as a bare 502 Bad Gateway, which tells
                # the visitor nothing and looks like the site is broken.
                self._json(404, {
                    "error": "no_release",
                    "message": ("No release has been published yet, so there "
                                "is nothing to download. Push a version tag "
                                "to build and publish one."),
                })
            elif e.code in (401, 403):
                self._json(503, {
                    "error": "token_invalid",
                    "message": ("The server's GitHub token is missing, expired "
                                "or lacks Contents: read on this repository."),
                })
            else:
                self._json(502, {
                    "error": "github_error",
                    "message": f"GitHub returned {e.code} while looking up "
                               "the release.",
                })
            return
        except Exception as exc:
            self._json(502, {"error": "github_unreachable",
                             "message": "Could not reach GitHub.",
                             "detail": type(exc).__name__})
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
