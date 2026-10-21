# SPDX-License-Identifier: GPL-3.0-or-later
"""SQLite: pouzivatelia, prava na albumy, sessions, cache metadat."""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time

from . import config

GUEST = "@guest"  # pseudo-pouzivatel pre pristup bez prihlasenia
GROUP_PREFIX = "#"  # prava skupiny su v tabulke access pod menom '#<skupina>'

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY COLLATE NOCASE,
    pw_hash  TEXT NOT NULL,
    admin    INTEGER NOT NULL DEFAULT 0,
    disabled INTEGER NOT NULL DEFAULT 0,
    note     TEXT
);
-- path = relativna cesta albumu; '' = cely koren. Pravo plati pre album aj vsetky podalbumy.
-- deny = 1: vylucenie albumu (najkonkretnejsie pravidlo vyhrava)
CREATE TABLE IF NOT EXISTS access (
    username TEXT NOT NULL COLLATE NOCASE,
    path     TEXT NOT NULL,
    upload   INTEGER NOT NULL DEFAULT 0,
    manage   INTEGER NOT NULL DEFAULT 0,
    deny     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (username, path)
);
CREATE TABLE IF NOT EXISTS sessions (
    sid      TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    expires  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    path     TEXT PRIMARY KEY,
    mtime    REAL NOT NULL,
    size     INTEGER NOT NULL,
    kind     TEXT NOT NULL,
    data     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS meta_kind ON meta(kind);
CREATE TABLE IF NOT EXISTS groups (
    name     TEXT PRIMARY KEY COLLATE NOCASE,
    note     TEXT
);
CREATE TABLE IF NOT EXISTS group_members (
    groupname TEXT NOT NULL COLLATE NOCASE,
    username  TEXT NOT NULL COLLATE NOCASE,
    PRIMARY KEY (groupname, username)
);
CREATE TABLE IF NOT EXISTS settings (
    key      TEXT PRIMARY KEY,
    value    TEXT
);
-- mode: private | password  (verejny = pravo pre @guest v tabulke access)
CREATE TABLE IF NOT EXISTS album_props (
    path        TEXT PRIMARY KEY,
    title       TEXT,
    description TEXT,
    cover       TEXT,
    mode        TEXT NOT NULL DEFAULT 'private',
    pw_hash     TEXT,
    album_order TEXT            -- zoradenie podalbumov: asc | desc (NULL = asc)
);
-- zdielanie odkazom: kind = album | photo | video, path = album alebo subor
CREATE TABLE IF NOT EXISTS shares (
    token          TEXT PRIMARY KEY,
    path           TEXT NOT NULL,
    kind           TEXT NOT NULL,
    created_by     TEXT,
    created        INTEGER NOT NULL,
    expires        INTEGER,
    allow_download INTEGER NOT NULL DEFAULT 0,
    note           TEXT
);
CREATE TABLE IF NOT EXISTS comments (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    path      TEXT NOT NULL,
    author    TEXT NOT NULL,
    username  TEXT,
    email     TEXT,
    text      TEXT NOT NULL,
    created   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS comments_path ON comments(path);
CREATE TABLE IF NOT EXISTS tags (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL UNIQUE COLLATE NOCASE
);
-- source: manual = pridal admin v galerii, file = klucove slovo zo suboru (IPTC/XMP)
CREATE TABLE IF NOT EXISTS item_tags (
    path      TEXT NOT NULL,
    tag_id    INTEGER NOT NULL,
    source    TEXT NOT NULL DEFAULT 'manual',
    PRIMARY KEY (path, tag_id)
);
-- tagy zo suboru, ktore admin rucne odobral (indexer ich nema vracat)
CREATE TABLE IF NOT EXISTS tag_suppress (
    path      TEXT NOT NULL,
    tag_id    INTEGER NOT NULL,
    PRIMARY KEY (path, tag_id)
);
CREATE INDEX IF NOT EXISTS item_tags_tag ON item_tags(tag_id);
-- chytre albumy: criteria = JSON {tags:[id], places:["cc|obec"], countries:["cc"], date_from, date_to, types:[..], path}
CREATE TABLE IF NOT EXISTS smart_albums (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    criteria   TEXT NOT NULL,
    created_by TEXT,
    created    INTEGER NOT NULL
);
-- ludia zo Synology Photos (spolocny priestor), prebera synosync; id = id osoby v Synology Photos
CREATE TABLE IF NOT EXISTS people (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    face_key   TEXT,          -- cache_key vyrezu tvare zo Synology Photos (zmena = stiahnut znova)
    cover_path TEXT           -- fotka, z ktorej je vyrez tvare (ukazat len tomu, kto ju smie vidiet)
);
CREATE TABLE IF NOT EXISTS people_items (
    person_id INTEGER NOT NULL,
    path      TEXT NOT NULL,
    PRIMARY KEY (person_id, path)
);
CREATE INDEX IF NOT EXISTS people_items_path ON people_items(path);
-- co videl posledny prechod indexu (zaklad pre rozpoznanie presunov; meta sa dopisuje aj priebezne)
CREATE TABLE IF NOT EXISTS last_seen (
    path     TEXT PRIMARY KEY,
    size     INTEGER NOT NULL
);
-- historia presunov albumov/suborov (kind: auto | manual | auto-file)
CREATE TABLE IF NOT EXISTS moves (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    old      TEXT NOT NULL,
    new      TEXT NOT NULL,
    kind     TEXT NOT NULL,
    created  INTEGER NOT NULL
);
-- presuny, kde index nasiel viac kandidatov (rozhodne admin)
CREATE TABLE IF NOT EXISTS moves_pending (
    old        TEXT PRIMARY KEY,
    candidates TEXT NOT NULL,
    created    INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS unlocks (
    sid      TEXT NOT NULL,
    path     TEXT NOT NULL,
    PRIMARY KEY (sid, path)
);
"""


def valid_name(name: str) -> bool:
    """Meno pouzivatela alebo skupiny: bez specialnych prefixov a riadiacich znakov."""
    name = (name or "").strip()
    return (0 < len(name) <= 64 and not name.startswith(("@", "#"))
            and all(c.isprintable() and c not in "/\\" for c in name))


def get_setting(key: str, default=None):
    row = db().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return default if row is None or row["value"] is None else row["value"]


def set_setting(key: str, value):
    db().execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, value))


# Prepinace obmedzeni (kluc -> predvolena hodnota). Na admina sa nevztahuju.
FLAGS = {
    "allow_download_user": True,    # prihlaseni mozu stiahnut original fotky
    "allow_download_guest": True,   # hostia mozu stiahnut original fotky
    "hide_gps": False,              # skryt polohu (GPS) pred vsetkymi okrem admina
    "hide_detail_user": False,      # skryt udaje z fotoaparatu pred prihlasenymi
    "hide_detail_guest": False,     # skryt udaje z fotoaparatu pred hostami
    "disable_timeline": False,      # vypnut casovu os
    "disable_search": False,        # vypnut vyhladavanie
    "allow_comment_user": True,     # prihlaseni mozu komentovat
    "allow_comment_guest": False,   # hostia mozu komentovat
    "root_files_public": False,     # fotky priamo v koreni (nie albumy) vidi kazdy, aj bez prihlasenia
    "people_for_guest": False,      # hostia bez prihlasenia vidia mena ludi na fotkach
}


def flag(key: str) -> bool:
    v = get_setting(key)
    return FLAGS[key] if v is None else v == "1"


def flags() -> dict:
    return {k: flag(k) for k in FLAGS}


def db() -> sqlite3.Connection:
    con = getattr(_local, "con", None)
    if con is None:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        con = sqlite3.connect(config.DB_PATH, timeout=30, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.executescript(SCHEMA)
        # migracia starsich databaz
        cols = {r[1] for r in con.execute("PRAGMA table_info(item_tags)")}
        if "source" not in cols:
            con.execute("ALTER TABLE item_tags ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'")
        if "deny" not in {r[1] for r in con.execute("PRAGMA table_info(access)")}:
            con.execute("ALTER TABLE access ADD COLUMN deny INTEGER NOT NULL DEFAULT 0")
        if "album_order" not in {r[1] for r in con.execute("PRAGMA table_info(album_props)")}:
            con.execute("ALTER TABLE album_props ADD COLUMN album_order TEXT")
        pcols = {r[1] for r in con.execute("PRAGMA table_info(people)")}
        for col in ("face_key", "cover_path"):
            if col not in pcols:
                con.execute(f"ALTER TABLE people ADD COLUMN {col} TEXT")
        _local.con = con
    return con


# ---------- hesla ----------
def hash_pw(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt$14$8$1${salt.hex()}${h.hex()}"


def check_pw(pw: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, h = stored.split("$")
        calc = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2**int(n), r=int(r), p=int(p))
        return hmac.compare_digest(calc.hex(), h)
    except Exception:
        return False


# ---------- pouzivatelia ----------
def get_user(username: str):
    return db().execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()


def authenticate(username: str, pw: str):
    u = get_user(username)
    if u is None:
        check_pw(pw, hash_pw("x"))  # rovnaky cas odpovede pre neexistujuceho pouzivatela
        return None
    if u["disabled"] or not check_pw(pw, u["pw_hash"]):
        return None
    return u


_exists_cache = {}  # cesta -> (cas, existuje)


def _dir_exists(rel: str) -> bool:
    """Existuje album na disku? Cache 60 s (kontroluje sa len pri zhode mena, teda zriedka)."""
    now = time.time()
    c = _exists_cache.get(rel)
    if c and now - c[0] < 60:
        return c[1]
    ok = os.path.isdir(os.path.join(config.PHOTO_ROOT, rel))
    _exists_cache[rel] = (now, ok)
    return ok


def _under(rel: str, path: str) -> bool:
    """rel je album path alebo jeho podalbum ('' = cely koren)."""
    return path == "" or rel == path or rel.startswith(path + "/")


class Perm:
    """Prava jedneho pouzivatela (alebo hosta) nad stromom albumov."""

    def __init__(self, username: str, admin: bool, grants, pw_albums=(), unlocked=()):
        """grants = riadky z access; kazdy ma path, deny a '_own' (vlastne pravidlo vs. skupiny)."""
        self.username = username
        self.admin = admin
        # pravidla: (path, deny, own)
        self.rules = [(g["path"], bool(g["deny"]), bool(g["_own"])) for g in grants]
        # cesta -> najsilnejsie pravidlo na nej (own, deny); vyhladanie podla predkov = O(hlbka), nie O(pocet pravidiel)
        self._map = {}
        for p, deny, own in self.rules:
            k = (own, deny)
            if p not in self._map or k > self._map[p]:
                self._map[p] = k
        # ochrana pri presune: meno vylucenych albumov -> ich cesty
        self._deny_names = {}
        for p, deny, _ in self.rules:
            if deny and p:
                self._deny_names.setdefault(p.rsplit("/", 1)[-1], set()).add(p)
        self.grants = {p: (False, False) for p, deny, _ in self.rules if not deny}
        self.denies = {p for p, deny, _ in self.rules if deny}
        self.pw_albums = set(pw_albums)   # albumy chranene heslom (vidi ich kazdy so zamkom)
        self.unlocked = set(unlocked)     # albumy odomknute heslom v tejto session
        self.forced = set()               # albumy zo zdielaneho odkazu (vylucenie na ne neplati)
        self.items = set()                # jednotlive subory pristupne cez zdielany odkaz
        self._folder_memo = {}            # priecinok -> can_browse (lists over 70,000 files ask per file)
        self._memo_ver = None

    def can_item(self, rel: str) -> bool:
        """Pristup k suboru: cez album, alebo priamo zdielany subor."""
        if rel in self.items:
            return True
        folder = rel.rsplit("/", 1)[0] if "/" in rel else ""
        ver = (len(self.unlocked), len(self.forced), len(self.pw_albums), self.root_public)
        if ver != self._memo_ver:
            self._folder_memo, self._memo_ver = {}, ver
        ok = self._folder_memo.get(folder)
        if ok is None:
            ok = self._folder_memo[folder] = self.can_browse(folder)
        return ok

    def best_rule(self, rel: str):
        """(cesta, vylucenie, vlastne) rozhodujuceho pravidla, alebo None.
        Najkonkretnejsie pravidlo vyhrava; pri rovnakej ceste vlastne pred skupinovym, potom vylucenie."""
        p = rel
        while True:
            k = self._map.get(p)
            if k is not None:
                return (p, k[1], k[0])
            if p == "":
                return None
            p = p.rsplit("/", 1)[0] if "/" in p else ""

    def _rule(self, rel: str):
        """True = povolene, False = vylucene, None = ziadne pravidlo."""
        b = self.best_rule(rel)
        return None if b is None else not b[1]

    def _moved_deny(self, rel: str) -> bool:
        """Album (alebo jeho predok) ma rovnake meno ako vylucany album, ktory zo svojho miesta zmizol
        (napr. presun 2026-08-08 X -> 2026/2026-08-08 X pred spracovanim indexom). Radsej skryt."""
        if not self._deny_names:
            return False
        a = rel
        while a:
            name = a.rsplit("/", 1)[-1]
            for dp in self._deny_names.get(name, ()):
                if dp != a and not _dir_exists(dp):
                    return True
            a = a.rsplit("/", 1)[0] if "/" in a else ""
        return False

    def _rule_allows(self, rel: str) -> bool:
        if self._rule(rel) is not True:
            return False
        br = self.best_rule(rel)
        # vylucenie s chybajucim povodnym miestom plati aj na novom mieste, kym ho index neprenesie
        if br and br[0] != rel and self._moved_deny(rel):
            return False
        return True

    def _excluded(self, rel: str) -> bool:
        """Vylucenie ma prednost aj pred albumom s heslom."""
        return not self.admin and self._rule(rel) is False

    root_public = False  # fotky priamo v koreni su verejne (len koren, nededi sa do albumov)

    def can_browse(self, rel: str) -> bool:
        if rel == "" and self.root_public:
            return True
        return (self.admin or self._rule_allows(rel)
                or (any(_under(rel, p) for p in self.unlocked) and not self._excluded(rel))
                or any(_under(rel, p) for p in self.forced))

    def pw_owner(self, rel: str):
        """Najblizsi album s heslom, pod ktory rel patri (None = ziadny)."""
        best = None
        for p in self.pw_albums:
            if _under(rel, p) and (best is None or len(p) > len(best)):
                best = p
        return best

    def is_locked(self, rel: str) -> bool:
        return not self.can_browse(rel) and self.pw_owner(rel) is not None and not self._excluded(rel)

    def is_ancestor(self, rel: str) -> bool:
        """Album nie je pristupny, ale lezi na ceste k pristupnemu (zobrazi sa len cesta dalej)."""
        if self.admin:
            return False
        pre = "" if rel == "" else rel + "/"
        targets = ([p for p in self.grants if p and self._rule_allows(p)]
                   + [p for p in self.pw_albums if not self._excluded(p)] + list(self.forced))
        return any(p != rel and p.startswith(pre) for p in targets if p)

    def can_see(self, rel: str) -> bool:
        return (self.can_browse(rel) or self.is_ancestor(rel)
                or (rel in self.pw_albums and not self._excluded(rel)))

    def can_upload(self, rel: str) -> bool:
        return False  # NFS je len na citanie

    def can_manage(self, rel: str) -> bool:
        return False  # zatial ziadne upravy

    def album_permission(self, rel: str) -> dict:
        return {"browse": self.can_browse(rel), "upload": self.can_upload(rel), "manage": self.can_manage(rel)}


def perm_for(username, sid=None) -> Perm:
    pw_albums = [r["path"] for r in db().execute("SELECT path FROM album_props WHERE mode='password'")]
    unlocked = [r["path"] for r in db().execute("SELECT path FROM unlocks WHERE sid=?", (sid,))] if sid else []
    p = _perm_base(username)
    p.pw_albums, p.unlocked = set(pw_albums), set(unlocked)
    p.root_public = flag("root_files_public")
    return p


def _perm_base(username) -> Perm:
    if not username:
        username = GUEST
        admin = False
    else:
        u = get_user(username)
        if u is None or u["disabled"]:
            username, admin = GUEST, False
        else:
            admin = bool(u["admin"])
    grants = list(db().execute("SELECT *, 1 AS _own FROM access WHERE username=?", (username,)).fetchall())
    if username != GUEST:
        grants += db().execute(
            "SELECT a.*, 0 AS _own FROM access a JOIN group_members m ON a.username = '" + GROUP_PREFIX + "' || m.groupname "
            "WHERE m.username=?", (username,)).fetchall()
    return Perm(username, admin, grants)


# ---------- sessions ----------
def new_session(username: str) -> str:
    sid = secrets.token_hex(16)
    db().execute("INSERT INTO sessions VALUES (?,?,?)",
                 (sid, username, int(time.time()) + config.SESSION_DAYS * 86400))
    return sid


def session_lookup(sid):
    """(platna, meno). Hostovska session (len odomknute albumy) = (True, None). Predlzuje platnost."""
    if not sid:
        return False, None
    now = int(time.time())
    row = db().execute("SELECT username, expires FROM sessions WHERE sid=?", (sid,)).fetchone()
    if row is None or row["expires"] < now:
        return False, None
    if row["username"] != GUEST:
        u = get_user(row["username"])
        if u is None or u["disabled"]:
            return False, None
    if row["expires"] - now < (config.SESSION_DAYS - 1) * 86400:
        db().execute("UPDATE sessions SET expires=? WHERE sid=?", (now + config.SESSION_DAYS * 86400, sid))
    return True, (None if row["username"] == GUEST else row["username"])


def session_user(sid):
    """Vrati meno prihlaseneho, None ak nie je (alebo je to hostovska session)."""
    return session_lookup(sid)[1]


def unlock(sid, path):
    db().execute("INSERT OR IGNORE INTO unlocks VALUES (?,?)", (sid, path))


def drop_session(sid):
    if sid:
        db().execute("DELETE FROM sessions WHERE sid=?", (sid,))
        db().execute("DELETE FROM unlocks WHERE sid=?", (sid,))


def purge_sessions():
    db().execute("DELETE FROM sessions WHERE expires<?", (int(time.time()),))
    db().execute("DELETE FROM unlocks WHERE sid NOT IN (SELECT sid FROM sessions)")


# ---------- zdielanie ----------
def share_get(token):
    """Platne zdielanie alebo None."""
    if not token or len(token) > 64:
        return None
    row = db().execute("SELECT * FROM shares WHERE token=?", (token,)).fetchone()
    if row is None or (row["expires"] and row["expires"] < int(time.time())):
        return None
    return row


def share_create(path, kind, created_by, days, allow_download, note) -> str:
    token = secrets.token_urlsafe(16)  # 128 bitov
    now = int(time.time())
    db().execute("INSERT INTO shares VALUES (?,?,?,?,?,?,?,?)",
                 (token, path, kind, created_by, now, now + int(days) * 86400 if days else None,
                  int(bool(allow_download)), note or None))
    return token


# ---------- vlastnosti albumov ----------
def album_props(path: str):
    return db().execute("SELECT * FROM album_props WHERE path=?", (path,)).fetchone()


def all_album_props() -> dict:
    return {r["path"]: r for r in db().execute("SELECT * FROM album_props")}


# ---------- cache metadat ----------
def meta_get(rel: str, mtime: float, size: int):
    row = db().execute("SELECT * FROM meta WHERE path=?", (rel,)).fetchone()
    if row and row["mtime"] == mtime and row["size"] == size:
        return json.loads(row["data"])
    return None


def meta_put(rel: str, mtime: float, size: int, kind: str, data: dict):
    db().execute("INSERT OR REPLACE INTO meta VALUES (?,?,?,?,?)",
                 (rel, mtime, size, kind, json.dumps(data, ensure_ascii=False)))
