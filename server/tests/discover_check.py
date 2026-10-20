# SPDX-License-Identifier: GPL-3.0-or-later
"""Kontrola Objavit v Edge: admin prida tag 'test-claude' k fotke, pozrie Objavit, otvori tag, tag odoberie."""
import os
import sys

from playwright.sync_api import sync_playwright

base, user, pwfile, outdir = sys.argv[1:5]
pw = [l.split(":", 1)[1].strip() for l in open(pwfile, encoding="utf-8") if l.startswith("heslo:")][0]
os.makedirs(outdir, exist_ok=True)
errors = []
TAG = "test-claude"

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    pg = b.new_context(viewport={"width": 1300, "height": 900}).new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("dialog", lambda d: d.accept())
    pg.goto(base + "/")
    pg.click("#loginBtn")
    pg.fill("#loginDlg input[name=username]", user)
    pg.fill("#loginDlg input[name=password]", pw)
    pg.click("#loginDlg button[type=submit]")
    pg.wait_for_selector(".album img", timeout=20000)
    pg.locator(".album").first.click()
    pg.wait_for_selector(".tile img", timeout=20000)
    pg.locator(".tile").first.click()
    if pg.locator("#vInfo").is_hidden():
        pg.click("#vInfoBtn")
    pg.wait_for_selector(".tag-form input", timeout=10000)
    pg.fill(".tag-form input", TAG)
    pg.press(".tag-form input", "Enter")
    pg.wait_for_selector(f".chip:has-text('{TAG}')", timeout=10000)
    pg.screenshot(path=f"{outdir}/disc-1-tag.png")
    pg.keyboard.press("Escape")
    pg.goto(base + "/#/x")
    pg.wait_for_selector(".disc-h", timeout=20000)
    pg.wait_for_timeout(2500)
    pg.screenshot(path=f"{outdir}/disc-2-objavit.png", full_page=False)
    secs = pg.locator(".disc-h h3").all_inner_texts()
    print("sekcie:", secs[:6], "... spolu", len(secs))
    pg.locator(".album", has_text=TAG).first.click()
    pg.wait_for_selector(".tile img", timeout=20000)
    print("tag skupina:", pg.inner_text("#crumbs").replace("\n", " "), "|", pg.inner_text("#count"))
    pg.locator(".tile").first.click()
    if pg.locator("#vInfo").is_hidden():
        pg.click("#vInfoBtn")
    pg.wait_for_selector(f".chip:has-text('{TAG}') .x", timeout=10000)
    pg.locator(".chip", has_text=TAG).locator(".x").click()
    pg.wait_for_timeout(1500)
    print("tag po odobrati:", pg.locator(".chip", has_text=TAG).count())
    b.close()
print("CHYBY JS:", errors or "ziadne")
