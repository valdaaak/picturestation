# SPDX-License-Identifier: GPL-3.0-or-later
"""ID poloziek presne ako Photo Station (sdk/WebAPI.php EncodeItemId, photoutil.php)."""
import os
import posixpath

from . import config


class BadId(ValueError):
    pass


def _hex(s: str) -> str:
    return s.encode("utf-8").hex()


def _unhex(h: str) -> str:
    try:
        return bytes.fromhex(h).decode("utf-8")
    except ValueError as e:
        raise BadId(h) from e


def clean_rel(rel: str) -> str:
    """Normalizuje relativnu cestu; odmietne vystup z korena a systemove priecinky Synology."""
    rel = (rel or "").replace("\\", "/").strip("/")
    if rel in ("", "."):
        return ""
    norm = posixpath.normpath(rel)
    parts = norm.split("/")
    if norm.startswith("..") or any(p in ("", ".", "..") or p.startswith(("@", "#")) for p in parts):
        raise BadId(rel)
    return norm


def abs_path(rel: str) -> str:
    p = os.path.realpath(os.path.join(config.PHOTO_ROOT, clean_rel(rel)))
    if p != config.PHOTO_ROOT and not p.startswith(config.PHOTO_ROOT + os.sep):
        raise BadId(rel)
    return p


def album_id(rel: str):
    return None if rel == "" else "album_" + _hex(rel)


def item_id(kind: str, rel: str) -> str:
    d, name = posixpath.split(rel)
    return f"{kind}_{_hex(d if d else '/')}_{_hex(name)}"


def parse(id_: str):
    """Vrati (typ, relativna_cesta). Typ: album | photo | video."""
    if not id_:
        raise BadId(id_)
    if id_.startswith("album_"):
        return "album", clean_rel(_unhex(id_[6:]))
    kind, _, rest = id_.partition("_")
    if kind in ("photo", "video"):
        hd, _, hn = rest.partition("_")
        d, name = _unhex(hd), _unhex(hn)
        if not name or "/" in name:
            raise BadId(id_)
        d = "" if d == "/" else d
        return kind, clean_rel(posixpath.join(d, name))
    raise BadId(id_)
