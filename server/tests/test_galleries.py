# SPDX-License-Identifier: GPL-3.0-or-later
"""Private galleries in one process. Run: python server/tests/test_galleries.py <work folder>"""
import io
import json
import os
import shutil
import sys

WORK = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "_test_galleries")
shutil.rmtree(WORK, ignore_errors=True)
MAIN_ROOT = os.path.join(WORK, "photo")
GROOTS = os.path.join(WORK, "groots")
TEST_ROOT = os.path.join(GROOTS, "test")
OUTSIDE = os.path.join(WORK, "outside")
for d in (MAIN_ROOT, TEST_ROOT, OUTSIDE):
    os.makedirs(d)
os.environ.update(PICTURESTATION_ROOT=MAIN_ROOT, PICTURESTATION_DATA=os.path.join(WORK, "data"),
                  PICTURESTATION_INDEX_INTERVAL="0", PICTURESTATION_GALLERY_ROOTS=GROOTS)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image  # noqa: E402


def photo(root, rel, color):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    Image.new("RGB", (900, 600), color).save(p, "JPEG")


photo(MAIN_ROOT, "Hlavny album/a.jpg", (200, 0, 0))
photo(TEST_ROOT, "Test album/b.jpg", (0, 200, 0))
photo(TEST_ROOT, "Test album/c.jpg", (0, 0, 200))
photo(OUTSIDE, "x.jpg", (9, 9, 9))

from starlette.testclient import TestClient  # noqa: E402
from picturestation import app as appmod, cli, config, galleries, media  # noqa: E402

sys.stdin = io.StringIO("bossheslo1\n")
cli.main(["useradd", "boss", "--admin", "--stdin"])

fails = 0


def check(name, cond, info=""):
    global fails
    print(("OK   " if cond else "FAIL ") + name + ("" if cond else f"  -> {info}"))
    fails += 0 if cond else 1


UA = {"User-Agent": "Mozilla/5.0 (test)"}
c = TestClient(appmod.app, headers=UA)


def api(cl, base, script, **p):
    r = cl.post(base + "/photo/webapi/" + script, data=p)
    return json.loads(r.text)


def login(cl, base, user, pw):
    return api(cl, base, "auth.php", api="SYNO.PhotoStation.Auth", method="login", version="1",
               username=user, password=pw)


def albums(cl, base):
    d = api(cl, base, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", offset="0",
            limit="50", type="album,photo")
    return [i["info"]["name"] for i in d["data"]["items"]] if d.get("success") else d


def adm(cl, base, op, body=None):
    if body is None:
        return cl.get(base + "/api/admin/" + op)
    return cl.post(base + "/api/admin/" + op, json=body)


# --- management in the main gallery ---
check("main: login boss", login(c, "", "boss", "bossheslo1")["success"])
r = adm(c, "", "gallery_create", {"name": "test", "title": "Test", "root": OUTSIDE, "hostnames": "test.example",
                                  "admin": "testadmin", "password": "testheslo1"})
check("folder outside allowed roots is refused", r.status_code == 400 and "inside" in r.json().get("error", ""), r.text)
r = adm(c, "", "gallery_create", {"name": "Zle Meno", "root": TEST_ROOT, "admin": "a", "password": "testheslo1"})
check("bad gallery name is refused", r.status_code == 400, r.text)
r = adm(c, "", "gallery_create", {"name": "test", "title": "Test", "root": TEST_ROOT, "hostnames": "test.example",
                                  "admin": "testadmin", "password": "testheslo1"})
check("gallery created", r.status_code == 200, r.text)
r = adm(c, "", "gallery_create", {"name": "test2", "root": TEST_ROOT, "hostnames": "test.example",
                                  "admin": "x", "password": "testheslo1"})
check("domain of another gallery is refused", r.status_code == 400 and "test.example" in r.json().get("error", ""), r.text)
gl = adm(c, "", "galleries_list").json()["galleries"]
check("gallery listed with its administrator", [(g["name"], g["admins"], g["path"]) for g in gl]
      == [("test", ["testadmin"], "/~test/")], gl)

