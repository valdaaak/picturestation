# SPDX-License-Identifier: GPL-3.0-or-later
"""Every text of the web gallery has a Slovak translation. Run: python server/tests/test_i18n.py"""
import json
import os
import re
import sys

WEB = os.path.join(os.path.dirname(__file__), "..", "picturestation", "web")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
fails = 0


def check(name, cond, info=""):
    global fails
    print(("OK   " if cond else "FAIL ") + name + ("" if cond else f"  -> {info}"))
    fails += 0 if cond else 1


def read(name):
    with open(os.path.join(WEB, name), encoding="utf-8") as fh:
        return fh.read()


src = read("i18n.js")
m = re.search(r"const I18N_SK = (\{.*?\n\});", src, re.S)
SK = json.loads(m.group(1))

STR = r'"(?:[^"\\]|\\.)*"'
CONCAT = rf"{STR}(?:\s*\+\s*{STR})*"


def lit(s):
    """'"a" + "b"' -> 'ab'"""
    return "".join(json.loads(x) for x in re.findall(STR, s))


used, plural = set(), set()
for name in ("app.js", "admin.js"):
    js = read(name)
    for c in re.finditer(rf"\bt\(\s*({CONCAT})", js):
        used.add(lit(c.group(1)))
    for c in re.finditer(rf"\btn\([^,]+,\s*({STR}),\s*({STR})", js):
        plural.add((json.loads(c.group(1)), json.loads(c.group(2))))
    # a local variable named t would hide the translation function
    shadow = re.findall(r"(?:\b(?:const|let|var)\s+t\b|\(\s*t\s*\)\s*=>|\bfor\s*\(\s*(?:const|let)\s+t\s+of)", js)
    check(f"{name}: nothing shadows t()", not shadow, shadow)
    # t( with something else than a literal cannot be checked
    odd = [ln for ln in re.findall(r"\bt\(\s*[^\"\s)][^\n]{0,40}", js)]
    check(f"{name}: t() always with a literal", not odd, odd[:5])
html = read("index.html")
for c in re.finditer(r'data-t(?:-placeholder|-title|-aria)?="([^"]*)"', html):
    used.add(c.group(1))

missing = sorted(k for k in used if not isinstance(SK.get(k), str))
check(f"{len(used)} texts have a Slovak translation", not missing, missing)
bad_pl = sorted(o for _, o in plural if not (isinstance(SK.get(o), list) and len(SK[o]) == 3))
check(f"{len(plural)} plurals have 3 Slovak forms", not bad_pl, bad_pl)
ph = [k for k, v in SK.items() if isinstance(v, str) and set(re.findall(r"\{\w+\}", k)) != set(re.findall(r"\{\w+\}", v))]
check("placeholders match in both languages", not ph, ph)
unused = sorted(set(SK) - used - {o for _, o in plural})
print("unused translations:", unused)

# server side: every message raised in admin.py/app.py has a Slovak translation
from picturestation import i18n  # noqa: E402
srv = read(os.path.join("..", "admin.py")) + read(os.path.join("..", "app.py"))
msgs = set(re.findall(r'AdminError\("([^"]+)"', srv)) | set(re.findall(r'i18n\.tr\("([^"]+)"', srv))
miss = sorted(x for x in msgs if x not in i18n.SK)
check(f"{len(msgs)} server messages have a Slovak translation", not miss, miss)
check("server: Accept-Language", i18n.pick("cs-CZ,cs;q=0.9,en;q=0.8") == "sk" and i18n.pick("de-DE,sk;q=0.5") == "en"
      and i18n.pick("") == "en")

print("\nCHYB:", fails)
sys.exit(1 if fails else 0)
