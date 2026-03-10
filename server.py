#!/usr/bin/env python3
"""
Scraperrr — server.py
======================
Local dev server. Serves the dashboard + a /run-scraper endpoint
that the dashboard Refresh button can call to get fresh data.

Run: python server.py
Open: http://127.0.0.1:3000/dashboard/
"""

import json
import subprocess
import sys
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).parent
PORT = 3000
PYTHON = sys.executable


class ScraperrHandler(SimpleHTTPRequestHandler):
    # Serve files from the project root
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        # ── API: trigger a fresh scrape ──────────────────────────
        if self.path == "/run-scraper":
            self.run_scraper()
            return

        # ── API: health check ────────────────────────────────────
        if self.path == "/health":
            self.send_json({"status": "ok"})
            return

        # ── Static file serving ──────────────────────────────────
        super().do_GET()

    def run_scraper(self):
        """Execute tools/scraper.py and return the resulting articles.json."""
        scraper = ROOT / "tools" / "scraper.py"
        try:
            result = subprocess.run(
                [PYTHON, str(scraper)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                err = result.stderr[-500:] if result.stderr else "Unknown error"
                self.send_json({"ok": False, "error": err}, status=500)
                return

            # Return the freshly written articles.json
            output_path = ROOT / ".tmp" / "articles.json"
            if output_path.exists():
                with open(output_path, encoding="utf-8") as f:
                    data = json.load(f)
                self.send_json({"ok": True, **data})
            else:
                self.send_json({"ok": False, "error": "articles.json not found after scrape"}, status=500)

        except subprocess.TimeoutExpired:
            self.send_json({"ok": False, "error": "Scraper timed out (60s)"}, status=500)
        except Exception as e:
            self.send_json({"ok": False, "error": str(e)}, status=500)

    def send_json(self, payload: dict, status: int = 200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Cleaner log output
        print(f"  {self.address_string()} {fmt % args}")


if __name__ == "__main__":
    os.chdir(ROOT)
    server = HTTPServer(("127.0.0.1", PORT), ScraperrHandler)
    print(f"\n  🚀 Scraperrr server running")
    print(f"  📺 Dashboard → http://127.0.0.1:{PORT}/dashboard/")
    print(f"  🔄 Scraper   → http://127.0.0.1:{PORT}/run-scraper")
    print(f"  Press Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
