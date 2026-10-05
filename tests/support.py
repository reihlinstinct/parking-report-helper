"""Shared helpers for the functional tests: run the real CLI, serve a fake municipal site."""
from __future__ import annotations

import http.server
import os
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE = ROOT / "sample.json"

try:
    import playwright.sync_api  # noqa: F401
    HAVE_PLAYWRIGHT = True
except ImportError:
    HAVE_PLAYWRIGHT = False

REPORTER = {
    "first_name": "דנה", "last_name": "לוי", "id_type": "תעודת זהות",
    "id_number": "000000018", "phone": "0500000000", "email": "dana@example.com",
}


def run_cli(*args: str) -> subprocess.CompletedProcess:
    """Run `python -m parking_report` as a user would, in a separate process."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    src = str(ROOT / "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "parking_report", *args],
        capture_output=True, text=True, encoding="utf-8", timeout=30, env=env,
    )


class FakeSite:
    """Local stand-in for the municipality site. Records every request it receives.

    Routes: /form (mock 106 form), /blocked (403, like the live site from cloud IPs),
    /captcha (200 with a reCAPTCHA widget), /empty (200, no fields).
    """

    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []
        site = self
        form = (FIXTURES / "mock_106_form.html").read_bytes()

        class Handler(http.server.BaseHTTPRequestHandler):
            def _serve(self) -> None:
                site.requests.append((self.command, self.path))
                routes = {
                    "/form": (200, form),
                    "/blocked": (403, b"<h1>Access Denied</h1>"),
                    "/captcha": (200, b'<html><body><div class="g-recaptcha"></div></body></html>'),
                    "/empty": (200, b"<html><body><p>hello</p></body></html>"),
                }
                status, body = routes.get(self.path, (404, b"not found"))
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = do_POST = _serve

            def log_message(self, *args) -> None:  # keep test output quiet
                pass

        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "FakeSite":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()

    def url(self, route: str) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}{route}"
