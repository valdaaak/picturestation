# SPDX-License-Identifier: GPL-3.0-or-later
"""Administracia pre webovu galeriu (/api/admin/*). Len pre adminov.

Ochrana proti CSRF: POST musi mat Content-Type application/json (formular z cudzej stranky
ho bez CORS preflightu poslat nevie) a session cookie ma SameSite=Lax.
"""
import collections
import json
import os
import threading

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from . import catalog, config, i18n, ids, media, store


class AdminError(Exception):
    def __init__(self, msg, status=400, **kw):
        super().__init__(msg)
        self.msg, self.status, self.kw = msg, status, kw


def _admin_user(req: Request):
    sid = store.request_sid(req)
    user = store.session_user(sid)
    if not user:
        raise AdminError("Not logged in.", 401)
    u = store.get_user(user)
    if not u or not u["admin"]:
        raise AdminError("Settings require an administrator.", 403)
    return u["username"]


def _admins_left(exclude=None) -> int:
    rows = store.db().execute("SELECT username FROM users WHERE admin=1 AND disabled=0").fetchall()
    return sum(1 for r in rows if not exclude or r["username"].lower() != exclude.lower())


def _principal(p: dict) -> str:
    t, name = p.get("type"), (p.get("name") or "").strip()
    if t == "guest":
        return store.GUEST
    if t == "group":
        if not store.db().execute("SELECT 1 FROM groups WHERE name=?", (name,)).fetchone():
            raise AdminError("Group does not exist.")
        return store.GROUP_PREFIX + name
    if t == "user":
        if not store.get_user(name):
            raise AdminError("User does not exist.")
        return name
    raise AdminError("Unknown type.")


def _grants(principal: str):
    return [{"path": r["path"], "deny": bool(r["deny"])} for r in store.db().execute(
        "SELECT path, deny FROM access WHERE username=? ORDER BY path", (principal,))]


def _password(pw):
    pw = pw or ""
    if len(pw) < 8:
        raise AdminError("Password must have at least 8 characters.")
    return store.hash_pw(pw)


# ---------------- operacie ----------------
def state(_me, _b):
    db = store.db()
    members = {}
    for r in db.execute("SELECT groupname, username FROM group_members ORDER BY username"):
        members.setdefault(r["groupname"].lower(), []).append(r["username"])
    users = []
    for u in db.execute("SELECT * FROM users ORDER BY username COLLATE NOCASE"):
        users.append({"username": u["username"], "admin": bool(u["admin"]), "disabled": bool(u["disabled"]),
                      "note": u["note"] or "", "grants": _grants(u["username"]),
                      "groups": [g for g, ms in members.items() if u["username"].lower() in (m.lower() for m in ms)]})
    groups = [{"name": g["name"], "note": g["note"] or "", "members": members.get(g["name"].lower(), []),
               "grants": _grants(store.GROUP_PREFIX + g["name"])}
              for g in db.execute("SELECT * FROM groups ORDER BY name COLLATE NOCASE")]
    # skupiny v users[].groups maju byt v povodnom zapise mena
    names = {g["name"].lower(): g["name"] for g in groups}
    for u in users:
        u["groups"] = sorted(names.get(g, g) for g in u["groups"])
    from . import __version__
    return {"version": __version__, "is_main": config.current().is_main,
            "best_pending": db.execute("SELECT COUNT(DISTINCT path) FROM best_proposals").fetchone()[0], "users": users, "groups": groups, "guest": {"grants": _grants(store.GUEST)},
            "settings": {"title": store.get_setting("title", store.default_title()), **store.flags(),
                         "root_album_order": store.get_setting("root_album_order", "asc"),
                         "language": store.get_setting("language", "auto") or "auto"}}


def user_create(_me, b):
    name = (b.get("username") or "").strip()
    if not store.valid_name(name):
        raise AdminError("Invalid name.")
    if store.get_user(name):
        raise AdminError("Such a user already exists.")
    store.db().execute("INSERT INTO users(username, pw_hash, admin, note) VALUES (?,?,?,?)",
                       (name, _password(b.get("password")), int(bool(b.get("admin"))), (b.get("note") or "").strip()))
    return {"ok": True}


def user_update(me, b):
    name = b.get("username") or ""
    u = store.get_user(name)
    if not u:
        raise AdminError("User does not exist.")
    db = store.db()
    if "admin" in b and not b["admin"] and u["admin"] and _admins_left(exclude=name) == 0:
        raise AdminError("At least one administrator must remain.")
    if b.get("disabled") and u["admin"] and _admins_left(exclude=name) == 0:
        raise AdminError("The last administrator cannot be disabled.")
    if "admin" in b:
        db.execute("UPDATE users SET admin=? WHERE username=?", (int(bool(b["admin"])), name))
    if "disabled" in b:
        db.execute("UPDATE users SET disabled=? WHERE username=?", (int(bool(b["disabled"])), name))
        if b["disabled"]:
            db.execute("DELETE FROM sessions WHERE username=?", (name,))
    if "note" in b:
        db.execute("UPDATE users SET note=? WHERE username=?", ((b["note"] or "").strip(), name))
    if b.get("password"):
        db.execute("UPDATE users SET pw_hash=? WHERE username=?", (_password(b["password"]), name))
        # ostatne prihlasenia zrusit; vlastne aktualne nechat
        db.execute("DELETE FROM sessions WHERE username=? AND sid<>?", (name, b.get("_sid") or ""))
    if "groups" in b:
        db.execute("DELETE FROM group_members WHERE username=?", (name,))
        for g in b["groups"] or []:
            if db.execute("SELECT 1 FROM groups WHERE name=?", (g,)).fetchone():
                db.execute("INSERT OR IGNORE INTO group_members VALUES (?,?)", (g, name))
    return {"ok": True}


def user_delete(me, b):
    name = b.get("username") or ""
    u = store.get_user(name)
    if not u:
        raise AdminError("User does not exist.")
    if name.lower() == me.lower():
        raise AdminError("You cannot delete yourself.")
    if u["admin"] and _admins_left(exclude=name) == 0:
        raise AdminError("At least one administrator must remain.")
    db = store.db()
    for sql in ("DELETE FROM users WHERE username=?", "DELETE FROM access WHERE username=?",
                "DELETE FROM sessions WHERE username=?", "DELETE FROM devices WHERE username=?",
                "DELETE FROM group_members WHERE username=?", "DELETE FROM best_proposals WHERE username=?"):
        db.execute(sql, (name,))
    return {"ok": True}


def group_create(_me, b):
    name = (b.get("name") or "").strip()
    if not store.valid_name(name):
        raise AdminError("Invalid group name.")
    if store.db().execute("SELECT 1 FROM groups WHERE name=?", (name,)).fetchone():
        raise AdminError("Such a group already exists.")
    store.db().execute("INSERT INTO groups VALUES (?,?)", (name, (b.get("note") or "").strip()))
    return {"ok": True}


def group_update(_me, b):
    name = b.get("name") or ""
    db = store.db()
    if not db.execute("SELECT 1 FROM groups WHERE name=?", (name,)).fetchone():
        raise AdminError("Group does not exist.")
    if "note" in b:
        db.execute("UPDATE groups SET note=? WHERE name=?", ((b["note"] or "").strip(), name))
    if "members" in b:
        db.execute("DELETE FROM group_members WHERE groupname=?", (name,))
        for m in b["members"] or []:
            if store.get_user(m):
                db.execute("INSERT OR IGNORE INTO group_members VALUES (?,?)", (name, m))
    return {"ok": True}


def group_delete(_me, b):
    name = b.get("name") or ""
    db = store.db()
    db.execute("DELETE FROM groups WHERE name=?", (name,))
    db.execute("DELETE FROM group_members WHERE groupname=?", (name,))
    db.execute("DELETE FROM access WHERE username=?", (store.GROUP_PREFIX + name,))
    return {"ok": True}


def grant(_me, b):
    pr = _principal(b)
    if not isinstance(b.get("path") or "", str):
        raise AdminError("Invalid path.")
    try:
        rel = ids.clean_rel(b.get("path") or "")
    except ids.BadId:
        raise AdminError("Invalid path.")
    if not os.path.isdir(ids.abs_path(rel)):
        raise AdminError("No such album.")
    deny = bool(b.get("deny"))
    if deny and rel == "":
        raise AdminError("The whole library cannot be excluded, remove the access instead.")
    db = store.db()
    removed = 0
    if b.get("clear_below") and not deny:
        # "allow everything inside": the principal's own rules in sub-albums go (groups keep theirs)
        below = _rules_below(pr, rel)
        for p in below:
            db.execute("DELETE FROM access WHERE username=? AND path=?", (pr, p))
        removed = len(below)
    # povolenie a vylucenie toho isteho albumu sa navzajom nahradia
    db.execute("INSERT OR REPLACE INTO access(username, path, deny) VALUES (?,?,?)", (pr, rel, int(deny)))
    return {"ok": True, "removed": removed}


