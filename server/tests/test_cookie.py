# SPDX-License-Identifier: GPL-3.0-or-later
"""Osobna galeria s vlastnym menom cookie (PICTURESTATION_COOKIE). Spustenie: python server/tests/test_cookie.py <pracovny_priecinok>"""
import io
import json
import os
import shutil
import sys

WORK = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "_test_cookie")
ROOT = os.path.join(WORK, "photo")
shutil.rmtree(WORK, ignore_errors=True)
os.makedirs(os.path.join(ROOT, "Album"))
os.environ.update(PICTURESTATION_ROOT=ROOT, PICTURESTATION_DATA=os.path.join(WORK, "data"), PICTURESTATION_INDEX_INTERVAL="0",
                  PICTURESTATION_COOKIE="PS_ALICE")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image  # noqa: E402

Image.new("RGB", (800, 600), (10, 20, 30)).save(os.path.join(ROOT, "Album", "a.jpg"))

from starlette.testclient import TestClient  # noqa: E402
from picturestation import app as appmod, cli, config  # noqa: E402

sys.stdin = io.StringIO("aliceheslo1\n")
cli.main(["useradd", "alice", "--admin", "--stdin"])

fails = 0


def check(name, cond, info=""):
    global fails
    print(("OK   " if cond else "FAIL ") + name + ("" if cond else f"  -> {info}"))
    fails += 0 if cond else 1


def call(cl, path, **p):
    r = cl.post("/photo/webapi/" + path, data=p)
    assert r.status_code == 200, (r.status_code, r.text)
    return json.loads(r.text)


check("config cita PICTURESTATION_COOKIE", config.SESSION_COOKIE == "PS_ALICE", config.SESSION_COOKIE)
c = TestClient(appmod.app, headers={"User-Agent": "Mozilla/5.0 (test)"})
lg = call(c, "auth.php", api="SYNO.PhotoStation.Auth", method="login", version="1",
          username="alice", password="aliceheslo1")
check("login nastavi vlastnu cookie", lg["success"] and c.cookies.get("PS_ALICE") == lg["data"]["sid"], lg)
check("PHPSESSID sa nenastavi", c.cookies.get("PHPSESSID") is None, dict(c.cookies))
ca = call(c, "auth.php", api="SYNO.PhotoStation.Auth", method="checkauth", version="1")
check("checkauth cez vlastnu cookie", ca["data"]["username"] == "alice", ca)
al = call(c, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", offset="0", limit="10",
          type="album,photo")
check("album list vidi Album", al["success"] and [i["info"]["name"] for i in al["data"]["items"]] == ["Album"], al)
check("admin API cez vlastnu cookie", c.get("/api/admin/state").status_code == 200)

# cookie inej galerie (PHPSESSID) tu neplati
sid = lg["data"]["sid"]
o = TestClient(appmod.app, headers={"User-Agent": "Mozilla/5.0 (test)"})
o.cookies.set("PHPSESSID", sid)
ca = call(o, "auth.php", api="SYNO.PhotoStation.Auth", method="checkauth", version="1")
check("PHPSESSID cookie sa ignoruje", not ca["data"].get("username"), ca)
check("admin API s PHPSESSID cookie = 401", o.get("/api/admin/state").status_code == 401)
# prehliadac NESMIE pouzit sid z URL parametra (uniklo by cez Referer/history)
ca = call(o, "auth.php", api="SYNO.PhotoStation.Auth", method="checkauth", version="1", PHPSESSID=sid)
check("prehliadac: parameter PHPSESSID sa ignoruje", not ca["data"].get("username"), ca)
# appka DS photo (User-Agent Synology-...) sid v parametri PHPSESSID pouzit smie
app2 = TestClient(appmod.app, headers={"User-Agent": "Synology-DS_photo_3.12.6"})
ca = call(app2, "auth.php", api="SYNO.PhotoStation.Auth", method="checkauth", version="1", PHPSESSID=sid)
check("appka: parameter PHPSESSID plati", ca["data"]["username"] == "alice", ca)

call(c, "auth.php", api="SYNO.PhotoStation.Auth", method="logout", version="1")
check("logout zmaze vlastnu cookie", not c.cookies.get("PS_ALICE"), dict(c.cookies))

# appka DS photo (User-Agent Synology-...) dostane aj PHPSESSID, inak nevie poskladat URL nahladov
app_c = TestClient(appmod.app, headers={"User-Agent": "Synology-DS_photo_3.12.6_Pixel_14_(Dalvik/2.1.0)"})
lg = call(app_c, "auth.php", api="SYNO.PhotoStation.Auth", method="login", version="1",
          username="alice", password="aliceheslo1")
check("appka dostane PHPSESSID", app_c.cookies.get("PHPSESSID") == lg["data"]["sid"], dict(app_c.cookies))
r = app_c.get("/photo/webapi/thumb.php", params={"api": "SYNO.PhotoStation.Thumb", "method": "get", "version": "1",
                                                  "id": al["data"]["items"][0]["id"], "size": "small",
                                                  "PHPSESSID": app_c.cookies.get("PHPSESSID")})
check("appka: nahlad cez PHPSESSID v URL", r.status_code == 200 and r.headers["content-type"].startswith("image/"),
      (r.status_code, r.headers.get("content-type")))
call(app_c, "auth.php", api="SYNO.PhotoStation.Auth", method="logout", version="1")
check("appka: logout zmaze PHPSESSID", not app_c.cookies.get("PHPSESSID"), dict(app_c.cookies))

print("\nCHYB:", fails)
sys.exit(1 if fails else 0)
