#!/usr/bin/env python3
"""Lightweight static + full-track YouTube ID lookup server for AURA."""

import http.server
import json
import os
import re
import socketserver
import urllib.parse
import urllib.request

PORT = int(os.environ.get("PORT", 8765))
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


def search_youtube_ids(query, limit=6):
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept-Language": "vi,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=6) as resp:
        html = resp.read().decode("utf-8", "ignore")
    ids = []
    for vid in re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', html):
        if vid not in ids:
            ids.append(vid)
        if len(ids) >= limit:
            break
    return ids


class AuraHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT_DIR, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/yt":
            qs = urllib.parse.parse_qs(parsed.query)
            q = (qs.get("q") or [""])[0].strip()
            if not q:
                self._send_json(400, {"error": "Missing q parameter", "videoIds": []})
                return
            try:
                vids = search_youtube_ids(q, limit=6)
                self._send_json(200, {"query": q, "videoIds": vids})
            except Exception as exc:
                self._send_json(502, {"error": str(exc), "videoIds": []})
            return

        if parsed.path == "/":
            self.path = "/aura.html"
        super().do_GET()

    def _send_json(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


class ReusableTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with ReusableTCPServer(("", PORT), AuraHandler) as httpd:
        print(f"AURA server running at http://localhost:{PORT}/aura.html", flush=True)
        httpd.serve_forever()