def _rules_below(pr, rel) -> list:
    """Paths of the principal's own rules inside album rel (not rel itself)."""
    return sorted(r["path"] for r in store.db().execute("SELECT path FROM access WHERE username=?", (pr,))
                  if r["path"] != rel and (rel == "" or r["path"].startswith(rel + "/")))


def _state_fn(t, pr):
    """Funkcia path -> {rule, effective, via} pre principala (user / skupina / host)."""
    own = {r["path"]: bool(r["deny"]) for r in store.db().execute("SELECT path, deny FROM access WHERE username=?", (pr,))}
    if t == "user":
        perm = store._perm_base(pr)
        groups = {r["groupname"] for r in store.db().execute("SELECT groupname FROM group_members WHERE username=?", (pr,))}
    else:
        rows = [{"path": p, "deny": int(d), "_own": 1} for p, d in own.items()]
        perm = store.Perm(pr, False, rows)
        groups = set()

    def state(path):
        if perm.admin:
            return {"rule": None, "effective": "all", "via": {"admin": True}}
        rule = None if path not in own else ("deny" if own[path] else "allow")
        below = sorted(p for p in own if p != path and (path == "" or p.startswith(path + "/")))
        if perm.can_browse(path):
            eff = "yes"
        elif perm.is_ancestor(path):
            eff = "path"
        else:
            eff = "no"
        via = None
        br = perm.best_rule(path)
        if br and path not in own:
            bpath, bdeny, bown = br
            via = {"deny": bool(bdeny), "path": bpath, "groups": []}
            if not bown and t == "user":
                which = [g for g in sorted(groups) if store.db().execute(
                    "SELECT 1 FROM access WHERE username=? AND path=? AND deny=?",
                    (store.GROUP_PREFIX + g, bpath, int(bdeny))).fetchone()]
                via["groups"] = which or sorted(groups)
        return {"rule": rule, "effective": eff, "via": via, "below": below}

    return state


def access_view(_me, b):
    """Editor pristupu: pre album a jeho podalbumy pravidlo principala a vysledny pristup."""
    pr = _principal(b)
    try:
        rel = ids.clean_rel(b.get("path") or "")
        dirs, files = media.list_dir(rel)
    except (ids.BadId, OSError):
        raise AdminError("Album does not exist.")
    state = _state_fn(b.get("type"), pr)
    return {"path": rel, "self": state(rel), "files": len(files),
            "albums": [{"name": d["name"], "path": d["rel"], **state(d["rel"])} for d in dirs]}


def album_access(_me, b):
    """Pristup k jednemu albumu z pohladu vsetkych skupin, pouzivatelov a hosti."""
    rel = _album_path(b)
    db = store.db()
    out = []
    for g in db.execute("SELECT name FROM groups ORDER BY name COLLATE NOCASE"):
        out.append({"type": "group", "name": g["name"],
                    **_state_fn("group", store.GROUP_PREFIX + g["name"])(rel)})
    for u in db.execute("SELECT username, admin, disabled FROM users ORDER BY username COLLATE NOCASE"):
        if u["admin"]:
            continue  # admin vidi vsetko, nema zmysel ho nastavovat
        out.append({"type": "user", "name": u["username"], "disabled": bool(u["disabled"]),
                    **_state_fn("user", u["username"])(rel)})
    out.append({"type": "guest", "name": "", **_state_fn("guest", store.GUEST)(rel)})
    return {"path": rel, "principals": out}


def revoke(_me, b):
    pr = _principal(b)
    if not isinstance(b.get("path") or "", str):
        raise AdminError("Invalid path.")
    store.db().execute("DELETE FROM access WHERE username=? AND path=?", (pr, b.get("path") or ""))
    return {"ok": True}


def albums(_me, b):
    try:
        rel = ids.clean_rel(b.get("path") or "")
        dirs, files = media.list_dir(rel)
    except (ids.BadId, OSError):
        raise AdminError("Album does not exist.")
    return {"path": rel, "albums": [d["name"] for d in dirs], "files": len(files)}


def settings(_me, b):
    if "title" in b:
        t = (b["title"] or "").strip()[:100]
        store.set_setting("title", t or None)
    live = store.flag("live_photos")
    for k in store.FLAGS:
        if k in b:
            store.set_setting(k, "1" if b[k] else "0")
    if store.flag("live_photos") != live:
        catalog.invalidate()  # the library list hides or shows the motion videos again
    if "root_album_order" in b:
        store.set_setting("root_album_order", "desc" if b["root_album_order"] == "desc" else "asc")
    if "language" in b:
        store.set_setting("language", b["language"] if b["language"] in i18n.LANGS else "auto")
    return {"ok": True}


