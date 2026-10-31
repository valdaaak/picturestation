# SPDX-License-Identifier: GPL-3.0-or-later
"""Every text of the web gallery and of the LG TV app has a Slovak translation. Run: python server/tests/test_i18n.py"""
import json
import os
import re
import sys

HERE = os.path.dirname(__file__)
WEB = os.path.join(HERE, "..", "..", "web")
TV = os.path.join(HERE, "..", "..", "LGTV", "app")
PKG = os.path.join(HERE, "..", "picturestation")
sys.path.insert(0, os.path.join(HERE, ".."))
fails = 0


def check(name, cond, info=""):
    global fails
    print(("OK   " if cond else "FAIL ") + name + ("" if cond else f"  -> {info}"))
    fails += 0 if cond else 1


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


STR = r'"(?:[^"\\]|\\.)*"'
CONCAT = rf"{STR}(?:\s*\+\s*{STR})*"


def lit(s):
    """'"a" + "b"' -> 'ab'"""
    return "".join(json.loads(x) for x in re.findall(STR, s))


def bundle(label, folder, dict_js, js_names, html_name):
    """One front end: its I18N_SK dictionary, the t()/tn() calls in its scripts and data-t in its HTML."""
    src = read(os.path.join(folder, dict_js))
    m = re.search(r"(?:const|var) I18N_SK = (\{.*?\n\});", src, re.S)
    sk = json.loads(m.group(1))
    used, plural = set(), set()
    for name in js_names:
        js = read(os.path.join(folder, name))
        for c in re.finditer(rf"\bt\(\s*({CONCAT})", js):
            used.add(lit(c.group(1)))
        for c in re.finditer(rf"\btn\([^,]+,\s*({STR}),\s*({STR})", js):
            plural.add((json.loads(c.group(1)), json.loads(c.group(2))))
        # a local variable named t would hide the translation function
        shadow = re.findall(r"(?:\b(?:const|let|var)\s+t\b|\(\s*t\s*\)\s*=>|\bfor\s*\(\s*(?:const|let)\s+t\s+of)", js)
        check(f"{label} {name}: nothing shadows t()", not shadow, shadow)
        # t( with something else than a literal cannot be checked
        odd = [ln for ln in re.findall(r"\bt\(\s*[^\"\s)][^\n]{0,40}", js)]
        check(f"{label} {name}: t() always with a literal", not odd, odd[:5])
    html = read(os.path.join(folder, html_name))
    for c in re.finditer(r'data-t(?:-placeholder|-title|-aria)?="([^"]*)"', html):
        used.add(c.group(1))
    missing = sorted(k for k in used if not isinstance(sk.get(k), str))
    check(f"{label}: {len(used)} texts have a Slovak translation", not missing, missing)
    bad_pl = sorted(o for _, o in plural if not (isinstance(sk.get(o), list) and len(sk[o]) == 3))
    check(f"{label}: {len(plural)} plurals have 3 Slovak forms", not bad_pl, bad_pl)
    ph = [k for k, v in sk.items() if isinstance(v, str) and set(re.findall(r"\{\w+\}", k)) != set(re.findall(r"\{\w+\}", v))]
    check(f"{label}: placeholders match in both languages", not ph, ph)
    unused = sorted(set(sk) - used - {o for _, o in plural})
    print(f"{label}: unused translations:", unused)


bundle("web", WEB, "i18n.js", ("app.js", "admin.js"), "index.html")
bundle("LG TV", TV, os.path.join("js", "i18n.js"), [os.path.join("js", n) for n in ("app.js", "api.js", "ui.js")], "index.html")

# server side: every message raised in admin.py/app.py has a Slovak translation
from picturestation import i18n  # noqa: E402
srv = "".join(read(os.path.join(PKG, f)) for f in ("admin.py", "app.py", "galleries.py"))
msgs = (set(re.findall(r'AdminError\("([^"]+)"', srv)) | set(re.findall(r'i18n\.tr\("([^"]+)"', srv))
        | set(re.findall(r'GalleryError\("([^"]+)"', srv)))
miss = sorted(x for x in msgs if x not in i18n.SK)
check(f"{len(msgs)} server messages have a Slovak translation", not miss, miss)
check("server: Accept-Language", i18n.pick("cs-CZ,cs;q=0.9,en;q=0.8") == "sk" and i18n.pick("de-DE,sk;q=0.5") == "en"
      and i18n.pick("") == "en")

print("\nCHYB:", fails)
sys.exit(1 if fails else 0)
