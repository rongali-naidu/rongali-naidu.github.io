"""Local preview server for dist/ (handles Windows paths over 260 chars).

Usage: python serve.py [port]
"""
import functools
import http.server
import os
import sys
from pathlib import Path

DIST = str(Path(__file__).resolve().parent / "dist")
if os.name == "nt":
    DIST = "\\\\?\\" + DIST


class Handler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        p = super().translate_path(path)
        return p.replace("/", "\\") if os.name == "nt" else p

    def send_error(self, code, message=None, explain=None):
        page = os.path.join(DIST, "404.html")
        if code == 404 and os.path.exists(page):
            body = open(page, "rb").read()
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().send_error(code, message, explain)


port = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
http.server.ThreadingHTTPServer(("127.0.0.1", port),
                                functools.partial(Handler, directory=DIST)).serve_forever()
