import json
import re
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler


def search_youtube_ids(query, limit=6):
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
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


class handler(BaseHTTPRequestHandler):
    """Vercel Python Serverless Function entrypoint."""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        q = (qs.get("q") or [""])[0].strip()

        if "/api/search" in parsed.path:
            if not q:
                self._send_json(400, {"error": "Missing q parameter", "results": []})
                return
            try:
                items = search_itunes(q, limit=25)
                self._send_json(200, {"query": q, "results": items})
            except Exception as exc:
                self._send_json(500, {"error": str(exc), "results": []})
            return

        if not q:
            self._send_json(400, {"error": "Missing q parameter", "videoIds": []})
            return
        try:
            vids = search_youtube_ids(q, limit=6)
            self._send_json(200, {"query": q, "videoIds": vids})
        except Exception as exc:
            self._send_json(502, {"error": str(exc), "videoIds": []})

    def _send_json(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        # Cache results at Vercel Edge for 24h to avoid hitting YouTube rate limits
        self.send_header("Cache-Control", "s-maxage=86400, stale-while-revalidate=86400")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass
