# SPDX-License-Identifier: GPL-3.0-or-later
"""Upright copies of sideways videos for the LG TV app (LGTV/).

Phones record portrait videos sideways and only set a rotation flag. Browsers and phones honour the flag,
the TV's player does not, so the TV would show them lying on their side. For such videos the server keeps a
copy with the frames really rotated (H.264/AAC, at most 1080p) in DATA/video_tv/, made by ffmpeg in a
background thread at the lowest priority, one at a time. The TV app asks for `variant=tv`: the copy when
it exists, otherwise the usual file plus the header X-Picturestation-Video: preparing. After the server
starts, the library is gone through once (newest folders first) so that the copies are ready in advance.
A video's rotation is kept in its metadata (key "rotation"); videos indexed before this existed are probed
on the first occasion."""
import collections
import hashlib
import logging
import os
import shutil
import subprocess
import threading
import time

from . import config, ids, media, store

log = logging.getLogger("picturestation.tvvideo")
ROTATED = (90, 180, 270)
MIN_FREE_BYTES = 2 * 1024 ** 3   # keep this much free on the data disk
FFMPEG_TIMEOUT = 4 * 3600        # per video
_queue = collections.deque()     # (gallery, rel), newest requests served first
_queued = set()                  # (gallery name, rel)
_failed = {}                     # (gallery name, rel) -> why it could not be converted in this run
_busy = None                     # (gallery name, rel) being converted now
_lock = threading.Lock()
_wake = threading.Event()
_started = False


def cache_path(rel: str) -> str:
    h = hashlib.sha1(rel.encode("utf-8")).hexdigest()
    return os.path.join(config.current().data_dir, "video_tv", h[:2], h + ".mp4")


def rotation_of(f: dict) -> int:
    """Rotation flag of a video item (0/90/180/270), from its metadata; probed and stored when unknown."""
    m = media.get_meta(f)
    r = m.get("rotation")
    if r is None:
        r = media.probe_rotation(ids.abs_path(f["rel"]))
        m["rotation"] = r
        store.meta_put(f["rel"], f["mtime"], f["size"], f["kind"], m)
    return r


def needs_copy(f: dict) -> bool:
    return rotation_of(f) in ROTATED


def ready_path(f: dict):
    """The upright copy of a video, when it exists and is not older than the video."""
    p = cache_path(f["rel"])
    try:
        return p if os.path.getsize(p) > 0 and os.path.getmtime(p) >= f["mtime"] - 1 else None
    except OSError:
        return None


def status(f: dict, rotation=None) -> str:
    """'none' = plays as it is, 'ready' = upright copy exists, 'waiting' = still to be made."""
    rotation = rotation_of(f) if rotation is None else rotation
    if rotation not in ROTATED:
        return "none"
    return "ready" if ready_path(f) else "waiting"


def request(f: dict, front=True):
    """Queue a video for conversion (no-op when its copy exists, or it failed in this run)."""
    g = config.current()
    key = (g.name, f["rel"])
    with _lock:
        if key in _queued or key in _failed or key == _busy:
            return
        _queued.add(key)
        if front:
            _queue.appendleft((g, f["rel"]))
        else:
            _queue.append((g, f["rel"]))
    _wake.set()


def _convert(g, rel: str) -> str:
    """Make the upright copy of one video. Returns "" when done, otherwise why not."""
    tok = config.use(g)
    try:
        src = ids.abs_path(rel)
        if not media.FFMPEG or not os.access(src, os.R_OK):
            why = "no ffmpeg" if not media.FFMPEG else "file not readable (permissions on the NAS?)"
            log.warning("cannot convert %s: %s", rel, why)
            return why
        out = cache_path(rel)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        if shutil.disk_usage(os.path.dirname(out)).free < MIN_FREE_BYTES:
            why = "less than %d MB free on the data disk" % (MIN_FREE_BYTES // 2 ** 20)
            log.warning("not converting %s: %s", rel, why)
            return why
        tmp = out + ".part"
        t0 = time.time()
        # ffmpeg applies the rotation flag itself; the copy has upright frames and no flag
        cmd = [media.FFMPEG, "-v", "error", "-nostdin", "-y", "-i", src,
               "-vf", "scale=w='min(1920,iw)':h='min(1080,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-movflags", "+faststart", "-f", "mp4", tmp]
        # lowest priority through the nice command, never preexec_fn (it can deadlock a forked child
        # of a multi-threaded server before ffmpeg even starts)
        nice = shutil.which("nice")
        if nice:
            cmd = [nice, "-n", "19"] + cmd
        r = subprocess.run(cmd, capture_output=True, timeout=FFMPEG_TIMEOUT)
        if r.returncode != 0 or not os.path.exists(tmp) or not os.path.getsize(tmp):
            why = "ffmpeg: " + r.stderr.decode("utf-8", "replace")[-300:].strip()
            log.warning("conversion of %s failed, %s", rel, why)
            try:
                os.remove(tmp)
            except OSError:
                pass
            return why
        os.replace(tmp, out)
        log.info("upright copy of %s made in %.0f s (%d MB)", rel, time.time() - t0, os.path.getsize(out) >> 20)
        return ""
    except Exception as e:
        log.exception("converting %s", rel)
        return repr(e)
    finally:
        config.reset(tok)


def process_now(limit=None) -> int:
    """Convert queued videos in the calling thread (tests, or a one-off run). Returns how many succeeded."""
    global _busy
    done = 0
    while limit is None or done < limit:
        with _lock:
            if not _queue:
                return done
            g, rel = _queue.popleft()
            _queued.discard((g.name, rel))
            _busy = (g.name, rel)
        why = _convert(g, rel)
        with _lock:
            _busy = None
            if why:
                _failed[(g.name, rel)] = why
        done += not why
    return done


def library_pass():
    """Queue every sideways video of every gallery, newest folders first; probes the videos whose rotation
    is not known yet (those indexed before the flag was recorded)."""
    from . import galleries
    for g in [config.MAIN] + galleries.all_enabled():
        tok = config.use(g)
        try:
            rows = store.db().execute("SELECT path, mtime, size, data FROM meta WHERE kind='video' ORDER BY path DESC").fetchall()
            n = 0
            for r in rows:
                f = {"rel": r["path"], "name": os.path.basename(r["path"]), "mtime": r["mtime"], "size": r["size"],
                     "kind": "video"}
                try:
                    if needs_copy(f) and not ready_path(f):
                        request(f, front=False)
                        n += 1
                except Exception as e:
                    log.debug("library pass %s: %s", r["path"], e)
                time.sleep(0.02)
            if n:
                log.info("%d sideways videos to convert for the TV (%s)", n, g.name or "main gallery")
        except Exception:
            log.exception("library pass failed (%s)", g.name or "main")
        finally:
            config.reset(tok)


def start():
    """The background worker: first the library pass, then whatever is queued, forever."""
    global _started
    if _started or not media.FFMPEG:
        return
    _started = True

    def loop():
        time.sleep(30)  # let the server settle first
        library_pass()
        while True:
            process_now()
            _wake.wait(300)
            _wake.clear()

    threading.Thread(target=loop, name="tvvideo", daemon=True).start()