def _album_path(b) -> str:
    try:
        rel = ids.clean_rel(b.get("path") or "")
    except ids.BadId:
        raise AdminError("Invalid path.")
    if not rel or not os.path.isdir(ids.abs_path(rel)):
        raise AdminError("No such album.")
    return rel


def album_get(_me, b):
    rel = _album_path(b)
    pr = store.album_props(rel)
    public = store.db().execute("SELECT 1 FROM access WHERE username=? AND path=? AND deny=0",
                                (store.GUEST, rel)).fetchone()
    mode = "password" if pr and pr["mode"] == "password" else ("public" if public else "private")
    rows = store.db().execute("SELECT username, deny FROM access WHERE path=? AND username<>?",
                              (rel, store.GUEST)).fetchall()
    label = lambda w: ("skupina " + w[1:]) if w.startswith(store.GROUP_PREFIX) else w
    who = [r["username"] for r in rows if not r["deny"]]
    return {"path": rel, "title": (pr["title"] or "") if pr else "", "description": (pr["description"] or "") if pr else "",
            "cover": (pr["cover"] or "") if pr else "", "ea_cover": media._ea_cover(rel) or "",
            "mode": mode, "has_password": bool(pr and pr["pw_hash"]),
            "album_order": (pr["album_order"] or "asc") if pr else "asc",
            "users": [w for w in who if not w.startswith(store.GROUP_PREFIX)],
            "groups": [w[1:] for w in who if w.startswith(store.GROUP_PREFIX)],
            "excluded": [label(r["username"]) for r in rows if r["deny"]]}


def album_set(_me, b):
    rel = _album_path(b)
    db = store.db()
    pr = store.album_props(rel)
    cur = dict(pr) if pr else {"path": rel, "title": None, "description": None, "cover": None, "mode": "private",
                                "pw_hash": None, "album_order": None}
    if "title" in b:
        cur["title"] = (b["title"] or "").strip()[:200] or None
    if "description" in b:
        cur["description"] = (b["description"] or "").strip()[:5000] or None
    if "cover" in b:
        cov = (b["cover"] or "").strip()
        if cov:
            try:
                cov = ids.clean_rel(cov)
            except ids.BadId:
                raise AdminError("Invalid cover photo.")
            if not (cov == rel or cov.startswith(rel + "/")) or not media._exists_media(cov):
                raise AdminError("The cover photo must be from this album.")
        cur["cover"] = cov or None
    if "mode" in b:
        mode = b["mode"]
        if mode not in ("private", "public", "password"):
            raise AdminError("Unknown access type.")
        if mode == "password":
            if b.get("password"):
                if len(b["password"]) < 4:
                    raise AdminError("Album password must have at least 4 characters.")
                cur["pw_hash"] = store.hash_pw(b["password"])
            elif not cur["pw_hash"]:
                raise AdminError("Enter the album password.")
            cur["mode"] = "password"
            db.execute("DELETE FROM access WHERE username=? AND path=?", (store.GUEST, rel))
        else:
            if cur["mode"] == "password" or b.get("password") is not None:
                # zmena hesla/zrusenie: odomknutia prestanu platit
                db.execute("DELETE FROM unlocks WHERE path=?", (rel,))
            cur["mode"], cur["pw_hash"] = "private", None
            if mode == "public":
                db.execute("INSERT OR REPLACE INTO access(username, path, deny) VALUES (?,?,0)", (store.GUEST, rel))
            else:
                db.execute("DELETE FROM access WHERE username=? AND path=?", (store.GUEST, rel))
        if mode == "password" and b.get("password"):
            db.execute("DELETE FROM unlocks WHERE path=?", (rel,))
    if "album_order" in b:
        cur["album_order"] = "desc" if b["album_order"] == "desc" else None
    db.execute("INSERT OR REPLACE INTO album_props(path, title, description, cover, mode, pw_hash, album_order) "
               "VALUES (?,?,?,?,?,?,?)",
               (rel, cur["title"], cur["description"], cur["cover"], cur["mode"], cur["pw_hash"], cur.get("album_order")))
    media.clear_cover_cache()
    if "cover" in b and cur["cover"]:
        return {"ok": True, "synology": push_cover(rel, cur["cover"])}
    return {"ok": True}


def push_cover(album, cover) -> str:
    """Sets the cover of the folder in Synology Photos too, when writing there is turned on (SYNO_WRITE_TAGS).
    The cover in the gallery stays whatever happens there: 'ok', 'missing' (Synology Photos does not have the
    folder or the file), 'failed' or 'off'. Resetting a cover here leaves Synology Photos as it is."""
    from . import synosync
    if not synosync.write_enabled():
        return "off"
    try:
        return synosync.push_cover(album, cover)
    except Exception as e:
        synosync.log.warning("cover %s of %s not written to Synology Photos: %s", cover, album, e)
        return "failed"


