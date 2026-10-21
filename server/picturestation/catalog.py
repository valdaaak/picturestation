# SPDX-License-Identifier: GPL-3.0-or-later
"""Tagy, miesta (z GPS) a chytre albumy nad indexom metadat.

ID v tvare, ktory pozna appka DS photo:
  tag_<cislo>        tag zadany rucne (typ 'desc')
  tag_g<hex>         miesto, hex('<kod krajiny>|<obec>')  (typ 'geo')
  smart_<cislo>      chytry album
"""
import json
import posixpath
import threading
import time

from . import geo, store

_snap = None
_snap_t = 0.0
_snap_lock = threading.Lock()
SNAP_TTL = 60


_snap_rebuilding = False


def _build_snapshot():
    global _snap, _snap_t
    rows = []
    for r in store.db().execute("SELECT path, kind, mtime, size, data FROM meta"):
        try:
            rows.append((r["path"], r["kind"], r["mtime"], r["size"], json.loads(r["data"])))
        except ValueError:
            continue
    with _snap_lock:
        _snap, _snap_t = rows, time.time()
    return rows


def _rebuild_in_background():
    global _snap_rebuilding
    try:
        _build_snapshot()
    finally:
        _snap_rebuilding = False


def snapshot():
    """Vsetky zaindexovane subory: zoznam (rel, kind, mtime, size, meta).
    After SNAP_TTL seconds the list is rebuilt in the background and requests keep using the previous one
    (about a second for 70,000 files), so nobody waits; only the very first call builds it directly."""
    global _snap_rebuilding
    with _snap_lock:
        snap, age = _snap, time.time() - _snap_t
        start = snap is not None and age >= SNAP_TTL and not _snap_rebuilding
        if start:
            _snap_rebuilding = True
    if start:
        threading.Thread(target=_rebuild_in_background, name="snapshot", daemon=True).start()
    return snap if snap is not None else _build_snapshot()


def invalidate():
    global _snap
    with _snap_lock:
        _snap = None
    with _covers_lock:
        _covers.clear()


# Covers of tags, places, people and smart albums: remembered when a list is built (it knows them anyway), so the
# thumbnails of the Collections page do not scan the whole library one by one. Per permission state, 10 minutes.
COVER_TTL = 600
_covers = {}            # (perm key, id) -> (time, rel)
_covers_lock = threading.Lock()


def clear_covers():
    with _covers_lock:
        _covers.clear()


def _perm_key(perm):
    k = getattr(perm, "_cover_key", None)
    if k is None:
        k = (perm.username, perm.admin, tuple(sorted(perm.rules)), frozenset(perm.unlocked),
             frozenset(perm.forced), frozenset(perm.items), frozenset(perm.pw_albums),
             getattr(perm, "root_public", None))
        perm._cover_key = k
    return k


def _remember(perm, rows):
    """rows = (id, name, count, (entry, meta) or None, ...) from the list functions."""
    k, now = _perm_key(perm), time.time()
    with _covers_lock:
        if len(_covers) > 20000:
            _covers.clear()
        for r in rows:
            _covers[(k, r[0])] = (now, r[3][0]["rel"] if r[3] else None)


def entry(rel, kind, mtime, size):
    return {"name": posixpath.basename(rel), "rel": rel, "mtime": mtime, "size": size, "kind": kind}


# ---------------- ID ----------------
def place_key(m: dict):
    if m.get("place"):
        return (m.get("cc") or "") + "|" + m["place"]
    return None


def place_id(key: str) -> str:
    return "tag_g" + key.encode("utf-8").hex()


def parse_tag_id(id_: str):
    """('desc', int) | ('geo', 'cc|obec') | ('people', int) | None"""
    if not id_ or not id_.startswith("tag_"):
        return None
    rest = id_[4:]
    if rest.startswith("p"):
        try:
            return "people", int(rest[1:])
        except ValueError:
            return None
    if rest.startswith("g"):
        try:
            return "geo", bytes.fromhex(rest[1:]).decode("utf-8")
        except ValueError:
            return None
    try:
        return "desc", int(rest)
    except ValueError:
        return None


def parse_smart_id(id_: str):
    if not id_ or not id_.startswith("smart_"):
        return None
    try:
        return int(id_[6:])
    except ValueError:
        return None


def place_label(key: str) -> str:
    cc, _, name = key.partition("|")
    return f"{name}, {geo.country_name(cc)}" if cc else name


# ---------------- tagy suborov ----------------
def tags_by_path() -> dict:
    out = {}
    for r in store.db().execute("SELECT path, tag_id FROM item_tags"):
        out.setdefault(r["path"], set()).add(r["tag_id"])
    return out


