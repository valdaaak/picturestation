# SPDX-License-Identifier: GPL-3.0-or-later
"""Kontrola webovej galerie v Edge: python web_check.py http://localhost user heslo_subor vystup_dir"""
import os
import sys

from playwright.sync_api import sync_playwright

base, user, pwfile, outdir = sys.argv[1:5]
pw = [l.split(":", 1)[1].strip() for l in open(pwfile, encoding="utf-8") if l.startswith("heslo:")][0]
os.makedirs(outdir, exist_ok=True)
errors = []

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    for name, vp in (("desktop", {"width": 1400, "height": 900}), ("mobil", {"width": 390, "height": 844})):
        ctx = b.new_context(viewport=vp, device_scale_factor=1)
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(f"{name} JS: {e}"))
        pg.on("console", lambda m: errors.append(f"{name} console {m.type}: {m.text}") if m.type == "error" else None)
        pg.goto(base + "/")
        pg.wait_for_timeout(800)
        pg.screenshot(path=f"{outdir}/{name}-0-host.png")
        pg.click("#loginBtn")
        pg.fill("#loginDlg input[name=username]", user)
        pg.fill("#loginDlg input[name=password]", pw)
        pg.click("#loginDlg button[type=submit]")
        pg.wait_for_selector(".album img", timeout=30000)
        pg.wait_for_timeout(2500)
        pg.screenshot(path=f"{outdir}/{name}-1-albumy.png")
        print(name, "albumov:", pg.locator(".album").count(), "| user:", pg.inner_text("#userName"))
        # album s fotkami
        pg.locator(".album").nth(0).click()
        pg.wait_for_selector(".tile img", timeout=30000)
        pg.wait_for_timeout(2500)
        pg.screenshot(path=f"{outdir}/{name}-2-album.png")
        print(name, "album:", pg.inner_text("#crumbs").replace("\n", " "), "| dlazdic:", pg.locator(".tile").count(),
              "| pocet:", pg.inner_text("#count"))
        pg.locator(".tile").nth(0).click()
        pg.wait_for_function("document.getElementById('vImg').complete && document.getElementById('vImg').naturalWidth > 0", timeout=30000)
        if name == "desktop":
            pg.keyboard.press("i")
        pg.wait_for_timeout(800)
        pg.screenshot(path=f"{outdir}/{name}-3-fotka.png")
        print(name, "prehliadac:", pg.inner_text("#vTitle"), "| img:", pg.evaluate("document.getElementById('vImg').naturalWidth"),
              "x", pg.evaluate("document.getElementById('vImg').naturalHeight"))
        pg.keyboard.press("ArrowRight")
        pg.wait_for_timeout(600)
        print(name, "dalsia:", pg.inner_text("#vTitle"))
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(300)
        # casova os
        pg.goto(base + "/#/t")
        pg.wait_for_selector(".tile img", timeout=30000)
        pg.wait_for_timeout(2500)
        pg.screenshot(path=f"{outdir}/{name}-4-casova-os.png")
        print(name, "casova os: mesiacov", pg.locator(".month").count(), "| prvy:", pg.locator(".month").first.inner_text(),
              "| pocet:", pg.inner_text("#count"))
        ctx.close()
    b.close()

print("CHYBY JS:", errors if errors else "ziadne")
