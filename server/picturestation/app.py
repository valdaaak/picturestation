# SPDX-License-Identifier: GPL-3.0-or-later
"""HTTP API v tvare Photo Station 6 webapi (/photo/webapi/*.php)."""
import json
import logging
import os
import posixpath
import threading
import time
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import admin, catalog, config, geo, i18n, ids, media, pairing, store

log = logging.getLogger("picturestation.api")

# Chybove kody (webapi.inc.php, sdk/WebAPI.inc.php)
E_UNKNOWN, E_BAD_REQUEST, E_NO_API, E_NO_METHOD, E_VERSION, E_NO_PERM = 100, 101, 102, 103, 104, 105
E_LOGIN_NOPRIV, E_LOGIN, E_LOGIN_MAX = 406, 407, 410
E_ALBUM_PASSWORD, E_ALBUM_NO_ACCESS = 416, 417
E_PHOTO_BAD, E_PHOTO_DENY = 456, 457
E_THUMB_BAD, E_THUMB_DENY, E_THUMB_NOFILE = 501, 502, 504
E_DL_BAD, E_DL_DENY = 506, 507

# Katalog API pre SYNO.API.Info (nazov -> subor, min, max verzia).
APIS = {
    "SYNO.API.Info": ("query.php", 1, 1),
    "SYNO.PhotoStation.Auth": ("auth.php", 1, 1),
    "SYNO.PhotoStation.Info": ("info.php", 1, 2),
    "SYNO.PhotoStation.Album": ("album.php", 1, 1),
    "SYNO.PhotoStation.Permission": ("permission.php", 1, 1),
    "SYNO.PhotoStation.Photo": ("photo.php", 1, 1),
    "SYNO.PhotoStation.Thumb": ("thumb.php", 1, 1),
    "SYNO.PhotoStation.Cover": ("cover.php", 1, 2),
    "SYNO.PhotoStation.SmartAlbum": ("smart_album.php", 1, 1),
    "SYNO.PhotoStation.File": ("file.php", 1, 1),
    "SYNO.PhotoStation.Download": ("download.php", 1, 1),
    "SYNO.PhotoStation.Category": ("category.php", 1, 1),
    "SYNO.PhotoStation.About": ("about.php", 1, 1),
    "SYNO.PhotoStation.Tag": ("tag.php", 1, 1),
    "SYNO.PhotoStation.PhotoTag": ("photo_tag.php", 1, 1),
    "SYNO.PhotoStation.Comment": ("comment.php", 1, 1),
    "SYNO.PhotoStation.Timeline": ("timeline.php", 1, 1),
    "SYNO.PhotoStation.Group": ("group.php", 1, 1),
    "SYNO.PhotoStation.Rotate": ("rotate.php", 1, 1),
    "SYNO.PhotoStation.SlideshowMusic": ("slideshow_music.php", 1, 1),
    "SYNO.PhotoStation.DsmShare": ("dsm_share.php", 1, 1),
    "SYNO.PhotoStation.SharedAlbum": ("shared_album.php", 1, 2),
    "SYNO.PhotoStation.PhotoLog": ("log.php", 1, 1),
    "SYNO.PhotoStation.Path": ("path.php", 1, 1),
    "SYNO.PhotoStation.Watermark": ("watermark.php", 1, 1),
    "SYNO.PhotoStation.Public": ("public.php", 1, 1),
    "SYNO.PhotoStation.Migration": ("migration.php", 1, 1),
    "SYNO.PhotoStation.ACL": ("acl.php", 1, 1),
    "SYNO.PhotoStation.AdvancedShare": ("advanced_share.php", 1, 1),
    "SYNO.PhotoStation.AppPrivilege": ("app_privilege.php", 1, 1),
}

# Prazdne odpovede pre funkcie, ktore server zatial nema (appka ich vola, nesmie spadnut).
EMPTY = {
    ("SYNO.PhotoStation.Category", "list"): {"categories": [], "total": 0, "offset": 0},
    ("SYNO.PhotoStation.Category", "getinfo"): {"categories": [], "total": 0, "offset": 0},
    ("SYNO.PhotoStation.Category", "listitem"): {"items": [], "total": 0, "offset": 0},
    ("SYNO.PhotoStation.SharedAlbum", "list"): {"items": [], "total": 0, "offset": 0},
    ("SYNO.PhotoStation.PhotoTag", "list"): {"tags": []},
    ("SYNO.PhotoStation.Timeline", "getindex"): {"date": [], "date_objs": [], "total": 0},
}

_fails = {}  # ip -> (pocet, od kedy)
_fails_lock = threading.Lock()
MAX_FAILS, FAIL_WINDOW = 10, 600


class ApiError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def out(payload, status=200, headers=None):
    return Response(json.dumps(payload, ensure_ascii=False), status_code=status,
                    media_type="text/plain; charset=utf-8", headers=headers)


def ok(data=None):
    return out({"success": True} if data is None else {"success": True, "data": data})


def err(code, headers=None):
    return out({"success": False, "error": {"code": code}}, headers=headers)


def _int(v, default):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def restrictions(username, admin: bool) -> dict:
    """Obmedzenia z nastaveni pre daneho pouzivatela (admin ich nema)."""
    f = store.flags()
    if admin:
        return {"download": True, "hide_gps": False, "hide_detail": False, "no_timeline": False, "no_search": False,
                "comment": True, "people": True}
    return {"people": True if username else f["people_for_guest"],
            "download": f["allow_download_user"] if username else f["allow_download_guest"],
            "hide_gps": f["hide_gps"],
            "hide_detail": f["hide_detail_user"] if username else f["hide_detail_guest"],
            "no_timeline": f["disable_timeline"], "no_search": f["disable_search"],
            "comment": f["allow_comment_user"] if username else f["allow_comment_guest"]}


