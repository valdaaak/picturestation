# SPDX-License-Identifier: GPL-3.0-or-later
"""Kontrola zdielania v Edge: admin vytvori odkaz na prvy album, anonym ho otvori, admin ho zrusi."""
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

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    adm = sk(b.new_context(viewport={"width": 1300, "height": 900})).new_page()
    adm.on("pageerror", lambda e: errors.append(f"admin JS: {e}"))
    adm.on("dialog", lambda d: d.accept())
    adm.goto(base + "/")
    adm.click("#loginBtn")
    adm.fill("#loginDlg input[name=username]", user)
    adm.fill("#loginDlg input[name=password]", pw)
    adm.click("#loginDlg button[type=submit]")
    adm.wait_for_selector(".album img", timeout=20000)
    adm.locator(".album").first.click()
    adm.wait_for_selector("#shareAlbumBtn:not([hidden])", timeout=20000)
    adm.click("#shareAlbumBtn")
    adm.wait_for_selector(".adm-dlg[open]")
    adm.fill(".adm-dlg input[name=note]", "test-claude")
    adm.click(".adm-dlg button[type=submit]")
    adm.wait_for_selector(".copy-in", timeout=10000)
    url = adm.input_value(".copy-in")
    adm.screenshot(path=f"{outdir}/share-1-dialog.png")
    print("odkaz:", url.split("/s/")[0] + "/s/<kod>")
    adm.click(".adm-dlg button:has-text('Zavrieť')")

    for name, vp in (("desktop", {"width": 1300, "height": 900}), ("mobil", {"width": 390, "height": 844})):
        anon = sk(b.new_context(viewport=vp)).new_page()
        anon.on("pageerror", lambda e: errors.append(f"anon JS: {e}"))
        anon.goto(url)
        anon.wait_for_selector(".tile img, .album img", timeout=20000)
        anon.wait_for_timeout(2000)
        anon.screenshot(path=f"{outdir}/share-2-{name}.png")
        print(name, "anonym:", anon.inner_text("#crumbs"), "| albumov", anon.locator(".album").count(),
              "| dlazdic", anon.locator(".tile").count(), "| prihlaseny:", repr(anon.inner_text("#userName")),
              "| zalozky skryte:", anon.locator(".tabs").is_hidden())
        anon.context.close()

    adm.goto(base + "/#/admin")
    adm.wait_for_selector(".adm-tabs")
    adm.click(".adm-tabs button:has-text('Zdieľania')")
    adm.wait_for_selector(".card:has-text('test-claude')", timeout=10000)
    adm.screenshot(path=f"{outdir}/share-3-zoznam.png")
    adm.locator(".card", has_text="test-claude").locator("button:has-text('Zrušiť')").click()
    adm.wait_for_timeout(1500)
    print("po zruseni ostal:", adm.locator(".card", has_text="test-claude").count())
    anon = sk(b.new_context()).new_page()
    anon.goto(url)
    anon.wait_for_selector("#empty:not([hidden])", timeout=10000)
    print("zruseny odkaz:", anon.inner_text("#empty"))
    b.close()
print("CHYBY JS:", errors or "ziadne")
