# SPDX-License-Identifier: GPL-3.0-or-later
"""Test API proti umelemu stromu fotiek. Spustenie: python server/tests/test_api.py <pracovny_priecinok>"""
import json
import os
import shutil
import sys
import time

WORK = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "_test_work")
ROOT = os.path.join(WORK, "photo")
shutil.rmtree(WORK, ignore_errors=True)
os.makedirs(ROOT)
os.environ.update(PICTURESTATION_ROOT=ROOT, PICTURESTATION_DATA=os.path.join(WORK, "data"), PICTURESTATION_INDEX_INTERVAL="0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image  # noqa: E402

# --- umely strom ---
def photo(rel, size=(2000, 1500), color=(200, 50, 50), exif_date=None, orient=None):
    p = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    im = Image.new("RGB", size, color)
    ex = Image.Exif()
    if exif_date:
        ex.get_ifd(0x8769)[0x9003] = exif_date
    if orient:
        ex[0x0112] = orient
    ex[0x010F] = "Canon"
    ex[0x0110] = "EOS Test"
    im.save(p, "JPEG", exif=ex.tobytes())

photo("2001/Maxim/01.jpg", exif_date="2001:05:01 10:00:00")
photo("2001/Maxim/02.jpg", exif_date="2001:04:01 10:00:00", orient=6)
photo("2001/Rodina/a.jpg")
photo("Súkromné/tajne.jpg")
photo("koren.jpg")
os.makedirs(os.path.join(ROOT, "2001", "@eaDir", "x"))
os.makedirs(os.path.join(ROOT, "#recycle"))
# hotovy nahlad v @eaDir (stary Photo Station nazov)
ea = os.path.join(ROOT, "2001", "Rodina", "@eaDir", "a.jpg")
os.makedirs(ea)
Image.new("RGB", (1280, 960), (0, 255, 0)).save(os.path.join(ea, "SYNOPHOTO:THUMB_XL.jpg"))

from starlette.testclient import TestClient  # noqa: E402
from picturestation import app as appmod, cli, ids  # noqa: E402

def run_cli(*a, stdin=None):
    if stdin is not None:
        import io
        sys.stdin = io.StringIO(stdin + "\n")
    cli.main(list(a))

run_cli("useradd", "spravca", "--admin", "--stdin", stdin="heslo1234")
run_cli("useradd", "kolega", "--stdin", stdin="heslo5678")
run_cli("grant", "kolega", "2001/Maxim")

c = TestClient(appmod.app)
W = "/photo/webapi/"
fails = 0

def call(path, **p):
    r = c.post(W + path, data=p)
    assert r.status_code == 200, (r.status_code, r.text)
    return json.loads(r.text)

def check(name, cond, info=""):
    global fails
    print(("OK   " if cond else "FAIL ") + name + ("" if cond else f"  -> {info}"))
    fails += 0 if cond else 1

# --- prihlasenie ---
q = call("query.php", api="SYNO.API.Info", method="query", version="1", query="all")
check("query vrati Auth", q["data"]["SYNO.PhotoStation.Auth"]["path"] == "auth.php", q)
bad = call("auth.php", api="SYNO.PhotoStation.Auth", method="login", version="1", username="spravca", password="zle")
check("zle heslo = 407", bad == {"success": False, "error": {"code": 407}}, bad)
lg = call("auth.php", api="SYNO.PhotoStation.Auth", method="login", version="1", username="spravca", password="heslo1234")
check("login ok", lg["success"] and lg["data"]["is_admin"] and c.cookies.get("PHPSESSID") == lg["data"]["sid"], lg)
info = call("info.php", api="SYNO.PhotoStation.Info", method="getinfo", version="1")
check("info version", info["data"]["version"] == "3483", info)
ca = call("auth.php", api="SYNO.PhotoStation.Auth", method="checkauth", version="1")
check("checkauth username", ca["data"]["username"] == "spravca", ca)

# --- koren ---
r = call("album.php", api="SYNO.PhotoStation.Album", method="list", version="1", offset="0", limit="120",
         type="album,video,photo", additional="album_permission,thumb_size")
names = [i["info"]["name"] for i in r["data"]["items"]]
check("koren: albumy + fotka, bez @eaDir/#recycle", names == ["2001", "Súkromné", "koren.jpg"], names)
a2001 = r["data"]["items"][0]
check("album id = album_ + hex", a2001["id"] == "album_" + "2001".encode().hex(), a2001["id"])
check("album ma nahlad", a2001["thumbnail_status"] == "small,large" and a2001["additional"]["thumb_size"]["sig"], a2001)
kor = r["data"]["items"][2]
check("fotka v koreni id photo_2f_", kor["id"] == "photo_2f_" + "koren.jpg".encode().hex(), kor["id"])

# --- album Maxim, zoradenie podla datumu ---
mid = ids.album_id("2001/Maxim")
r = call("album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=mid, offset="0", limit="120",
         type="album,video,photo", sort_by="takendate", sort_direction="asc",
         additional="photo_exif,thumb_size")
it = r["data"]["items"]
check("Maxim zoradene podla EXIF", [i["info"]["name"] for i in it] == ["02.jpg", "01.jpg"], [i["info"]["name"] for i in it])
p02 = it[0]
check("orientacia 6 otoci rozmery", (p02["info"]["resolutionx"], p02["info"]["resolutiony"]) == (1500, 2000), p02["info"])
check("takendate z EXIF", p02["info"]["takendate"] == "2001-04-01 10:00:00", p02["info"])
check("exif camera", p02["additional"]["photo_exif"]["camera"] == "Canon", p02["additional"])

# --- nahlady ---
sid = c.cookies.get("PHPSESSID")
t = c.get(W + "thumb.php", params={"api": "SYNO.PhotoStation.Thumb", "method": "get", "version": "1",
                                   "id": p02["id"], "size": "large", "PHPSESSID": sid})
im = Image.open(__import__("io").BytesIO(t.content))
check("vygenerovany large nahlad otoceny, kratsia strana 1280", t.headers["content-type"] == "image/jpeg" and im.size == (1280, 1707), im.size)
rid = ids.item_id("photo", "2001/Rodina/a.jpg")
t = c.get(W + "thumb.php", params={"api": "SYNO.PhotoStation.Thumb", "method": "get", "version": "1",
                                   "id": rid, "size": "large", "PHPSESSID": sid})
px = Image.open(__import__("io").BytesIO(t.content)).convert("RGB").getpixel((5, 5))
check("nahlad z @eaDir (zeleny)", px[1] > 200 and px[0] < 50, px)
t = c.get(W + "thumb.php", params={"api": "SYNO.PhotoStation.Thumb", "method": "get", "version": "1",
                                   "id": a2001["id"], "size": "small", "PHPSESSID": sid})
check("nahlad albumu", t.headers["content-type"] == "image/jpeg", t.text[:100])

# --- original s Range ---
d = c.get(W + "download.php", params={"api": "SYNO.PhotoStation.Download", "method": "getphoto", "version": "1",
                                      "id": p02["id"], "PHPSESSID": sid}, headers={"Range": "bytes=0-9"})
check("download Range 206", d.status_code == 206 and len(d.content) == 10 and d.content[:2] == b"\xff\xd8", d.status_code)

# --- timeline z indexu ---
from picturestation import media  # noqa: E402
media.index_once()
r = call("photo.php", api="SYNO.PhotoStation.Photo", method="list", version="1", type="photo,video",
         offset="0", limit="10", sort_by="takendate", sort_direction="desc")
check("timeline vsetky fotky", r["data"]["total"] == 5, r["data"]["total"])
g = call("photo.php", api="SYNO.PhotoStation.Photo", method="getinfo", version="1", id=p02["id"])
check("photo getinfo = pole", isinstance(g["data"], list) and g["data"][0]["id"] == p02["id"], g)

# --- chybajuce API nesmu padnut ---
s = call("smart_album.php", api="SYNO.PhotoStation.SmartAlbum", method="list", version="1")
check("smart album prazdny", s["data"]["smart_albums"] == [], s)
e = call("album.php", api="SYNO.PhotoStation.Album", method="delete", version="1", id=mid)
check("mazanie zakazane 105", e["error"]["code"] == 105, e)

# --- prava: kolega vidi len 2001/Maxim ---
c.cookies.clear()
call("auth.php", api="SYNO.PhotoStation.Auth", method="login", version="1", username="kolega", password="heslo5678")
r = call("album.php", api="SYNO.PhotoStation.Album", method="list", version="1", offset="0", limit="120", type="album,video,photo")
check("kolega koren = len cesta 2001", [i["info"]["name"] for i in r["data"]["items"]] == ["2001"], r["data"]["items"])
check("kolega 2001 browse=false", r["data"]["items"][0]["additional"]["album_permission"]["browse"] is False)
r = call("album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("2001"),
         offset="0", limit="120", type="album,video,photo")
check("kolega v 2001 vidi len Maxim", [i["info"]["name"] for i in r["data"]["items"]] == ["Maxim"], r["data"]["items"])
r = call("album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("Súkromné"),
         offset="0", limit="120", type="album,video,photo")
check("kolega Súkromné = 417", r == {"success": False, "error": {"code": 417}}, r)
sid = c.cookies.get("PHPSESSID")
t = c.get(W + "download.php", params={"api": "SYNO.PhotoStation.Download", "method": "getphoto", "version": "1",
                                      "id": ids.item_id("photo", "Súkromné/tajne.jpg"), "PHPSESSID": sid})
check("kolega nestiahne cudziu fotku", t.headers["content-type"].startswith("text/plain") and '"code": 507' in t.text, t.text[:80])
r = call("photo.php", api="SYNO.PhotoStation.Photo", method="list", version="1", type="photo,video", offset="0", limit="10")
check("kolega timeline len Maxim", r["data"]["total"] == 2, r["data"]["total"])
t = c.get(W + "thumb.php", params={"api": "SYNO.PhotoStation.Thumb", "method": "get", "version": "1",
                                   "id": "photo_" + "..".encode().hex() + "_" + "x.jpg".encode().hex(), "size": "small"})
check("path traversal odmietnuty", '"success": false' in t.text, t.text[:80])

# --- vyprsana session ---
c.cookies.clear()
c.cookies.set("PHPSESSID", "neplatna")
r = c.post(W + "album.php", data=dict(api="SYNO.PhotoStation.Album", method="list", version="1"))
check("neplatna session -> error_timeout", r.headers.get("x-request-error") == "error_timeout", dict(r.headers))

# --- host bez prihlasenia ---
c.cookies.clear()
r = call("album.php", api="SYNO.PhotoStation.Album", method="list", version="1", type="album,video,photo")
check("host bez prav nevidi nic", r["data"]["items"] == [], r)

# --- webova galeria ---
r = c.get("/")
check("web index.html", r.status_code == 200 and "app.js" in r.text and "text/html" in r.headers["content-type"], r.status_code)
r = c.get("/app.js")
check("web app.js", r.status_code == 200 and "SYNO.PhotoStation" in r.text, r.status_code)
r = c.get("/photo/", follow_redirects=False)
check("/photo/ presmeruje na galeriu", r.status_code == 302 and r.headers["location"] == "/", r.status_code)
r = c.get("/../picturestation/app.py")
check("web nevydá zdrojaky", r.status_code == 404, r.status_code)

# --- video pre prehliadac: AVI s prekodovanou verziou v @eaDir ---
vdir = os.path.join(ROOT, "2001", "Maxim")
open(os.path.join(vdir, "film.avi"), "wb").write(b"RIFF....AVI ")
os.makedirs(os.path.join(vdir, "@eaDir", "film.avi"))
open(os.path.join(vdir, "@eaDir", "film.avi", "SYNOPHOTO_FILM_M.mp4"), "wb").write(b"\x00\x00\x00\x18ftypmp42")
c.cookies.clear()
call("auth.php", api="SYNO.PhotoStation.Auth", method="login", version="1", username="spravca", password="heslo1234")
vid = ids.item_id("video", "2001/Maxim/film.avi")
r = c.get(W + "download.php", params={"api": "SYNO.PhotoStation.Download", "method": "getvideo", "version": "1",
                                      "id": vid, "variant": "web"})
check("video pre web = prekodovane mp4", r.headers["content-type"] == "video/mp4" and b"ftypmp42" in r.content, r.headers)
r = c.get(W + "download.php", params={"api": "SYNO.PhotoStation.Download", "method": "getvideo", "version": "1", "id": vid})
check("video original = avi", r.content.startswith(b"RIFF"), r.content[:10])

# --- video nabok (priznak otocenia z mobilu): pre telku vznikne otocena kopia (variant=tv) ---
from picturestation import media, tvvideo  # noqa: E402
if media.FFMPEG and media.FFPROBE:
    import subprocess  # noqa: E402
    vrot = os.path.join(vdir, "rot.mp4")
    plain = os.path.join(WORK, "plain.mp4")
    subprocess.run([media.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=10", "-t", "1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", plain], check=True)
    # the rotation flag the way a phone sets it (display matrix), frames stay 160x90 on their side
    subprocess.run([media.FFMPEG, "-v", "error", "-y", "-display_rotation", "90", "-i", plain, "-c", "copy", vrot], check=True)
    media._dir_cache.clear()
    rid = ids.item_id("video", "2001/Maxim/rot.mp4")
    r = call("photo.php", api="SYNO.PhotoStation.Photo", method="getinfo", version="1", id=rid, additional="video_codec")
    vc = r["data"][0]["additional"]["video_codec"]
    check("video nabok: rotation v metadatach, kopia caka", vc.get("rotation") in (90, 270) and vc.get("tv_version") == "waiting", vc)
    check("video nabok: rozmery uz otocene", (vc["resolutionx"], vc["resolutiony"]) == (90, 160), vc)
    r = c.get(W + "download.php", params={"api": "SYNO.PhotoStation.Download", "method": "getvideo", "version": "1",
                                          "id": rid, "variant": "tv"})
    check("variant=tv pred prekodovanim = original + hlavicka preparing", r.status_code == 200
          and r.headers.get("x-picturestation-video") == "preparing" and len(r.content) == os.path.getsize(vrot), dict(r.headers))
    tvvideo.MIN_FREE_BYTES = 0  # the test library may sit in a small tmpfs
    n = tvvideo.process_now()
    fe = media.file_entry("2001/Maxim/rot.mp4")
    rp = tvvideo.ready_path(fe)
    check("otocena kopia vyrobena", n == 1 and rp, (n, rp, tvvideo._failed))
    pr = media._probe_video(rp) if rp else {}
    check("kopia stoji rovno: 90x160, h264, bez priznaku", (pr.get("w"), pr.get("h"), pr.get("vcodec"), pr.get("rotation")) == (90, 160, "h264", 0), pr)
    r = c.get(W + "download.php", params={"api": "SYNO.PhotoStation.Download", "method": "getvideo", "version": "1",
                                          "id": rid, "variant": "tv"})
    check("variant=tv = otocena kopia", r.headers["content-type"] == "video/mp4" and "x-picturestation-video" not in r.headers
          and len(r.content) == os.path.getsize(tvvideo.ready_path(fe)), dict(r.headers))
    r = c.get(W + "download.php", params={"api": "SYNO.PhotoStation.Download", "method": "getvideo", "version": "1",
                                          "id": rid, "variant": "web"})
    check("variant=web ostava original", len(r.content) == os.path.getsize(vrot), len(r.content))
    r = call("photo.php", api="SYNO.PhotoStation.Photo", method="getinfo", version="1", id=rid, additional="video_codec")
    check("tv_version = ready", r["data"][0]["additional"]["video_codec"]["tv_version"] == "ready", r["data"][0]["additional"])
    r = c.get(W + "download.php", params={"api": "SYNO.PhotoStation.Download", "method": "getvideo", "version": "1",
                                          "id": vid, "variant": "tv"})
    check("video bez priznaku: variant=tv = ako web", b"ftypmp42" in r.content and "x-picturestation-video" not in r.headers, dict(r.headers))
    # library pass: a video indexed without the flag is probed and queued
    from picturestation import store as _store  # noqa: E402
    _store.db().execute("UPDATE meta SET data=json_remove(data, '$.rotation') WHERE path='2001/Maxim/rot.mp4'")
    if rp:
        os.remove(rp)
    tvvideo.library_pass()  # finds the video without the flag, probes it and converts it right away
    check("prechod kniznicou zaradi a prekoduje video nabok", bool(tvvideo.ready_path(fe)), tvvideo._failed)
else:
    print("OK   video nabok preskocene (bez ffmpeg)")

# --- administracia ---
def adm(op, body=None, client=None):
    cl = client or c
    if body is None:
        return cl.get("/api/admin/" + op)
    return cl.post("/api/admin/" + op, json=body)

c.cookies.clear()
call("auth.php", api="SYNO.PhotoStation.Auth", method="login", version="1", username="kolega", password="heslo5678")
check("admin API: bezny pouzivatel 403", adm("state").status_code == 403)
c.cookies.clear()
check("admin API: bez prihlasenia 401", adm("state").status_code == 401)
call("auth.php", api="SYNO.PhotoStation.Auth", method="login", version="1", username="spravca", password="heslo1234")
st = adm("state").json()
check("admin state", [u["username"] for u in st["users"]] == ["kolega", "spravca"], st)
from picturestation import __version__  # noqa: E402
check("verzia v admin state", st.get("version") == __version__ and __version__.count(".") == 2, st.get("version"))
r = c.post("/api/admin/user_create", data={"username": "x", "password": "12345678"})
check("admin POST bez JSON = 415", r.status_code == 415, r.status_code)
check("kratke heslo odmietnute", adm("user_create", {"username": "jana", "password": "kratke"}).status_code == 400)
r = c.post("/api/admin/user_create", json={"username": "jana", "password": "kratke"})
check("chyba admin API anglicky", r.json().get("error") == "Password must have at least 8 characters.", r.text)
r = c.post("/api/admin/user_create", json={"username": "jana", "password": "kratke"}, headers={"X-Lang": "sk"})
check("chyba admin API po slovensky", r.json().get("error") == "Heslo musí mať aspoň 8 znakov.", r.text)
check("user_create", adm("user_create", {"username": "jana", "password": "janaheslo1"}).status_code == 200)
check("group_create", adm("group_create", {"name": "Rodina"}).status_code == 200)
check("grant skupine", adm("grant", {"type": "group", "name": "Rodina", "path": "2001/Rodina"}).status_code == 200)
check("neexistujuci album odmietnuty", adm("grant", {"type": "user", "name": "jana", "path": "nie/je"}).status_code == 400)
check("clenstvo", adm("group_update", {"name": "Rodina", "members": ["jana"]}).status_code == 200)
check("posledny admin sa nezmaze", adm("user_update", {"username": "spravca", "admin": False}).status_code == 400)
check("sam seba nezmaze", adm("user_delete", {"username": "spravca"}).status_code == 400)
check("nazov galerie", adm("settings", {"title": "Moje fotky"}).status_code == 200)
info = call("info.php", api="SYNO.PhotoStation.Info", method="getinfo", version="1")
check("nazov sa prejavi v Info", info["data"]["title"] == "Moje fotky", info["data"]["title"])
pk = adm("albums?path=2001").json()
check("vyber albumov", pk["albums"] == ["Maxim", "Rodina"], pk)
c2 = TestClient(appmod.app)
r = json.loads(c2.post(W + "auth.php", data=dict(api="SYNO.PhotoStation.Auth", method="login", version="1",
                                                 username="jana", password="janaheslo1")).text)
check("jana login", r["success"], r)
r = json.loads(c2.post(W + "album.php", data=dict(api="SYNO.PhotoStation.Album", method="list", version="1",
                                                  id=ids.album_id("2001"), type="album,photo,video")).text)
check("jana cez skupinu vidi len Rodina", [i["info"]["name"] for i in r["data"]["items"]] == ["Rodina"], r)
adm("group_update", {"name": "Rodina", "members": []})
r = json.loads(c2.post(W + "album.php", data=dict(api="SYNO.PhotoStation.Album", method="list", version="1",
                                                  id=ids.album_id("2001/Rodina"), type="album,photo,video")).text)
check("po vyradeni zo skupiny pristup zmizne", r.get("error", {}).get("code") == 417, r)
check("user_delete", adm("user_delete", {"username": "jana"}).status_code == 200)
check("group_delete", adm("group_delete", {"name": "Rodina"}).status_code == 200)

# --- vlastnosti albumov ---
ea = os.path.join(ROOT, "2001", "@eaDir", "Maxim")
os.makedirs(ea, exist_ok=True)
open(os.path.join(ea, "SYNOPHOTO_ALBUM.cover"), "w").write("02.jpg")
from picturestation import media as _m  # noqa: E402
_m.clear_cover_cache()
r = call("album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("2001"), type="album")
mx = [i for i in r["data"]["items"] if i["info"]["name"] == "Maxim"][0]
check("povodna titulna z @eaDir", mx["additional"]["thumb_size"]["sig"] == "2001/Maxim/02.jpg".encode().hex(), mx["additional"]["thumb_size"])
check("album_set titulok", adm("album_set", {"path": "2001/Maxim", "title": "Maxim detstvo", "description": "Popis"}).status_code == 200)
g = call("album.php", api="SYNO.PhotoStation.Album", method="getinfo", version="1", id=ids.album_id("2001/Maxim"))
check("titulok a popis v getinfo", (g["data"]["items"][0]["info"]["title"], g["data"]["items"][0]["info"]["description"]) == ("Maxim detstvo", "Popis"), g)
check("cudzia titulna odmietnuta", adm("album_set", {"path": "2001/Maxim", "cover": "koren.jpg"}).status_code == 400)
check("titulna z galerie", adm("album_set", {"path": "2001/Maxim", "cover": "2001/Maxim/01.jpg"}).status_code == 200)
r = call("album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("2001"), type="album")
mx = [i for i in r["data"]["items"] if i["info"]["name"] == "Maxim"][0]
check("titulna nastavena ma prednost", mx["additional"]["thumb_size"]["sig"] == "2001/Maxim/01.jpg".encode().hex())
ag = adm("album_get?path=2001/Maxim").json()
check("album_get", ag["title"] == "Maxim detstvo" and ag["ea_cover"] == "2001/Maxim/02.jpg" and ag["users"] == ["kolega"], ag)

g1 = TestClient(appmod.app)  # host
def gcall(cl, path, **p):
    return json.loads(cl.post(W + path, data=p).text)
check("verejny", adm("album_set", {"path": "2001/Rodina", "mode": "public"}).status_code == 200)
r = gcall(g1, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", type="album,photo,video")
check("host vidi cestu k verejnemu", [i["info"]["name"] for i in r["data"]["items"]] == ["2001"], r)
r = gcall(g1, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("2001/Rodina"), type="photo")
check("host vidi verejny album", r["success"] and r["data"]["total"] == 1, r)
check("bez hesla nejde", adm("album_set", {"path": "2001/Maxim", "mode": "password"}).status_code == 400)
check("heslo albumu", adm("album_set", {"path": "2001/Maxim", "mode": "password", "password": "tajne1"}).status_code == 200)
check("verejny -> sukromny", adm("album_set", {"path": "2001/Rodina", "mode": "private"}).status_code == 200)
r = gcall(g1, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("2001"), type="album")
items = r["data"]["items"]
check("host vidi album s heslom zamknuty", [(i["info"]["name"], i["info"]["type"], i["thumbnail_status"]) for i in items] == [("Maxim", "password", "default")], items)
r = gcall(g1, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("2001/Maxim"))
check("zamknuty = 416", r.get("error", {}).get("code") == 416, r)
r = gcall(g1, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("2001/Maxim"), password="zle")
check("zle heslo = 416", r.get("error", {}).get("code") == 416, r)
r = gcall(g1, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("2001/Maxim"), password="tajne1", type="photo")
check("spravne heslo odomkne", r["success"] and r["data"]["total"] == 2 and g1.cookies.get("PHPSESSID"), r)
r = gcall(g1, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("2001/Maxim"), type="photo")
check("odomknute zostane v session", r["success"], r)
t = g1.get(W + "thumb.php", params={"api": "SYNO.PhotoStation.Thumb", "method": "get", "version": "1",
                                    "id": ids.item_id("photo", "2001/Maxim/01.jpg"), "size": "small"})
check("nahlad v odomknutom albume", t.headers["content-type"] == "image/jpeg", t.text[:80])
g2 = TestClient(appmod.app)
r = gcall(g2, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("2001/Maxim"))
check("iny navstevnik stale zamknuty", r.get("error", {}).get("code") == 416, r)
# --- obmedzenia ---
adm("album_set", {"path": "2001/Rodina", "mode": "public"})
g3 = TestClient(appmod.app)
rid = ids.item_id("photo", "2001/Rodina/a.jpg")
r = g3.get(W + "download.php", params={"api": "SYNO.PhotoStation.Download", "method": "getphoto", "version": "1", "id": rid})
check("host stiahne original (predvolene)", r.headers["content-type"] == "image/jpeg", r.text[:60])
check("vypnut stahovanie hostom", adm("settings", {"allow_download_guest": False, "hide_gps": True,
                                                   "hide_detail_guest": True, "disable_timeline": True, "disable_search": True}).status_code == 200)
r = g3.get(W + "download.php", params={"api": "SYNO.PhotoStation.Download", "method": "getphoto", "version": "1", "id": rid})
check("host nestiahne original", '"code": 507' in r.text, r.text[:60])
i = gcall(g3, "info.php", api="SYNO.PhotoStation.Info", method="getinfo", version="1")["data"]
check("info obmedzenia pre hosta", (i["allow_download_orig"], i["hide_search"], i["disable_timeline"]) == (False, True, True), i)
r = gcall(g3, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("2001/Rodina"),
          type="photo", additional="photo_exif")
ex = r["data"]["items"][0]["additional"]["photo_exif"]
check("host bez udajov z fotoaparatu", ex["camera"] == "" and ex["gps"] is None, ex)
r = gcall(g3, "photo.php", api="SYNO.PhotoStation.Photo", method="list", version="1", type="photo")
check("casova os vypnuta", r["data"]["total"] == 0, r["data"]["total"])
r = gcall(g3, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", keyword="a", type="album,photo")
check("vyhladavanie vypnute", r["data"]["total"] == 0, r["data"])
i = call("info.php", api="SYNO.PhotoStation.Info", method="getinfo", version="1")["data"]
check("admin obmedzenia nema", (i["allow_download_orig"], i["hide_search"], i["disable_timeline"]) == (True, False, False), i)
st = adm("state").json()["settings"]
check("nastavenia ulozene", st["allow_download_guest"] is False and st["hide_gps"] is True and st["allow_download_user"] is True, st)
adm("settings", {k: v for k, v in __import__("picturestation.store", fromlist=["FLAGS"]).FLAGS.items()})

# --- zdielanie odkazom ---
adm("album_set", {"path": "2001/Rodina", "mode": "private"})
r = adm("share_create", {"path": "Súkromné", "days": 30})
check("share album", r.status_code == 200, r.text)
tok = r.json()["token"]
r = adm("share_create", {"path": "2001/Maxim/01.jpg", "days": 0, "allow_download": True})
tok_p = r.json()["token"]
check("share zoznam", len(adm("share_list").json()["shares"]) == 2)
s1 = TestClient(appmod.app)
r = s1.get("/s/" + tok, follow_redirects=False)
check("kratky odkaz presmeruje", r.status_code == 302 and r.headers["location"] == "/#/share/" + tok, r.headers)
i = s1.get("/api/share/" + tok).json()
check("share info", i["kind"] == "album" and i["id"] == ids.album_id("Súkromné"), i)
check("neplatny odkaz 404", s1.get("/api/share/nieje").status_code == 404)
r = gcall(s1, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("Súkromné"))
check("bez share parametra nic", r.get("error", {}).get("code") == 417, r)
r = gcall(s1, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("Súkromné"), share=tok, type="photo")
check("so share vidi album", r["success"] and r["data"]["total"] == 1, r)
r = gcall(s1, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("2001/Maxim"), share=tok)
check("share nepusti inam", r.get("error", {}).get("code") in (416, 417), r)
sp = ids.item_id("photo", "Súkromné/tajne.jpg")
t = s1.get(W + "thumb.php", params={"api": "SYNO.PhotoStation.Thumb", "method": "get", "version": "1", "id": sp, "size": "small", "share": tok})
check("share nahlad", t.headers["content-type"] == "image/jpeg", t.text[:60])
t = s1.get(W + "download.php", params={"api": "SYNO.PhotoStation.Download", "method": "getphoto", "version": "1", "id": sp, "share": tok})
check("share bez stahovania", '"code": 507' in t.text, t.text[:60])
t = s1.get(W + "download.php", params={"api": "SYNO.PhotoStation.Download", "method": "getvideo", "version": "1", "id": sp, "share": tok})
check("fotka cez getvideo neobide zakaz", t.headers["content-type"].startswith("text/plain") and '"success": false' in t.text, t.text[:60])
p1 = ids.item_id("photo", "2001/Maxim/01.jpg")
t = s1.get(W + "download.php", params={"api": "SYNO.PhotoStation.Download", "method": "getphoto", "version": "1", "id": p1, "share": tok_p})
check("share fotky so stahovanim", t.headers["content-type"] == "image/jpeg", t.text[:60])
t = s1.get(W + "thumb.php", params={"api": "SYNO.PhotoStation.Thumb", "method": "get", "version": "1",
                                    "id": ids.item_id("photo", "2001/Maxim/02.jpg"), "size": "small", "share": tok_p})
check("share fotky nepusti susednu", '"success": false' in t.text, t.text[:60])
store_mod = __import__("picturestation.store", fromlist=["db"])
store_mod.db().execute("UPDATE shares SET expires=1 WHERE token=?", (tok,))
check("vyprsany odkaz", s1.get("/api/share/" + tok).status_code == 404)
check("share zrusenie", adm("share_delete", {"token": tok_p}).status_code == 200 and s1.get("/api/share/" + tok_p).status_code == 404)
check("koren nezdielat", adm("share_create", {"path": ""}).status_code == 400)

# --- komentare ---
pid = ids.item_id("photo", "2001/Rodina/a.jpg")
r = call("comment.php", api="SYNO.PhotoStation.Comment", method="create", version="1", id=pid, name="ignoruj",
         email="", comment="Pekná fotka")
check("admin komentuje", r["success"], r)
r = call("comment.php", api="SYNO.PhotoStation.Comment", method="list", version="1", id=pid)
cm = r["data"]["comments"]
check("zoznam komentarov, meno = prihlaseny", len(cm) == 1 and cm[0]["name"] == "spravca" and cm[0]["comment"] == "Pekná fotka", cm)
r = c.get(W + "comment.php", params={"api": "SYNO.PhotoStation.Comment", "method": "create", "version": "1",
                                     "id": pid, "comment": "cez odkaz"}).json()
check("komentar cez GET (CSRF odkazom) = 105", r.get("error", {}).get("code") == 105, r)
r = c.get(W + "auth.php", params={"api": "SYNO.PhotoStation.Auth", "method": "logout", "version": "1"}).json()
check("odhlasenie cez GET = 105", r.get("error", {}).get("code") == 105, r)
cm = call("comment.php", api="SYNO.PhotoStation.Comment", method="list", version="1", id=pid)["data"]["comments"]
check("komentar cez GET sa neulozil", len(cm) == 1, cm)
adm("album_set", {"path": "2001/Rodina", "mode": "public"})
g4 = TestClient(appmod.app)
r = gcall(g4, "comment.php", api="SYNO.PhotoStation.Comment", method="create", version="1", id=pid, name="Hosť", comment="ahoj")
check("host predvolene nekomentuje", r.get("error", {}).get("code") == 492, r)
r = gcall(g4, "comment.php", api="SYNO.PhotoStation.Comment", method="list", version="1", id=pid)
check("host komentare cita", r["success"] and len(r["data"]["comments"]) == 1, r)
adm("settings", {"allow_comment_guest": True})
r = gcall(g4, "comment.php", api="SYNO.PhotoStation.Comment", method="create", version="1", id=pid, name="", comment="ahoj")
check("host bez mena = 491", r.get("error", {}).get("code") == 491, r)
r = gcall(g4, "comment.php", api="SYNO.PhotoStation.Comment", method="create", version="1", id=pid, name="Hosť", comment="ahoj")
check("host s povolenim komentuje", r["success"], r)
r = gcall(g4, "comment.php", api="SYNO.PhotoStation.Comment", method="list", version="1",
          id=ids.item_id("photo", "Súkromné/tajne.jpg"))
check("komentare nevidno k cudzej fotke", r.get("error", {}).get("code") == 492, r)
cid = call("comment.php", api="SYNO.PhotoStation.Comment", method="list", version="1", id=pid)["data"]["comments"][-1]["id"]
check("admin zmaze komentar", adm("comment_delete", {"id": cid}).status_code == 200)
r = call("comment.php", api="SYNO.PhotoStation.Comment", method="list", version="1", id=pid)
check("po zmazani ostal 1", len(r["data"]["comments"]) == 1, r)
adm("settings", {"allow_comment_guest": False})
adm("album_set", {"path": "2001/Rodina", "mode": "private"})

# --- miesta, tagy, chytre albumy ---
gdir = os.path.join(WORK, "data", "geonames")
os.makedirs(gdir, exist_ok=True)
with open(os.path.join(gdir, "cities500.txt"), "w", encoding="utf-8") as fh:
    fh.write("3060972\tBratislava\tBratislava\t\t48.14816\t17.10674\tP\tPPLC\tSK\t\t02\t\t\t\t423737\t\t\tEurope/Bratislava\t2020-01-01\n")
    fh.write("2761369\tVienna\tVienna\t\t48.20849\t16.37208\tP\tPPLC\tAT\t\t09\t\t\t\t1691468\t\t\tEurope/Vienna\t2020-01-01\n")
with open(os.path.join(gdir, "countryInfo.txt"), "w", encoding="utf-8") as fh:
    fh.write("#ISO\tISO3\tISO-Numeric\tfips\tCountry\n")
    fh.write("SK\tSVK\t703\tLO\tSlovakia\n")
p = os.path.join(ROOT, "2001", "Maxim", "gps.jpg")
im = Image.new("RGB", (800, 600), (10, 10, 200))
ex = Image.Exif()
gi = ex.get_ifd(0x8825)
gi[1], gi[2], gi[3], gi[4] = "N", (48.0, 9.0, 0.0), "E", (17.0, 7.0, 0.0)
ex.get_ifd(0x8769)[0x9003] = "2020:06:01 12:00:00"
im.save(p, "JPEG", exif=ex.tobytes())
from picturestation import catalog as _cat  # noqa: E402
media.index_once()
_cat.invalidate()
g = call("photo.php", api="SYNO.PhotoStation.Photo", method="getinfo", version="1", id=ids.item_id("photo", "2001/Maxim/gps.jpg"))
check("miesto z GPS (anglicky predvolene)", g["data"][0]["info"].get("place") == "Bratislava, Slovakia", g["data"][0]["info"])
g = json.loads(c.post(W + "photo.php", data={"api": "SYNO.PhotoStation.Photo", "method": "getinfo", "version": "1",
                "id": ids.item_id("photo", "2001/Maxim/gps.jpg")}, headers={"X-Lang": "sk"}).text)
check("miesto z GPS po slovensky (X-Lang)", g["data"][0]["info"].get("place") == "Bratislava, Slovensko", g["data"][0]["info"])
g = json.loads(c.post(W + "photo.php", data={"api": "SYNO.PhotoStation.Photo", "method": "getinfo", "version": "1",
                "id": ids.item_id("photo", "2001/Maxim/gps.jpg")}, headers={"Accept-Language": "cs-CZ,cs;q=0.9"}).text)
check("Accept-Language cs = slovensky", g["data"][0]["info"].get("place") == "Bratislava, Slovensko", g["data"][0]["info"])
r = call("tag.php", api="SYNO.PhotoStation.Tag", method="list", version="1", type="geo")
check("zoznam miest", [(t["name"], t["info"]["count"]) for t in r["data"]["tags"]] == [("Bratislava, Slovakia", 1)], r)
geo_id = r["data"]["tags"][0]["id"]
r = call("photo.php", api="SYNO.PhotoStation.Photo", method="list", version="1", filter_tag=geo_id, type="photo,video")
check("fotky z miesta", r["data"]["total"] == 1, r["data"]["total"])
t = c.get(W + "thumb.php", params={"api": "SYNO.PhotoStation.Thumb", "method": "get", "version": "1", "id": geo_id, "size": "small"})
check("nahlad miesta", t.headers["content-type"] == "image/jpeg", t.text[:60])
check("tag pridany", adm("tag_add", {"path": "2001/Maxim/01.jpg", "name": "Rodina"}).status_code == 200)
adm("tag_add", {"path": "2001/Rodina/a.jpg", "name": "rodina"})  # rovnaky tag bez ohladu na velkost pismen
r = call("tag.php", api="SYNO.PhotoStation.Tag", method="list", version="1", type="desc")
check("zoznam tagov", [(x["name"], x["info"]["count"]) for x in r["data"]["tags"]] == [("Rodina", 2)], r)
tag_id = r["data"]["tags"][0]["id"]
g = call("photo.php", api="SYNO.PhotoStation.Photo", method="getinfo", version="1", id=ids.item_id("photo", "2001/Maxim/01.jpg"), additional="tags")
check("tagy pri fotke", g["data"][0]["info"]["tags"] == [{"id": tag_id, "name": "Rodina"}], g["data"][0]["info"])
k3 = TestClient(appmod.app)
gcall(k3, "auth.php", api="SYNO.PhotoStation.Auth", method="login", version="1", username="kolega", password="heslo5678")
r = gcall(k3, "tag.php", api="SYNO.PhotoStation.Tag", method="list", version="1", type="desc")
check("kolega vidi tag len so svojou fotkou", [(x["name"], x["info"]["count"]) for x in r["data"]["tags"]] == [("Rodina", 1)], r)
r = adm("smart_save", {"name": "Rodina 2001", "criteria": {"tags": [int(tag_id[4:])], "path": "2001"}})
check("chytry album ulozeny", r.status_code == 200, r.text)
smart_id = r.json()["id"]
check("chytry bez kriterii odmietnuty", adm("smart_save", {"name": "x", "criteria": {}}).status_code == 400)
r = call("smart_album.php", api="SYNO.PhotoStation.SmartAlbum", method="list", version="1")
check("zoznam chytrych albumov", [(x["name"], x["info"]["count"]) for x in r["data"]["smart_albums"]] == [("Rodina 2001", 2)], r)
r = call("photo.php", api="SYNO.PhotoStation.Photo", method="list", version="1", filter_smart=smart_id, type="photo,video")
check("obsah chytreho albumu", r["data"]["total"] == 2, r["data"])
r = gcall(k3, "photo.php", api="SYNO.PhotoStation.Photo", method="list", version="1", filter_smart=smart_id, type="photo,video")
check("chytry album respektuje prava", r["data"]["total"] == 1, r["data"])
g5 = TestClient(appmod.app)  # host bez prav
r = gcall(g5, "smart_album.php", api="SYNO.PhotoStation.SmartAlbum", method="list", version="1")
check("host nevidi chytre albumy bez obsahu", r["data"]["smart_albums"] == [], r)
r = gcall(g5, "smart_album.php", api="SYNO.PhotoStation.SmartAlbum", method="getinfo", version="1", id=smart_id)
check("host nevidi getinfo chytreho albumu", r["data"]["smart_albums"] == [], r)
r = gcall(g5, "tag.php", api="SYNO.PhotoStation.Tag", method="getinfo", version="1", id=tag_id)
check("host nevidi nazov tagu", r["data"]["tags"] == [], r)
r = gcall(k3, "smart_album.php", api="SYNO.PhotoStation.SmartAlbum", method="list", version="1")
check("kolega bez kriterii", r["data"]["smart_albums"] and "criteria" not in r["data"]["smart_albums"][0]["info"], r)
t = c.get(W + "thumb.php", params={"api": "SYNO.PhotoStation.Thumb", "method": "get", "version": "1", "id": smart_id, "size": "small"})
check("nahlad chytreho albumu", t.headers["content-type"] == "image/jpeg", t.text[:60])
r = adm("smart_save", {"name": "Leto 2020", "criteria": {"date_from": "2020-06-01", "date_to": "2020-08-31", "countries": ["SK"]}})
loc_id = r.json()["id"]
r = call("photo.php", api="SYNO.PhotoStation.Photo", method="list", version="1", filter_smart=loc_id, type="photo")
check("chytry podla datumu a krajiny", r["data"]["total"] == 1, r["data"])
adm("settings", {"hide_gps": True})
r = gcall(k3, "tag.php", api="SYNO.PhotoStation.Tag", method="list", version="1", type="geo")
check("skryte GPS = ziadne miesta", r["data"]["tags"] == [], r)
r = gcall(k3, "smart_album.php", api="SYNO.PhotoStation.SmartAlbum", method="list", version="1")
check("skryte GPS = bez chytrych podla polohy", all(x["id"] != loc_id for x in r["data"]["smart_albums"]), r)
r = gcall(k3, "photo.php", api="SYNO.PhotoStation.Photo", method="list", version="1", filter_smart=loc_id, type="photo")
check("skryte GPS = obsah podla krajiny prazdny", r["data"]["total"] == 0, r["data"])
t = k3.get(W + "thumb.php", params={"api": "SYNO.PhotoStation.Thumb", "method": "get", "version": "1", "id": loc_id, "size": "small"})
check("skryte GPS = bez nahladu", '"success": false' in t.text, t.text[:60])
adm("settings", {"hide_gps": False})
check("odobratie tagu", adm("tag_remove", {"path": "2001/Maxim/01.jpg", "tag": tag_id}).status_code == 200)
check("smart zmazany", adm("smart_delete", {"id": smart_id}).status_code == 200)
# --- klucove slova zo suborov (IPTC + XMP) -> tagy ---
import io as _io  # noqa: E402

def jpeg_with_keywords(path, iptc_kw, xmp_kw):
    buf = _io.BytesIO()
    Image.new("RGB", (400, 300), (120, 120, 0)).save(buf, "JPEG")
    b = buf.getvalue()
    iptc = b"".join(b"\x1c\x02\x19" + len(k.encode()).to_bytes(2, "big") + k.encode() for k in iptc_kw)
    res = b"8BIM" + b"\x04\x04" + b"\x00\x00" + len(iptc).to_bytes(4, "big") + iptc + (b"\x00" if len(iptc) % 2 else b"")
    app13 = b"Photoshop 3.0\x00" + res
    lis = "".join(f"<rdf:li>{k}</rdf:li>" for k in xmp_kw)
    xmp = ('<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
           '<rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:subject><rdf:Bag>' + lis +
           '</rdf:Bag></dc:subject></rdf:Description></rdf:RDF></x:xmpmeta>').encode()
    app1 = b"http://ns.adobe.com/xap/1.0/\x00" + xmp
    seg = lambda mk, pl: mk + (len(pl) + 2).to_bytes(2, "big") + pl
    open(path, "wb").write(b[:2] + seg(b"\xff\xe1", app1) + seg(b"\xff\xed", app13) + b[2:])

kwp = os.path.join(ROOT, "2001", "Maxim", "kw.jpg")
jpeg_with_keywords(kwp, ["Spomienka na Deda", "Best Foto"], ["best foto", "Rodinné &amp; priatelia"])
media.index_once()
_cat.invalidate()
g = call("photo.php", api="SYNO.PhotoStation.Photo", method="getinfo", version="1", id=ids.item_id("photo", "2001/Maxim/kw.jpg"), additional="tags")
names = sorted(t["name"] for t in g["data"][0]["info"]["tags"])
check("tagy z IPTC aj XMP, bez duplicit", names == ["Best Foto", "Rodinné & priatelia", "Spomienka na Deda"], names)
deda = [t for t in g["data"][0]["info"]["tags"] if t["name"] == "Spomienka na Deda"][0]["id"]
check("odobratie tagu zo suboru", adm("tag_remove", {"path": "2001/Maxim/kw.jpg", "tag": deda}).status_code == 200)
store_mod.db().execute("UPDATE meta SET data=json_set(data,'$.v',2) WHERE path='2001/Maxim/kw.jpg'")  # vynuti precitanie
media.index_once()
g = call("photo.php", api="SYNO.PhotoStation.Photo", method="getinfo", version="1", id=ids.item_id("photo", "2001/Maxim/kw.jpg"), additional="tags")
names = sorted(t["name"] for t in g["data"][0]["info"]["tags"])
check("rucne odobraty tag sa po indexe nevrati", names == ["Best Foto", "Rodinné & priatelia"], names)
check("tag rucne vrateny", adm("tag_add", {"path": "2001/Maxim/kw.jpg", "name": "Spomienka na Deda"}).status_code == 200)
jpeg_with_keywords(kwp, ["Best Foto"], [])  # klucove slova v subore sa zmenili
os.utime(kwp, (time.time() + 10, time.time() + 10))
media.index_once()
g = call("photo.php", api="SYNO.PhotoStation.Photo", method="getinfo", version="1", id=ids.item_id("photo", "2001/Maxim/kw.jpg"), additional="tags")
names = sorted(t["name"] for t in g["data"][0]["info"]["tags"])
check("zmena v subore sa prejavi, rucny tag ostane", names == ["Best Foto", "Spomienka na Deda"], names)

# --- vylucenie albumu ---
adm("user_create", {"username": "kamos", "password": "kamosheslo1"})
adm("group_create", {"name": "Kamosi"})
adm("group_update", {"name": "Kamosi", "members": ["kamos"]})
adm("grant", {"type": "group", "name": "Kamosi", "path": "2001"})
check("vylucenie ulozene", adm("grant", {"type": "group", "name": "Kamosi", "path": "2001/Maxim", "deny": True}).status_code == 200)
check("vylucit celu kniznicu nejde", adm("grant", {"type": "group", "name": "Kamosi", "path": "", "deny": True}).status_code == 400)
kg = [g for g in adm("state").json()["groups"] if g["name"] == "Kamosi"][0]["grants"]
check("state ukazuje vylucenie", kg == [{"path": "2001", "deny": False}, {"path": "2001/Maxim", "deny": True}], kg)
km = TestClient(appmod.app)
gcall(km, "auth.php", api="SYNO.PhotoStation.Auth", method="login", version="1", username="kamos", password="kamosheslo1")
r = gcall(km, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("2001"), type="album,photo,video")
check("kamos v 2001 nevidi Maxim", [i["info"]["name"] for i in r["data"]["items"]] == ["Rodina"], r["data"]["items"])
r = gcall(km, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("2001/Maxim"))
check("kamos do Maxim nevojde", r.get("error", {}).get("code") == 417, r)
r = gcall(km, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("2001/Maxim"), password="tajne1")
check("vylucenie ma prednost pred heslom", r.get("error", {}).get("code") == 417, r)
store_mod.unlock(km.cookies.get("PHPSESSID"), "2001/Maxim")  # odomknute este pred vylucenim
r = gcall(km, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("2001/Maxim"))
check("vylucenie ma prednost aj pred odomknutym", r.get("error", {}).get("code") == 417, r)
t = km.get(W + "thumb.php", params={"api": "SYNO.PhotoStation.Thumb", "method": "get", "version": "1",
                                    "id": ids.item_id("photo", "2001/Maxim/01.jpg"), "size": "small"})
check("kamos nedostane nahlad z Maxim", '"success": false' in t.text, t.text[:60])
t = km.get(W + "download.php", params={"api": "SYNO.PhotoStation.Download", "method": "getphoto", "version": "1",
                                       "id": ids.item_id("photo", "2001/Maxim/01.jpg")})
check("kamos nestiahne z Maxim", '"success": false' in t.text, t.text[:60])
r = gcall(km, "photo.php", api="SYNO.PhotoStation.Photo", method="list", version="1", type="photo,video", limit="100")
paths = [i["additional"]["file_location"] for i in r["data"]["items"]]
check("kamos casova os bez Maxim", paths and all(not p.startswith("2001/Maxim") for p in paths), paths)
r = gcall(km, "tag.php", api="SYNO.PhotoStation.Tag", method="list", version="1", type="desc")
check("kamos tagy bez Maxim", all(x["name"] != "Spomienka na Deda" for x in r["data"]["tags"]), r["data"]["tags"])
os.makedirs(os.path.join(ROOT, "2001", "Maxim", "Skola"), exist_ok=True)
photo("2001/Maxim/Skola/s.jpg")
adm("grant", {"type": "group", "name": "Kamosi", "path": "2001/Maxim/Skola"})
_m.clear_cover_cache()
r = gcall(km, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("2001"), type="album")
check("hlbsie povolenie: Maxim ako cesta", [(i["info"]["name"], i["additional"]["album_permission"]["browse"]) for i in r["data"]["items"]]
      == [("Maxim", False), ("Rodina", True)], r["data"]["items"])
r = gcall(km, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("2001/Maxim"), type="album,photo")
check("v Maxim len Skola, bez fotiek", [i["info"]["name"] for i in r["data"]["items"]] == ["Skola"], r["data"]["items"])
adm("grant", {"type": "user", "name": "kamos", "path": "2001/Maxim"})
r = gcall(km, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("2001/Maxim"), type="photo")
check("vlastne povolenie prebije vylucenie skupiny", r["success"] and r["data"]["total"] >= 2, r)
adm("revoke", {"type": "user", "name": "kamos", "path": "2001/Maxim"})
tk = adm("share_create", {"path": "2001/Maxim"}).json()["token"]
r = gcall(km, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("2001/Maxim"), share=tk, type="photo")
check("zdielany odkaz plati aj pre vylucene", r["success"] and r["data"]["total"] >= 2, r)
av = adm("access_view", {"type": "user", "name": "kamos", "path": "2001"}).json()
st_ = {a["name"]: (a["rule"], a["effective"]) for a in av["albums"]}
check("editor: vysledok pre clena skupiny", av["self"]["effective"] == "yes" and st_ == {"Maxim": (None, "path"), "Rodina": (None, "yes")}, av)
check("editor: odkial pravo", (av["self"]["via"] or {}).get("groups") == ["Kamosi"], av["self"])
av = adm("access_view", {"type": "group", "name": "Kamosi", "path": "2001"}).json()
st_ = {a["name"]: (a["rule"], a["effective"]) for a in av["albums"]}
check("editor: pravidla skupiny", av["self"]["rule"] == "allow" and st_["Maxim"] == ("deny", "path"), av)
aa = {(p["type"], p["name"]): (p["rule"], p["effective"]) for p in adm("album_access", {"path": "2001/Rodina"}).json()["principals"]}
check("pristup z pohladu albumu", aa.get(("group", "Kamosi")) == (None, "yes") and aa.get(("user", "kamos")) == (None, "yes")
      and aa.get(("guest", "")) == (None, "no") and ("user", "spravca") not in aa, aa)
adm("grant", {"type": "user", "name": "kamos", "path": "2001/Rodina", "deny": True})
aa = {p["name"]: p for p in adm("album_access", {"path": "2001/Rodina"}).json()["principals"]}
check("vylucenie pouzivatela z albumu", (aa["kamos"]["rule"], aa["kamos"]["effective"]) == ("deny", "no"), aa["kamos"])
adm("revoke", {"type": "user", "name": "kamos", "path": "2001/Rodina"})
aa = {p["name"]: p for p in adm("album_access", {"path": "2001/Rodina"}).json()["principals"]}
check("odkial pravo: konkretna skupina", aa["kamos"]["via"] == {"deny": False, "path": "2001", "groups": ["Kamosi"]}, aa["kamos"])
check("zly tvar poziadavky = 400", adm("revoke", {"type": "group", "name": "Kamosi", "path": {"path": "x"}}).status_code == 400)
check("zrusenie vylucenia", adm("revoke", {"type": "group", "name": "Kamosi", "path": "2001/Maxim"}).status_code == 200)
r = gcall(km, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("2001/Maxim"), type="photo")
check("po zruseni vylucenia vidi Maxim", r["success"], r)
adm("user_delete", {"username": "kamos"}); adm("group_delete", {"name": "Kamosi"})

# --- zoradenie albumov ---
for n in ("1999", "2020", "Auto"):
    os.makedirs(os.path.join(ROOT, n), exist_ok=True)
    photo(n + "/x.jpg")
_m._dir_cache.clear()
r = call("album.php", api="SYNO.PhotoStation.Album", method="list", version="1", type="album,photo")
check("koren predvolene A-Z", [i["info"]["name"] for i in r["data"]["items"]][:5] == ["1999", "2001", "2020", "Auto", "Súkromné"],
      [i["info"]["name"] for i in r["data"]["items"]])
adm("settings", {"root_album_order": "desc"})
r = call("album.php", api="SYNO.PhotoStation.Album", method="list", version="1", type="album,photo")
names = [i["info"]["name"] for i in r["data"]["items"]]
check("koren od najnovsich, ostatne za nimi, subory na konci", names == ["2020", "2001", "1999", "Auto", "Súkromné", "koren.jpg"], names)
adm("album_set", {"path": "2001", "album_order": "desc"})
r = call("album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("2001"), type="album")
check("podalbumy podla nastavenia albumu", [i["info"]["name"] for i in r["data"]["items"]] == ["Maxim", "Rodina"], r["data"]["items"])
check("album_get vrati zoradenie", adm("album_get?path=2001").json()["album_order"] == "desc")
adm("album_set", {"path": "2001", "album_order": "asc"})
adm("settings", {"root_album_order": "asc"})

# --- presun albumov na konci roka (koren -> 2026/) ---
photo("2026-08-08 Svadba/a.jpg", color=(1, 2, 3))
photo("2026-08-08 Svadba/b.jpg", size=(1000, 800))
photo("2026-08-09 Vylet/c.jpg", size=(1200, 900))
photo("2026/2026-01-01 Novy rok/d.jpg", size=(900, 700))
photo("Archiv-stary/Leto/e.jpg", size=(640, 480))
photo("Archiv-stary/Zima/f.jpg", size=(700, 500))
adm("user_create", {"username": "kamos2", "password": "kamosheslo2"})
adm("group_create", {"name": "Kamosi2"})
adm("group_update", {"name": "Kamosi2", "members": ["kamos2"]})
adm("grant", {"type": "group", "name": "Kamosi2", "path": "2026"})
adm("grant", {"type": "group", "name": "Kamosi2", "path": "2026-08-09 Vylet"})
adm("grant", {"type": "group", "name": "Kamosi2", "path": "2026-08-08 Svadba", "deny": True})
adm("grant", {"type": "group", "name": "Kamosi2", "path": "Archiv-stary"})
adm("album_set", {"path": "2026-08-08 Svadba", "title": "Svadba Peťa", "cover": "2026-08-08 Svadba/b.jpg"})
adm("tag_add", {"path": "2026-08-08 Svadba/a.jpg", "name": "Svadby"})
call("comment.php", api="SYNO.PhotoStation.Comment", method="create", version="1", id=ids.item_id("photo", "2026-08-08 Svadba/b.jpg"), comment="krasne")
tok_sv = adm("share_create", {"path": "2026-08-08 Svadba"}).json()["token"]
sm = adm("smart_save", {"name": "Svadba album", "criteria": {"path": "2026-08-08 Svadba"}}).json()["id"]
media.index_once()
os.makedirs(os.path.join(ROOT, "2026"), exist_ok=True)
os.rename(os.path.join(ROOT, "2026-08-08 Svadba"), os.path.join(ROOT, "2026", "2026-08-08 Svadba"))
os.rename(os.path.join(ROOT, "2026-08-09 Vylet"), os.path.join(ROOT, "2026", "2026-08-09 Vylet"))
os.makedirs(os.path.join(ROOT, "Archiv"), exist_ok=True)
os.rename(os.path.join(ROOT, "Archiv-stary"), os.path.join(ROOT, "Archiv", "Archiv-stary"))
_m._dir_cache.clear(); _m.clear_cover_cache()
store_mod._exists_cache.clear()
km2 = TestClient(appmod.app)
gcall(km2, "auth.php", api="SYNO.PhotoStation.Auth", method="login", version="1", username="kamos2", password="kamosheslo2")
r = gcall(km2, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("2026"), type="album")
check("pred indexom: vylucena Svadba ostane skryta aj na novom mieste",
      [i["info"]["name"] for i in r["data"]["items"]] == ["2026-01-01 Novy rok", "2026-08-09 Vylet"], r["data"]["items"])
t = km2.get(W + "thumb.php", params={"api": "SYNO.PhotoStation.Thumb", "method": "get", "version": "1",
                                     "id": ids.item_id("photo", "2026/2026-08-08 Svadba/a.jpg"), "size": "small"})
check("pred indexom: ani nahlad zo Svadby", '"success": false' in t.text, t.text[:60])
media.index_once()
_cat.invalidate()
ms = adm("moves_state").json()
pairs = {(m["old"], m["new"]) for m in ms["history"]}
check("presuny rozpoznane", {("2026-08-08 Svadba", "2026/2026-08-08 Svadba"), ("2026-08-09 Vylet", "2026/2026-08-09 Vylet"),
                             ("Archiv-stary", "Archiv/Archiv-stary")} <= pairs, pairs)
kg = {g["path"]: g["deny"] for g in [g for g in adm("state").json()["groups"] if g["name"] == "Kamosi2"][0]["grants"]}
check("pravidla prenesene", kg == {"2026": False, "2026/2026-08-09 Vylet": False, "2026/2026-08-08 Svadba": True,
                                   "Archiv/Archiv-stary": False}, kg)
ag = adm("album_get?path=2026/2026-08-08 Svadba").json()
check("titulok a titulna fotka prenesene", ag["title"] == "Svadba Peťa" and ag["cover"] == "2026/2026-08-08 Svadba/b.jpg", ag)
g = call("photo.php", api="SYNO.PhotoStation.Photo", method="getinfo", version="1", id=ids.item_id("photo", "2026/2026-08-08 Svadba/a.jpg"), additional="tags")
check("rucny tag prenesený", [t["name"] for t in g["data"][0]["info"]["tags"]] == ["Svadby"], g["data"][0]["info"])
r = call("comment.php", api="SYNO.PhotoStation.Comment", method="list", version="1", id=ids.item_id("photo", "2026/2026-08-08 Svadba/b.jpg"))
check("komentar preneseny", [c["comment"] for c in r["data"]["comments"]] == ["krasne"], r)
check("odkaz funguje na novom mieste", TestClient(appmod.app).get("/api/share/" + tok_sv).json()["id"] == ids.album_id("2026/2026-08-08 Svadba"))
r = call("photo.php", api="SYNO.PhotoStation.Photo", method="list", version="1", filter_smart=sm, type="photo")
check("chytry album s cestou funguje", r["data"]["total"] == 2, r["data"])
r = call("photo.php", api="SYNO.PhotoStation.Photo", method="list", version="1", type="photo", limit="500")
locs = [i["additional"]["file_location"] for i in r["data"]["items"]]
check("casova os bez duplicit a starych ciest", len(locs) == len(set(locs)) and not any(l.startswith("2026-08") for l in locs), locs)
r = gcall(km2, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("2026"), type="album")
check("po indexe kamos vidi to iste", [i["info"]["name"] for i in r["data"]["items"]] == ["2026-01-01 Novy rok", "2026-08-09 Vylet"], r["data"]["items"])
check("ziadne osirele nastavenia", adm("moves_state").json()["orphans"] == [], adm("moves_state").json()["orphans"])
# rucny presun a mazanie osireleho
adm("grant", {"type": "group", "name": "Kamosi2", "path": "2026"})
store_mod.db().execute("INSERT INTO access(username, path, deny) VALUES ('#Kamosi2', 'Zmiznuty/Album', 1)")
o = adm("moves_state").json()["orphans"]
check("osirela cesta v prehlade", [x["path"] for x in o] == ["Zmiznuty/Album"], o)
check("rucny presun osirelej cesty", adm("moves_remap", {"old": "Zmiznuty/Album", "new": "2026/2026-01-01 Novy rok"}).status_code == 200)
kg = {g["path"]: g["deny"] for g in [g for g in adm("state").json()["groups"] if g["name"] == "Kamosi2"][0]["grants"]}
check("rucne prenesene pravidlo", kg.get("2026/2026-01-01 Novy rok") is True, kg)
store_mod.db().execute("INSERT INTO access(username, path, deny) VALUES ('#Kamosi2', 'Iny/Zmiznuty', 0)")
check("zmazanie osireleho", adm("orphan_delete", {"path": "Iny/Zmiznuty"}).status_code == 200 and adm("moves_state").json()["orphans"] == [])
adm("user_delete", {"username": "kamos2"}); adm("group_delete", {"name": "Kamosi2"})

# --- ludia zo Synology Photos ---
sdb = store_mod.db()
sdb.execute("DELETE FROM people"); sdb.execute("DELETE FROM people_items")
sdb.execute("INSERT INTO people(id, name, face_key, cover_path) VALUES (2610, 'Jana', 'k1', '2001/Rodina/a.jpg'), "
            "(99, 'Neviditelny', NULL, NULL)")
from picturestation import synosync as _ss  # noqa: E402
os.makedirs(_ss.FACE_DIR, exist_ok=True)
open(_ss.face_path(2610), "wb").write(b"\xff\xd8FACE")
sdb.executemany("INSERT INTO people_items VALUES (?,?)", [(2610, "2001/Maxim/01.jpg"), (2610, "2001/Rodina/a.jpg"),
                                                          (99, "Súkromné/tajne.jpg")])
_cat.invalidate()
r = call("tag.php", api="SYNO.PhotoStation.Tag", method="list", version="1", type="people")
check("admin vidi ludi", [(x["name"], x["info"]["count"]) for x in r["data"]["tags"]] == [("Jana", 2), ("Neviditelny", 1)], r)
r = call("photo.php", api="SYNO.PhotoStation.Photo", method="list", version="1", filter_tag="tag_p2610", type="photo")
check("fotky osoby", sorted(i["additional"]["file_location"] for i in r["data"]["items"]) == ["2001/Maxim/01.jpg", "2001/Rodina/a.jpg"], r["data"])
g = call("photo.php", api="SYNO.PhotoStation.Photo", method="getinfo", version="1", id=ids.item_id("photo", "2001/Maxim/01.jpg"), additional="tags")
check("ludia pri fotke", g["data"][0]["info"]["people"] == [{"id": "tag_p2610", "name": "Jana"}], g["data"][0]["info"])
t = c.get(W + "thumb.php", params={"api": "SYNO.PhotoStation.Thumb", "method": "get", "version": "1", "id": "tag_p2610", "size": "small"})
check("admin dostane vyrez tvare", t.content == b"\xff\xd8FACE", t.content[:20])
t = k3.get(W + "thumb.php", params={"api": "SYNO.PhotoStation.Thumb", "method": "get", "version": "1", "id": "tag_p2610", "size": "small"})
check("kolega bez pristupu k zdrojovej fotke dostane inu fotku", t.headers["content-type"] == "image/jpeg" and t.content != b"\xff\xd8FACE", t.content[:20])
r = gcall(k3, "tag.php", api="SYNO.PhotoStation.Tag", method="list", version="1", type="people")
check("kolega vidi len ludi na svojich fotkach", [(x["name"], x["info"]["count"]) for x in r["data"]["tags"]] == [("Jana", 1)], r)
adm("album_set", {"path": "2001/Rodina", "mode": "public"})
g7 = TestClient(appmod.app)
r = gcall(g7, "tag.php", api="SYNO.PhotoStation.Tag", method="list", version="1", type="people")
check("host predvolene mena nevidi", r["data"]["tags"] == [], r)
g = gcall(g7, "photo.php", api="SYNO.PhotoStation.Photo", method="getinfo", version="1", id=ids.item_id("photo", "2001/Rodina/a.jpg"), additional="tags")
check("host nevidi ludi pri fotke", "people" not in g["data"][0]["info"], g["data"][0]["info"])
adm("settings", {"people_for_guest": True})
r = gcall(g7, "tag.php", api="SYNO.PhotoStation.Tag", method="list", version="1", type="people")
check("host s povolenim vidi", [(x["name"], x["info"]["count"]) for x in r["data"]["tags"]] == [("Jana", 1)], r)
adm("settings", {"people_for_guest": False})
adm("album_set", {"path": "2001/Rodina", "mode": "private"})
from picturestation import synosync  # noqa: E402
check("preberanie bez nastavenia vypnute", synosync.enabled() is False)

# --- titulna fotka nadradeneho albumu z podalbumu ---
check("titulna pre nadradeny album", adm("album_set", {"path": "2001", "cover": "2001/Rodina/a.jpg"}).status_code == 200)
r = call("album.php", api="SYNO.PhotoStation.Album", method="list", version="1", type="album")
y = [i for i in r["data"]["items"] if i["info"]["name"] == "2001"][0]
check("rok ma titulnu z podalbumu", y["additional"]["thumb_size"]["sig"] == "2001/Rodina/a.jpg".encode().hex(), y["additional"]["thumb_size"])
adm("album_set", {"path": "2001", "cover": ""})

# --- titulna fotka z appky (Cover set) ---
r = call("cover.php", api="SYNO.PhotoStation.Cover", method="set", version="1", id=ids.album_id("2001/Maxim"),
         item_id=ids.item_id("photo", "2001/Maxim/02.jpg"))
check("appka nastavi titulnu", r["success"], r)
check("titulna ulozena", adm("album_get?path=2001/Maxim").json()["cover"] == "2001/Maxim/02.jpg")
r = call("cover.php", api="SYNO.PhotoStation.Cover", method="set", version="1", id=ids.album_id("2001/Maxim"),
         item_id=ids.item_id("photo", "koren.jpg"))
check("cudzia fotka ako titulna = 529", r.get("error", {}).get("code") == 529, r)
r = gcall(k3, "cover.php", api="SYNO.PhotoStation.Cover", method="set", version="1", id=ids.album_id("2001/Maxim"),
          item_id=ids.item_id("photo", "2001/Maxim/01.jpg"))
check("bezny pouzivatel titulnu nemeni", r.get("error", {}).get("code") == 526, r)

# --- verejne len subory v koreni ---
adm("album_set", {"path": "2001/Maxim", "mode": "private"})  # album s heslom by hostovi ukazal cestu 2001
adm("settings", {"root_files_public": True})
g6 = TestClient(appmod.app)
r = gcall(g6, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", type="album,photo,video")
check("host vidi len subor v koreni", [i["info"]["name"] for i in r["data"]["items"]] == ["koren.jpg"], r["data"]["items"])
r = gcall(g6, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=ids.album_id("2001"), type="album,photo")
check("albumy ostavaju neverejne", r.get("error", {}).get("code") == 417, r)
t = g6.get(W + "download.php", params={"api": "SYNO.PhotoStation.Download", "method": "getphoto", "version": "1",
                                       "id": ids.item_id("photo", "koren.jpg")})
check("host stiahne subor z korena", t.headers["content-type"] == "image/jpeg", t.text[:60])
r = gcall(g6, "photo.php", api="SYNO.PhotoStation.Photo", method="list", version="1", type="photo,video")
check("casova os hosta len koren", [i["info"]["name"] for i in r["data"]["items"]] == ["koren.jpg"], r["data"]["items"])
adm("settings", {"root_files_public": False})
r = gcall(g6, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1", type="album,photo,video")
check("po vypnuti host nevidi nic", r["data"]["items"] == [], r["data"]["items"])

i = call("info.php", api="SYNO.PhotoStation.Info", method="getinfo", version="1")["data"]
check("appka: virtualne tagy zapnute", i["virtual_tag"] == {"people_tag": True, "geo_tag": True, "desc_tag": True}, i["virtual_tag"])

# --- male obce z uplneho zoznamu krajiny (SK.txt): blizsia dedina vyhra, mestska cast (PPLX) sa ignoruje ---
from picturestation import geo as _geo  # noqa: E402
with open(os.path.join(gdir, "SK.txt"), "w", encoding="utf-8") as fh:
    # osada Malovo patri pod obec Velka Obec (ADM3 s rovnakymi kodmi admin1/2/3)
    fh.write("1\tMalovo\tMalovo\t\t48.1500\t17.1170\tP\tPPL\tSK\t\t02\t102\t529001\t\t120\t\t\tEurope/Bratislava\t2020-01-01\n")
    fh.write("2\tCastovo\tCastovo\t\t48.1500\t17.1167\tP\tPPLX\tSK\t\t02\t102\t529001\t\t9000\t\t\tEurope/Bratislava\t2020-01-01\n")
    fh.write("3\tBratislava\tBratislava\t\t48.14816\t17.10674\tP\tPPLC\tSK\t\t02\t101\t\t\t423737\t\t\tEurope/Bratislava\t2020-01-01\n")
    fh.write("4\tVelka Obec\tVelka Obec\t\t48.2000\t17.2000\tA\tADM3\tSK\t\t02\t102\t529001\t\t900\t\t\tEurope/Bratislava\t2020-01-01\n")
_geo._grid = None
media.index_once()
_cat.invalidate()
g = call("photo.php", api="SYNO.PhotoStation.Photo", method="getinfo", version="1", id=ids.item_id("photo", "2001/Maxim/gps.jpg"))
check("osada z SK.txt sa ukaze ako jej obec", g["data"][0]["info"].get("place") == "Velka Obec, Slovakia", g["data"][0]["info"])
check("prepocet miest len raz na verziu dat", media.refresh_places() == 0)

# --- zapamatane titulky zbierok su oddelene podla prav ---
c.cookies.clear()
call("auth.php", api="SYNO.PhotoStation.Auth", method="login", version="1", username="spravca", password="heslo1234")
adm("tag_add", {"path": "Súkromné/tajne.jpg", "name": "tajny-titulka"})
adm_perm = store_mod.perm_for("spravca", None)
kol_perm = store_mod.perm_for("kolega", None)
tid = [t[0] for t in _cat.list_tags(adm_perm) if t[1] == "tajny-titulka"]
check("titulka tagu pre admina", tid and _cat.cover_for(tid[0], adm_perm) == "Súkromné/tajne.jpg", tid)
check("zapamatana titulka admina sa k inemu nedostane", tid and _cat.cover_for(tid[0], kol_perm) is None)

# --- exiftool parser: rovnaky vystup ako Pillow (overene na JPG; v produkcii sluzi pre HEIC/RAW) ---
from picturestation import media as _m2  # noqa: E402
_gp = os.path.join(ROOT, "2001", "Maxim", "gps.jpg")
if _m2.EXIFTOOL and os.path.isfile(_gp):
    em, pm = _m2._exiftool_meta(_gp), _m2._exif_photo(_gp)
    check("exiftool: rozmer ako Pillow", em["w"] == pm["w"] and em["h"] == pm["h"] and em["w"] > 0, (em, pm))
    check("exiftool: datum ako Pillow", em.get("taken") == pm.get("taken"), (em.get("taken"), pm.get("taken")))
    check("exiftool: GPS ako Pillow", bool(em.get("gps")) and abs(em["gps"]["lat"] - pm["gps"]["lat"]) < 1e-4
          and abs(em["gps"]["lng"] - pm["gps"]["lng"]) < 1e-4, (em.get("gps"), pm.get("gps")))
else:
    print("OK   exiftool test preskoceny (exiftool nie je / subor chyba)")

# ================= Live Photos: fotka + kratke .MOV s rovnakym menom = jedna polozka =================
import subprocess  # noqa: E402
from picturestation import catalog as _cat, media as _lm, store as _ls  # noqa: E402


def mov(rel, secs):
    p = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    subprocess.run([_lm.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=duration={secs}:size=160x120:rate=10",
                    "-c:v", "mpeg4", p], check=True)


if _lm.FFMPEG and _lm.FFPROBE:
    photo("2002/Live/IMG_1.jpg", exif_date="2002:06:01 10:00:00")
    mov("2002/Live/IMG_1.MOV", 2)            # Live Photo
    photo("2002/Live/IMG_2.jpg", exif_date="2002:06:02 10:00:00")
    mov("2002/Live/IMG_2.MOV", 8)            # dlhe video s rovnakym menom = samostatne
    mov("2002/Live/Klip.MOV", 2)             # kratke video bez fotky = samostatne
    _lm.index_once()
    c.cookies.clear()
    call("auth.php", api="SYNO.PhotoStation.Auth", method="login", version="1", username="spravca", password="heslo1234")
    LIVE_MOV = ids.item_id("video", "2002/Live/IMG_1.MOV")

    def live_album():
        r = call("album.php", api="SYNO.PhotoStation.Album", method="list", version="1",
                 id=ids.album_id("2002/Live"), type="photo,video", additional="thumb_size")
        return {i["info"]["name"]: i for i in r["data"]["items"]}

    la = live_album()
    check("live: album bez videa z paru", sorted(la) == sorted(["IMG_1.jpg", "IMG_2.jpg", "IMG_2.MOV", "Klip.MOV"]), sorted(la))
    check("live: fotka ma id pohybu", la["IMG_1.jpg"]["info"].get("live") == LIVE_MOV, la["IMG_1.jpg"]["info"])
    check("live: fotka bez paru nema live", "live" not in la["IMG_2.jpg"]["info"], la["IMG_2.jpg"]["info"])
    tl = call("photo.php", api="SYNO.PhotoStation.Photo", method="list", version="1", type="photo,video", limit="5000")
    names = [i["additional"]["file_location"] for i in tl["data"]["items"]]
    check("live: casova os bez videa z paru", "2002/Live/IMG_1.MOV" not in names and "2002/Live/IMG_2.MOV" in names)
    adm("settings", {"disable_search": False, "disable_timeline": False})
    sr = call("album.php", api="SYNO.PhotoStation.Album", method="list", version="1", recursive="true",
              keyword="img_1", type="photo,video")
    sn = [i["info"]["name"] for i in sr["data"].get("items", [])]
    check("live: vyhladavanie bez videa z paru", "IMG_1.MOV" not in sn and "IMG_1.jpg" in sn, sr)
    check("live: pocet v snapshote", not any(r[0] == "2002/Live/IMG_1.MOV" for r in _cat.snapshot()))
    dv = c.get(W + "download.php", params={"api": "SYNO.PhotoStation.Download", "method": "getvideo", "version": "1",
                                           "id": LIVE_MOV})
    check("live: pohyb sa da prehrat", dv.status_code == 200 and dv.content[4:8] == b"ftyp", dv.status_code)

    # zdielanie jednej fotky: pohyb ide s nou, ine video v priecinku nie
    tokl = adm("share_create", {"path": "2002/Live/IMG_1.jpg", "days": 1}).json()["token"]
    spl = TestClient(appmod.app)
    dv = spl.get(W + "download.php", params={"api": "SYNO.PhotoStation.Download", "method": "getvideo", "version": "1",
                                             "id": LIVE_MOV, "share": tokl})
    check("live: zdielana fotka pusti svoj pohyb", dv.status_code == 200 and dv.content[4:8] == b"ftyp", dv.text[:80])
    dv = gcall(spl, "download.php", api="SYNO.PhotoStation.Download", method="getvideo", version="1",
               id=ids.item_id("video", "2002/Live/IMG_2.MOV"), share=tokl)
    check("live: zdielana fotka nepusti ine video", dv.get("success") is False, dv)
    adm("share_delete", {"token": tokl})

    # vypnute v nastaveniach: video je zase samostatna polozka
    adm("settings", {"live_photos": False})
    la = live_album()
    check("live vypnute: video z paru viditelne", "IMG_1.MOV" in la and "live" not in la["IMG_1.jpg"]["info"], sorted(la))
    adm("settings", {"live_photos": True})
    check("live zapnute znova", "IMG_1.MOV" not in live_album())
    check("live: predvolene zapnute", _ls.FLAGS["live_photos"] is True)
else:
    print("OK   Live Photos test preskoceny (bez ffmpeg/ffprobe)")

# ================= Povolit vsetko vnutri: zrusi vlastne pravidla v podalbumoch =================
c.cookies.clear()
call("auth.php", api="SYNO.PhotoStation.Auth", method="login", version="1", username="spravca", password="heslo1234")
adm("user_create", {"username": "zuza", "password": "zuzaheslo1"})
adm("group_create", {"name": "ZuzaSkup"})
adm("group_update", {"name": "ZuzaSkup", "members": ["zuza"]})
adm("grant", {"type": "user", "name": "zuza", "path": "2001"})
adm("grant", {"type": "user", "name": "zuza", "path": "2001/Maxim", "deny": True})
adm("grant", {"type": "user", "name": "zuza", "path": "2001/Rodina", "deny": True})
adm("grant", {"type": "user", "name": "zuza", "path": "Súkromné"})
adm("grant", {"type": "group", "name": "ZuzaSkup", "path": "2001/Maxim", "deny": True})
adm("grant", {"type": "user", "name": "kolega", "path": "2001/Rodina", "deny": True})
av = adm("access_view", {"type": "user", "name": "zuza", "path": ""}).json()
check("below: koren vidi 4 vlastne pravidla nizsie",
      av["self"]["below"] == ["2001", "2001/Maxim", "2001/Rodina", "Súkromné"], av["self"])
av = adm("access_view", {"type": "user", "name": "zuza", "path": "2001"}).json()
check("below: 2001 vidi 2 vylucenia pod sebou", av["self"]["below"] == ["2001/Maxim", "2001/Rodina"], av["self"])
r = adm("grant", {"type": "user", "name": "zuza", "path": "2001", "clear_below": True})
check("povolit vsetko vnutri: zrusene 2", r.status_code == 200 and r.json().get("removed") == 2, r.text)
from picturestation import store as _zs  # noqa: E402
own = {r["path"]: r["deny"] for r in _zs.db().execute("SELECT path, deny FROM access WHERE username='zuza'")}
check("zuza: ostalo povolenie 2001 a Súkromné", own == {"2001": 0, "Súkromné": 0}, own)
grp = {r["path"]: r["deny"] for r in _zs.db().execute("SELECT path, deny FROM access WHERE username=?", (_zs.GROUP_PREFIX + "ZuzaSkup",))}
check("skupina: vylucenie nedotknute", grp == {"2001/Maxim": 1}, grp)
kol = _zs.db().execute("SELECT deny FROM access WHERE username='kolega' AND path='2001/Rodina'").fetchone()
check("iny pouzivatel: pravidlo nedotknute", kol is not None and kol["deny"] == 1)
av = adm("access_view", {"type": "user", "name": "zuza", "path": "2001"}).json()
eff = {a["name"]: a["effective"] for a in av["albums"]}
check("zuza vidi Rodinu, Maxima nie (skupina)", eff.get("Rodina") == "yes" and eff.get("Maxim") != "yes", eff)
r = adm("grant", {"type": "user", "name": "zuza", "path": "", "clear_below": True})
own = {r["path"]: r["deny"] for r in _zs.db().execute("SELECT path, deny FROM access WHERE username='zuza'")}
check("povolit celu kniznicu: ostane len koren", r.json().get("removed") == 2 and own == {"": 0}, (r.text, own))
r = adm("grant", {"type": "user", "name": "zuza", "path": "2001/Maxim", "deny": True, "clear_below": True})
check("vylucenie s clear_below nic nemaze", r.json().get("removed") == 0, r.text)
adm("revoke", {"type": "user", "name": "kolega", "path": "2001/Rodina"})

# ================= bezpecnostne regresie (audit 2026-10) =================
from picturestation import store as _sec_store  # noqa: E402

# 1) Vnorene heslo / zdielanie nesmie obist blizsi album s heslom (_pw_ok)
pm = _sec_store.Perm("hostX", False, [])
pm.pw_albums = {"A", "A/B"}
pm.unlocked = {"A"}
check("odomknutie A pusti A", pm.can_browse("A"))
check("odomknutie A pusti nechranene A/x", pm.can_browse("A/x"))
check("odomknutie A NEodomkne vnorene heslo A/B", not pm.can_browse("A/B"))
pm.unlocked = {"A", "A/B"}
check("odomknutie oboch pusti A/B", pm.can_browse("A/B"))
pf = _sec_store.Perm("hostY", False, [])
pf.pw_albums = {"A", "A/B"}
pf.forced = {"A"}
check("share nad A NEobide heslo A/B", not pf.can_browse("A/B"))
check("share nad A pusti nechranene A/x", pf.can_browse("A/x"))
pf.forced = {"A/B"}
check("share priamo na A/B pusti A/B", pf.can_browse("A/B"))

# 2) cez API: share nad rodicom neukaze album s heslom pod nim, nechraneny ano
c.cookies.clear()
call("auth.php", api="SYNO.PhotoStation.Auth", method="login", version="1", username="spravca", password="heslo1234")
adm("album_set", {"path": "2001/Maxim", "mode": "password", "password": "secpw123"})  # cisty stav pre tento test
adm("album_set", {"path": "2001/Rodina", "mode": "private"})
rs = adm("share_create", {"path": "2001", "days": 30})
tok2 = rs.json()["token"]
sp2 = TestClient(appmod.app)
rr = gcall(sp2, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1",
           id=ids.album_id("2001/Maxim"), share=tok2, type="photo")
check("share rodica: album s heslom ostane zamknuty", rr.get("error", {}).get("code") in (416, 417), rr)
rr = gcall(sp2, "album.php", api="SYNO.PhotoStation.Album", method="list", version="1",
           id=ids.album_id("2001/Rodina"), share=tok2, type="photo")
check("share rodica: nechraneny podalbum viditelny", rr.get("success") is True, rr)
adm("share_delete", {"token": tok2})

# 3) NUL / riadiace znaky v ceste
try:
    ids.clean_rel("a\x00b")
    check("NUL v ceste odmietnuty", False)
except ids.BadId:
    check("NUL v ceste odmietnuty", True)

# 4) Secure cookie podla X-Forwarded-Proto
c3 = TestClient(appmod.app)
r = c3.post(W + "auth.php", data={"api": "SYNO.PhotoStation.Auth", "method": "login", "version": "1",
                                  "username": "spravca", "password": "heslo1234"},
            headers={"X-Forwarded-Proto": "https"})
ck = " ".join(r.headers.get_list("set-cookie")).lower()
check("HTTPS -> cookie ma Secure", "secure" in ck, ck[:120])
c4 = TestClient(appmod.app)
r = c4.post(W + "auth.php", data={"api": "SYNO.PhotoStation.Auth", "method": "login", "version": "1",
                                  "username": "spravca", "password": "heslo1234"})
ck = " ".join(r.headers.get_list("set-cookie")).lower()
check("HTTP -> cookie bez Secure", "secure" not in ck, ck[:120])

# 5) @eaDir symlink mimo korena sa neservuje (len na systeme so symlinkami)
import os as _os  # noqa: E402
secret = _os.path.join(WORK, "unikat.txt")
open(secret, "w").write("LEAK_SECRET_XYZ_UNIKATNY_RETAZEC")
photo("2001/Leak/pic.jpg", color=(123, 45, 67))
ea = _os.path.join(ROOT, "2001", "Leak", "@eaDir", "pic.jpg")
_os.makedirs(ea, exist_ok=True)
link = _os.path.join(ea, "SYNOPHOTO_THUMB_M.jpg")
try:
    _os.symlink(secret, link)
    _os.utime(link, (9e9, 9e9), follow_symlinks=False) if False else None
    import time as _t  # noqa: E402
    _os.utime(secret, (_t.time() + 1000, _t.time() + 1000))
    have_symlink = True
except (OSError, NotImplementedError):
    have_symlink = False
if have_symlink:
    from picturestation import media as _media  # noqa: E402
    _media._dir_cache.clear()
    tt = c.get(W + "thumb.php", params={"api": "SYNO.PhotoStation.Thumb", "method": "get", "version": "1",
                                        "id": ids.item_id("photo", "2001/Leak/pic.jpg"), "size": "small"})
    leaked = b"LEAK_SECRET_XYZ" in tt.content
    check("@eaDir symlink mimo korena sa neservuje", not leaked, ("uniklo!" if leaked else "ok"))
else:
    print("OK   @eaDir symlink test preskoceny (bez podpory symlinkov)")

# --- LG TV app (LGTV/): CORS bez credentials, session ako appka DS photo ---
r = c.options(W + "query.php", headers={"Origin": "null", "Access-Control-Request-Method": "POST",
                                        "Access-Control-Request-Headers": "x-syno-token"})
check("CORS preflight", r.status_code == 204 and r.headers.get("access-control-allow-origin") == "*"
      and "x-syno-token" in r.headers.get("access-control-allow-headers", "").lower()
      and "POST" in r.headers.get("access-control-allow-methods", ""), (r.status_code, dict(r.headers)))
r = c.post(W + "query.php", data={"api": "SYNO.API.Info", "method": "query", "version": "1", "query": "all"})
check("CORS hlavicka v odpovedi API, bez credentials", r.headers.get("access-control-allow-origin") == "*"
      and r.headers.get("access-control-allow-credentials") is None
      and "x-request-error" in r.headers.get("access-control-expose-headers", ""), dict(r.headers))
TV_UA = ("Mozilla/5.0 (Web0S; Linux/SmartTV) AppleWebKit/537.36 (KHTML, like Gecko) "
         "Chrome/38.0.2125.122 Safari/537.36 WebAppManager")
tv = TestClient(appmod.app, headers={"User-Agent": TV_UA})
lg = tv.post(W + "auth.php", data={"api": "SYNO.PhotoStation.Auth", "method": "login", "version": "1",
                                   "username": "spravca", "password": "heslo1234"}).json()
tvsid = lg["data"]["sid"]
tv2 = TestClient(appmod.app, headers={"User-Agent": TV_UA})  # bez cookies, ako XHR z appky
r = tv2.post(W + "auth.php", data={"api": "SYNO.PhotoStation.Auth", "method": "checkauth", "version": "1"},
             headers={"X-SYNO-TOKEN": tvsid}).json()
check("TV appka: session z hlavicky X-SYNO-TOKEN", r["success"] and r["data"]["username"] == "spravca", r)
r = tv.post(W + "photo.php", data={"api": "SYNO.PhotoStation.Photo", "method": "list", "version": "1",
                                   "type": "photo", "offset": "0", "limit": "1", "sort_by": "takendate",
                                   "sort_direction": "desc"}).json()
pid = r["data"]["items"][0]["id"]
r = tv2.get(W + "thumb.php", params={"api": "SYNO.PhotoStation.Thumb", "method": "get", "version": "1",
                                     "id": pid, "size": "small", "PHPSESSID": tvsid})
check("TV appka: nahlad s PHPSESSID v URL", r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
      and r.headers.get("access-control-allow-origin") == "*", (r.status_code, dict(r.headers)))
r = tv2.get(W + "thumb.php", params={"api": "SYNO.PhotoStation.Thumb", "method": "get", "version": "1",
                                     "id": pid, "size": "small", "PHPSESSID": "neplatna"})
check("TV appka: neplatna session nedostane nahlad", r.status_code != 200 or r.headers["content-type"] != "image/jpeg",
      (r.status_code, r.headers.get("content-type")))
br = TestClient(appmod.app, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0 Safari/537.36"})
r = br.post(W + "auth.php", data={"api": "SYNO.PhotoStation.Auth", "method": "checkauth", "version": "1"},
            headers={"X-SYNO-TOKEN": tvsid}).json()
check("prehliadac: X-SYNO-TOKEN sa ignoruje", r["success"] and r["data"]["username"] == "", r)
r = br.get(W + "thumb.php", params={"api": "SYNO.PhotoStation.Thumb", "method": "get", "version": "1",
                                    "id": pid, "size": "small", "PHPSESSID": tvsid})
check("prehliadac: PHPSESSID v URL sa ignoruje", not (r.status_code == 200 and r.headers["content-type"] == "image/jpeg"),
      (r.status_code, r.headers.get("content-type")))

# --- parovanie telky (LGTV/): telka ukaze kod, admin ho povoli pod pouzivatelom ---
from picturestation import pairing  # noqa: E402
r = tv2.post("/api/tv/code", data={"name": "  55UH8507-ZA  "})
j = r.json()
check("TV kod", r.status_code == 200 and len(j["code"]) == 6 and set(j["code"]) <= set(pairing.ALPHABET)
      and len(j["token"]) == 32 and r.headers.get("access-control-allow-origin") == "*", (r.status_code, j))
r = tv2.options("/api/tv/poll", headers={"Origin": "null", "Access-Control-Request-Method": "POST"})
check("TV preflight", r.status_code == 204 and r.headers.get("access-control-allow-origin") == "*", r.status_code)
check("TV poll caka na admina", tv2.post("/api/tv/poll", data={"token": j["token"]}).json() == {"status": "pending"})
check("TV poll s cudzim tokenom", tv2.post("/api/tv/poll", data={"token": "x" * 32}).json() == {"status": "unknown"})
c.cookies.clear()
call("auth.php", api="SYNO.PhotoStation.Auth", method="login", version="1", username="spravca", password="heslo1234")
adm("user_create", {"username": "telka", "password": "heslo-tv-123"})
r = adm("device_pair", {"code": "ZZZZZZ", "user": "telka"})
check("zly kod = chyba", r.status_code == 400 and "code" in r.json()["error"], (r.status_code, r.text))
r = adm("device_pair", {"code": j["code"], "user": "nikto"})
check("neznamy pouzivatel = chyba", r.status_code == 400, (r.status_code, r.text))
r = adm("device_pair", {"code": " " + j["code"].lower() + " ", "user": "telka"})
check("admin povoli telku", r.status_code == 200 and r.json() == {"name": "55UH8507-ZA", "username": "telka"}, (r.status_code, r.text))
r = tv2.post("/api/tv/poll", data={"token": j["token"]}).json()
check("TV poll dostane session", r["status"] == "ok" and r["username"] == "telka" and len(r["sid"]) == 32 and r["title"], r)
dsid = r["sid"]
check("TV poll druhy raz uz nic", tv2.post("/api/tv/poll", data={"token": j["token"]}).json() == {"status": "unknown"})
r = tv2.post(W + "auth.php", data={"api": "SYNO.PhotoStation.Auth", "method": "checkauth", "version": "1"},
             headers={"X-SYNO-TOKEN": dsid}).json()
check("telka je prihlasena", r["data"]["username"] == "telka", r)
devs = adm("device_list").json()["devices"]
check("zoznam teliek", len(devs) == 1 and devs[0]["name"] == "55UH8507-ZA" and devs[0]["username"] == "telka"
      and devs[0]["last_seen"] > 0 and "sid" not in devs[0], devs)
adm("device_delete", {"id": devs[0]["id"]})
r = tv2.post(W + "album.php", data={"api": "SYNO.PhotoStation.Album", "method": "list", "version": "1", "offset": "0",
                                    "limit": "1"}, headers={"X-SYNO-TOKEN": dsid})
check("odstranena telka = session prec", r.headers.get("x-request-error") == "error_timeout"
      and adm("device_list").json()["devices"] == [], (dict(r.headers), adm("device_list").json()))
adm("user_delete", {"username": "telka"})

print("\nCHYB:", fails)
sys.exit(1 if fails else 0)