class Ctx:
    def __init__(self, req: Request, p: dict, sid, username):
        self.req, self.p, self.sid, self.username = req, p, sid, username
        self.new_sid = None  # nova hostovska session (odomknutie albumu heslom) -> nastavit cookie
        self.perm = store.perm_for(username, sid)
        self.additional = set(filter(None, (p.get("additional") or "").split(",")))
        self._props = None
        self._public = None
        self.r = restrictions(username, self.perm.admin)

    def props(self, rel):
        if self._props is None:
            self._props = store.all_album_props()
        return self._props.get(rel)

    def is_public(self, rel):
        if self._public is None:
            self._public = {r["path"] for r in store.db().execute(
                "SELECT path FROM access WHERE username=? AND deny=0", (store.GUEST,))}
        return rel in self._public

    def unlock(self, path):
        if not self.sid:
            self.sid = self.new_sid = store.new_session(store.GUEST)
        store.unlock(self.sid, path)
        self.perm = store.perm_for(self.username, self.sid)
        self.apply_share(self.share_token)

    share_token = None
    share = None

    def apply_share(self, token):
        """Zdielany odkaz (parameter 'share') prida pristup k albumu alebo jednemu suboru."""
        self.share_token = token
        sh = store.share_get(token) if token else None
        self.share = sh
        if sh is None:
            return
        if sh["kind"] == "album":
            self.perm.forced.add(sh["path"])
        else:
            self.perm.items.add(sh["path"])
        if not self.username:
            self.r["download"] = bool(sh["allow_download"])


# ---------------- polozky ----------------
def _dir_mtime(rel: str) -> float:
    try:
        return os.stat(ids.abs_path(rel)).st_mtime
    except OSError:
        return 0


def album_type(ctx: Ctx, rel: str) -> str:
    pr = ctx.props(rel)
    if pr and pr["mode"] == "password":
        return "password"
    return "public" if ctx.is_public(rel) else "private"


def album_item(ctx: Ctx, d: dict) -> dict:
    rel = d["rel"]
    name = posixpath.basename(rel) if rel else "/"
    locked = ctx.perm.is_locked(rel)
    cov = None if locked else media.cover(rel, ctx.perm)
    pr = ctx.props(rel)
    item = {
        "id": ids.album_id(rel),
        "type": "album",
        "thumbnail_status": "small,large" if cov else "default",
        "info": {"sharepath": rel or "/", "name": name, "title": (pr["title"] if pr and pr["title"] else name),
                 "description": (pr["description"] or "") if pr else "", "hits": "0",
                 "type": album_type(ctx, rel), "conversion": True, "allow_comment": ctx.r["comment"]},
    }
    if locked:
        item["info"]["locked"] = True
    add = {
        "album_permission": ctx.perm.album_permission(rel),
        "album_sorting": {"sort_by": "filename", "sort_direction": "asc", "sort_customized": False},
        "file_location": rel,
        "album_createdate": int(d.get("mtime") or _dir_mtime(rel)),
    }
    if cov:
        try:
            cf = media.file_entry(cov)
            cm = media.get_meta(cf)
            mt = str(int(cf["mtime"]))
            add["thumb_size"] = {"small": {**media.thumb_dims(cm, "small"), "mtime": mt},
                                 "large": {**media.thumb_dims(cm, "large"), "mtime": mt},
                                 "sig": cov.encode("utf-8").hex()}
        except (OSError, ids.BadId):
            item["thumbnail_status"] = "default"
    if "thumb_size" not in add:
        z = {"resolutionx": 0, "resolutiony": 0}
        add["thumb_size"] = {"small": dict(z), "large": dict(z), "sig": ""}
    item["additional"] = add
    return item


def media_item(ctx: Ctx, f: dict, m=None) -> dict:
    f = media.with_stat(f)
    m = m if m is not None else media.get_meta(f)
    kind, rel = f["kind"], f["rel"]
    mt = str(int(f["mtime"]))
    title = f["name"].rsplit(".", 1)[0]
    has_thumb = True
    if kind == "photo" and media.ext_of(f["name"]) not in config.PIL_EXT:
        has_thumb = media._ea_thumb(rel, "small") is not None
    if kind == "video" and not media.FFMPEG:
        has_thumb = media._ea_thumb(rel, "small") is not None
    info = {"name": f["name"], "title": title, "description": "", "createdate": media.fmt_ts(f["mtime"]),
            "takendate": m.get("taken") or media.fmt_ts(f["mtime"]), "size": f["size"],
            "resolutionx": m.get("w", 0), "resolutiony": m.get("h", 0), "rotated": False, "rating": 0}
    add = {"thumb_size": {"small": {**media.thumb_dims(m, "small"), "mtime": mt},
                          "large": {**media.thumb_dims(m, "large"), "mtime": mt},
                          "preview": {**media.thumb_dims(m, "preview"), "mtime": mt}},
           "file_location": rel}
    gps = None if ctx.r["hide_gps"] else m.get("gps")
    pk = None if ctx.r["hide_gps"] else catalog.place_key(m)
    if pk:
        info["place"] = catalog.place_label(pk)
        info["place_id"] = catalog.place_id(pk)
    if "tags" in ctx.additional:
        info["tags"] = catalog.item_tags(rel)
        if ctx.r["people"]:
            info["people"] = catalog.item_people(rel)
    if kind == "photo":
        if ctx.r["hide_detail"]:
            add["photo_exif"] = {"takendate": info["takendate"], "camera": "", "camera_model": "", "exposure": "",
                                 "aperture": "", "iso": 0, "gps": gps, "focal_length": "", "lens": "", "flash": ""}
        else:
            add["photo_exif"] = {"takendate": info["takendate"], "camera": m.get("camera", ""),
                                 "camera_model": m.get("model", ""), "exposure": m.get("exposure", ""),
                                 "aperture": m.get("aperture", ""), "iso": m.get("iso", 0), "gps": gps,
                                 "focal_length": m.get("focal", ""), "lens": m.get("lens", ""), "flash": ""}
        if gps:
            info["gps"] = gps
        motion = catalog.live_pairs()[0].get(rel)
        if motion:
            info["live"] = ids.item_id("video", motion)  # Live Photo: id of its motion video
    else:
        info["duration"] = str(m.get("duration", 0))
        add["video_codec"] = {"container": m.get("container", ""), "vcodec": m.get("vcodec", ""),
                              "acodec": m.get("acodec", ""), "resolutionx": m.get("w", 0),
                              "resolutiony": m.get("h", 0), "video_bitrate": m.get("vbitrate", 0),
                              "audio_bitrate": m.get("abitrate", 0)}
        add["video_quality"] = []
    return {"id": ids.item_id(kind, rel), "type": kind,
            "thumbnail_status": "small,large" if has_thumb else "default",
            "info": info, "additional": add}


