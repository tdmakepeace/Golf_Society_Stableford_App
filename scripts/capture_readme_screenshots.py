"""
Capture PNGs for README (docs/screenshots/). Requires the Flask app running on
BASE_URL (default http://127.0.0.1:5000) and: pip install playwright && playwright install chromium

Usage (from repo root, server already running):
    .venv\\Scripts\\python scripts\\capture_readme_screenshots.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "screenshots"
BASE = os.environ.get("BASE_URL", "http://127.0.0.1:5000").rstrip("/")
COMP_ID = int(os.environ.get("COMPETITION_ID", "1"))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 800})

            page.goto(f"{BASE}/", wait_until="networkidle")
            page.screenshot(path=str(OUT / "01-home.png"), full_page=True)

            page.goto(f"{BASE}/admin/login", wait_until="networkidle")
            page.locator('input[name="email"]').fill("test@test.com")
            page.locator('input[name="password"]').fill("Edcvfr1!")
            page.screenshot(path=str(OUT / "02-admin-login.png"), full_page=True)
            page.locator('form button[type="submit"]').click()
            page.wait_for_url(f"{BASE}/admin/", timeout=15000)
            page.screenshot(path=str(OUT / "03-admin-dashboard.png"), full_page=True)

            page.goto(
                f"{BASE}/admin/competitions/{COMP_ID}/results",
                wait_until="networkidle",
            )
            page.screenshot(path=str(OUT / "04-results.png"), full_page=True)

            page.goto(f"{BASE}/login", wait_until="networkidle")
            page.locator("#player-email").fill("toby@test.com")
            page.locator("#player-password").fill("Edcvfr1!")
            page.screenshot(path=str(OUT / "05-player-login.png"), full_page=True)
        finally:
            browser.close()
    print("Wrote:", OUT / "01-home.png", "…", OUT / "05-player-login.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
