# SPDX-License-Identifier: GPL-3.0-or-later
"""Rozpoznanie presunutych/premenovanych albumov a suborov a prenos vsetkeho, co je naviazane na cestu.

Na ceste visia: prava a vylucenia (access), vlastnosti albumu (album_props vratane titulnej fotky),
odomknutia (unlocks), zdielane odkazy (shares), chytre albumy (criteria.path), tagy (item_tags,
tag_suppress), komentare (comments), index (meta).

Priecinok sa povazuje za presunuty, ak vsetky jeho subory zmizli a inde sa objavil novy priecinok
s presne rovnakou sadou (meno, velkost) a takych priecinkov je prave jeden. Nadradeny priecinok bez
vlastnych suborov je presunuty, ak sa vsetky jeho podpriecinky presunuli do toho isteho noveho rodica.
"""
import collections
import json
import logging
import posixpath
import time

from . import store

log = logging.getLogger("picturestation.moves")


def _parent(p):
    return posixpath.dirname(p)


def detect(old: dict, seen: dict):
    """old/seen: rel -> velkost. Vrati (dir_map, file_map, nejednoznacne)."""
    missing = set(old) - set(seen)
    new = set(seen) - set(old)
    if not missing or not new:
        return {}, {}, []

    old_dirs = collections.defaultdict(set)    # priecinok -> subory (vsetky stare)
    for p in old:
        old_dirs[_parent(p)].add(p)
    new_dirs = collections.defaultdict(set)    # priecinok -> subory (vsetky aktualne)
    for p in seen:
        new_dirs[_parent(p)].add(p)

    def sig(files, sizes):
        return frozenset((posixpath.basename(f), sizes[f]) for f in files)

    # stare priecinky, ktorych subory zmizli vsetky; nove priecinky, ktore su cele nove
    gone = {d: sig(fs, old) for d, fs in old_dirs.items() if d and fs and fs <= missing}
    fresh = {d: sig(fs, seen) for d, fs in new_dirs.items() if d and fs and fs <= new}
    by_sig = collections.defaultdict(list)
    for d, s in fresh.items():
        by_sig[s].append(d)

    dir_map, ambiguous = {}, []
    for d, s in gone.items():
        c = by_sig.get(s, [])
        if len(c) == 1:
            if c[0] != d:
                dir_map[d] = c[0]
        elif len(c) > 1:
            ambiguous.append((d, sorted(c)))

    # nadradene priecinky bez vlastnych suborov: vsetky podpriecinky presunute pod ten isty novy rodic
    all_old_dirs = set()
    for d in old_dirs:
        while d:
            all_old_dirs.add(d)
            d = _parent(d)
    changed = True
    while changed:
        changed = False
        for d in sorted(all_old_dirs, key=lambda x: -x.count("/")):
            if d in dir_map or old_dirs.get(d):
                continue
            kids = [k for k in all_old_dirs if _parent(k) == d]
            if not kids or not all(k in dir_map for k in kids):
                continue
            targets = {_parent(dir_map[k]) for k in kids}
            names_ok = all(posixpath.basename(dir_map[k]) == posixpath.basename(k) for k in kids)
            if len(targets) == 1 and names_ok:
                t = targets.pop()
                if t and t != d and not t.startswith(d + "/"):
                    dir_map[d] = t
                    changed = True

    # jednotlive subory mimo presunutych priecinkov: jednoznacna zhoda (meno, velkost)
    def under_map(p):
        return any(p == d or p.startswith(d + "/") for d in dir_map)

    moved_targets = set(dir_map.values())
    new_by_key = collections.defaultdict(list)
    for p in new:
        if not any(p.startswith(t + "/") for t in moved_targets):
            new_by_key[(posixpath.basename(p), seen[p])].append(p)
    file_map = {}
    for p in missing:
        if under_map(p):
            continue
        c = new_by_key.get((posixpath.basename(p), old[p]), [])
        if len(c) == 1:
            file_map[p] = c[0]
    # jeden novy subor nesmie dostat dva stare
    taken = collections.Counter(file_map.values())
    file_map = {k: v for k, v in file_map.items() if taken[v] == 1}
    return dir_map, file_map, ambiguous


def map_path(p, dir_map, file_map=None):
    """Nova cesta pre p (album alebo subor), alebo None."""
    best = None
    for d in dir_map:
        if (p == d or p.startswith(d + "/")) and (best is None or len(d) > len(best)):
            best = d
    if best is not None:
        return dir_map[best] + p[len(best):]
    if file_map and p in file_map:
        return file_map[p]
    return None


def rewrite(dir_map, file_map=None, kind="auto"):
    """Prenesie vsetky zaznamy zo starych ciest na nove. Pri konflikte ostava to, co uz je na novej ceste."""
    if not dir_map and not file_map:
        return 0
    db = store.db()
    n = 0

    def move_rows(table, keycols):
        nonlocal n
        cols = ", ".join(keycols)
        for row in db.execute(f"SELECT rowid AS rid, path FROM {table}").fetchall():
            np = map_path(row["path"], dir_map, file_map)
            if np is None:
                continue
            cur = db.execute(f"UPDATE OR IGNORE {table} SET path=? WHERE rowid=?", (np, row["rid"]))
            if cur.rowcount == 0:  # na novej ceste uz zaznam je -> stary zahodit
                db.execute(f"DELETE FROM {table} WHERE rowid=?", (row["rid"],))
            n += 1

    for table in ("access", "album_props", "unlocks", "shares", "item_tags", "tag_suppress", "comments",
                  "best_proposals"):
        move_rows(table, ["path"])
    # titulna fotka albumu je cesta k suboru
    for row in db.execute("SELECT path, cover FROM album_props WHERE cover IS NOT NULL").fetchall():
        nc = map_path(row["cover"], dir_map, file_map)
        if nc:
            db.execute("UPDATE album_props SET cover=? WHERE path=?", (nc, row["path"]))
    # chytre albumy obmedzene na album
    for row in db.execute("SELECT id, criteria FROM smart_albums").fetchall():
        try:
            c = json.loads(row["criteria"])
        except ValueError:
            continue
        if c.get("path"):
            np = map_path(c["path"], dir_map, file_map)
            if np:
                c["path"] = np
                db.execute("UPDATE smart_albums SET criteria=? WHERE id=?", (json.dumps(c, ensure_ascii=False), row["id"]))
    now = int(time.time())
    for old, new in dir_map.items():
        db.execute("INSERT INTO moves(old, new, kind, created) VALUES (?,?,?,?)", (old, new, kind, now))
        log.info("album moved %s -> %s (%s)", old, new, kind)
    for old, new in (file_map or {}).items():
        db.execute("INSERT INTO moves(old, new, kind, created) VALUES (?,?,?,?)", (old, new, kind + "-file", now))
    return n


def record_ambiguous(ambiguous):
    db = store.db()
    now = int(time.time())
    for old, cands in ambiguous:
        db.execute("INSERT OR REPLACE INTO moves_pending(old, candidates, created) VALUES (?,?,?)",
                   (old, json.dumps(cands, ensure_ascii=False), now))
