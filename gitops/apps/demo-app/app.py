"""Demo app: one page that shows the bucket the platform created for it.

Reads BUCKET_NAME and friends from the ConfigMap the apply worker commits
to. The ConfigMap is mounted as files under CONFIG_DIR, which Kubernetes
refreshes while the pod runs (environment variables would not), so the
page changes within a minute of the commit. Falls back to the environment.
No dependencies.
"""

from __future__ import annotations

import html
import os
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PORT = int(os.environ.get("PORT", "8080"))
CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", "/config"))


def setting(key: str, default: str = "") -> str:
    """A ConfigMap key: the mounted file first (live), then the environment."""
    path = CONFIG_DIR / key
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    return os.environ.get(key, default)


def page() -> str:
    bucket = setting("BUCKET_NAME")
    arn = setting("BUCKET_ARN")
    request_id = setting("BUCKET_REQUEST_ID")
    greeting = setting("GREETING", "hello")
    status = (
        f"<p class='ok'>Bucket <code>{html.escape(bucket)}</code> is mine.</p>"
        f"<p>ARN <code>{html.escape(arn)}</code>, request <code>{html.escape(request_id)}</code>.</p>"
        if bucket
        else "<p class='wait'>No bucket yet. Run <code>make request</code> and approve the PR.</p>"
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>demo-app</title>
<style>
 body {{ font: 16px system-ui, sans-serif; margin: 3rem auto; max-width: 40rem; color: #222; }}
 code {{ background: #eee; padding: .1rem .3rem; border-radius: 3px; }}
 .ok {{ color: #1a7f37; }} .wait {{ color: #9a6700; }} small {{ color: #666; }}
</style></head>
<body>
<h1>demo-app says {html.escape(greeting)}</h1>
{status}
<small>pod {html.escape(socket.gethostname())}</small>
</body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        if self.path == "/healthz":
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
        else:
            body = page().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} {fmt % args}", flush=True)


if __name__ == "__main__":
    print(f"demo-app listening on :{PORT}", flush=True)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