def share_create(me, b):
    try:
        rel = ids.clean_rel(b.get("path") or "")
    except ids.BadId:
        raise AdminError("Invalid path.")
    if not rel:
        raise AdminError("The whole library cannot be shared.")
    p = ids.abs_path(rel)
    if os.path.isdir(p):
        kind = "album"
    elif os.path.isfile(p) and media.kind_of(rel):
        kind = media.kind_of(rel)
    else:
        raise AdminError("No such album or file.")
    days = int(b.get("days") or 0)
    if days < 0 or days > 3650:
        raise AdminError("Invalid validity.")
    token = store.share_create(rel, kind, me, days, b.get("allow_download"), (b.get("note") or "").strip()[:200])
    return {"token": token}


def share_list(_me, _b):
    now = int(__import__("time").time())
    out = []
    for r in store.db().execute("SELECT * FROM shares ORDER BY created DESC"):
        out.append({"token": r["token"], "path": r["path"], "kind": r["kind"], "created_by": r["created_by"],
                    "created": r["created"], "expires": r["expires"], "expired": bool(r["expires"] and r["expires"] < now),
                    "allow_download": bool(r["allow_download"]), "note": r["note"] or ""})
    return {"shares": out}


def share_delete(_me, b):
    store.db().execute("DELETE FROM shares WHERE token=?", (b.get("token") or "",))
    return {"ok": True}


# ---------- paired TVs (the LG TV app, LGTV/): the TV shows a code, the administrator allows it here ----------
def device_pair(_me, b):
    from . import pairing
    u = store.get_user((b.get("user") or "").strip())
    if not u or u["disabled"]:
        raise AdminError("User does not exist.")
    try:
        return pairing.approve(b.get("code") or "", u["username"])
    except KeyError:
        raise AdminError("Unknown or expired code. Check it on the TV; after 10 minutes it shows a new one.")


def device_list(_me, _b):
    return {"devices": store.device_list()}


def device_delete(_me, b):
    store.device_delete(int(b.get("id") or 0))
    return {"ok": True}


def device_rename(_me, b):
    name = " ".join(str(b.get("name") or "").split())[:60]   # the same shape as the name a TV sends (pairing.py)
    if not name:
        raise AdminError("Enter a name.")
    if not store.device_rename(int(b.get("id") or 0), name):
        raise AdminError("No such device.")
    return {"ok": True, "name": name}


def _file_rel(b) -> str:
    try:
        rel = ids.clean_rel(b.get("path") or "")
    except ids.BadId:
        raise AdminError("Invalid path.")
    if not rel or not media._exists_media(rel):
        raise AdminError("No such file.")
    return rel


def tag_add(_me, b):
    rel = _file_rel(b)
    name = " ".join((b.get("name") or "").split())[:64]
    if not name:
        raise AdminError("Enter a tag name.")
    db = store.db()
    db.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (name,))
    tid = db.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()["id"]
    db.execute("INSERT OR IGNORE INTO item_tags(path, tag_id, source) VALUES (?,?,'manual')", (rel, tid))
    db.execute("DELETE FROM tag_suppress WHERE path=? AND tag_id=?", (rel, tid))
    return {"ok": True, "id": f"tag_{tid}", "synology": _push_tag(rel, name, True)}


def _push_tag(rel, name, add) -> str:
    """Writes the change to Synology Photos too, when that is turned on (SYNO_WRITE_TAGS). The tag in the gallery
    stays whatever happens there: 'ok', 'missing' (Synology Photos does not have the file), 'failed' or 'off'."""
    from . import synosync
    if not synosync.write_enabled():
        return "off"
    try:
        return synosync.push_tag(rel, name, add)
    except Exception as e:
        synosync.log.warning("tag %s %r on %s not written to Synology Photos: %s", "add" if add else "remove", name, rel, e)
        return "failed"


