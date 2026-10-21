# SPDX-License-Identifier: GPL-3.0-or-later
"""Private galleries: several photo archives served by one server, managed from the main gallery.

Each gallery has its own database, users, thumbnails and photo folder; code and GeoNames are shared.
A request belongs to a gallery by its host name (photos.example.com) or by the path prefix /~name/.
"""
import concurrent.futures
import os
import re
import shutil
import threading
import time

from . import config, store

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")
HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")
CACHE_TTL = 5

_lock = threading.Lock()
_cache = (0.0, {}, {})   # (time, name -> row, host -> name)


class GalleryError(ValueError):
    def __init__(self, msg, **kw):
        super().__init__(msg)
        self.msg, self.kw = msg, kw


def _rows():
    global _cache
    with _lock:
        t, by_name, by_host = _cache
        if time.time() - t < CACHE_TTL:
            return by_name, by_host
    by_name, by_host = {}, {}
    for r in store.main_db().execute("SELECT * FROM galleries"):
        r = dict(r)
        by_name[r["name"]] = r
        if r["enabled"]:
            for h in hostnames(r["hostnames"]):
                by_host[h] = r["name"]
    with _lock:
        _cache = (time.time(), by_name, by_host)
    return by_name, by_host


def invalidate():
    global _cache
    with _lock:
        _cache = (0.0, {}, {})


def hostnames(text: str) -> list:
    return [h for h in re.split(r"[\s,;]+", (text or "").strip().lower()) if h]


def _gallery(row, prefix=""):
    g = config.private(row["name"], row["root"], row["title"])
    return config.Gallery(g.name, g.root, g.data_dir, g.title, prefix) if prefix else g


def by_name(name: str, prefix: str = ""):
    """Enabled gallery of this name, or None."""
    row = _rows()[0].get(name)
    return _gallery(row, prefix) if row and row["enabled"] else None


def by_host(host: str):
    host = (host or "").split(":")[0].strip().lower().rstrip(".")
    by_name_, by_host_ = _rows()
    name = by_host_.get(host)
    return _gallery(by_name_[name]) if name else None


def all_enabled() -> list:
    return [_gallery(r) for r in _rows()[0].values() if r["enabled"]]


# ---------------- validation ----------------
def check_root(path: str) -> str:
    """Photo folder of a gallery: an existing, readable folder below one of the allowed roots."""
    path = (path or "").strip()
    if not path.startswith("/"):
        raise GalleryError("The folder must be an absolute path.")
    try:
        real = _probe.submit(os.path.realpath, path).result(timeout=3.0)
    except Exception:
        raise GalleryError("The folder does not exist or cannot be read.")
    if not any(real == r or real.startswith(r + os.sep) for r in config.GALLERY_ROOTS):
        raise GalleryError("The folder must be inside: {roots}.", roots=", ".join(config.GALLERY_ROOTS))
    if not root_available(real) or not os.access(real, os.R_OK | os.X_OK):
        raise GalleryError("The folder does not exist or cannot be read.")
    return real


def check_hosts(text: str, name: str) -> str:
    hosts = hostnames(text)
    for h in hosts:
        if not HOST_RE.match(h):
            raise GalleryError("Invalid domain: {host}.", host=h)
        other = _rows()[1].get(h)
        if other and other != name:
            raise GalleryError("The domain {host} already belongs to another gallery.", host=h)
    return " ".join(hosts)


# ---------------- management (main gallery's admin) ----------------
_probe = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="root-probe")


def root_available(path: str, timeout: float = 3.0) -> bool:
    """Is the photo folder there? With a time limit: a dead NFS mount must not hang the Settings page."""
    try:
        return _probe.submit(os.path.isdir, path).result(timeout=timeout)
    except Exception:
        return False


def info(row) -> dict:
    root_ok = root_available(row["root"])
    files = None
    if root_ok:
        tok = config.use(_gallery(row))
        try:
            files = store.db().execute("SELECT COUNT(*) FROM meta").fetchone()[0]
            admins = [r["username"] for r in store.db().execute(
                "SELECT username FROM users WHERE admin=1 ORDER BY username COLLATE NOCASE")]
        finally:
            config.reset(tok)
    else:
        admins = []
    return {"name": row["name"], "title": row["title"], "root": row["root"], "hostnames": hostnames(row["hostnames"]),
            "enabled": bool(row["enabled"]), "created": row["created"], "root_ok": root_ok, "files": files,
            "admins": admins, "path": "/~" + row["name"] + "/"}