def tag_names() -> dict:
    return {r["id"]: r["name"] for r in store.db().execute("SELECT id, name FROM tags")}


def clean_keyword(k: str):
    k = " ".join(str(k).replace(chr(0), "").split())[:64]
    return k or None


def sync_file_tags(rel: str, keywords):
    """Zosuladi tagy zo suboru (source='file') s klucovymi slovami. Rucne odobrate sa nevracaju."""
    db = store.db()
    want = set()
    seen = set()
    for k in keywords or ():
        k = clean_keyword(k)
        if not k or k.lower() in seen:
            continue
        seen.add(k.lower())
        db.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (k,))
        want.add(db.execute("SELECT id FROM tags WHERE name=?", (k,)).fetchone()["id"])
    have = {r["tag_id"] for r in db.execute("SELECT tag_id FROM item_tags WHERE path=? AND source='file'", (rel,))}
    suppressed = {r["tag_id"] for r in db.execute("SELECT tag_id FROM tag_suppress WHERE path=?", (rel,))}
    for t in want - have - suppressed:
        db.execute("INSERT OR IGNORE INTO item_tags(path, tag_id, source) VALUES (?,?,'file')", (rel, t))
    for t in have - want:
        db.execute("DELETE FROM item_tags WHERE path=? AND tag_id=? AND source='file'", (rel, t))


def people_by_path() -> dict:
    out = {}
    for r in store.db().execute("SELECT path, person_id FROM people_items"):
        out.setdefault(r["path"], set()).add(r["person_id"])
    return out


def people_names() -> dict:
    return {r["id"]: r["name"] for r in store.db().execute("SELECT id, name FROM people")}


def item_people(rel: str):
    return [{"id": f"tag_p{r['id']}", "name": r["name"]} for r in store.db().execute(
        "SELECT p.id, p.name FROM people p JOIN people_items i ON i.person_id=p.id WHERE i.path=? ORDER BY p.name", (rel,))]


def item_tags(rel: str):
    return [{"id": f"tag_{r['id']}", "name": r["name"]} for r in store.db().execute(
        "SELECT t.id, t.name FROM tags t JOIN item_tags i ON i.tag_id=t.id WHERE i.path=? ORDER BY t.name", (rel,))]


# ---------------- filtre ----------------
def _match(rel, kind, m, crit, tagmap, peoplemap=None):
    peoplemap = peoplemap or {}
    types = crit.get("types")
    if types and kind not in types:
        return False
    path = crit.get("path")
    if path and not (rel == path or rel.startswith(path + "/")):
        return False
    taken = (m.get("taken") or "")[:10]
    if crit.get("date_from") and taken < crit["date_from"]:
        return False
    if crit.get("date_to") and taken > crit["date_to"]:
        return False
    if crit.get("tags"):
        if not tagmap.get(rel, set()) & set(crit["tags"]):
            return False
    if crit.get("people"):
        if not peoplemap.get(rel, set()) & set(crit["people"]):
            return False
    if crit.get("places") or crit.get("countries"):
        key = place_key(m)
        ok = bool(key) and (key in (crit.get("places") or ()) or key.split("|")[0] in (crit.get("countries") or ()))
        if not ok:
            return False
    return True


def filter_items(perm, crit: dict):
    """[(entry, meta)] viditelne pre perm a vyhovujuce kriteriam."""
    tagmap = tags_by_path() if crit.get("tags") else {}
    peoplemap = people_by_path() if crit.get("people") else {}
    out = []
    for rel, kind, mtime, size, m in snapshot():
        if not perm.can_item(rel):
            continue
        if _match(rel, kind, m, crit, tagmap, peoplemap):
            out.append((entry(rel, kind, mtime, size), m))
    return out


def crit_for_tag(id_: str):
    t = parse_tag_id(id_)
    if t is None:
        return None
    if t[0] == "desc":
        return {"tags": [t[1]]}
    if t[0] == "people":
        return {"people": [t[1]]}
    return {"places": [t[1]]}


def has_location(crit) -> bool:
    """Kriteria podla polohy (pri skrytom GPS sa nesmu vyhodnotit)."""
    return bool(crit and (crit.get("places") or crit.get("countries")))


def smart_get(sid: int):
    return store.db().execute("SELECT * FROM smart_albums WHERE id=?", (sid,)).fetchone()


def crit_for_smart(id_: str):
    sid = parse_smart_id(id_)
    row = smart_get(sid) if sid is not None else None
    if row is None:
        return None
    try:
        return json.loads(row["criteria"])
    except ValueError:
        return None