def tag_remove(_me, b):
    rel = _file_rel(b)
    t = catalog.parse_tag_id(b.get("tag") or "")
    if not t or t[0] != "desc":
        raise AdminError("Invalid tag.")
    db = store.db()
    row = db.execute("SELECT source FROM item_tags WHERE path=? AND tag_id=?", (rel, t[1])).fetchone()
    nm = db.execute("SELECT name FROM tags WHERE id=?", (t[1],)).fetchone()
    pushed = _push_tag(rel, nm["name"], False) if row and nm else "off"
    # klucove slovo v subore alebo tag v Synology Photos: zapamatat, aby ho indexer ani preberanie znova nepridali.
    # Tag odobraty aj v Synology Photos si pamatat netreba: ked ho tam niekto prida znova, ma sa vratit.
    if row and (row["source"] == "file" or (row["source"] == "synology" and pushed != "ok")):
        db.execute("INSERT OR IGNORE INTO tag_suppress VALUES (?,?)", (rel, t[1]))
    db.execute("DELETE FROM item_tags WHERE path=? AND tag_id=?", (rel, t[1]))
    # nepouzity tag zmazat
    if not db.execute("SELECT 1 FROM item_tags WHERE tag_id=? UNION SELECT 1 FROM tag_suppress WHERE tag_id=?",
                      (t[1], t[1])).fetchone():
        db.execute("DELETE FROM tags WHERE id=?", (t[1],))
    return {"ok": True, "synology": pushed}


def best_list(me, b):
    """Navrhy na Best Foto, ktore cakaju na admina: jedna polozka na fotku, s tym, kto ju navrhol."""
    from . import app as api
    ctx = api.Ctx(None, {}, b.get("_sid"), me)
    db, have, by = store.db(), catalog.best_paths(), {}
    for r in db.execute("SELECT path, username, created FROM best_proposals ORDER BY created, username"):
        by.setdefault(r["path"], []).append(r)
    items, missing = [], 0
    for path, rows in by.items():
        if path in have:  # tag medzitym pribudol inak (subor, Synology Photos, rucne) -> navrh je vybaveny
            db.execute("DELETE FROM best_proposals WHERE path=?", (path,))
            continue
        try:
            item = api.media_item(ctx, media.file_entry(path))
        except (OSError, ids.BadId):
            missing += 1  # subor teraz nie je dostupny; navrh nechat, moze sa vratit (presun, odpojeny disk)
            continue
        items.append({"path": path, "item": item, "users": [r["username"] for r in rows], "created": rows[0]["created"]})
    return {"tag": catalog.best_name(), "items": items, "missing": missing}


def _best_paths(b):
    paths = b.get("paths")
    if not isinstance(paths, list) or not paths or not all(isinstance(p, str) for p in paths):
        raise AdminError("Invalid path.")
    return paths


def best_approve(me, b):
    db, name, done, failed = store.db(), catalog.best_name(), 0, 0
    for path in _best_paths(b):
        if not db.execute("SELECT 1 FROM best_proposals WHERE path=?", (path,)).fetchone():
            continue
        try:
            res = tag_add(me, {"path": path, "name": name})
        except AdminError:
            continue  # subor nie je -> navrh ostava
        db.execute("DELETE FROM best_proposals WHERE path=?", (path,))
        done += 1
        failed += res["synology"] in ("failed", "missing")
    return {"ok": True, "approved": done, "synology_failed": failed}


def best_reject(_me, b):
    db, n = store.db(), 0
    for path in _best_paths(b):
        n += db.execute("DELETE FROM best_proposals WHERE path=?", (path,)).rowcount > 0
    return {"ok": True, "rejected": n}


def tag_names(_me, _b):
    return {"tags": [r["name"] for r in store.db().execute("SELECT name FROM tags ORDER BY name COLLATE NOCASE")]}


def _criteria(b) -> dict:
    c = b.get("criteria") or {}
    out = {}
    if c.get("tags"):
        out["tags"] = [int(x) for x in c["tags"]]
    if c.get("places"):
        out["places"] = [str(x)[:200] for x in c["places"]]
    if c.get("countries"):
        out["countries"] = [str(x)[:3] for x in c["countries"]]
    for k in ("date_from", "date_to"):
        v = (c.get(k) or "").strip()
        if v:
            if len(v) != 10 or v[4] != "-" or v[7] != "-":
                raise AdminError("Dates use the format YYYY-MM-DD.")
            out[k] = v
    if c.get("types"):
        out["types"] = [t for t in c["types"] if t in ("photo", "video")]
    if c.get("path"):
        try:
            out["path"] = ids.clean_rel(c["path"])
        except ids.BadId:
            raise AdminError("Invalid album.")
    if not out:
        raise AdminError("Enter at least one criterion.")
    return out


