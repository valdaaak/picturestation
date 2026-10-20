"""Kontrola komentarov v Edge: admin prida komentar k prvej fotke prveho albumu a zmaze ho."""
import os
import sys

from playwright.sync_api import sync_playwright

base, user, pwfile, outdir = sys.argv[1:5]
pw = [l.split(":", 1)[1].strip() for l in open(pwfile, encoding="utf-8") if l.startswith("heslo:")][0]
os.makedirs(outdir, exist_ok=True)
errors = []
TXT = "test-claude komentar"

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
    pg.wait_for_selector("#vInfoBtn")
    if pg.locator("#vInfo").is_hidden():
        pg.click("#vInfoBtn")
    pg.wait_for_selector(".cmt-form textarea", timeout=10000)
    before = pg.locator(".cmt").count()
    pg.fill(".cmt-form textarea", TXT)
    pg.click(".cmt-form button[type=submit]")
    pg.wait_for_selector(f".cmt:has-text('{TXT}')", timeout=10000)
    pg.screenshot(path=f"{outdir}/cmt-1.png")
    print("komentarov pred/po:", before, pg.locator(".cmt").count(), "| tlacidlo:", pg.inner_text("#vInfoBtn"))
    pg.locator(".cmt", has_text=TXT).locator("button.x").click()
    pg.wait_for_timeout(1500)
    print("po zmazani:", pg.locator(".cmt", has_text=TXT).count())
    b.close()
print("CHYBY JS:", errors or "ziadne")
