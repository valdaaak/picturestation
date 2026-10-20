# SPDX-License-Identifier: GPL-3.0-or-later
"""Import of tags and albums from Synology Photos (DSM 7), from .tsv exports of the synofoto database.

  python3 -m picturestation.synofoto_import FOLDER            # dry run
  python3 -m picturestation.synofoto_import FOLDER --apply

Expected files: tags.tsv, unit_tags.tsv, condition_albums.tsv, normal_albums.tsv.
- tags of the shared space (id_user 0 = the photo share) -> Picturestation tags (source 'synofoto'),
  the same name = one tag
- albums by tags (condition_album) -> smart albums with the same name
- normal albums (normal_album) -> a tag named like the album + a smart album
Personal spaces of users (id_user != 0) are skipped, they are not in the photo share.
Existing smart albums with the same name are not changed.
"""
import argparse
import collections
import json
import os
import sys
import time

from . import ids, media, store


def read_tsv(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = [l.rstrip("\n").split("\t") for l in fh if l.strip()]
    return lines[1:] if lines else []  # bez hlavicky


def rel_of(folder: str, filename: str):
    folder = folder.strip("/")
    rel = f"{folder}/{filename}" if folder else filename
    try:
        rel = ids.clean_rel(rel)
    except ids.BadId:
        return None
    return rel if media._exists_media(rel) else None


def tag_id(db, name, apply):
    row = db.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()
    if row:
        return row["id"]
    if not apply:
        return None
    db.execute("INSERT INTO tags(name) VALUES (?)", (name,))
    return db.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()["id"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    d = a.folder
    db = store.db()

    # --- tagy k fotkam ---
    by_tag = collections.defaultdict(set)
    skipped_personal = collections.Counter()
    missing = collections.Counter()
    for row in read_tsv(os.path.join(d, "unit_tags.tsv")):
        if len(row) < 4:
            continue
        uid, folder, fn, tag = row[0], row[1], row[2], row[3].strip()
        if uid != "0":
            skipped_personal[tag] += 1
            continue
        rel = rel_of(folder, fn)
        if rel is None:
            missing[tag] += 1
            continue
        by_tag[tag].add(rel)

    # tagy v nasej databaze (bez ohladu na velkost pismen)
    existing = {r["name"].lower(): r["name"] for r in db.execute("SELECT name FROM tags")}
    print("Tags from Synology Photos (shared space):")
    added_total = 0
    for tag, rels in sorted(by_tag.items(), key=lambda x: -len(x[1])):
        tid = tag_id(db, tag, a.apply)
        have = set()
        if tid is not None:
            have = {r["path"] for r in db.execute("SELECT path FROM item_tags WHERE tag_id=?", (tid,))}
            suppressed = {r["path"] for r in db.execute("SELECT path FROM tag_suppress WHERE tag_id=?", (tid,))}
        else:
            suppressed = set()
        new = rels - have - suppressed
        added_total += len(new)
        note = f"merged with the existing '{existing[tag.lower()]}'" if tag.lower() in existing else "new tag"
        print(f"  {tag}: photos {len(rels)}, already tagged {len(rels & have)}, new {len(new)}"
              f"{', not found ' + str(missing[tag]) if missing[tag] else ''} ({note})")
        if a.apply:
            for rel in new:
                db.execute("INSERT OR IGNORE INTO item_tags(path, tag_id, source) VALUES (?,?,'synofoto')", (rel, tid))
    for tag, n in missing.items():
        if tag not in by_tag:
            print(f"  {tag}: {n} photos not found in the gallery (skipped)")
    if skipped_personal:
        print("Skipped (personal spaces, not in the photo share):", dict(skipped_personal))

    # --- nazvy tagov podla id v Synology Photos ---
    syno_tag = {r[0]: r[2].strip() for r in read_tsv(os.path.join(d, "tags.tsv")) if len(r) >= 3}

    # --- albumy podla tagov -> chytre albumy ---
    names = {r["name"].lower() for r in db.execute("SELECT name FROM smart_albums")}
    print("Albums by tags -> smart albums:")
    for row in read_tsv(os.path.join(d, "condition_albums.tsv")):
        if len(row) < 3:
            continue
        name = row[1].strip()
        try:
            cond = json.loads(row[2])
        except ValueError:
            print(f"  {name}: unknown condition, skipped")
            continue
        tnames = [syno_tag.get(str(x)) for x in cond.get("general_tag", [])]
        tnames = [t for t in tnames if t]
        extra = set(cond) - {"general_tag", "general_tag_policy", "user_id"}
        if not tnames or extra or cond.get("general_tag_policy", "or") != "or":
            print(f"  {name}: condition {cond} is not just 'any of the tags' - skipped")
            continue
        if name.lower() in names:
            print(f"  {name}: the smart album already exists - not changed")
            continue
        tids = [tag_id(db, t, a.apply) for t in tnames]
        print(f"  {name}: tags {tnames}")
        if a.apply:
            db.execute("INSERT INTO smart_albums(name, criteria, created_by, created) VALUES (?,?,?,?)",
                       (name, json.dumps({"tags": [t for t in tids if t]}), "synofoto", int(time.time())))
            names.add(name.lower())

    # --- bezne albumy -> tag + chytry album ---
    albums = collections.defaultdict(set)
    amiss = collections.Counter()
    for row in read_tsv(os.path.join(d, "normal_albums.tsv")):
        if len(row) < 4:
            continue
        aname, uid, folder, fn = row[0].strip(), row[1], row[2], row[3]
        rel = rel_of(folder, fn) if uid == "0" else None
        if rel is None:
            amiss[aname] += 1
            continue
        albums[aname].add(rel)
    print("Normal albums -> tag + smart album:")
    for aname, rels in albums.items():
        exists_smart = aname.lower() in names
        print(f"  {aname}: photos {len(rels)}{', not found ' + str(amiss[aname]) if amiss[aname] else ''}"
              f"{', the smart album already exists' if exists_smart else ''}")
        if a.apply:
            tid = tag_id(db, aname, True)
            for rel in rels:
                db.execute("INSERT OR IGNORE INTO item_tags(path, tag_id, source) VALUES (?,?,'synofoto')", (rel, tid))
            if not exists_smart:
                db.execute("INSERT INTO smart_albums(name, criteria, created_by, created) VALUES (?,?,?,?)",
                           (aname, json.dumps({"tags": [tid]}), "synofoto", int(time.time())))
                names.add(aname.lower())
    print(f"New tag assignments in total: {added_total}")
    print("DONE" if a.apply else "DRY RUN - nothing was written (add --apply)")


if __name__ == "__main__":
    main(sys.argv[1:])
