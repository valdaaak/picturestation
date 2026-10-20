# SPDX-License-Identifier: GPL-3.0-or-later
"""Preberanie ludi zo Synology Photos (spolocny priestor) cez API. Len citanie.

Servisny ucet potrebuje v Synology Photos uroven Full Access k spolocnemu priestoru - inak
Synology Photos osoby v spolocnom priestore nevrati (chyba 801, viz KB Synology).
Nastavenie v picturestation.env: SYNO_URL, SYNO_USER, SYNO_PASS_FILE. Bez nich sa nic nespusti.
"""
import json
import logging
import os
import ssl
import threading
import time
import urllib.parse
import urllib.request

from . import config, ids, store

log = logging.getLogger("picturestation.synosync")
URL = os.environ.get("SYNO_URL", "").rstrip("/")
USER = os.environ.get("SYNO_USER", "")
PASS_FILE = os.environ.get("SYNO_PASS_FILE", "")
INTERVAL = int(os.environ.get("SYNO_SYNC_INTERVAL", str(config.INDEX_INTERVAL or 1800)))

_ctx = ssl.create_default_context()  # plne overenie certifikatu


def enabled() -> bool:
    return bool(URL and USER and PASS_FILE and os.path.isfile(PASS_FILE))


def _call(api, method, version, sid=None, **params):
    data = {"api": api, "method": method, "version": str(version),
            **{k: (json.dumps(v) if isinstance(v, (list, dict, bool)) else str(v)) for k, v in params.items()}}
    if sid:
        data["_sid"] = sid
    req = urllib.request.Request(URL + "/webapi/entry.cgi", data=urllib.parse.urlencode(data).encode(), method="POST")
    with urllib.request.urlopen(req, context=_ctx, timeout=120) as r:
        return json.loads(r.read().decode())


FACE_DIR = os.path.join(config.DATA_DIR, "faces")


def face_path(pid: int) -> str:
    return os.path.join(FACE_DIR, f"{int(pid)}.jpg")


def _download_face(sid, pid, cache_key) -> bool:
    data = {"api": "SYNO.FotoTeam.Thumbnail", "method": "get", "version": "1", "id": str(pid),
            "type": "person", "size": "sm", "cache_key": cache_key, "_sid": sid}
    url = URL + "/webapi/entry.cgi?" + urllib.parse.urlencode(data)
    with urllib.request.urlopen(url, context=_ctx, timeout=60) as r:
        if not (r.headers.get("Content-Type") or "").startswith("image/"):
            return False
        body = r.read()
    os.makedirs(FACE_DIR, exist_ok=True)
    tmp = face_path(pid) + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(body)
    os.replace(tmp, face_path(pid))
    return True


def fetch():
    """[(id, meno, [cesty], face_key, cover_path)] pomenovanych a zobrazenych osob v spolocnom priestore.
    Vyrezy tvari stiahne len pri zmene."""
    old_keys = {r["id"]: r["face_key"] for r in store.db().execute("SELECT id, face_key FROM people")}
    with open(PASS_FILE, encoding="utf-8") as fh:
        pw = fh.read().strip()
    lg = _call("SYNO.API.Auth", "login", 6, account=USER, passwd=pw, session="webui", format="sid")
    if not lg.get("success"):
        raise RuntimeError(f"prihlasenie zlyhalo: {lg.get('error')}")
    sid = lg["data"]["sid"]
    try:
        persons, off = [], 0
        while True:
            r = _call("SYNO.FotoTeam.Browse.Person", "list", 1, sid, offset=off, limit=5000, additional=["thumbnail"])
            if not r.get("success"):
                hint = " (treba Full Access v Synology Photos)" if r.get("error", {}).get("code") == 801 else ""
                raise RuntimeError(f"zoznam osob: {r.get('error')}{hint}")
            persons += r["data"]["list"]
            if len(r["data"]["list"]) < 5000:
                break
            off += 5000
        out = []
        for p in persons:
            name = (p.get("name") or "").strip()
            if not name or p.get("show") is False:
                continue
            paths, by_unit, off = [], {}, 0
            while True:
                it = _call("SYNO.FotoTeam.Browse.Item", "list", 1, sid, offset=off, limit=500,
                           person_id=p["id"], additional=["folder"])
                if not it.get("success"):
                    raise RuntimeError(f"fotky osoby {name}: {it.get('error')}")
                lst = it["data"]["list"]
                for x in lst:
                    folder = ((x.get("additional") or {}).get("folder") or "").strip("/")
                    fn = x.get("filename") or ""
                    if fn:
                        rel = f"{folder}/{fn}" if folder else fn
                        paths.append(rel)
                        by_unit[x.get("id")] = rel
                if len(lst) < 500:
                    break
                off += 500
            pid = int(p["id"])
            key = ((p.get("additional") or {}).get("thumbnail") or {}).get("cache_key")
            if key and (old_keys.get(pid) != key or not os.path.exists(face_path(pid))):
                try:
                    if not _download_face(sid, pid, key):
                        key = None
                except Exception as e:
                    log.debug("face crop %s: %s", name, e)
                    key = None
            # cache_key vyrezu = "<id fotky>_<cas>"; z tej fotky je vyrez tvare
            cover_unit = None
            ck = ((p.get("additional") or {}).get("thumbnail") or {}).get("cache_key") or ""
            if "_" in ck and ck.split("_", 1)[0].isdigit():
                cover_unit = int(ck.split("_", 1)[0])
            out.append((pid, name, paths, key, by_unit.get(cover_unit)))
        return out
    finally:
        try:
            _call("SYNO.API.Auth", "logout", 6, sid, session="webui")
        except Exception:
            pass


def sync_once():
    t0 = time.time()
    people = fetch()
    rows, missing = [], 0
    for pid, name, paths, _key, _cov in people:
        for p in paths:
            try:
                rel = ids.clean_rel(p)
            except ids.BadId:
                missing += 1
                continue
            rows.append((pid, rel))
    db = store.db()
    db.execute("BEGIN")
    db.execute("DELETE FROM people")
    db.execute("DELETE FROM people_items")
    db.executemany("INSERT INTO people(id, name, face_key, cover_path) VALUES (?,?,?,?)",
                   [(pid, n, key, cov) for pid, n, _p, key, cov in people])
    db.executemany("INSERT OR IGNORE INTO people_items(person_id, path) VALUES (?,?)", rows)
    db.execute("COMMIT")
    log.info("people from Synology Photos: %d persons, %d assignments (%d invalid paths) in %.0f s",
             len(people), len(rows), missing, time.time() - t0)
    return len(people), len(rows)


def start():
    if not enabled():
        log.info("people from Synology Photos: off (SYNO_URL/USER/PASS_FILE not set)")
        return

    def loop():
        time.sleep(30)
        while True:
            try:
                sync_once()
            except Exception as e:
                log.warning("people sync failed: %s", e)
            time.sleep(INTERVAL)

    threading.Thread(target=loop, name="synosync", daemon=True).start()
