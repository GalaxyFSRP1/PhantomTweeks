"""Vercel serverless function: GET /api/health — deployment sanity check."""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_GET(self):                            # noqa: N802
        configured = bool(os.environ.get("PHANTOM_PUBLIC_KEY", "").strip())
        body = json.dumps({
            "status": "ok",
            "service": "phantom-tweeks-licensing",
            "public_key_configured": configured,
            "note": ("Set PHANTOM_PUBLIC_KEY in Vercel project settings if this "
                     "is false, or license checks will fail."),
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
