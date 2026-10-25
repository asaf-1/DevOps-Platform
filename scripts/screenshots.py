"""Screenshots for the README: the two Grafana dashboards, through a real login.

Runs inside the devcontainer (Playwright + Chromium in agents/.venv):

    kubectl -n observability port-forward svc/kps-grafana 3000:80 &
    GRAFANA_URL=http://localhost:3000 GRAFANA_USER=... GRAFANA_PASSWORD=... \
        agents/.venv/bin/python scripts/screenshots.py docs/images

No Grafana setting is changed: the script logs in with the admin account the
cluster generated (scripts/up.sh), like a person would.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

DASHBOARDS = {
    "dashboard-platform-dx.png": "/d/platform-dx/platform-dx?orgId=1&kiosk&from=now-7d&to=now",
    "dashboard-agents.png": "/d/platform-agents/agents?orgId=1&kiosk&from=now-7d&to=now",
}


def main(out_dir: Path) -> int:
    base = os.environ.get("GRAFANA_URL", "http://localhost:3000").rstrip("/")
    user = os.environ["GRAFANA_USER"]
    password = os.environ["GRAFANA_PASSWORD"]
    out_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.goto(f"{base}/login", wait_until="networkidle")
        page.fill('input[name="user"]', user)
        page.fill('input[name="password"]', password)
        page.click('button[type="submit"]')
        page.wait_for_url(lambda url: "/login" not in url, timeout=30000)
        for name, path in DASHBOARDS.items():
            page.goto(f"{base}{path}", wait_until="networkidle")
            page.wait_for_timeout(4000)  # panels query Prometheus after load
            page.screenshot(path=str(out_dir / name))
            print("wrote", out_dir / name)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "docs/images")))