def smart_save(me, b):
    name = (b.get("name") or "").strip()[:100]
    if not name:
        raise AdminError("Enter a name for the smart album.")
    crit = json.dumps(_criteria(b), ensure_ascii=False)
    db = store.db()
    sid = catalog.parse_smart_id(b.get("id") or "")
    if sid:
        db.execute("UPDATE smart_albums SET name=?, criteria=? WHERE id=?", (name, crit, sid))
    else:
        cur = db.execute("INSERT INTO smart_albums(name, criteria, created_by, created) VALUES (?,?,?,?)",
                         (name, crit, me, int(__import__("time").time())))
        sid = cur.lastrowid
    return {"ok": True, "id": f"smart_{sid}"}


def smart_delete(_me, b):
    sid = catalog.parse_smart_id(b.get("id") or "")
    store.db().execute("DELETE FROM smart_albums WHERE id=?", (sid,))
    return {"ok": True}


def _known_dirs():
    dirs = set()
    for r in store.db().execute("SELECT path FROM meta"):
        d = r["path"].rsplit("/", 1)[0] if "/" in r["path"] else ""
        while d:
            dirs.add(d)
            d = d.rsplit("/", 1)[0] if "/" in d else ""
    return dirs


def moves_state(_me, _b):
    """Historia presunov, nejednoznacne presuny a cesty v nastaveniach, ktore uz na disku nie su."""
    db = store.db()
    hist = [dict(r) for r in db.execute("SELECT old, new, kind, created FROM moves WHERE kind IN ('auto','manual') "
                                         "ORDER BY id DESC LIMIT 50")]
    pending = [{"old": r["old"], "candidates": json.loads(r["candidates"]), "created": r["created"]}
               for r in db.execute("SELECT * FROM moves_pending ORDER BY created DESC")]
    known = _known_dirs()

    def exists(p):
        return p == "" or p in known or os.path.isdir(ids.abs_path(p))

    orphans = collections.defaultdict(lambda: {"rules": 0, "props": False, "shares": 0, "smart": 0})
    for r in db.execute("SELECT path, COUNT(*) n FROM access GROUP BY path"):
        if not exists(r["path"]):
            orphans[r["path"]]["rules"] = r["n"]
    for r in db.execute("SELECT path FROM album_props"):
        if not exists(r["path"]):
            orphans[r["path"]]["props"] = True
    for r in db.execute("SELECT path, COUNT(*) n FROM shares WHERE kind='album' GROUP BY path"):
        if not exists(r["path"]):
            orphans[r["path"]]["shares"] = r["n"]
    for r in db.execute("SELECT criteria FROM smart_albums"):
        try:
            p = json.loads(r["criteria"]).get("path")
        except ValueError:
            p = None
        if p and not exists(p):
            orphans[p]["smart"] += 1
    # schovat podcesty, ak je osireny uz ich rodic (riesia sa spolu)
    top = sorted(orphans)
    top = [p for p in top if not any(p.startswith(q + "/") for q in top if q != p)]
    return {"history": hist, "pending": pending,
            "orphans": [{"path": p, **orphans[p],
                         "nested": sum(1 for q in orphans if q.startswith(p + "/"))} for p in top]}


def moves_remap(_me, b):
    """Rucny presun: vsetko naviazane na staru cestu (aj podcesty) prenesie na novu."""
    from . import moves
    old = (b.get("old") or "").strip("/")
    try:
        new = ids.clean_rel(b.get("new") or "")
    except ids.BadId:
        raise AdminError("Invalid path.")
    if not old or not new or not os.path.isdir(ids.abs_path(new)):
        raise AdminError("The target album does not exist.")
    if new == old or new.startswith(old + "/"):
        raise AdminError("An album cannot be moved into itself.")
    moves.rewrite({old: new}, None, "manual")
    store.db().execute("DELETE FROM moves_pending WHERE old=?", (old,))
    return {"ok": True}


def orphan_delete(_me, b):
    """Zmaze pravidla, vlastnosti a zdielania pre cestu, ktora uz neexistuje (aj podcesty)."""
    old = (b.get("path") or "").strip("/")
    if not old:
        raise AdminError("Invalid path.")
    if os.path.isdir(ids.abs_path(old)):
        raise AdminError("The album exists on disk, nothing deleted.")
    db = store.db()
    for t in ("access", "album_props", "unlocks"):
        db.execute(f"DELETE FROM {t} WHERE path=? OR path LIKE ?", (old, old + "/%"))
    db.execute("DELETE FROM shares WHERE kind='album' AND (path=? OR path LIKE ?)", (old, old + "/%"))
    db.execute("DELETE FROM moves_pending WHERE old=?", (old,))
    return {"ok": True}


def comment_delete(_me, b):
    store.db().execute("DELETE FROM comments WHERE id=?", (int(b.get("id") or 0),))
    return {"ok": True}


