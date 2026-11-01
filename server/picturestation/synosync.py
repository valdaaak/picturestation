# SPDX-License-Identifier: GPL-3.0-or-later
"""Preberanie ludi a tagov zo Synology Photos (spolocny priestor) cez API. Len citanie.

Servisny ucet potrebuje v Synology Photos uroven Full Access k spolocnemu priestoru - inak
Synology Photos osoby v spolocnom priestore nevrati (chyba 801, viz KB Synology).
Nastavenie v picturestation.env: SYNO_URL, SYNO_USER, SYNO_PASS_FILE. Bez nich sa nic nespusti.

Tagy (vseobecne tagy Synology Photos) idu do item_tags so source='synology': co v Synology pribudne,
pribudne aj tu, co tam zmizne, zmizne aj tu. Tag, ktory admin v galerii rucne odobral, sa nevracia
(tag_suppress). Tagy zo suboru (source='file') a rucne (source='manual') ostavaju, ako su.
"""
import json
import logging
import os
import ssl
import threading
import time
import urllib.parse
import urllib.request

from . import catalog, config, ids, store

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


def _login() -> str:
    with open(PASS_FILE, encoding="utf-8") as fh:
        pw = fh.read().strip()
    lg = _call("SYNO.API.Auth", "login", 6, account=USER, passwd=pw, session="webui", format="sid")
    if not lg.get("success"):
        raise RuntimeError(f"prihlasenie zlyhalo: {lg.get('error')}")
    return lg["data"]["sid"]


def _logout(sid):
    try:
        _call("SYNO.API.Auth", "logout", 6, sid, session="webui")
    except Exception:
        pass


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


def _item_paths(sid, what, **filt):
    """([cesty], {id polozky: cesta}) vsetkych poloziek s filtrom (person_id=.., general_tag_id=..).
    Cesty su relativne ku korenu spolocneho priestoru (= koren hlavnej galerie)."""
    paths, by_unit, off = [], {}, 0
    while True:
        it = _call("SYNO.FotoTeam.Browse.Item", "list", 1, sid, offset=off, limit=500, additional=["folder"], **filt)
        if not it.get("success"):
            raise RuntimeError(f"{what}: {it.get('error')}")
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
    return paths, by_unit


def _list_all(sid, api, what, **params):
    out, off = [], 0
    while True:
        r = _call(api, "list", 1, sid, offset=off, limit=5000, **params)
        if not r.get("success"):
            hint = " (treba Full Access v Synology Photos)" if r.get("error", {}).get("code") == 801 else ""
            raise RuntimeError(f"{what}: {r.get('error')}{hint}")
        out += r["data"]["list"]
        if len(r["data"]["list"]) < 5000:
            break
        off += 5000
    return out


def fetch(sid):
    """[(id, meno, [cesty], face_key, cover_path)] pomenovanych a zobrazenych osob v spolocnom priestore.
    Vyrezy tvari stiahne len pri zmene."""
    old_keys = {r["id"]: r["face_key"] for r in store.db().execute("SELECT id, face_key FROM people")}
    out = []
    for p in _list_all(sid, "SYNO.FotoTeam.Browse.Person", "zoznam osob", additional=["thumbnail"]):
        name = (p.get("name") or "").strip()
        if not name or p.get("show") is False:
            continue
        paths, by_unit = _item_paths(sid, f"fotky osoby {name}", person_id=p["id"])
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


def fetch_tags(sid):
    """[(nazov, [cesty])] vseobecnych tagov spolocneho priestoru."""
    out = []
    for t in _list_all(sid, "SYNO.FotoTeam.Browse.GeneralTag", "zoznam tagov"):
        name = (t.get("name") or "").strip()
        if name:
            out.append((name, _item_paths(sid, f"fotky tagu {name}", general_tag_id=t["id"])[0]))
    return out


def apply_people(people) -> tuple:
    rows, missing = [], 0
    for pid, _name, paths, _key, _cov in people:
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
    return len(people), len(rows), missing


def apply_tags(tags) -> tuple:
    """Zosuladi tagy zo Synology Photos (source='synology') so zoznamom [(nazov, [cesty])].
    Vrati (pocet tagov, pocet priradeni, neplatne cesty)."""
    db = store.db()
    want, missing, names = set(), 0, set()
    db.execute("BEGIN")
    try:
        for name, paths in tags:
            name = catalog.clean_keyword(name)
            if not name or name.lower() in names:
                continue
            names.add(name.lower())
            db.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (name,))
            tid = db.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()["id"]
            for p in paths:
                try:
                    want.add((ids.clean_rel(p), tid))
                except ids.BadId:
                    missing += 1
        have = {(r["path"], r["tag_id"]) for r in db.execute("SELECT path, tag_id FROM item_tags WHERE source='synology'")}
        suppressed = {(r["path"], r["tag_id"]) for r in db.execute("SELECT path, tag_id FROM tag_suppress")}
        db.executemany("INSERT OR IGNORE INTO item_tags(path, tag_id, source) VALUES (?,?,'synology')",
                       sorted(want - have - suppressed))
        gone = have - want
        db.executemany("DELETE FROM item_tags WHERE path=? AND tag_id=? AND source='synology'", sorted(gone))
        for tid in {t for _p, t in gone}:   # tag, ktory uz nic nema, zmizne (ako pri rucnom odobrati)
            if not db.execute("SELECT 1 FROM item_tags WHERE tag_id=? UNION SELECT 1 FROM tag_suppress WHERE tag_id=?",
                              (tid, tid)).fetchone():
                db.execute("DELETE FROM tags WHERE id=?", (tid,))
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise
    catalog.invalidate()
    return len(names), len(want), missing


def sync_once():
    t0 = time.time()
    sid = _login()
    try:
        people = fetch(sid)
        tags = fetch_tags(sid)
    finally:
        _logout(sid)
    np, na, nm = apply_people(people)
    log.info("people from Synology Photos: %d persons, %d assignments (%d invalid paths) in %.0f s",
             np, na, nm, time.time() - t0)
    nt, nta, ntm = apply_tags(tags)
    log.info("tags from Synology Photos: %d tags, %d assignments (%d invalid paths)", nt, nta, ntm)
    return np, na


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
                log.warning("people and tags sync failed: %s", e)
            time.sleep(INTERVAL)

    threading.Thread(target=loop, name="synosync", daemon=True).start()