def _sort_media(files, metas, sort_by, direction):
    desc = (direction or "").lower() == "desc"
    if sort_by in ("takendate", "timetaken"):
        key = lambda i: (metas[i].get("taken") or "", files[i]["name"].lower())
    elif sort_by in ("createdate", "mtime", "modifydate"):
        key = lambda i: (files[i]["mtime"], files[i]["name"].lower())
    elif sort_by in ("filesize", "size"):
        key = lambda i: files[i]["size"]
    else:
        key = lambda i: files[i]["name"].lower()
    order = sorted(range(len(files)), key=key, reverse=desc)
    return [files[i] for i in order], [metas[i] for i in order]


# ---------------- API ----------------
def api_query(ctx: Ctx):
    q = ctx.p.get("query", "all")
    sel = {}
    for name, (path, mn, mx) in APIS.items():
        if q == "all" or any(name == x or (x.endswith(".") and name.startswith(x)) for x in q.split(",")):
            sel[name] = {"path": path, "minVersion": mn, "maxVersion": mx}
    return ok(sel)


def auth_data(ctx: Ctx, username, sid) -> dict:
    perm = store.perm_for(username)
    r = restrictions(username, perm.admin)
    return {"sid": sid or "", "username": username or "", "reg_syno_user": bool(username),
            "is_admin": perm.admin, "allow_comment": r["comment"],
            "permission": {"browse": perm.can_see(""), "upload": False, "manage": False},
            "enable_face_recog": False, "allow_public_share": False,
            "allow_download": r["download"], "show_detail": not r["hide_detail"]}


def _client_ip(req: Request) -> str:
    return req.client.host if req.client else "?"


def _too_many_fails(req: Request) -> bool:
    now = time.time()
    with _fails_lock:
        n, since = _fails.get(_client_ip(req), (0, now))
        return now - since <= FAIL_WINDOW and n >= MAX_FAILS


def _add_fail(req: Request):
    now = time.time()
    ip = _client_ip(req)
    with _fails_lock:
        n, since = _fails.get(ip, (0, now))
        if now - since > FAIL_WINDOW:
            n, since = 0, now
        _fails[ip] = (n + 1, since)


def api_auth(ctx: Ctx):
    m = ctx.p["method"]
    if m in ("login", "photo_login"):
        ip = _client_ip(ctx.req)
        now = time.time()
        with _fails_lock:
            n, since = _fails.get(ip, (0, now))
            if now - since > FAIL_WINDOW:
                n, since = 0, now
            if n >= MAX_FAILS:
                return err(E_LOGIN_MAX)
        user = ctx.p.get("username", "")
        u = store.authenticate(user, ctx.p.get("password", ""))
        if u is None:
            with _fails_lock:
                _fails[ip] = (n + 1, since)
            log.warning("failed login %r from %s", user, ip)
            return err(E_LOGIN)
        with _fails_lock:
            _fails.pop(ip, None)
        sid = store.new_session(u["username"])
        resp = ok(auth_data(ctx, u["username"], sid))
        store.set_session_cookie(resp, ctx.req, sid)
        log.info("login %s from %s", u["username"], ip)
        return resp
    if m == "logout":
        store.drop_session(ctx.sid)
        resp = ok()
        store.clear_session_cookie(resp, ctx.req)
        return resp
    if m == "checkauth":
        return ok(auth_data(ctx, ctx.username, ctx.sid if ctx.username else ""))
    return err(E_NO_METHOD)


def api_info(ctx: Ctx):
    if ctx.p["method"] not in ("getinfo",):
        return ok({"external_ip": ""}) if ctx.p["method"] == "getexternalip" else err(E_NO_METHOD)
    return ok({
        "version": config.PKG_VERSION, "version_string": config.PKG_VERSION_STRING,
        "title": store.get_setting("title", store.default_title()),
        "hide_search": ctx.r["no_search"], "disable_timeline": ctx.r["no_timeline"],
        "home_category": "", "sort_by": "filename", "sort_direction": "asc",
        "allow_download_orig": ctx.r["download"], "allow_download_album": False, "allow_download_video": True,
        "allow_social_share": False, "allow_social_upload": False, "allow_social_upload_guest": False,
        "support_large_file": True, "hide_gps_from_normal_user": ctx.r["hide_gps"], "folder_sort_only_name": True,
        "external_host_quickconnect": "", "external_host": "", "use_dsm_account": False,
        "virtual_tag": {"people_tag": bool(ctx.r["people"] and store.db().execute("SELECT 1 FROM people LIMIT 1").fetchone()),
                        "geo_tag": geo.available(), "desc_tag": True},
        "paging_item_count": 120, "show_album_hit": False, "show_lightbox_information": True,
    })


def album_order(rel: str) -> str:
    """Zoradenie podalbumov: 'desc' = od najnovsich (podla nazvu), inak A-Z. Koren v nastaveniach."""
    if rel == "":
        return store.get_setting("root_album_order", "asc")
    pr = store.album_props(rel)
    return (pr["album_order"] if pr and pr["album_order"] else "asc")


def order_albums(albums, order: str):
    if order != "desc":
        return albums
    # nazvy zacinajuce cislom (roky, datumy) od najnovsich, ostatne za nimi abecedne
    dated = [d for d in albums if d["name"][:1].isdigit()]
    other = [d for d in albums if not d["name"][:1].isdigit()]
    return sorted(dated, key=lambda d: d["name"].lower(), reverse=True) + other


def _album_rel(ctx: Ctx, id_):
    if not id_:
        return ""
    kind, rel = ids.parse(id_)
    if kind != "album":
        raise ApiError(E_BAD_REQUEST)
    return rel


