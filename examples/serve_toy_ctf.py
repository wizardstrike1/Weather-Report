"""Serve the bundled toy CTF on http://127.0.0.1:8000 for EXAMPLES.md.

    python examples/serve_toy_ctf.py

Routes:
  /                     -> toy_ctf.html
  /files/challenge.txt  -> a file containing a planted flag (for download test)
"""
from __future__ import annotations

import http.server
import socketserver
from pathlib import Path

HERE = Path(__file__).parent
PORT = 8000

CHALLENGE_FILE = b"binary-ish content\x00\x01 ... flag{toy_downloaded_file_flag} ... end\n"


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, body: bytes, ctype: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if "octet-stream" in ctype:
            self.send_header("Content-Disposition",
                             'attachment; filename="challenge.txt"')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            self._send((HERE / "toy_ctf.html").read_bytes(), "text/html")
        elif self.path == "/files/challenge.txt":
            self._send(CHALLENGE_FILE, "application/octet-stream")
        elif self.path == "/robots.txt":
            self._send(b"User-agent: *\nDisallow: /secret/\n", "text/plain")
        else:
            self.send_error(404)

    def log_message(self, *a):  # quiet
        pass


if __name__ == "__main__":
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        print(f"Toy CTF on http://127.0.0.1:{PORT}  (Ctrl+C to stop)")
        httpd.serve_forever()
