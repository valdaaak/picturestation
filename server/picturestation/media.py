# SPDX-License-Identifier: GPL-3.0-or-later
"""Priecinky, metadata, nahlady, titulne fotky albumov."""
import hashlib
import json
import logging
import os
import posixpath
import shutil
import stat
import subprocess
import threading
import time
from datetime import datetime

from PIL import Image, ImageOps

import html
import re

from . import config, geo, ids, store

log = logging.getLogger("picturestation.media")
_ISO6709 = re.compile(r"^([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)")
Image.MAX_IMAGE_PIXELS = 250_000_000

_thumb_sem = threading.BoundedSemaphore(config.THUMB_WORKERS)
_dir_cache = {}      # (gallery, rel) -> (dir_mtime, dirs, files)
_cover_cache = {}    # (gallery, rel, perm...) -> (dir_mtime, cover_rel|None, time)
_lock = threading.Lock()
FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
NUL = chr(0)


def ext_of(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def kind_of(name: str):
    e = ext_of(name)
    if e in config.PHOTO_EXT:
        return "photo"
    if e in config.VIDEO_EXT:
        return "video"
    return None


def fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _clean(v) -> str:
    return str(v or "").replace(NUL, "").strip()


# ---------------- priecinky ----------------
def list_dir(rel: str):
    """Vrati (podpriecinky, media) pre album; zoznamy slovnikov name/rel/mtime/size/kind."""
    p = ids.abs_path(rel)
    st = os.stat(p)
    with _lock:
        c = _dir_cache.get((config.current().name, rel))
        if c and c[0] == st.st_mtime:
            return c[1], c[2]
    dirs, files = [], []
    with os.scandir(p) as it:
        for e in it:
            n = e.name
            if n.startswith((".", "@", "#")):
                continue
            r = n if rel == "" else rel + "/" + n
            try:
                # Bez stat() kazdeho suboru: cez NFS je to jeden dotaz na NAS na subor.
                # Velkost a cas sa doplnia az pre zobrazene polozky (with_stat).
                if e.is_dir(follow_symlinks=False):
                    dirs.append({"name": n, "rel": r})
                else:
                    k = kind_of(n)
                    if k:
                        files.append({"name": n, "rel": r, "kind": k})
            except OSError:
                continue
    dirs.sort(key=lambda d: d["name"].lower())
    files.sort(key=lambda f: f["name"].lower())
    with _lock:
        _dir_cache[(config.current().name, rel)] = (st.st_mtime, dirs, files)
    return dirs, files


# ---------------- metadata ----------------
def _ratio(v):
    try:
        return float(v)
    except Exception:
        return None


_XMP_SUBJECT = re.compile(rb"<dc:subject[^>]*>(.*?)</dc:subject>", re.S)
_XMP_LI = re.compile(rb"<rdf:li[^>]*>(.*?)</rdf:li>", re.S)


def _dec(b: bytes) -> str:
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("cp1250", "replace")


def _keywords(im) -> list:
    """Klucove slova z IPTC (2:25) a XMP (dc:subject). Takto si Photo Station a Lightroom zapisovali tagy."""
    out = []
    try:
        from PIL import IptcImagePlugin
        iptc = IptcImagePlugin.getiptcinfo(im) or {}
        v = iptc.get((2, 25))
        for b in (v if isinstance(v, list) else [v] if v else []):
            out.append(_dec(b))
    except Exception:
        pass
    xmp = im.info.get("xmp") or im.info.get("XML:com.adobe.xmp")
    if isinstance(xmp, str):
        xmp = xmp.encode("utf-8")
    if xmp:
        m = _XMP_SUBJECT.search(xmp)
        if m:
            out += [html.unescape(_dec(x)) for x in _XMP_LI.findall(m.group(1))]
    seen, res = set(), []
    for k in out:
        k = " ".join(k.replace(NUL, "").split())
        if k and k.lower() not in seen:
            seen.add(k.lower())
            res.append(k)
    return res


def _exif_photo(path: str) -> dict:
    d = {"w": 0, "h": 0}
    try:
        with Image.open(path) as im:
            w, h = im.size
            ex = im.getexif()
            orient = ex.get(0x0112, 1)
            if orient in (5, 6, 7, 8):
                w, h = h, w
            d.update(w=w, h=h)
            sub = ex.get_ifd(0x8769)
            taken = sub.get(0x9003) or sub.get(0x9004) or ex.get(0x0132)
            if taken:
                try:
                    d["taken"] = datetime.strptime(_clean(taken)[:19], "%Y:%m:%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    pass
            d["camera"] = _clean(ex.get(0x010F))
            d["model"] = _clean(ex.get(0x0110))
            et = _ratio(sub.get(0x829A))
            if et:
                d["exposure"] = f"1/{round(1 / et)} s" if et < 1 else f"{et:g} s"
            fn = _ratio(sub.get(0x829D))
            if fn:
                d["aperture"] = f"F{fn:.1f}"
            iso = sub.get(0x8827)
            if isinstance(iso, (tuple, list)):
                iso = iso[0] if iso else None
            if iso:
                d["iso"] = int(iso)
            fl = _ratio(sub.get(0x920A))
            if fl:
                d["focal"] = f"{fl:g} mm"
            if sub.get(0xA434):
                d["lens"] = _clean(sub.get(0xA434))
            kw = _keywords(im)
            if kw:
                d["kw"] = kw
            gps = ex.get_ifd(0x8825)
            if gps and 2 in gps and 4 in gps:
                def deg(v, ref):
                    x = float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
                    return -x if _clean(ref) in ("S", "W") else x
                lat, lng = deg(gps[2], gps.get(1, "N")), deg(gps[4], gps.get(3, "E"))
                if lat or lng:
                    d["gps"] = {"lat": round(lat, 6), "lng": round(lng, 6)}
    except Exception as e:
        log.debug("EXIF %s: %s", path, e)
    return d


def _probe_video(path: str) -> dict:
    d = {"w": 0, "h": 0, "duration": 0}
    if not FFPROBE:
        return d
    try:
        out = subprocess.run([FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
                             capture_output=True, timeout=60).stdout
        j = json.loads(out or b"{}")
        fmt = j.get("format", {})
        d["duration"] = int(float(fmt.get("duration", 0) or 0) * 1000)
        d["container"] = (fmt.get("format_name") or "").split(",")[0]
        ct = (fmt.get("tags") or {}).get("creation_time")
        for s in j.get("streams", []):
            if s.get("codec_type") == "video" and not d["w"]:
                d.update(w=int(s.get("width") or 0), h=int(s.get("height") or 0), vcodec=s.get("codec_name", ""),
                         vbitrate=int(s.get("bit_rate") or 0))
                rot = (s.get("tags") or {}).get("rotate")
                for sd in s.get("side_data_list", []) or []:
                    rot = sd.get("rotation", rot)
                try:
                    if rot and abs(int(float(rot))) in (90, 270):
                        d["w"], d["h"] = d["h"], d["w"]
                except ValueError:
                    pass
                ct = ct or (s.get("tags") or {}).get("creation_time")
            elif s.get("codec_type") == "audio" and "acodec" not in d:
                d.update(acodec=s.get("codec_name", ""), abitrate=int(s.get("bit_rate") or 0))
        if ct:
            try:
                dt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
                if dt.year > 1971:
                    d["taken"] = dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
        # poloha videa: ISO 6709, napr. "+48.2381+017.0475+123.000/" (telefony, QuickTime)
        tags = fmt.get("tags") or {}
        loc = tags.get("location") or tags.get("com.apple.quicktime.location.ISO6709") or tags.get("location-eng")
        if loc:
            mm = _ISO6709.match(loc.strip())
            if mm:
                lat, lng = float(mm.group(1)), float(mm.group(2))
                if lat or lng:
                    d["gps"] = {"lat": round(lat, 6), "lng": round(lng, 6)}
    except Exception as e:
        log.debug("ffprobe %s: %s", path, e)
    return d


def with_stat(f: dict) -> dict:
    """Polozka doplnena o aktualny cas zmeny a velkost."""
    if "mtime" in f:
        return f
    st = os.stat(ids.abs_path(f["rel"]))
    return {**f, "mtime": st.st_mtime, "size": st.st_size}


META_VERSION = 3  # 2 = poloha videi + miesto z GPS, 3 = klucove slova z fotiek (tagy)


def _add_place(m: dict) -> bool:
    """Doplni miesto z GPS (offline GeoNames). True = metadata sa zmenili."""
    g = m.get("gps")
    if not g or "place" in m or not geo.available():
        return False
    res = geo.lookup(g["lat"], g["lng"])
    m["place"], m["cc"] = (res if res else ("", ""))
    return True


def refresh_places() -> int:
    """After the GeoNames data changed (e.g. a country with small villages was added), look up the place
    of every photo with GPS again. Runs once per data version; returns the number of changed places."""
    if not geo.available():
        return 0
    sig = geo.signature()
    if store.get_setting("geo_signature") == sig:
        return 0
    db = store.db()
    changed = 0
    for r in db.execute("SELECT path, data FROM meta WHERE data LIKE '%\"gps\"%'").fetchall():
        m = json.loads(r["data"])
        g = m.get("gps")
        if not g:
            continue
        res = geo.lookup(g["lat"], g["lng"]) or ("", "")
        if (m.get("place"), m.get("cc")) != res:
            m["place"], m["cc"] = res
            db.execute("UPDATE meta SET data=? WHERE path=?", (json.dumps(m, ensure_ascii=False), r["path"]))
            changed += 1
    store.set_setting("geo_signature", sig)
    if changed:
        log.info("places looked up again: %d photos changed", changed)
    return changed


def get_meta(f: dict) -> dict:
    """f = polozka z list_dir. Metadata z cache, alebo ich precita zo suboru."""
    f = with_stat(f)
    m = store.meta_get(f["rel"], f["mtime"], f["size"])
    # videa nemaju klucove slova -> staci verzia 2
    need = META_VERSION if f["kind"] == "photo" else 2
    if m is not None and m.get("v", 1) >= need:
        if _add_place(m):
            store.meta_put(f["rel"], f["mtime"], f["size"], f["kind"], m)
        return m
    p = ids.abs_path(f["rel"])
    if f["kind"] == "photo":
        m = _exif_photo(p) if ext_of(f["name"]) in config.PIL_EXT else {"w": 0, "h": 0}
    elif m is not None and m.get("v", 1) >= 2:
        pass  # video uz ma aktualne udaje
    else:
        m = _probe_video(p)
    m["v"] = need
    m.setdefault("taken", fmt_ts(f["mtime"]))
    _add_place(m)
    store.meta_put(f["rel"], f["mtime"], f["size"], f["kind"], m)
    if f["kind"] == "photo":
        from . import catalog
        catalog.sync_file_tags(f["rel"], m.get("kw"))
    return m


def file_entry(rel: str):
    """Polozka ako z list_dir pre jeden subor."""
    p = ids.abs_path(rel)
    st = os.stat(p)
    name = posixpath.basename(rel)
    k = kind_of(name)
    if k is None:
        raise FileNotFoundError(rel)
    return {"name": name, "rel": rel, "mtime": st.st_mtime, "size": st.st_size, "kind": k}


# ---------------- nahlady ----------------
# Mena v @eaDir: nove (DSM 7 / PS s '_') aj stare (Photo Station s ':'), od najvhodnejsieho.
EA_NAMES = {
    "large": ["SYNOPHOTO_THUMB_XL.jpg", "SYNOPHOTO:THUMB_XL.jpg", "SYNOPHOTO_THUMB_LARGE_PREVIEW.jpg",
              "SYNOPHOTO_THUMB_L.jpg", "SYNOPHOTO:THUMB_L.jpg"],
    "small": ["SYNOPHOTO_THUMB_M.jpg", "SYNOPHOTO:THUMB_M.jpg", "SYNOPHOTO_THUMB_SM.jpg"],
    "preview": ["SYNOPHOTO_THUMB_PREVIEW.jpg", "SYNOPHOTO:THUMB_PREVIEW.jpg", "SYNOPHOTO_THUMB_SM.jpg",
                "SYNOPHOTO_THUMB_M.jpg", "SYNOPHOTO:THUMB_M.jpg"],
}


def _ea_serve(p: str):
    """Stat of a ready-made @eaDir file to serve directly, but only if it really resolves to a regular file
    INSIDE this gallery's photo root. A symlink in a user-writable archive must not read files outside it."""
    root = config.current().root
    try:
        rp = os.path.realpath(p)
        if rp != root and not rp.startswith(root + os.sep):
            return None
        st = os.stat(rp)
    except OSError:
        return None
    return st if stat.S_ISREG(st.st_mode) else None


def _ea_thumb(rel: str, size: str):
    d, n = posixpath.split(rel)
    base = os.path.join(ids.abs_path(d), "@eaDir", n)
    try:
        src_m = os.stat(ids.abs_path(rel)).st_mtime
    except OSError:
        return None
    for name in EA_NAMES[size]:
        st = _ea_serve(os.path.join(base, name))
        # Nahlad starsi nez original = original bol upraveny -> nepouzit.
        if st and st.st_mtime + 5 >= src_m:
            return os.path.join(base, name)
    return None


WEB_VIDEO_EXT = {"mp4", "m4v", "webm"}
EA_VIDEOS = ["SYNOPHOTO_FILM_H.mp4", "SYNOPHOTO:FILM_H.mp4", "SYNOPHOTO_FILM_H264.mp4", "SYNOPHOTO:FILM_H264.mp4",
             "SYNOPHOTO_FILM_M.mp4", "SYNOPHOTO:FILM_M.mp4", "SYNOPHOTO_FILM_CONVERT_MPEG4.mp4",
             "SYNOPHOTO:FILM_CONVERT_MPEG4.mp4", "SYNOPHOTO_FILM_MPEG4.mp4", "SYNOPHOTO:FILM_MPEG4.mp4",
             "SYNOPHOTO:FILM_MOBILE.mp4"]


def web_video(rel: str):
    """Cesta k verzii videa, ktoru prehra prehliadac. None = pouzi original."""
    if ext_of(rel) in WEB_VIDEO_EXT:
        return None
    d, n = posixpath.split(rel)
    base = os.path.join(ids.abs_path(d), "@eaDir", n)
    for name in EA_VIDEOS:
        st = _ea_serve(os.path.join(base, name))
        if st and st.st_size > 0:
            return os.path.join(base, name)
    return None


def _cache_path(rel: str, size: str) -> str:
    h = hashlib.sha1(rel.encode("utf-8")).hexdigest()
    return os.path.join(config.current().thumb_cache, h[:2], f"{h}_{size}.jpg")


def _fresh(out: str, src: str) -> bool:
    try:
        return os.stat(out).st_mtime + 5 >= os.stat(src).st_mtime
    except OSError:
        return False


def _generate(rel: str, kind: str, size: str, out: str) -> bool:
    px = config.THUMB_PX[size]
    src = ids.abs_path(rel)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".tmp"
    try:
        if kind == "photo":
            if ext_of(src) not in config.PIL_EXT:
                return False
            with Image.open(src) as im:
                tw, th = fit_short(im.size[0], im.size[1], px)
                if im.format == "JPEG":
                    im.draft("RGB", (tw, th))
                im = ImageOps.exif_transpose(im)
                tw, th = fit_short(im.size[0], im.size[1], px)
                if (tw, th) != im.size:
                    im = im.resize((tw, th), Image.Resampling.LANCZOS)
                if im.mode != "RGB":
                    im = im.convert("RGB")
                im.save(tmp, "JPEG", quality=85, optimize=True)
        else:
            if not FFMPEG:
                return False
            # kratsia strana = px (ak je video vacsie), druha dopocitana
            scale = f"scale='if(gt(iw,ih),-2,min({px},iw))':'if(gt(iw,ih),min({px},ih),-2)'"
            ok = False
            for ss in ("1", "0"):
                r = subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", ss, "-i", src, "-frames:v", "1",
                                    "-vf", scale, "-q:v", "3", "-f", "image2", tmp],
                                   capture_output=True, timeout=180)
                if r.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
                    ok = True
                    break
            if not ok:
                return False
        os.replace(tmp, out)
        return True
    except Exception as e:
        log.warning("thumbnail %s %s: %s", rel, size, e)
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def thumb_file(kind: str, rel: str, size: str):
    """Cesta k JPEG nahladu (z @eaDir alebo z cache), pripadne ho vygeneruje. None = nie je."""
    p = _ea_thumb(rel, size)
    if p:
        return p
    src = ids.abs_path(rel)
    out = _cache_path(rel, size)
    if _fresh(out, src):
        return out
    with _thumb_sem:
        if _fresh(out, src):
            return out
        return out if _generate(rel, kind, size, out) else None


def fit_short(w: int, h: int, px: int):
    """Pravidlo Photo Station (albumutil.php CalculateThumbSize): ak su obe strany vacsie nez px,
    kratsia strana sa zmensi na px; inak zostava povodna velkost."""
    if w > px and h > px:
        if w >= h:
            return max(1, round(w * px / h)), px
        return px, max(1, round(h * px / w))
    return w, h


def thumb_dims(m: dict, size: str) -> dict:
    w, h = fit_short(m.get("w", 0), m.get("h", 0), config.THUMB_PX[size])
    return {"resolutionx": w, "resolutiony": h}


# ---------------- titulna fotka albumu ----------------
COVER_TTL = 600


def clear_cover_cache():
    """Drop album cover cache of the current gallery only (one tenant's change must not flush others)."""
    name = config.current().name
    with _lock:
        for k in [k for k in _cover_cache if k[0] == name]:
            del _cover_cache[k]


def _set_cover(rel: str):
    """Titulna fotka nastavena v galerii (relativna cesta suboru)."""
    if not rel:
        return None
    p = store.album_props(rel)
    return p["cover"] if p and p["cover"] else None


def _ea_cover(rel: str):
    """Titulna fotka vybrana kedysi v Photo Station: <rodic>/@eaDir/<album>/SYNOPHOTO_ALBUM.cover = meno suboru."""
    if not rel:
        return None
    parent, name = posixpath.split(rel)
    base = os.path.join(ids.abs_path(parent), "@eaDir", name)
    for fn in ("SYNOPHOTO_ALBUM.cover", "SYNOPHOTO:ALBUM.cover"):
        try:
            with open(os.path.join(base, fn), "rb") as fh:
                v = fh.read(1024).decode("utf-8", "replace").strip().strip(NUL)
        except OSError:
            continue
        if v:
            try:
                return ids.clean_rel(posixpath.join(rel, v))
            except ids.BadId:
                return None
    return None


def _exists_media(rel: str) -> bool:
    try:
        return kind_of(rel) is not None and os.path.isfile(ids.abs_path(rel))
    except ids.BadId:
        return False


def cover(rel: str, perm, depth: int = 0):
    """Prva fotka/video v albume; ak nie je, hlada v podalbumoch (do hlbky 3)."""
    try:
        st = os.stat(ids.abs_path(rel))
    except OSError:
        return None
    key = (config.current().name, rel, perm.username, perm.admin, frozenset(perm.unlocked), frozenset(perm.rules),
           frozenset(perm.forced))
    with _lock:
        c = _cover_cache.get(key)
        # platnost: kym sa nezmeni priecinok a najviac COVER_TTL (titulka v @eaDir sa moze zmenit zvonku)
        if c and c[0] == st.st_mtime and time.time() - c[2] < COVER_TTL:
            return c[1]
    res = None
    try:
        dirs, files = list_dir(rel)
        for cand in (_set_cover(rel), _ea_cover(rel)):
            if cand and perm.can_browse(posixpath.dirname(cand)) and _exists_media(cand):
                res = cand
                break
        if res:
            pass
        elif files and perm.can_browse(rel):
            res = files[0]["rel"]
        elif depth < 3:
            for d in dirs:
                if perm.can_see(d["rel"]):
                    res = cover(d["rel"], perm, depth + 1)
                    if res:
                        break
    except OSError:
        res = None
    with _lock:
        _cover_cache[key] = (st.st_mtime, res, time.time())
    return res


# ---------------- indexer na pozadi ----------------
def index_once():
    from . import catalog, moves
    t0, n, errors = time.time(), 0, 0
    db = store.db()
    if refresh_places():
        catalog.invalidate()
    # stav z posledneho prechodu (nie meta - tu sa dopisuju aj subory otvorene medzi prechodmi)
    old = {r["path"]: r["size"] for r in db.execute("SELECT path, size FROM last_seen")}
    in_meta = [r["path"] for r in db.execute("SELECT path FROM meta")]
    seen = {}
    photo_root = config.current().root
    for root, dirs, _files in os.walk(photo_root, onerror=lambda e: None):
        dirs[:] = sorted(d for d in dirs if not d.startswith((".", "@", "#")))
        relroot = os.path.relpath(root, photo_root).replace(os.sep, "/")
        relroot = "" if relroot == "." else relroot
        try:
            _dir_cache.pop((config.current().name, relroot), None)  # vzdy cerstvy vypis
            _, media = list_dir(relroot)
        except (OSError, ids.BadId):
            errors += 1
            continue
        for f in media:
            try:
                f = with_stat(f)
                get_meta(f)
                seen[f["rel"]] = f["size"]
                n += 1
            except Exception as e:
                errors += 1
                log.debug("index %s: %s", f["rel"], e)
    # poistka: ak prechod videl podozrivo malo (vypadok NFS), nic nepresuvat ani nemazat
    base = max(len(old), len(in_meta))
    if base and len(seen) < 0.5 * base:
        log.warning("index saw only %d of %d files - skipping move detection and cleanup", len(seen), base)
    else:
        try:
            if old:  # prvy prechod po nasadeni nema s cim porovnat
                dir_map, file_map, ambiguous = moves.detect(old, seen)
                if dir_map or file_map:
                    moves.rewrite(dir_map, file_map, "auto")
                    clear_cover_cache()
                if ambiguous:
                    moves.record_ambiguous(ambiguous)
        except Exception:
            log.exception("move detection failed")
        gone = [p for p in in_meta if p not in seen]
        if gone:
            for i in range(0, len(gone), 500):
                part = gone[i:i + 500]
                db.execute(f"DELETE FROM meta WHERE path IN ({','.join('?' * len(part))})", part)
            log.info("removed %d files from the index that are no longer on disk", len(gone))
        db.execute("BEGIN")
        db.execute("DELETE FROM last_seen")
        db.executemany("INSERT INTO last_seen VALUES (?,?)", seen.items())
        db.execute("COMMIT")
    store.purge_sessions()
    catalog.invalidate()
    log.info("index done: %d files in %.0f s (%d errors)", n, time.time() - t0, errors)


def start_indexer():
    if config.INDEX_INTERVAL <= 0:
        return

    def loop():
        from . import catalog, galleries
        # warm-up: the library lists and place names are ready before the first visitor asks for them
        try:
            if geo.available():
                geo._load()
            for g in [config.MAIN] + galleries.all_enabled():
                tok = config.use(g)
                try:
                    catalog.snapshot()
                finally:
                    config.reset(tok)
        except Exception:
            log.exception("warm-up failed")
        while True:
            for g in [config.MAIN] + galleries.all_enabled():
                index_gallery(g)
            time.sleep(config.INDEX_INTERVAL)

    threading.Thread(target=loop, name="indexer", daemon=True).start()


_index_locks = {}


def index_gallery(g):
    """One index pass of a gallery (skipped when another pass of the same gallery is running)."""
    with _lock:
        lk = _index_locks.setdefault(g.name, threading.Lock())
    if not lk.acquire(blocking=False):
        return
    tok = config.use(g)
    try:
        index_once()
    except Exception:
        log.exception("index failed (%s)", g.name or "main")
    finally:
        config.reset(tok)
        lk.release()
