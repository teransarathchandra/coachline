"""Renders docs/demo/social.html to docs/assets/social.png (1280x640), the social preview. Needs Playwright with Chromium:
  python docs/demo/social.py
"""
import os
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
with sync_playwright() as p:
    b = p.chromium.launch(); page = b.new_page(viewport={"width": 1280, "height": 640})
    page.goto("file:///" + os.path.join(HERE, "social.html").replace("\\", "/")); page.wait_for_timeout(1200)   # the web fonts
    page.screenshot(path=os.path.join(HERE, "..", "assets", "social.png")); b.close()
print("docs/assets/social.png")
