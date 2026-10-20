# SPDX-License-Identifier: GPL-3.0-or-later
"""Zivy test proti beziacemu serveru: python live_check.py http://localhost user heslo_subor"""
import json
import sys
import time

import httpx

base, user, pwfile = sys.argv[1], sys.argv[2], sys.argv[3]
pw = [l.split(":", 1)[1].strip() for l in open(pwfile, encoding="utf-8") if l.startswith("heslo:")][0]
W = base.rstrip("/") + "/photo/webapi/"
c = httpx.Client(timeout=120)


def call(path, **p):
    t = time.time()
    r = c.post(W + path, data=p)
    j = json.loads(r.text)
    return j, time.time() - t


j, dt = call("query.php", api="SYNO.API.Info", method="query", version="1", query="all")
print(f"query: {len(j['data'])} API, {dt*1000:.0f} ms")
j, dt = call("auth.php", api="SYNO.PhotoStation.Auth", method="login", version="1", username=user, password=pw)
print(f"login: success={j['success']} admin={j.get('data', {}).get('is_admin')} {dt*1000:.0f} ms")
sid = c.cookies.get("PHPSESSID")
j, dt = call("album.php", api="SYNO.PhotoStation.Album", method="list", version="1", offset="0", limit="120",
             type="album,video,photo", recursive="false",
             additional="album_permission,thumb_size,photo_exif,video_quality,video_codec,album_sorting,file_location,album_createdate")
items = j["data"]["items"]
print(f"koren: total={j['data']['total']} na strane={len(items)} {dt:.1f} s")
print("  prve:", [i["info"]["name"] for i in items[:8]])
nothumb = [i["info"]["name"] for i in items if i["thumbnail_status"] == "default"]
print(f"  albumy bez titulnej fotky: {len(nothumb)} {nothumb[:5]}")

# album s fotkami: prvy album, ktory ma priamo fotky
target = None
for a in items:
    if a["type"] != "album":
        continue
    j, dt = call("album.php", api="SYNO.PhotoStation.Album", method="list", version="1", id=a["id"], offset="0",
                 limit="120", type="album,video,photo", additional="thumb_size,photo_exif,video_codec")
    media = [i for i in j["data"]["items"] if i["type"] != "album"]
    if media:
        target = (a["info"]["name"], media, dt, j["data"]["total"])
        break
name, media, dt, total = target
print(f"album '{name}': total={total}, fotiek/videi na strane={len(media)}, {dt:.1f} s")
m0 = media[0]
print("  prva:", m0["info"]["name"], m0["info"]["takendate"], m0["info"]["resolutionx"], "x", m0["info"]["resolutiony"],
      m0["additional"].get("photo_exif", {}).get("camera_model"))
for size in ("small", "large"):
    t = time.time()
    r = c.get(W + "thumb.php", params={"api": "SYNO.PhotoStation.Thumb", "method": "get", "version": "1",
                                       "id": m0["id"], "size": size, "PHPSESSID": sid})
    print(f"  nahlad {size}: {r.status_code} {r.headers.get('content-type')} {len(r.content)} B {1000*(time.time()-t):.0f} ms")
t = time.time()
r = c.get(W + "download.php", params={"api": "SYNO.PhotoStation.Download", "method": "getphoto", "version": "1",
                                      "id": m0["id"], "PHPSESSID": sid}, headers={"Range": "bytes=0-1023"})
print(f"  original Range: {r.status_code} {r.headers.get('content-range')} {1000*(time.time()-t):.0f} ms")