def listing() -> list:
    rows = store.main_db().execute("SELECT * FROM galleries ORDER BY name").fetchall()
    return [info(dict(r)) for r in rows]


def create(name, title, root, hosts, admin_user, admin_pw):
    name = (name or "").strip().lower()
    if not NAME_RE.match(name):
        raise GalleryError("The name may contain lower-case letters, digits and dashes (max. 31).")
    if store.main_db().execute("SELECT 1 FROM galleries WHERE name=?", (name,)).fetchone():
        raise GalleryError("Such a gallery already exists.")
    root = check_root(root)
    hosts = check_hosts(hosts, name)
    admin_user = (admin_user or "").strip()
    if not store.valid_name(admin_user):
        raise GalleryError("Invalid name.")
    if len(admin_pw or "") < 8:
        raise GalleryError("Password must have at least 8 characters.")
    data_dir = os.path.join(config.GALLERIES_DIR, name)
    if os.path.exists(data_dir):
        raise GalleryError("Data of a gallery with this name already exist.")
    store.main_db().execute("INSERT INTO galleries(name, title, root, hostnames, enabled, created) VALUES (?,?,?,?,1,?)",
                            (name, (title or "").strip()[:100] or name, root, hosts, int(time.time())))
    invalidate()
    set_admin(name, admin_user, admin_pw)


def update(name, title=None, root=None, hosts=None, enabled=None):
    row = store.main_db().execute("SELECT * FROM galleries WHERE name=?", (name,)).fetchone()
    if row is None:
        raise GalleryError("No such gallery.")
    sets, vals = [], []
    if title is not None:
        sets.append("title=?"); vals.append(title.strip()[:100] or name)
    if root is not None:
        sets.append("root=?"); vals.append(check_root(root))
    if hosts is not None:
        sets.append("hostnames=?"); vals.append(check_hosts(hosts, name))
    if enabled is not None:
        sets.append("enabled=?"); vals.append(1 if enabled else 0)
    if sets:
        store.main_db().execute(f"UPDATE galleries SET {', '.join(sets)} WHERE name=?", (*vals, name))
        invalidate()


def delete(name):
    """Removes the gallery; its database and thumbnails go to galleries/.deleted, the photos stay."""
    if store.main_db().execute("DELETE FROM galleries WHERE name=?", (name,)).rowcount == 0:
        raise GalleryError("No such gallery.")
    invalidate()
    src = os.path.join(config.GALLERIES_DIR, name)
    if os.path.isdir(src):
        dst = os.path.join(config.GALLERIES_DIR, ".deleted", f"{name}-{time.strftime('%Y%m%d-%H%M%S')}")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)


def _in_gallery(name):
    row = store.main_db().execute("SELECT * FROM galleries WHERE name=?", (name,)).fetchone()
    if row is None:
        raise GalleryError("No such gallery.")
    return _gallery(dict(row))


def set_admin(name, user, pw):
    """Adds an administrator to the gallery, or sets a new password for an existing one."""
    user = (user or "").strip()
    if not store.valid_name(user):
        raise GalleryError("Invalid name.")
    if len(pw or "") < 8:
        raise GalleryError("Password must have at least 8 characters.")
    tok = config.use(_in_gallery(name))
    try:
        d = store.db()
        if store.get_user(user):
            d.execute("UPDATE users SET pw_hash=?, admin=1, disabled=0 WHERE username=?", (store.hash_pw(pw), user))
            d.execute("DELETE FROM sessions WHERE username=?", (user,))
        else:
            d.execute("INSERT INTO users(username, pw_hash, admin, note) VALUES (?,?,1,?)",
                      (user, store.hash_pw(pw), "administrator"))
    finally:
        config.reset(tok)


def remove_admin(name, user):
    tok = config.use(_in_gallery(name))
    try:
        d = store.db()
        admins = [r["username"] for r in d.execute("SELECT username FROM users WHERE admin=1")]
        if user not in admins:
            raise GalleryError("User does not exist.")
        if len(admins) == 1:
            raise GalleryError("At least one administrator must remain.")
        d.execute("DELETE FROM users WHERE username=?", (user,))
        d.execute("DELETE FROM access WHERE username=?", (user,))
        d.execute("DELETE FROM sessions WHERE username=?", (user,))
    finally:
        config.reset(tok)
