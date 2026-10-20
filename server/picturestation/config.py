import os


def env(name: str, default: str = "") -> str:
    """PICTURESTATION_<name>, pre starsie instalacie aj DSPHOTO_<name>."""
    v = os.environ.get("PICTURESTATION_" + name)
    if v is None:
        v = os.environ.get("DSPHOTO_" + name)
    return default if v is None else v


# Koren s fotkami (NFS, len na citanie) a pracovny priecinok servera (DB + cache nahladov).
PHOTO_ROOT = os.path.realpath(env("ROOT", "/mnt/photo"))
DATA_DIR = env("DATA", "/var/lib/picturestation")
TITLE = env("TITLE", "Picturestation")
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

DB_PATH = os.path.join(DATA_DIR, "picturestation.sqlite")
if not os.path.exists(DB_PATH) and os.path.exists(os.path.join(DATA_DIR, "dsphoto.sqlite")):
    DB_PATH = os.path.join(DATA_DIR, "dsphoto.sqlite")  # databaza zo starsej instalacie (DSphoto-server)
THUMB_CACHE = os.path.join(DATA_DIR, "thumbs")

PHOTO_EXT = {"jpg", "jpeg", "jpe", "png", "gif", "bmp", "tif", "tiff", "heic", "heif",
             "cr2", "cr3", "nef", "arw", "dng", "orf", "rw2", "raf"}
VIDEO_EXT = {"mp4", "mov", "avi", "mts", "m2ts", "mkv", "mpg", "mpeg", "3gp", "m4v",
             "wmv", "flv", "vob", "webm"}
# Formaty, ktore vie Pillow otvorit bez dalsich pluginov (pre generovanie nahladov a EXIF).
PIL_EXT = {"jpg", "jpeg", "jpe", "png", "gif", "bmp", "tif", "tiff"}

# Velkosti nahladov - dlhsia strana v px (syno_defines.php: PREVIEW 160, MEDIUM 320, XLARGE 1280).
THUMB_PX = {"preview": 160, "small": 320, "large": 1280}
