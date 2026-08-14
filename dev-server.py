#!/usr/bin/env python3
"""Local preview server for the ZWISCHENWELTEN website.

GitHub Pages serves clean URLs (/aktuelles -> aktuelles.html) automatically.
Plain static servers and file:// cannot, so use this for local previews:

    python3 dev-server.py

Then open http://localhost:8000
"""
import http.server
import os

PORT = 8000
ROOT = os.path.dirname(os.path.abspath(__file__))


class CleanUrlHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def translate_path(self, path):
        resolved = super().translate_path(path)
        # GitHub Pages serves foo.html for /foo even when a foo/ directory
        # also exists (e.g. journalistennetzwerk.html + journalistennetzwerk/),
        # so the .html file must win over the directory here too.
        if not os.path.isfile(resolved) and os.path.isfile(resolved.rstrip("/") + ".html"):
            return resolved.rstrip("/") + ".html"
        return resolved


if __name__ == "__main__":
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), CleanUrlHandler)
    except OSError:
        raise SystemExit(
            f"Port {PORT} is already in use — most likely by a plain "
            f"`python3 -m http.server`, which cannot serve clean URLs like "
            f"/aktuelles/medienpreis-2026 and will return 404 for them.\n"
            f"Stop it first:  pkill -f http.server\n"
            f"Then run this script again."
        )
    print(f"Serving on http://localhost:{PORT} (Ctrl+C to stop)")
    server.serve_forever()
