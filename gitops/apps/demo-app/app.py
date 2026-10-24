"""Demo app: one page that shows the bucket the platform created for it.

Reads BUCKET_NAME and friends from the environment, which the Deployment
fills from the ConfigMap the apply worker commits to. No dependencies.
"""

from __future__ import annotations

import html
import os
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("PORT", "8080"))


def page() -> str:
    bucket = os.environ.get("BUCKET_NAME", "")
    arn = os.environ.get("BUCKET_ARN", "")
    request_id = os.environ.get("BUCKET_REQUEST_ID", "")
    greeting = os.environ.get("GREETING", "hello")
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
