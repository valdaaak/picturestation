# SPDX-License-Identifier: GPL-3.0-or-later
"""Administracia pre webovu galeriu (/api/admin/*). Len pre adminov.

Ochrana proti CSRF: POST musi mat Content-Type application/json (formular z cudzej stranky
ho bez CORS preflightu poslat nevie) a session cookie ma SameSite=Lax.
"""
import collections
import json
import os

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from . import catalog, config, ids, media, store


class AdminError(Exception):
    def __init__(self, msg, status=400):
        super().__init__(msg)
        self.msg, self.status = msg, status


def _admin_user(req: Request):
    sid = req.cookies.get(config.SESSION_COOKIE)
    user = store.session_user(sid)
    if not user:
        raise AdminError("Nie si prihlásený.", 401)
    u = store.get_user(user)
    if not u or not u["admin"]:
        raise AdminError("Na nastavenia treba admina.", 403)
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
            raise AdminError("Skupina neexistuje.")
        return store.GROUP_PREFIX + name
    if t == "user":
        if not store.get_user(name):
            raise AdminError("Používateľ neexistuje.")
        return name
    raise AdminError("Neznámy typ.")


def _grants(principal: str):
    return [{"path": r["path"], "deny": bool(r["deny"])} for r in store.db().execute(
        "SELECT path, deny FROM access WHERE username=? ORDER BY path", (principal,))]


def _password(pw):
    pw = pw or ""
    if len(pw) < 8:
        raise AdminError("Heslo musí mať aspoň 8 znakov.")
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
    return {"users": users, "groups": groups, "guest": {"grants": _grants(store.GUEST)},
            "settings": {"title": store.get_setting("title", config.TITLE), **store.flags(),
                         "root_album_order": store.get_setting("root_album_order", "asc")}}


def user_create(_me, b):
    name = (b.get("username") or "").strip()
    if not store.valid_name(name):
        raise AdminError("Neplatné meno.")
    if store.get_user(name):
        raise AdminError("Taký používateľ už existuje.")
    store.db().execute("INSERT INTO users(username, pw_hash, admin, note) VALUES (?,?,?,?)",
                       (name, _password(b.get("password")), int(bool(b.get("admin"))), (b.get("note") or "").strip()))
    return {"ok": True}


def user_update(me, b):
    name = b.get("username") or ""
    u = store.get_user(name)
    if not u:
        raise AdminError("Používateľ neexistuje.")
    db = store.db()
    if "admin" in b and not b["admin"] and u["admin"] and _admins_left(exclude=name) == 0:
        raise AdminError("Aspoň jeden admin musí zostať.")
    if b.get("disabled") and u["admin"] and _admins_left(exclude=name) == 0:
        raise AdminError("Posledného admina nemožno zablokovať.")
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
        raise AdminError("Používateľ neexistuje.")
    if name.lower() == me.lower():
        raise AdminError("Sám seba zmazať nemôžeš.")
    if u["admin"] and _admins_left(exclude=name) == 0:
        raise AdminError("Aspoň jeden admin musí zostať.")
    db = store.db()
    for sql in ("DELETE FROM users WHERE username=?", "DELETE FROM access WHERE username=?",
                "DELETE FROM sessions WHERE username=?", "DELETE FROM group_members WHERE username=?"):
        db.execute(sql, (name,))
    return {"ok": True}


def group_create(_me, b):
    name = (b.get("name") or "").strip()
    if not store.valid_name(name):
        raise AdminError("Neplatný názov skupiny.")
    if store.db().execute("SELECT 1 FROM groups WHERE name=?", (name,)).fetchone():
        raise AdminError("Taká skupina už existuje.")
    store.db().execute("INSERT INTO groups VALUES (?,?)", (name, (b.get("note") or "").strip()))
    return {"ok": True}