# --- routing and separation ---
check("main gallery shows its own albums", albums(c, "") == ["Hlavny album"], albums(c, ""))
t = TestClient(appmod.app, headers=UA)
check("main admin cannot sign in to the private gallery", not login(t, "/~test", "boss", "bossheslo1")["success"])
check("owner signs in to the private gallery", login(t, "/~test", "testadmin", "testheslo1")["success"])
check("private gallery shows only its folder", albums(t, "/~test") == ["Test album"], albums(t, "/~test"))
check("private cookie is scoped to the gallery", any(ck.name == "PS_TEST" and ck.path == "/~test/" for ck in t.cookies.jar),
      [(ck.name, ck.path) for ck in t.cookies.jar])
check("owner of the private gallery cannot sign in to the main one", not login(t, "", "testadmin", "testheslo1")["success"])

# one browser, both galleries: the sessions do not replace each other
check("same browser: private login", login(c, "/~test", "testadmin", "testheslo1")["success"])
ca_main = api(c, "", "auth.php", api="SYNO.PhotoStation.Auth", method="checkauth", version="1")
ca_test = api(c, "/~test", "auth.php", api="SYNO.PhotoStation.Auth", method="checkauth", version="1")
check("same browser: both sessions stay", ca_main["data"]["username"] == "boss" and ca_test["data"]["username"] == "testadmin",
      (ca_main, ca_test))

# host name
h = TestClient(appmod.app, headers={**UA, "Host": "test.example"})
check("host name selects the gallery", login(h, "", "testadmin", "testheslo1")["success"] and albums(h, "") == ["Test album"])

# thumbnails and index stay in the gallery's data folder
media.index_gallery(galleries.by_name("test"))
tl = api(t, "/~test", "photo.php", api="SYNO.PhotoStation.Photo", method="list", version="1", type="photo,video",
         offset="0", limit="50")
check("timeline of the private gallery", tl.get("data", {}).get("total") == 2, tl)
pid = tl["data"]["items"][0]["id"]
r = t.get("/~test/photo/webapi/thumb.php", params={"api": "SYNO.PhotoStation.Thumb", "method": "get", "version": "1",
                                                   "id": pid, "size": "small"})
check("thumbnail in the private gallery", r.status_code == 200 and r.headers["content-type"].startswith("image/"), r.status_code)
thumbs = os.path.join(config.GALLERIES_DIR, "test", "thumbs")
check("its thumbnail cache is separate", os.path.isdir(thumbs) and any(os.scandir(thumbs)), thumbs)
tl_main = api(c, "", "photo.php", api="SYNO.PhotoStation.Photo", method="list", version="1", type="photo,video",
              offset="0", limit="50")
check("main timeline does not contain private photos", all("Test" not in i["info"]["name"] for i in tl_main["data"]["items"])
      and tl_main["data"]["total"] <= 1, tl_main["data"]["total"])

# web page and admin of the private gallery
html = t.get("/~test/").text
check("page knows its base", 'window.PS_BASE="/~test"' in html and "window.PS_MAIN=false" in html)
check("/~test without slash redirects", t.get("/~test", follow_redirects=False).status_code == 302)
check("unknown gallery = 404", t.get("/~nope/").status_code == 404)
st = adm(t, "/~test", "state").json()
check("private admin has its own settings", st.get("is_main") is False and [u["username"] for u in st["users"]] == ["testadmin"], st)
check("private admin cannot manage galleries", adm(t, "/~test", "galleries_list").status_code == 403)
r = adm(c, "", "gallery_admin_set", {"name": "test", "user": "druhy", "password": "druheheslo1"})
check("main admin adds a second administrator", r.status_code == 200 and login(TestClient(appmod.app, headers=UA), "/~test",
                                                                                 "druhy", "druheheslo1")["success"], r.text)
r = adm(c, "", "gallery_admin_remove", {"name": "test", "user": "druhy"})
check("and removes him", r.status_code == 200)

# disable and delete
adm(c, "", "gallery_update", {"name": "test", "enabled": False})
galleries.invalidate()
check("disabled gallery = 404", t.get("/~test/").status_code == 404)
adm(c, "", "gallery_update", {"name": "test", "enabled": True})
galleries.invalidate()
check("enabled again", t.get("/~test/").status_code == 200)
r = adm(c, "", "gallery_delete", {"name": "test"})
galleries.invalidate()
check("deleted gallery = 404, data kept aside", r.status_code == 200 and t.get("/~test/").status_code == 404
      and os.path.isdir(os.path.join(config.GALLERIES_DIR, ".deleted")) and os.path.isfile(os.path.join(TEST_ROOT, "Test album", "b.jpg")))

print("\nCHYB:", fails)
sys.exit(1 if fails else 0)
