"""Serve the repo folder on localhost so the browser view can load the WebAssembly engine."""
from __future__ import annotations

import http.server
import mimetypes
import threading
import webbrowser
from functools import partial

from .export import export
from .graph import ROOT

mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("text/plain", ".cypher")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def serve(port: int = 8765, open_browser: bool = True):
    export()  # always show what is in the store right now
    handler = partial(Quiet, directory=str(ROOT))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/web/"
    print(f"Trailmark view: {url}   (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.6, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
