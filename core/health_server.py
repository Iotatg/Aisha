# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Simple self-ping health server for Render — /health and /debug endpoints.

/debug dumps diagnostics (handler count + diag ring buffers) so issues can
be diagnosed by fetching the public URL, without needing Render logs.
"""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("PORT", "8080"))

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/debug"):
            self._serve_debug()
            return
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK\n")

    def _serve_debug(self):
        try:
            import handlers.diag as diag
            import core.app as appmod
            import time
            client = getattr(appmod, "CLIENT", None)
            conn = None
            me = None
            if client is not None:
                conn = getattr(client, "is_connected", None)
                cme = getattr(client, "me", None)
                if cme is not None:
                    me = getattr(cme, "username", None)
            payload = {
                "handler_count": getattr(appmod, "HANDLER_COUNT", None),
                "client_connected": conn,
                "client_me": me,
                "raw_update_count": getattr(diag, "_raw_count", 0),
                "raw_updates": list(getattr(diag, "_raw_ring", []))[-25:],
                "seen_texts": list(getattr(diag, "_text_ring", []))[-25:],
                "uptime_s": int(time.time() - getattr(diag, "_boot", time.time())),
            }
            body = json.dumps(payload, indent=1).encode()
        except Exception as e:
            body = json.dumps({"error": str(e)}).encode()
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # suppress noisy logs

def start():
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
