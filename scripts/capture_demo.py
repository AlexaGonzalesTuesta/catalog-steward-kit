"""Capture site/screenshot.png and site/demo.gif from the built site.

Runs in the Pages workflow after each scan, so the README images always show the current data.
Needs: pip install playwright pillow && python -m playwright install chromium
"""
from __future__ import annotations

import functools
import http.server
import io
import sys
import threading
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

SITE = Path(__file__).resolve().parent.parent / "site"


def serve() -> http.server.ThreadingHTTPServer:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main(chrome: str = "") -> None:
    httpd = serve()
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    frames = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome or None)
        page = browser.new_page(viewport={"width": 1280, "height": 860}, device_scale_factor=1)
        page.goto(url, wait_until="networkidle")
        page.wait_for_selector("article.item")
        page.screenshot(path=str(SITE / "screenshot.png"))

        def frame() -> None:
            frames.append(Image.open(io.BytesIO(page.screenshot())).convert("P", palette=Image.ADAPTIVE, colors=128))

        frame()
        pii = page.locator("article.item:has(.title:has-text('Possible')) >> text=Confirm PII")
        for _ in range(min(3, pii.count())):
            pii.first.click()
            page.wait_for_timeout(150)
            frame()
        owner = page.locator("article.item:has(.title:text-is('No data owner')) >> text=Set owner")
        if owner.count():
            owner.first.scroll_into_view_if_needed()
            owner.first.click()
            page.evaluate("window.scrollTo(0, 0)")
            frame()
        page.click("#nav a:has-text('Catalog health')")
        frame()
        page.click("#nav a:has-text('Quality checks')")
        frame()
        browser.close()
    httpd.shutdown()
    durations = [1600] + [900] * (len(frames) - 2) + [2200]
    frames[0].save(SITE / "demo.gif", save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True)
    print(f"Wrote {SITE / 'screenshot.png'} and {SITE / 'demo.gif'} ({len(frames)} frames)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
