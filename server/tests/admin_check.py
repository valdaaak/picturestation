# SPDX-License-Identifier: GPL-3.0-or-later
"""Kontrola nastaveni v Edge: python admin_check.py http://localhost user heslo_subor vystup_dir
Zalozi pouzivatela 'test-claude', da mu album, overi a zmaze ho."""
import os
import sys

from playwright.sync_api import sync_playwright


def sk(ctx):
    """Slovak UI: the selectors below use Slovak labels."""
    ctx.add_init_script("try { localStorage.setItem('lang', 'sk') } catch (e) {}")
    return ctx

base, user, pwfile, outdir = sys.argv[1:5]
pw = [l.split(":", 1)[1].strip() for l in open(pwfile, encoding="utf-8") if l.startswith("heslo:")][0]
os.makedirs(outdir, exist_ok=True)
errors = []
T = "test-claude"

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    for name, vp in (("desktop", {"width": 1300, "height": 900}), ("mobil", {"width": 390, "height": 844})):
        pg = sk(b.new_context(viewport=vp)).new_page()
        pg.on("pageerror", lambda e: errors.append(f"{name} JS: {e}"))
        pg.on("dialog", lambda d: d.accept())
        pg.goto(base + "/")
        pg.click("#loginBtn")
        pg.fill("#loginDlg input[name=username]", user)
        pg.fill("#loginDlg input[name=password]", pw)
        pg.click("#loginDlg button[type=submit]")
        pg.wait_for_selector("#adminTab:not([hidden])", timeout=15000)
        pg.click("#adminTab")
        pg.wait_for_selector(".adm-new", timeout=15000)
        pg.fill(".adm-new input[name=username]", T)
        pg.fill(".adm-new input[name=password]", "testheslo123")
        pg.fill(".adm-new input[name=note]", "docasny test")
        pg.click(".adm-new button[type=submit]")
        pg.wait_for_selector(f".card:has-text('{T}')", timeout=15000)
        card = pg.locator(".card", has_text=T)
        card.locator("button", has_text="Upraviť prístup").click()
        try:
            pg.wait_for_selector(".acc-list .acc-row", timeout=15000)
        except Exception:
            pg.screenshot(path=f"{outdir}/{name}-adm-chyba.png")
            raise
        pg.locator(".acc-list .acc-row").first.locator("button.add").click()
        pg.wait_for_timeout(1000)
        pg.screenshot(path=f"{outdir}/{name}-adm-1-vyber.png")
        pg.locator(".adm-dlg button.primary", has_text="Hotovo").click()
        pg.wait_for_timeout(1000)
        print(name, "prava:", card.locator(".grants .path").all_inner_texts())
        pg.screenshot(path=f"{outdir}/{name}-adm-2-pouzivatelia.png", full_page=False)
        card.locator(".card-a button").click()
        pg.wait_for_selector(".adm-dlg[open]")
        pg.screenshot(path=f"{outdir}/{name}-adm-3-uprava.png")
        pg.locator(".adm-dlg button", has_text="Zmazať").click()
        pg.wait_for_timeout(1200)
        print(name, "po zmazani este existuje:", pg.locator(".card", has_text=T).count() > 0)
        pg.click(".adm-tabs button:has-text('Skupiny')")
        pg.wait_for_timeout(500)
        pg.screenshot(path=f"{outdir}/{name}-adm-4-skupiny.png")
        pg.context.close()
    b.close()
print("CHYBY JS:", errors or "ziadne")
