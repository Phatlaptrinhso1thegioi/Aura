#!/usr/bin/env python3
"""Lightweight static + full-track YouTube ID lookup + Authentication & Sync Server for AURA."""

import http.server
import json
import os
import re
import socketserver
import urllib.parse
import urllib.request

import auth_db

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


def search_itunes(query, limit=25):
    url = "https://itunes.apple.com/search?term=" + urllib.parse.quote(query) + "&country=VN&media=music&entity=song&limit=" + str(limit)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept-Language": "vi,en;q=0.9",
        },
    )
    results = []
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
        results = data.get("results", [])
    except Exception:
        results = []

    if not results:
        url_us = "https://itunes.apple.com/search?term=" + urllib.parse.quote(query) + "&country=US&media=music&entity=song&limit=" + str(limit)
        req_us = urllib.request.Request(url_us, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req_us, timeout=6) as resp_us:
                data_us = json.loads(resp_us.read().decode("utf-8", "ignore"))
            results = data_us.get("results", [])
        except Exception:
            results = []
    return results


class AuraHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT_DIR, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def _get_auth_token(self):
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:].strip()
        return None

    def _read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw)
        except Exception:
            return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/auth/me":
            token = self._get_auth_token()
            if not token:
                self._send_json(401, {"error": "Chưa đăng nhập."})
                return
            user, data = auth_db.get_user_by_token(token)
            if not user:
                self._send_json(401, {"error": "Phiên đăng nhập đã hết hạn."})
                return
            self._send_json(200, {"user": user, "data": data})
            return

        if parsed.path == "/api/search":
            qs = urllib.parse.parse_qs(parsed.query)
            q = (qs.get("q") or [""])[0].strip()
            if not q:
                self._send_json(400, {"error": "Missing q parameter", "results": []})
                return
            try:
                items = search_itunes(q, limit=25)
                self._send_json(200, {"query": q, "results": items})
            except Exception as exc:
                self._send_json(500, {"error": str(exc), "results": []})
            return

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

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/auth/register":
            payload = self._read_json_body()
            email = payload.get("email", "")
            password = payload.get("password", "")
            full_name = payload.get("full_name", "")
            try:
                user, token, data = auth_db.register_user(email, password, full_name)
                self._send_json(201, {"user": user, "token": token, "data": data, "message": "Đăng ký thành công!"})
            except ValueError as val_err:
                self._send_json(400, {"error": str(val_err)})
            except Exception as exc:
                self._send_json(500, {"error": "Lỗi máy chủ khi đăng ký: " + str(exc)})
            return

        if parsed.path == "/api/auth/login":
            payload = self._read_json_body()
            email = payload.get("email", "")
            password = payload.get("password", "")
            try:
                user, token, data = auth_db.login_user(email, password)
                self._send_json(200, {"user": user, "token": token, "data": data, "message": "Đăng nhập thành công!"})
            except ValueError as val_err:
                self._send_json(400, {"error": str(val_err)})
            except Exception as exc:
                self._send_json(500, {"error": "Lỗi máy chủ khi đăng nhập: " + str(exc)})
            return

        if parsed.path == "/api/auth/logout":
            token = self._get_auth_token()
            if token:
                auth_db.logout_user(token)
            self._send_json(200, {"message": "Đã đăng xuất thành công."})
            return

        if parsed.path == "/api/user/sync":
            token = self._get_auth_token()
            if not token:
                self._send_json(401, {"error": "Chưa đăng nhập."})
                return
            user, _ = auth_db.get_user_by_token(token)
            if not user:
                self._send_json(401, {"error": "Phiên đăng nhập không hợp lệ hoặc đã hết hạn."})
                return

            payload = self._read_json_body()
            try:
                auth_db.save_user_data(user["id"], payload)
                self._send_json(200, {"success": True, "message": "Đã đồng bộ dữ liệu vào tài khoản cá nhân!"})
            except Exception as exc:
                self._send_json(500, {"error": "Lỗi lưu dữ liệu: " + str(exc)})
            return

        self._send_json(404, {"error": "Endpoint không tồn tại."})

    def _send_json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


class ReusableTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    auth_db.init_db()
    with ReusableTCPServer(("", PORT), AuraHandler) as httpd:
        print(f"AURA server with Auth & Database running at http://localhost:{PORT}/aura.html", flush=True)
        httpd.serve_forever()