def group_update(_me, b):
    name = b.get("name") or ""
    db = store.db()
    if not db.execute("SELECT 1 FROM groups WHERE name=?", (name,)).fetchone():
        raise AdminError("Skupina neexistuje.")
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
        raise AdminError("Neplatná cesta.")
    try:
        rel = ids.clean_rel(b.get("path") or "")
    except ids.BadId:
        raise AdminError("Neplatná cesta.")
    if not os.path.isdir(ids.abs_path(rel)):
        raise AdminError("Taký album neexistuje.")
    deny = bool(b.get("deny"))
    if deny and rel == "":
        raise AdminError("Celú knižnicu vylúčiť nemožno, stačí odobrať prístup.")
    # povolenie a vylucenie toho isteho albumu sa navzajom nahradia
    store.db().execute("INSERT OR REPLACE INTO access(username, path, deny) VALUES (?,?,?)", (pr, rel, int(deny)))
    return {"ok": True}


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
            return {"rule": None, "effective": "all", "via": "admin vidí všetko"}
        rule = None if path not in own else ("deny" if own[path] else "allow")
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
            src = ""
            if not bown and t == "user":
                which = [g for g in sorted(groups) if store.db().execute(
                    "SELECT 1 FROM access WHERE username=? AND path=? AND deny=?",
                    (store.GROUP_PREFIX + g, bpath, int(bdeny))).fetchone()]
                src = " (skupina " + ", ".join(which or sorted(groups)) + ")"
            via = ("vylúčené v " if bdeny else "povolené cez ") + (bpath or "celú knižnicu") + src
        return {"rule": rule, "effective": eff, "via": via}

    return state


def access_view(_me, b):
    """Editor pristupu: pre album a jeho podalbumy pravidlo principala a vysledny pristup."""
    pr = _principal(b)
    try:
        rel = ids.clean_rel(b.get("path") or "")
        dirs, files = media.list_dir(rel)
    except (ids.BadId, OSError):
        raise AdminError("Album neexistuje.")
    state = _state_fn(b.get("type"), pr)
    return {"path": rel, "self": state(rel), "files": len(files),
            "albums": [{"name": d["name"], "path": d["rel"], **state(d["rel"])} for d in dirs]}


def album_access(_me, b):
    """Pristup k jednemu albumu z pohladu vsetkych skupin, pouzivatelov a hosti."""
    rel = _album_path(b)
    db = store.db()
    out = []
    for g in db.execute("SELECT name FROM groups ORDER BY name COLLATE NOCASE"):
        out.append({"type": "group", "name": g["name"], "label": "Skupina " + g["name"],
                    **_state_fn("group", store.GROUP_PREFIX + g["name"])(rel)})
    for u in db.execute("SELECT username, admin, disabled FROM users ORDER BY username COLLATE NOCASE"):
        if u["admin"]:
            continue  # admin vidi vsetko, nema zmysel ho nastavovat
        out.append({"type": "user", "name": u["username"], "label": u["username"] + (" (zablokovaný)" if u["disabled"] else ""),
                    **_state_fn("user", u["username"])(rel)})
    out.append({"type": "guest", "name": "", "label": "Bez prihlásenia", **_state_fn("guest", store.GUEST)(rel)})
    return {"path": rel, "principals": out}


def revoke(_me, b):
    pr = _principal(b)
    if not isinstance(b.get("path") or "", str):
        raise AdminError("Neplatná cesta.")
    store.db().execute("DELETE FROM access WHERE username=? AND path=?", (pr, b.get("path") or ""))
    return {"ok": True}


def albums(_me, b):
    try:
        rel = ids.clean_rel(b.get("path") or "")
        dirs, files = media.list_dir(rel)
    except (ids.BadId, OSError):
        raise AdminError("Album neexistuje.")
    return {"path": rel, "albums": [d["name"] for d in dirs], "files": len(files)}


def settings(_me, b):
    if "title" in b:
        t = (b["title"] or "").strip()[:100]
        store.set_setting("title", t or None)
    for k in store.FLAGS:
        if k in b:
            store.set_setting(k, "1" if b[k] else "0")
    if "root_album_order" in b:
        store.set_setting("root_album_order", "desc" if b["root_album_order"] == "desc" else "asc")
    return {"ok": True}


