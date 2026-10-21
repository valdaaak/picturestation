# SPDX-License-Identifier: GPL-3.0-or-later
import contextvars
import os
import threading
from dataclasses import dataclass


def env(name: str, default: str = "") -> str:
    """PICTURESTATION_<name>, pre starsie instalacie aj DSPHOTO_<name>."""
    v = os.environ.get("PICTURESTATION_" + name)
    if v is None:
        v = os.environ.get("DSPHOTO_" + name)
    return default if v is None else v


# Main gallery: photo folder (read-only is enough) and the server's data folder (database, thumbnails, GeoNames).
MAIN_ROOT = os.path.realpath(env("ROOT", "/mnt/photo"))
DATA_DIR = env("DATA", "/var/lib/picturestation")
TITLE = env("TITLE", "Picturestation")
# Private galleries: their data in DATA_DIR/galleries/<name>, their photos only below these folders.
GALLERIES_DIR = os.path.join(DATA_DIR, "galleries")
GALLERY_ROOTS = [os.path.realpath(p) for p in env("GALLERY_ROOTS", "/srv/galleries:/mnt/galleries").split(":") if p]
# Verzia, ktoru hlasime appke. Appka zapina funkcie od 2115/2124/2700; 3483 = posledna Photo Station 6.8.9.
PKG_VERSION = "3483"
PKG_VERSION_STRING = "6.8.9-3483"
SESSION_DAYS = int(env("SESSION_DAYS", "30"))
# Meno session cookie. Viac galerii na jednej IP (rozne porty) musi mat rozne mena - cookie sa neviaze na port.
SESSION_COOKIE = env("COOKIE", "PHPSESSID")
# Ako casto prejst cely strom a doplnit metadata (sekundy). 0 = vypnute.
INDEX_INTERVAL = int(env("INDEX_INTERVAL", str(6 * 3600)))
# Kolko nahladov sa smie generovat naraz (zvysok caka).
THUMB_WORKERS = int(env("THUMB_WORKERS", "2"))

_MAIN_DB = os.path.join(DATA_DIR, "picturestation.sqlite")
if not os.path.exists(_MAIN_DB) and os.path.exists(os.path.join(DATA_DIR, "dsphoto.sqlite")):
    _MAIN_DB = os.path.join(DATA_DIR, "dsphoto.sqlite")  # databaza zo starsej instalacie (DSphoto-server)


@dataclass(frozen=True)
class Gallery:
    """One gallery: the main one (name "") or a private one. Everything that depends on the gallery of the
    current request (photo folder, database, thumbnails, cookie scope) comes from current()."""
    name: str
    root: str
    data_dir: str
    title: str = ""
    prefix: str = ""   # "/~name" when the request came by path, "" by host name (or the main gallery)

    @property
    def is_main(self) -> bool:
        return self.name == ""

    @property
    def cookie(self) -> str:
        """Session cookie name; private galleries have their own so that browsers keep both sessions."""
        return SESSION_COOKIE if self.is_main else "PS_" + self.name.upper().replace("-", "_")

    @property
    def cookie_path(self) -> str:
        return self.prefix + "/" if self.prefix else "/"

    @property
    def db_path(self) -> str:
        return _MAIN_DB if self.is_main else os.path.join(self.data_dir, "picturestation.sqlite")

    @property
    def thumb_cache(self) -> str:
        return os.path.join(self.data_dir, "thumbs")

    @property
    def base(self) -> str:
        """URL prefix for links in this request: "" or "/~name"."""
        return self.prefix


MAIN = Gallery("", MAIN_ROOT, DATA_DIR, TITLE)
_current = contextvars.ContextVar("picturestation_gallery", default=MAIN)


def current() -> Gallery:
    return _current.get()


def use(g: Gallery):
    """Switch the current gallery (returns a token for reset())."""
    return _current.set(g)


def reset(token):
    _current.reset(token)


def private(name: str, root: str, title: str = "") -> Gallery:
    return Gallery(name, os.path.realpath(root), os.path.join(GALLERIES_DIR, name), title)


def in_thread(target, *args):
    """A thread that runs in the gallery of the caller (contextvars are not inherited by new threads)."""
    ctx = contextvars.copy_context()
    return threading.Thread(target=ctx.run, args=(target, *args), daemon=True)

PHOTO_EXT = {"jpg", "jpeg", "jpe", "png", "gif", "bmp", "tif", "tiff", "heic", "heif",
             "cr2", "cr3", "nef", "arw", "dng", "orf", "rw2", "raf"}
VIDEO_EXT = {"mp4", "mov", "avi", "mts", "m2ts", "mkv", "mpg", "mpeg", "3gp", "m4v",
             "wmv", "flv", "vob", "webm"}
# Formaty, ktore vie Pillow otvorit bez dalsich pluginov (pre generovanie nahladov a EXIF).
PIL_EXT = {"jpg", "jpeg", "jpe", "png", "gif", "bmp", "tif", "tiff"}

# Velkosti nahladov - dlhsia strana v px (syno_defines.php: PREVIEW 160, MEDIUM 320, XLARGE 1280).
THUMB_PX = {"preview": 160, "small": 320, "large": 1280}