def api_album(ctx: Ctx):
    m, p = ctx.p["method"], ctx.p
    if m == "getinfo":
        items = []
        for id_ in filter(None, (p.get("id") or "").split(",")):
            rel = _album_rel(ctx, id_)
            if not ctx.perm.can_see(rel):
                raise ApiError(E_ALBUM_NO_ACCESS)
            st = os.stat(ids.abs_path(rel))
            items.append(album_item(ctx, {"rel": rel, "mtime": st.st_mtime}))
        return ok({"items": items, "total": len(items), "offset": 0})
    if m != "list":
        return err(E_NO_PERM)

    offset, limit = max(0, _int(p.get("offset"), 0)), _int(p.get("limit"), 120)
    limit = 1000 if limit <= 0 else min(limit, 5000)
    types = set(filter(None, (p.get("type") or "album,photo,video").split(",")))
    recursive = (p.get("recursive") or "").lower() == "true"
    keyword = (p.get("keyword") or "").strip().lower()

    if keyword and ctx.r["no_search"]:
        return ok({"items": [], "total": 0, "offset": offset})
    if recursive or keyword:
        return _album_list_recursive(ctx, types, offset, limit, keyword)

    rel = _album_rel(ctx, p.get("id"))
    if rel and ctx.perm.is_locked(rel):
        # album s heslom: spravne heslo ho odomkne pre tuto session (appka aj web posielaju 'password')
        owner = ctx.perm.pw_owner(rel)
        pr = store.album_props(owner)
        if not p.get("password"):
            raise ApiError(E_ALBUM_PASSWORD)
        if _too_many_fails(ctx.req):
            raise ApiError(E_LOGIN_MAX)
        if pr and pr["pw_hash"] and store.check_pw(p["password"], pr["pw_hash"]):
            ctx.unlock(owner)
        else:
            _add_fail(ctx.req)
            raise ApiError(E_ALBUM_PASSWORD)
    if rel and not ctx.perm.can_see(rel):  # koren je vzdy dostupny, len moze byt prazdny
        raise ApiError(E_ALBUM_NO_ACCESS)
    try:
        dirs, files = media.list_dir(rel)
    except FileNotFoundError:
        raise ApiError(E_ALBUM_NO_ACCESS)
    albums = [d for d in dirs if ctx.perm.can_see(d["rel"])] if "album" in types else []
    albums = order_albums(albums, album_order(rel))
    files = [f for f in files if f["kind"] in types] if ctx.perm.can_browse(rel) else []
    total = len(albums) + len(files)
    page_albums = albums[offset:offset + limit]
    rest_off = max(0, offset - len(albums))
    rest_lim = limit - len(page_albums)
    items = [album_item(ctx, d) for d in page_albums]
    if rest_lim > 0 and files:
        sort_by = (p.get("sort_by") or "filename").lower()
        if sort_by in ("filename", "name", "preference", ""):
            fs = files
            if (p.get("sort_direction") or "").lower() == "desc":
                fs = list(reversed(fs))
            for f in fs[rest_off:rest_off + rest_lim]:
                items.append(media_item(ctx, f))
        else:
            files = [media.with_stat(f) for f in files]
            metas = [media.get_meta(f) for f in files]
            fs, ms = _sort_media(files, metas, sort_by, p.get("sort_direction"))
            for f, mm in list(zip(fs, ms))[rest_off:rest_off + rest_lim]:
                items.append(media_item(ctx, f, mm))
    return ok({"items": items, "total": total, "offset": offset})


def _all_dirs():
    rows = store.db().execute("SELECT path FROM meta").fetchall()
    dirs = set()
    for r in rows:
        d = posixpath.dirname(r["path"])
        while d:
            dirs.add(d)
            d = posixpath.dirname(d)
    return sorted(dirs, key=str.lower)


def _album_list_recursive(ctx, types, offset, limit, keyword):
    """Vyhladavanie a zoznam vsetkych albumov - z indexu (plny prechod NFS by trval minuty)."""
    found = []
    if "album" in types:
        for d in _all_dirs():
            if ctx.perm.can_see(d) and (not keyword or keyword in posixpath.basename(d).lower()):
                found.append(("album", d))
    if keyword and types & {"photo", "video"}:
        # % and _ are LIKE wildcards: escaped, so that "IMG_1" finds IMG_1.jpg
        pat = "%" + keyword.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
        motion = catalog.live_pairs()[1]
        for r in store.db().execute("SELECT path, kind FROM meta WHERE lower(path) LIKE ? ESCAPE '!' ORDER BY path",
                                    (pat,)):
            if r["kind"] in types and r["path"] not in motion and keyword in posixpath.basename(r["path"]).lower() \
                    and ctx.perm.can_browse(posixpath.dirname(r["path"])):
                found.append((r["kind"], r["path"]))
    items = []
    for kind, rel in found[offset:offset + limit]:
        try:
            if kind == "album":
                items.append(album_item(ctx, {"rel": rel, "mtime": os.stat(ids.abs_path(rel)).st_mtime}))
            else:
                items.append(media_item(ctx, media.file_entry(rel)))
        except (OSError, ids.BadId):
            continue
    return ok({"items": items, "total": len(found), "offset": offset})


def _media_from_id(ctx: Ctx, id_):
    kind, rel = ids.parse(id_)
    if kind not in ("photo", "video"):
        raise ApiError(E_PHOTO_BAD)
    if not ctx.perm.can_item(rel):
        # the motion video of a Live Photo goes with its photo (also for a link sharing just that photo)
        photo = catalog.live_pairs()[1].get(rel)
        if photo is None or not ctx.perm.can_item(photo):
            raise ApiError(E_PHOTO_DENY)
    try:
        return media.file_entry(rel)
    except (OSError, FileNotFoundError):
        raise ApiError(E_PHOTO_BAD)