def _album_path(b) -> str:
    try:
        rel = ids.clean_rel(b.get("path") or "")
    except ids.BadId:
        raise AdminError("Neplatná cesta.")
    if not rel or not os.path.isdir(ids.abs_path(rel)):
        raise AdminError("Taký album neexistuje.")
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
                raise AdminError("Neplatná titulná fotka.")
            if not (cov == rel or cov.startswith(rel + "/")) or not media._exists_media(cov):
                raise AdminError("Titulná fotka musí byť z tohto albumu.")
        cur["cover"] = cov or None
    if "mode" in b:
        mode = b["mode"]
        if mode not in ("private", "public", "password"):
            raise AdminError("Neznámy typ prístupu.")
        if mode == "password":
            if b.get("password"):
                if len(b["password"]) < 4:
                    raise AdminError("Heslo albumu musí mať aspoň 4 znaky.")
                cur["pw_hash"] = store.hash_pw(b["password"])
            elif not cur["pw_hash"]:
                raise AdminError("Zadaj heslo albumu.")
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
    return {"ok": True}


def share_create(me, b):
    try:
        rel = ids.clean_rel(b.get("path") or "")
    except ids.BadId:
        raise AdminError("Neplatná cesta.")
    if not rel:
        raise AdminError("Celú knižnicu zdieľať nemožno.")
    p = ids.abs_path(rel)
    if os.path.isdir(p):
        kind = "album"
    elif os.path.isfile(p) and media.kind_of(rel):
        kind = media.kind_of(rel)
    else:
        raise AdminError("Taký album ani súbor neexistuje.")
    days = int(b.get("days") or 0)
    if days < 0 or days > 3650:
        raise AdminError("Neplatná platnosť.")
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


def _file_rel(b) -> str:
    try:
        rel = ids.clean_rel(b.get("path") or "")
    except ids.BadId:
        raise AdminError("Neplatná cesta.")
    if not rel or not media._exists_media(rel):
        raise AdminError("Taký súbor neexistuje.")
    return rel


def tag_add(_me, b):
    rel = _file_rel(b)
    name = " ".join((b.get("name") or "").split())[:64]
    if not name:
        raise AdminError("Zadaj názov tagu.")
    db = store.db()
    db.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (name,))
    tid = db.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()["id"]
    db.execute("INSERT OR IGNORE INTO item_tags(path, tag_id, source) VALUES (?,?,'manual')", (rel, tid))
    db.execute("DELETE FROM tag_suppress WHERE path=? AND tag_id=?", (rel, tid))
    return {"ok": True, "id": f"tag_{tid}"}


def tag_remove(_me, b):
    rel = _file_rel(b)
    t = catalog.parse_tag_id(b.get("tag") or "")
    if not t or t[0] != "desc":
        raise AdminError("Neplatný tag.")
    db = store.db()
    row = db.execute("SELECT source FROM item_tags WHERE path=? AND tag_id=?", (rel, t[1])).fetchone()
    if row and row["source"] == "file":
        # klucove slovo je v subore: zapamatat, aby ho indexer znova nepridal
        db.execute("INSERT OR IGNORE INTO tag_suppress VALUES (?,?)", (rel, t[1]))
    db.execute("DELETE FROM item_tags WHERE path=? AND tag_id=?", (rel, t[1]))
    # nepouzity tag zmazat
    if not db.execute("SELECT 1 FROM item_tags WHERE tag_id=? UNION SELECT 1 FROM tag_suppress WHERE tag_id=?",
                      (t[1], t[1])).fetchone():
        db.execute("DELETE FROM tags WHERE id=?", (t[1],))
    return {"ok": True}


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
                raise AdminError("Dátum má tvar RRRR-MM-DD.")
            out[k] = v
    if c.get("types"):
        out["types"] = [t for t in c["types"] if t in ("photo", "video")]
    if c.get("path"):
        try:
            out["path"] = ids.clean_rel(c["path"])
        except ids.BadId:
            raise AdminError("Neplatný album.")
    if not out:
        raise AdminError("Zadaj aspoň jedno kritérium.")
    return out