# ---------------- zoznamy ----------------
def _newest(items):
    """Titulna polozka skupiny = najnovsia podla datumu odfotenia."""
    return max(items, key=lambda x: x[1].get("taken") or "") if items else None


def list_tags(perm):
    """[(id, nazov, pocet, (entry, meta) titulna)] rucnych tagov s aspon jednou viditelnou polozkou."""
    names = tag_names()
    groups = {}
    tagmap = tags_by_path()
    for rel, kind, mtime, size, m in snapshot():
        tids = tagmap.get(rel)
        if not tids or not perm.can_item(rel):
            continue
        for t in tids:
            groups.setdefault(t, []).append((entry(rel, kind, mtime, size), m))
    out = [(f"tag_{t}", names.get(t, "?"), len(v), _newest(v)) for t, v in groups.items() if t in names]
    _remember(perm, out)
    return sorted(out, key=lambda x: x[1].lower())


def list_people(perm):
    """[(id, meno, pocet, titulna)] ludi s aspon jednou viditelnou fotkou, podla poctu zostupne."""
    names = people_names()
    if not names:
        return []
    pmap = people_by_path()
    groups = {}
    for rel, kind, mtime, size, m in snapshot():
        pids = pmap.get(rel)
        if not pids or not perm.can_item(rel):
            continue
        for pid in pids:
            groups.setdefault(pid, []).append((entry(rel, kind, mtime, size), m))
    out = [(f"tag_p{pid}", names[pid], len(v), _newest(v)) for pid, v in groups.items() if pid in names]
    _remember(perm, out)
    return sorted(out, key=lambda x: (-x[2], x[1].lower()))


def list_places(perm):
    """[(id, popis, pocet, titulna, kod krajiny)] miest s viditelnymi polozkami."""
    groups = {}
    for rel, kind, mtime, size, m in snapshot():
        key = place_key(m)
        if not key or not perm.can_item(rel):
            continue
        groups.setdefault(key, []).append((entry(rel, kind, mtime, size), m))
    out = [(place_id(k), place_label(k), len(v), _newest(v), k.split("|")[0]) for k, v in groups.items()]
    _remember(perm, out)
    return sorted(out, key=lambda x: (geo.country_name(x[4]).lower(), -x[2]))


def list_smart(perm):
    """[(id, nazov, pocet, titulna, kriteria)]"""
    out = []
    for r in store.db().execute("SELECT * FROM smart_albums ORDER BY name COLLATE NOCASE"):
        try:
            crit = json.loads(r["criteria"])
        except ValueError:
            continue
        items = filter_items(perm, crit)
        out.append((f"smart_{r['id']}", r["name"], len(items), _newest(items), crit))
    _remember(perm, out)
    return out


_snap_idx = None
_snap_idx_src = None


def snapshot_index() -> dict:
    """rel -> (kind, mtime, size, meta) zo snapshotu (rychle hladanie podla cesty)."""
    global _snap_idx, _snap_idx_src
    s = snapshot()
    if _snap_idx_src is not s:
        _snap_idx = {r[0]: r[1:] for r in s}
        _snap_idx_src = s
    return _snap_idx


def _newest_of_paths(paths, perm):
    idx = snapshot_index()
    best = None
    for rel in paths:
        row = idx.get(rel)
        if row is None or not perm.can_item(rel):
            continue
        taken = row[3].get("taken") or ""
        if best is None or taken > best[0]:
            best = (taken, rel)
    return best[1] if best else None


def cover_for(id_: str, perm):
    """Titulny subor (rel) pre tag/miesto/chytry album."""
    key = (_perm_key(perm), id_)
    with _covers_lock:
        hit = _covers.get(key)
    if hit and time.time() - hit[0] < COVER_TTL:
        return hit[1]
    rel = _cover_compute(id_, perm)
    with _covers_lock:
        _covers[key] = (time.time(), rel)
    return rel


def _cover_compute(id_: str, perm):
    t = parse_tag_id(id_) if id_.startswith("tag_") else None
    if t and t[0] in ("people", "desc"):
        # rychla cesta: len subory danej osoby/tagu, nie cela kniznica
        q = ("SELECT path FROM people_items WHERE person_id=?" if t[0] == "people"
             else "SELECT path FROM item_tags WHERE tag_id=?")
        return _newest_of_paths([r["path"] for r in store.db().execute(q, (t[1],))], perm)
    crit = crit_for_tag(id_) if id_.startswith("tag_") else crit_for_smart(id_)
    if crit is None:
        return None
    best = _newest(filter_items(perm, crit))
    return best[0]["rel"] if best else None