def api_photo(ctx: Ctx):
    m, p = ctx.p["method"], ctx.p
    if m == "getinfo":
        return ok([media_item(ctx, _media_from_id(ctx, i)) for i in filter(None, (p.get("id") or "").split(","))])
    if m == "getexif":
        f = _media_from_id(ctx, p.get("id"))
        mi = media_item(ctx, f)
        return ok({"exifs": [{"label": k, "value": str(v)} for k, v in (mi["additional"].get("photo_exif") or {}).items()
                             if v not in ("", None, 0)]})
    if m != "list":
        return err(E_NO_PERM)
    offset, limit = max(0, _int(p.get("offset"), 0)), _int(p.get("limit"), 120)
    limit = 1000 if limit <= 0 else min(limit, 5000)
    types = set(filter(None, (p.get("type") or "photo,video").split(",")))
    if p.get("filter_shared_album") or p.get("filter_category"):
        return ok({"items": [], "total": 0, "offset": offset})
    want_gps = (p.get("gps") or "").lower() == "true"
    sort_by = (p.get("sort_by") or "takendate").lower()
    direction = p.get("sort_direction") or "desc"

    if p.get("filter_tag") or p.get("filter_smart"):
        crit = (catalog.crit_for_tag(p["filter_tag"]) if p.get("filter_tag")
                else catalog.crit_for_smart(p["filter_smart"]))
        if crit is None:
            return ok({"items": [], "total": 0, "offset": offset})
        if catalog.has_location(crit) and ctx.r["hide_gps"]:
            return ok({"items": [], "total": 0, "offset": offset})
        if crit.get("people") and not ctx.r["people"]:
            return ok({"items": [], "total": 0, "offset": offset})
        found = [(f, m) for f, m in catalog.filter_items(ctx.perm, crit) if f["kind"] in types]
        files, metas = [f for f, _ in found], [m for _, m in found]
    elif p.get("filter_album"):
        files, metas = [], []
        for id_ in p["filter_album"].split(","):
            rel = _album_rel(ctx, id_)
            if not ctx.perm.can_browse(rel):
                continue
            _, fs = media.list_dir(rel)
            for f in fs:
                if f["kind"] in types:
                    f = media.with_stat(f)
                    files.append(f)
                    metas.append(media.get_meta(f))
    elif ctx.r["no_timeline"] or (want_gps and ctx.r["hide_gps"]):
        return ok({"items": [], "total": 0, "offset": offset})
    else:
        # cela kniznica (timeline) z indexu
        files, metas = [], []
        motion = catalog.live_pairs()[1]
        for r in store.db().execute("SELECT path, mtime, size, kind, data FROM meta"):
            if r["kind"] not in types or r["path"] in motion or not ctx.perm.can_browse(posixpath.dirname(r["path"])):
                continue
            files.append({"name": posixpath.basename(r["path"]), "rel": r["path"], "mtime": r["mtime"],
                          "size": r["size"], "kind": r["kind"]})
            metas.append(json.loads(r["data"]))
    if want_gps:
        keep = [i for i, mm in enumerate(metas) if mm.get("gps")]
        files, metas = [files[i] for i in keep], [metas[i] for i in keep]
    files, metas = _sort_media(files, metas, sort_by, direction)
    items = [media_item(ctx, f, mm) for f, mm in list(zip(files, metas))[offset:offset + limit]]
    return ok({"items": items, "total": len(files), "offset": offset})


def _send_file(req: Request, path: str, media_type: str, filename=None, cache=False):
    """Subor s podporou HTTP Range (video, velke originaly)."""
    st = os.stat(path)
    if not os.access(path, os.R_OK):
        # typically a file uploaded from a phone with owner-only permissions on the NAS
        log.warning("cannot read %s: check the permissions on the NAS (others need read)", path)
        return err(E_DL_DENY)
    size = st.st_size
    headers = {"Accept-Ranges": "bytes", "Last-Modified": time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(st.st_mtime))}
    if cache:
        headers["Cache-Control"] = "max-age=604800"
    if filename:
        headers["Content-Disposition"] = "inline; filename*=UTF-8''" + _quote(filename)
    rng = req.headers.get("range", "")
    start, end = 0, size - 1
    status = 200
    if rng.startswith("bytes=") and size > 0:
        a, _, b = rng[6:].split(",")[0].strip().partition("-")
        try:
            if a == "":
                start = max(0, size - int(b))
            else:
                start = int(a)
                end = min(size - 1, int(b)) if b else size - 1
            if start > end or start >= size:
                return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
            status = 206
            headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        except ValueError:
            start, end = 0, size - 1
    length = end - start + 1
    headers["Content-Length"] = str(length)
    if req.method == "HEAD":
        return Response(status_code=status, headers=headers, media_type=media_type)

    def body():
        with open(path, "rb") as fh:
            fh.seek(start)
            left = length
            while left > 0:
                chunk = fh.read(min(1024 * 1024, left))
                if not chunk:
                    break
                left -= len(chunk)
                yield chunk

    return StreamingResponse(body(), status_code=status, headers=headers, media_type=media_type)


def _quote(s):
    from urllib.parse import quote
    return quote(s, safe="")


MIME = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "jpe": "image/jpeg", "png": "image/png", "gif": "image/gif",
        "bmp": "image/bmp", "tif": "image/tiff", "tiff": "image/tiff", "heic": "image/heic", "heif": "image/heif",
        "mp4": "video/mp4", "m4v": "video/mp4", "mov": "video/quicktime", "avi": "video/x-msvideo",
        "mkv": "video/x-matroska", "mts": "video/mp2t", "m2ts": "video/mp2t", "mpg": "video/mpeg",
        "mpeg": "video/mpeg", "3gp": "video/3gpp", "wmv": "video/x-ms-wmv", "webm": "video/webm"}


def api_thumb(ctx: Ctx):
    p = ctx.p
    size = p.get("size", "")
    if size not in config.THUMB_PX or not p.get("id"):
        return err(E_THUMB_BAD)
    if p["id"].startswith(("tag_", "smart_")):
        if ctx.r["hide_gps"] and (p["id"].startswith("tag_g") or (
                p["id"].startswith("smart_") and catalog.has_location(catalog.crit_for_smart(p["id"])))):
            return err(E_THUMB_DENY)
        if p["id"].startswith("tag_p") and not ctx.r["people"]:
            return err(E_THUMB_DENY)
        if p["id"].startswith("tag_p"):
            # vyrez tvare zo Synology Photos - len ak smie vidiet fotku, z ktorej je
            from . import synosync
            t = catalog.parse_tag_id(p["id"])
            row = store.db().execute("SELECT cover_path FROM people WHERE id=?", (t[1],)).fetchone() if t else None
            fp = synosync.face_path(t[1]) if t else None
            if row and row["cover_path"] and fp and os.path.exists(fp) and ctx.perm.can_item(row["cover_path"]):
                return _send_file(ctx.req, fp, "image/jpeg", cache=True)
        rel = catalog.cover_for(p["id"], ctx.perm)
        if not rel:
            return err(E_THUMB_NOFILE)
        path = media.thumb_file(media.kind_of(rel), rel, size)
        return _send_file(ctx.req, path, "image/jpeg", cache=True) if path else err(E_THUMB_NOFILE)
    try:
        kind, rel = ids.parse(p["id"])
    except ids.BadId:
        return err(E_THUMB_BAD)
    if kind == "album":
        if not ctx.perm.can_see(rel):
            return err(E_THUMB_DENY)
        rel = media.cover(rel, ctx.perm)
        if not rel:
            return err(E_THUMB_NOFILE)
        kind = media.kind_of(rel)
    elif not ctx.perm.can_item(rel):
        return err(E_THUMB_DENY)
    try:
        path = media.thumb_file(kind, rel, size)
    except (OSError, ids.BadId):
        path = None
    if not path:
        return err(E_THUMB_NOFILE)
    return _send_file(ctx.req, path, "image/jpeg", cache=True)