def smart_save(me, b):
    name = (b.get("name") or "").strip()[:100]
    if not name:
        raise AdminError("Zadaj názov chytrého albumu.")
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
        raise AdminError("Neplatná cesta.")
    if not old or not new or not os.path.isdir(ids.abs_path(new)):
        raise AdminError("Cieľový album neexistuje.")
    if new == old or new.startswith(old + "/"):
        raise AdminError("Album nemožno presunúť do seba.")
    moves.rewrite({old: new}, None, "manual")
    store.db().execute("DELETE FROM moves_pending WHERE old=?", (old,))
    return {"ok": True}


def orphan_delete(_me, b):
    """Zmaze pravidla, vlastnosti a zdielania pre cestu, ktora uz neexistuje (aj podcesty)."""
    old = (b.get("path") or "").strip("/")
    if not old:
        raise AdminError("Neplatná cesta.")
    if os.path.isdir(ids.abs_path(old)):
        raise AdminError("Album na disku existuje, nič nemažem.")
    db = store.db()
    for t in ("access", "album_props", "unlocks"):
        db.execute(f"DELETE FROM {t} WHERE path=? OR path LIKE ?", (old, old + "/%"))
    db.execute("DELETE FROM shares WHERE kind='album' AND (path=? OR path LIKE ?)", (old, old + "/%"))
    db.execute("DELETE FROM moves_pending WHERE old=?", (old,))
    return {"ok": True}


def comment_delete(_me, b):
    store.db().execute("DELETE FROM comments WHERE id=?", (int(b.get("id") or 0),))
    return {"ok": True}


OPS = {
    "moves_state": moves_state, "moves_remap": moves_remap, "orphan_delete": orphan_delete,
    "access_view": access_view, "album_access": album_access,
    "tag_add": tag_add, "tag_remove": tag_remove, "tag_names": tag_names,
    "smart_save": smart_save, "smart_delete": smart_delete,
    "comment_delete": comment_delete,
    "share_create": share_create, "share_list": share_list, "share_delete": share_delete,
    "album_get": album_get, "album_set": album_set,
    "state": state, "user_create": user_create, "user_update": user_update, "user_delete": user_delete,
    "group_create": group_create, "group_update": group_update, "group_delete": group_delete,
    "grant": grant, "revoke": revoke, "albums": albums, "settings": settings,
}


async def endpoint(req: Request):
    op = req.path_params["op"]
    fn = OPS.get(op)
    if fn is None:
        return JSONResponse({"error": "Neznáma operácia."}, status_code=404)
    if req.method == "POST":
        if not req.headers.get("content-type", "").startswith("application/json"):
            return JSONResponse({"error": "Očakávam JSON."}, status_code=415)
        try:
            body = json.loads(await req.body() or b"{}")
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            return JSONResponse({"error": "Zlý JSON."}, status_code=400)
    else:
        if op not in ("state", "albums", "album_get", "share_list", "tag_names", "moves_state"):
            return JSONResponse({"error": "Treba POST."}, status_code=405)
        body = dict(req.query_params)
    body["_sid"] = req.cookies.get(config.SESSION_COOKIE)

    def run():
        me = _admin_user(req)
        res = fn(me, body)
        if req.method == "POST":
            media.clear_cover_cache()  # prava/titulky sa mohli zmenit
        return res

    try:
        resp = JSONResponse(await run_in_threadpool(run))
    except AdminError as e:
        resp = JSONResponse({"error": e.msg}, status_code=e.status)
    except (TypeError, ValueError, AttributeError):
        # nespravny tvar poziadavky (napr. stara verzia stranky) -> 400, nie 500
        resp = JSONResponse({"error": "Neplatná požiadavka. Obnov stránku (F5)."}, status_code=400)
    from .web_version import VERSION
    resp.headers["x-picturestation-version"] = VERSION
    return resp


routes = [Route("/api/admin/{op}", endpoint, methods=["GET", "POST"])]