# ---------- private galleries (only from the main gallery) ----------
def _galleries_op(fn):
    def run(me, b):
        if not config.current().is_main:
            raise AdminError("Galleries are managed in the main gallery.", 403)
        from . import galleries
        try:
            return fn(galleries, b) or {"ok": True}
        except galleries.GalleryError as e:
            raise AdminError(e.msg, **e.kw)
    return run


def _gallery_index_soon(name):
    from . import galleries
    g = galleries.by_name(name)
    if g is not None:
        threading.Thread(target=media.index_gallery, args=(g,), name="index-" + name, daemon=True).start()


def _g_list(gal, b):
    return {"galleries": gal.listing(), "roots": config.GALLERY_ROOTS}


def _g_create(gal, b):
    gal.create(b.get("name"), b.get("title"), b.get("root"), b.get("hostnames", ""), b.get("admin"), b.get("password"))
    _gallery_index_soon((b.get("name") or "").strip().lower())


def _g_update(gal, b):
    gal.update(b.get("name"), title=b.get("title"), root=b.get("root"), hosts=b.get("hostnames"),
               enabled=b.get("enabled"))
    if b.get("root") is not None or b.get("enabled"):
        _gallery_index_soon(b.get("name"))


OPS_GALLERIES = {
    "galleries_list": _galleries_op(_g_list),
    "gallery_create": _galleries_op(_g_create),
    "gallery_update": _galleries_op(_g_update),
    "gallery_delete": _galleries_op(lambda gal, b: gal.delete(b.get("name"))),
    "gallery_admin_set": _galleries_op(lambda gal, b: gal.set_admin(b.get("name"), b.get("user"), b.get("password"))),
    "gallery_admin_remove": _galleries_op(lambda gal, b: gal.remove_admin(b.get("name"), b.get("user"))),
}


OPS = {
    **OPS_GALLERIES,
    "moves_state": moves_state, "moves_remap": moves_remap, "orphan_delete": orphan_delete,
    "access_view": access_view, "album_access": album_access,
    "tag_add": tag_add, "tag_remove": tag_remove, "tag_names": tag_names,
    "best_list": best_list, "best_approve": best_approve, "best_reject": best_reject,
    "smart_save": smart_save, "smart_delete": smart_delete,
    "comment_delete": comment_delete,
    "share_create": share_create, "share_list": share_list, "share_delete": share_delete,
    "device_pair": device_pair, "device_list": device_list, "device_delete": device_delete, "device_rename": device_rename,
    "album_get": album_get, "album_set": album_set,
    "state": state, "user_create": user_create, "user_update": user_update, "user_delete": user_delete,
    "group_create": group_create, "group_update": group_update, "group_delete": group_delete,
    "grant": grant, "revoke": revoke, "albums": albums, "settings": settings,
}


async def endpoint(req: Request):
    op = req.path_params["op"]
    lang = await run_in_threadpool(i18n.for_request, req)
    fn = OPS.get(op)
    if fn is None:
        return JSONResponse({"error": i18n.tr("Unknown operation.", lang)}, status_code=404)
    if req.method == "POST":
        if not req.headers.get("content-type", "").startswith("application/json"):
            return JSONResponse({"error": i18n.tr("JSON expected.", lang)}, status_code=415)
        try:
            body = json.loads(await req.body() or b"{}")
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            return JSONResponse({"error": i18n.tr("Bad JSON.", lang)}, status_code=400)
    else:
        if op not in ("state", "albums", "album_get", "share_list", "device_list", "tag_names", "moves_state", "best_list",
                      "galleries_list"):
            return JSONResponse({"error": i18n.tr("POST required.", lang)}, status_code=405)
        body = dict(req.query_params)
    body["_sid"] = store.request_sid(req)

    def run():
        me = _admin_user(req)
        res = fn(me, body)
        if req.method == "POST":
            media.clear_cover_cache()  # prava/titulky sa mohli zmenit
            catalog.clear_covers()     # tagy a chytre albumy tiez
        return res

    try:
        resp = JSONResponse(await run_in_threadpool(run))
    except AdminError as e:
        resp = JSONResponse({"error": i18n.tr(e.msg, lang, **e.kw)}, status_code=e.status)
    except (TypeError, ValueError, AttributeError):
        # nespravny tvar poziadavky (napr. stara verzia stranky) -> 400, nie 500
        resp = JSONResponse({"error": i18n.tr("Invalid request. Reload the page (F5).", lang)}, status_code=400)
    from .web_version import VERSION
    resp.headers["x-picturestation-version"] = VERSION
    return resp


routes = [Route("/api/admin/{op}", endpoint, methods=["GET", "POST"])]