def api_download(ctx: Ctx):
    m = ctx.p["method"]
    if m not in ("getphoto", "getvideo"):
        return err(E_NO_PERM)
    ua = ctx.req.headers.get("user-agent", "")[:100]  # video players (TV, phone) fetch with their own agent
    try:
        f = _media_from_id(ctx, ctx.p.get("id"))
    except ids.BadId:
        return err(E_DL_BAD)
    except ApiError as e:
        log.warning("%s denied for %s (%s): id=%s", m, ctx.username or "no session", ua, ctx.p.get("id"))
        return err(E_DL_DENY if e.code == E_PHOTO_DENY else E_DL_BAD)
    # metoda musi sediet so skutocnym typom suboru (inak by getvideo obislo zakaz stahovania fotiek)
    if (m == "getvideo") != (f["kind"] == "video"):
        return err(E_DL_BAD)
    if f["kind"] == "photo" and not ctx.r["download"]:
        return err(E_DL_DENY)  # videa ostavaju (prehravanie ide tou istou cestou)
    if m == "getvideo" and ctx.p.get("variant") == "web":
        # pre prehliadac: original ak je mp4/webm, inak prekodovana verzia z @eaDir (ak ju NAS ma)
        web = media.web_video(f["rel"])
        log.info("video %s for %s (%s): %s, range=%s", f["name"], ctx.username or "guest", ua,
                 "converted mp4" if web else "original", ctx.req.headers.get("range", "-"))
        if web:
            return _send_file(ctx.req, web, "video/mp4", filename=f["name"].rsplit(".", 1)[0] + ".mp4")
    mime = MIME.get(media.ext_of(f["name"]), "application/octet-stream")
    return _send_file(ctx.req, ids.abs_path(f["rel"]), mime, filename=f["name"])


def group_item(id_, name, count, newest, kind, extra=None) -> dict:
    """Polozka tagu/miesta/chytreho albumu v tvare BasicItem (appka cita name, thumbnail_status, thumb_size)."""
    item = {"id": id_, "type": kind, "name": name,
            "info": {"name": name, "title": name, "count": count, **(extra or {})},
            "thumbnail_status": "small,large" if newest else "default",
            "additional": {"thumb_size": {"small": {"resolutionx": 0, "resolutiony": 0},
                                          "large": {"resolutionx": 0, "resolutiony": 0}}}}
    if newest:
        f, m = newest
        mt = str(int(f["mtime"]))
        item["additional"]["thumb_size"] = {"small": {**media.thumb_dims(m, "small"), "mtime": mt},
                                            "large": {**media.thumb_dims(m, "large"), "mtime": mt}}
    return item


def api_tag(ctx: Ctx):
    m, p = ctx.p["method"], ctx.p
    offset, limit = max(0, _int(p.get("offset"), 0)), _int(p.get("limit"), 500)
    limit = 5000 if limit <= 0 else min(limit, 5000)
    if m == "list":
        t = p.get("type") or "desc"
        if t == "geo":
            rows = [] if ctx.r["hide_gps"] else [
                (i, n, c, nw, {"country": geo.country_name(cc), "cc": cc}) for i, n, c, nw, cc in catalog.list_places(ctx.perm)]
        elif t == "people":
            rows = [] if not ctx.r["people"] else [(i, n, c, nw, {}) for i, n, c, nw in catalog.list_people(ctx.perm)]
        elif t == "desc":
            rows = [(i, n, c, nw, {}) for i, n, c, nw in catalog.list_tags(ctx.perm)]
        else:
            rows = []
        items = [group_item(i, n, c, nw, "tag", {"tag_type": t, **ex}) for i, n, c, nw, ex in rows[offset:offset + limit]]
        return ok({"tags": items, "total": len(rows), "offset": offset})
    if m == "getinfo":
        out = []
        for id_ in filter(None, (p.get("id") or "").split(",")):
            t = catalog.parse_tag_id(id_)
            if t is None or (t[0] == "geo" and ctx.r["hide_gps"]) or (t[0] == "people" and not ctx.r["people"]):
                continue
            items = catalog.filter_items(ctx.perm, catalog.crit_for_tag(id_))
            if not items and not ctx.perm.admin:
                continue  # nazov tagu bez viditelnych poloziek neprezradit
            if t[0] == "desc":
                name = catalog.tag_names().get(t[1])
            elif t[0] == "people":
                name = catalog.people_names().get(t[1])
            else:
                name = catalog.place_label(t[1])
            if name is None:
                continue
            out.append(group_item(id_, name, len(items), catalog._newest(items), "tag", {"tag_type": t[0]}))
        return ok({"tags": out, "total": len(out), "offset": 0})
    return err(E_NO_PERM)


def api_smart(ctx: Ctx):
    m, p = ctx.p["method"], ctx.p
    adm = ctx.perm.admin
    # bezny pouzivatel vidi len chytre albumy s aspon jednou viditelnou polozkou; kriteria (cesty) len admin
    if m == "list":
        rows = [r for r in catalog.list_smart(ctx.perm) if (adm or r[2] > 0)
                and not (ctx.r["hide_gps"] and catalog.has_location(r[4]))]
        items = [group_item(i, n, c, nw, "smart", {"criteria": cr} if adm else {}) for i, n, c, nw, cr in rows]
        return ok({"smart_albums": items, "total": len(items), "offset": 0})
    if m == "getinfo":
        out = []
        for id_ in filter(None, (p.get("id") or "").split(",")):
            sid = catalog.parse_smart_id(id_)
            row = catalog.smart_get(sid) if sid is not None else None
            if row is None:
                continue
            crit = catalog.crit_for_smart(id_) or {}
            if ctx.r["hide_gps"] and catalog.has_location(crit):
                continue
            items = catalog.filter_items(ctx.perm, crit)
            if not items and not adm:
                continue
            out.append(group_item(id_, row["name"], len(items), catalog._newest(items), "smart",
                                  {"criteria": crit} if adm else {}))
        return ok({"smart_albums": out, "total": len(out), "offset": 0})
    return err(E_NO_PERM)


E_COVER_DENY, E_COVER_NO_ALBUM, E_COVER_NO_ITEM, E_COVER_NOT_IN = 526, 527, 528, 529


def api_cover(ctx: Ctx):
    """Titulna fotka albumu z appky DS photo (len admin, rovnako ako v galerii)."""
    m, p = ctx.p["method"], ctx.p
    if m != "set":
        return err(E_NO_PERM)
    if not ctx.perm.admin:
        return err(E_COVER_DENY)
    try:
        kind, rel = ids.parse(p.get("id") or "")
        ikind, irel = ids.parse(p.get("item_id") or "")
    except ids.BadId:
        return err(E_BAD_REQUEST)
    if kind != "album" or not rel or not os.path.isdir(ids.abs_path(rel)):
        return err(E_COVER_NO_ALBUM)
    if ikind not in ("photo", "video") or not media._exists_media(irel):
        return err(E_COVER_NO_ITEM)
    if not irel.startswith(rel + "/"):
        return err(E_COVER_NOT_IN)
    store.db().execute("INSERT INTO album_props(path, cover) VALUES (?,?) "
                       "ON CONFLICT(path) DO UPDATE SET cover=excluded.cover", (rel, irel))
    media.clear_cover_cache()
    return ok()


E_COMMENT_VALIDATE, E_COMMENT_DENY, E_COMMENT_FAIL = 491, 492, 493
_comment_rate = {}  # ip -> [casy] pre hosti
COMMENT_MAX_PER_HOUR = 20


def api_comment(ctx: Ctx):
    m, p = ctx.p["method"], ctx.p
    try:
        f = _media_from_id(ctx, p.get("id"))
    except (ApiError, ids.BadId):
        return err(E_COMMENT_DENY)
    if m == "list":
        rows = store.db().execute("SELECT * FROM comments WHERE path=? ORDER BY created, id", (f["rel"],)).fetchall()
        return ok({"comments": [{"id": str(r["id"]), "name": r["author"],
                                 "email": (r["email"] or "") if ctx.perm.admin else "",
                                 "comment": r["text"], "date": media.fmt_ts(r["created"]),
                                 "is_user": bool(r["username"])} for r in rows]})
    if m != "create":
        return err(E_NO_PERM)
    if not ctx.r["comment"]:
        return err(E_COMMENT_DENY)
    text = (p.get("comment") or "").strip()
    if ctx.username:
        author = ctx.username
    else:
        author = (p.get("name") or "").strip()
        ip, now = _client_ip(ctx.req), time.time()
        with _fails_lock:
            recent = [t for t in _comment_rate.get(ip, []) if now - t < 3600]
            if len(recent) >= COMMENT_MAX_PER_HOUR:
                return err(E_COMMENT_FAIL)
            _comment_rate[ip] = recent + [now]
    email = (p.get("email") or "").strip()[:200]
    if not text or len(text) > 2000 or not author or len(author) > 64:
        return err(E_COMMENT_VALIDATE)
    cur = store.db().execute(
        "INSERT INTO comments(path, author, username, email, text, created) VALUES (?,?,?,?,?,?)",
        (f["rel"], author, ctx.username, email or None, text, int(time.time())))
    return ok({"id": str(cur.lastrowid)})


HANDLERS = {
    "SYNO.PhotoStation.Cover": api_cover,
    "SYNO.PhotoStation.Comment": api_comment,
    "SYNO.PhotoStation.Tag": api_tag,
    "SYNO.PhotoStation.SmartAlbum": api_smart,
    "SYNO.API.Info": api_query,
    "SYNO.PhotoStation.Auth": api_auth,
    "SYNO.PhotoStation.Info": api_info,
    "SYNO.PhotoStation.Album": api_album,
    "SYNO.PhotoStation.Photo": api_photo,
    "SYNO.PhotoStation.Thumb": api_thumb,
    "SYNO.PhotoStation.Download": api_download,
}
NO_SESSION_CHECK = {"SYNO.API.Info", "SYNO.PhotoStation.Auth", "SYNO.PhotoStation.Info"}


MUTATING = {("SYNO.PhotoStation.Comment", "create"), ("SYNO.PhotoStation.Cover", "set"),
            ("SYNO.PhotoStation.Auth", "logout")}


def dispatch(req: Request, p: dict, sid):
    api, method, version = p.get("api"), p.get("method"), p.get("version")
    if not api or not method or not version:
        return err(E_BAD_REQUEST)
    if api not in APIS:
        return err(E_NO_API)
    if (api, method) in MUTATING and req.method != "POST":
        # zmena udajov len cez POST: session cookie (SameSite=Lax) prehliadac posle aj pri GET odkaze z cudzej stranky
        return err(E_NO_PERM)
    mn, mx = APIS[api][1], APIS[api][2]
    v = _int(version, -1)
    if not mn <= v <= mx:
        return err(E_VERSION)
    i18n.set_lang(i18n.for_request(req))
    valid, username = store.session_lookup(sid)
    headers = None
    if sid and not valid and api not in NO_SESSION_CHECK:
        # neplatna/vyprsana session -> appka sa prihlasi znova (sdk/WebAPI.php CheckSessionTimeout)
        headers = {"x-request-error": "error_timeout"}
    ctx = Ctx(req, p, sid, username)
    ctx.apply_share(p.get("share"))
    try:
        h = HANDLERS.get(api)
        if h is not None:
            resp = h(ctx)
        elif (api, method) in EMPTY:
            resp = ok(EMPTY[(api, method)])
        else:
            resp = err(E_NO_PERM)
    except ApiError as e:
        resp = err(e.code)
    except ids.BadId:
        resp = err(E_BAD_REQUEST)
    except FileNotFoundError:
        resp = err(E_BAD_REQUEST)
    except Exception:
        log.exception("error %s %s", api, method)
        resp = err(E_UNKNOWN)
    if headers:
        resp.headers.update(headers)
    if ctx.new_sid:
        g = config.current()
        resp.set_cookie(g.cookie, ctx.new_sid, path=g.cookie_path, httponly=True, samesite="lax",
                        secure=store.is_https(req), max_age=config.SESSION_DAYS * 86400)
    return resp


# CORS for the LG TV app (LGTV/): a packaged webOS web app has no web origin, so the API allows any origin,
# without credentials. A browser session stays in its cookie, which is never sent cross-site under "*";
# the TV app carries its session like the DS photo app (X-SYNO-TOKEN header, PHPSESSID in image URLs).
CORS_HEADERS = pairing.CORS
CORS_PREFLIGHT = {**CORS_HEADERS, "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                  "Access-Control-Allow-Headers": "X-SYNO-TOKEN, Content-Type", "Access-Control-Max-Age": "86400"}


async def webapi(req: Request):
    if req.method == "OPTIONS":
        return Response(status_code=204, headers=CORS_PREFLIGHT)
    p = dict(req.query_params)
    if req.method == "POST":
        ctype = req.headers.get("content-type", "")
        if ctype.startswith("application/x-www-form-urlencoded"):
            body = (await req.body()).decode("utf-8", "replace")
            p.update(parse_qsl(body, keep_blank_values=True))
        elif ctype.startswith("multipart/"):
            return err(E_NO_PERM)  # upload zatial nie je (NFS len na citanie)
    # cookie (web), parameter PHPSESSID v URL a hlavicka X-SYNO-TOKEN (appka DS photo)
    sid = store.request_sid(req, p)
    resp = await run_in_threadpool(dispatch, req, p, sid)
    from .web_version import VERSION
    resp.headers["x-picturestation-version"] = VERSION
    resp.headers["X-Content-Type-Options"] = "nosniff"  # JSON je servovany ako text/plain (kvoli appke)
    resp.headers.update(CORS_HEADERS)
    return resp


from .web_version import WEB_DIR  # web/ at the top of the repository, or /opt/picturestation/web


class WebFiles(StaticFiles):
    """Webova galeria; index.html sa nekesuje, aby sa nova verzia prejavila hned."""

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        if path in ("", ".", "index.html"):
            resp.headers["Cache-Control"] = "no-cache"
        else:
            resp.headers["Cache-Control"] = "no-cache"  # male subory, revalidacia cez ETag
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        return resp


async def index_page(req: Request):
    """index.html s verziou v odkazoch na skripty (prehliadac tak vzdy nacita aktualne)."""
    from starlette.responses import HTMLResponse
    from .web_version import VERSION
    with open(os.path.join(WEB_DIR, "index.html"), encoding="utf-8") as fh:
        html = fh.read()
    for f in ("i18n.js", "app.js", "admin.js", "style.css"):
        html = html.replace(f'"{f}"', f'"{f}?v={VERSION}"')
    lang = await run_in_threadpool(store.get_setting, "language", "auto")
    if lang not in i18n.LANGS:
        lang = "auto"
    from . import __version__
    g = config.current()
    base = json.dumps(g.base).replace("</", "<\\/")  # nikdy neuzavrie <script> (base = "" alebo "/~meno")
    html = html.replace("</head>", f'<script>window.PS_VERSION="{VERSION}";window.PS_LANG="{lang}";'
                                   f'window.PS_RELEASE="{__version__}";'
                                   f'window.PS_BASE={base};window.PS_MAIN={"true" if g.is_main else "false"};'
                                   f'</script>\n</head>', 1)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff",
                                       "X-Frame-Options": "DENY"})


async def photo_redirect(req: Request):
    return RedirectResponse(config.current().base + "/", status_code=302)


async def share_redirect(req: Request):
    """Kratky odkaz /s/<kod> -> galeria v rezime zdielania."""
    token = req.path_params["token"]
    return RedirectResponse(config.current().base + "/#/share/" + _quote(token), status_code=302)


def _share_info(token):
    sh = store.share_get(token)
    if sh is None:
        return None
    rel = sh["path"]
    if sh["kind"] == "album":
        pr = store.album_props(rel)
        title = (pr["title"] if pr and pr["title"] else posixpath.basename(rel)) or "Album"
        id_ = ids.album_id(rel)
    else:
        title = posixpath.basename(rel)
        id_ = ids.item_id(sh["kind"], rel)
    return {"kind": sh["kind"], "id": id_, "title": title, "expires": sh["expires"],
            "allow_download": bool(sh["allow_download"])}


async def share_api(req: Request):
    from starlette.responses import JSONResponse
    info = await run_in_threadpool(_share_info, req.path_params["token"])
    if info is None:
        lang = await run_in_threadpool(i18n.for_request, req)
        return JSONResponse({"error": i18n.tr("The link is not valid or has expired.", lang)}, status_code=404)
    return JSONResponse(info)


@asynccontextmanager
async def lifespan(_app):
    media.start_indexer()
    from . import synosync
    synosync.start()
    yield


_routes = Starlette(routes=[
    Route("/photo/webapi/{script}", webapi, methods=["GET", "POST", "HEAD", "OPTIONS"]),
    Route("/", index_page),
    Route("/index.html", index_page),
    Route("/photo", photo_redirect),
    Route("/photo/", photo_redirect),
    Route("/s/{token}", share_redirect),
    Route("/api/share/{token}", share_api),
    Route("/api/tv/{op}", pairing.tv_api, methods=["POST", "OPTIONS"]),  # LG TV app pairing
    *admin.routes,
    Mount("/", app=WebFiles(directory=WEB_DIR, html=True), name="web"),
], lifespan=lifespan)


class GalleryRouter:
    """Picks the gallery of a request: path prefix /~name/ (stripped, so all routes work below it),
    else the host name of a private gallery, else the main gallery."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.inner(scope, receive, send)
        from . import galleries
        path = scope["path"]
        g = None
        if path.startswith("/~"):
            name, _, rest = path[2:].partition("/")
            g = await run_in_threadpool(galleries.by_name, name, "/~" + name)
            if g is None:
                return await Response("Not found", status_code=404, media_type="text/plain")(scope, receive, send)
            if not _ and not rest:
                return await RedirectResponse(path + "/", status_code=302)(scope, receive, send)
            prefix = "/~" + name
            scope = dict(scope, path="/" + rest)
            if "raw_path" in scope and scope["raw_path"]:
                raw = scope["raw_path"]
                scope["raw_path"] = raw[len(prefix.encode()):] if raw.startswith(prefix.encode()) else raw
        else:
            host = ""
            for k, v in scope.get("headers", ()):
                if k == b"host":
                    host = v.decode("latin-1")
                    break
            if host:
                g = await run_in_threadpool(galleries.by_host, host)
        tok = config.use(g or config.MAIN)
        try:
            await self.inner(scope, receive, send)
        finally:
            config.reset(tok)


app = GalleryRouter(_routes)
