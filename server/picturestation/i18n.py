# SPDX-License-Identifier: GPL-3.0-or-later
"""Server-side texts in English and Slovak.

Source strings in the code are English; SK maps them to Slovak. The language of a request is
the X-Lang header sent by the web gallery, otherwise the gallery setting "language"
(auto = Accept-Language, sk or cs -> Slovak, anything else -> English).
"""
import threading

LANGS = ("en", "sk")
_local = threading.local()

SK = {
    # admin API
    "Not logged in.": "Nie si prihlásený.",
    "Settings require an administrator.": "Na nastavenia treba admina.",
    "User does not exist.": "Používateľ neexistuje.",
    "Unknown type.": "Neznámy typ.",
    "Group does not exist.": "Skupina neexistuje.",
    "Unknown or expired code. Check it on the TV; after 10 minutes it shows a new one.":
        "Neznámy alebo vypršaný kód. Skontroluj ho na telke; po 10 minútach ukáže nový.",
    "Enter a name.": "Zadaj názov.",
    "No such device.": "Také zariadenie neexistuje.",
    "Enter the album password.": "Zadaj heslo albumu.",
    "Password must have at least 8 characters.": "Heslo musí mať aspoň 8 znakov.",
    "Invalid name.": "Neplatné meno.",
    "Such a user already exists.": "Taký používateľ už existuje.",
    "At least one administrator must remain.": "Aspoň jeden admin musí zostať.",
    "The last administrator cannot be disabled.": "Posledného admina nemožno zablokovať.",
    "You cannot delete yourself.": "Sám seba zmazať nemôžeš.",
    "Invalid group name.": "Neplatný názov skupiny.",
    "Such a group already exists.": "Taká skupina už existuje.",
    "Invalid path.": "Neplatná cesta.",
    "No such album.": "Taký album neexistuje.",
    "Album does not exist.": "Album neexistuje.",
    "The whole library cannot be excluded, remove the access instead.":
        "Celú knižnicu vylúčiť nemožno, stačí odobrať prístup.",
    "Invalid cover photo.": "Neplatná titulná fotka.",
    "The cover photo must be from this album.": "Titulná fotka musí byť z tohto albumu.",
    "Unknown access type.": "Neznámy typ prístupu.",
    "Album password must have at least 4 characters.": "Heslo albumu musí mať aspoň 4 znaky.",
    "The whole library cannot be shared.": "Celú knižnicu zdieľať nemožno.",
    "No such album or file.": "Taký album ani súbor neexistuje.",
    "Invalid validity.": "Neplatná platnosť.",
    "No such file.": "Taký súbor neexistuje.",
    "Enter a tag name.": "Zadaj názov tagu.",
    "Invalid tag.": "Neplatný tag.",
    "Dates use the format YYYY-MM-DD.": "Dátum má tvar RRRR-MM-DD.",
    "Invalid album.": "Neplatný album.",
    "Enter at least one criterion.": "Zadaj aspoň jedno kritérium.",
    "Enter a name for the smart album.": "Zadaj názov chytrého albumu.",
    "The target album does not exist.": "Cieľový album neexistuje.",
    "An album cannot be moved into itself.": "Album nemožno presunúť do seba.",
    "The album exists on disk, nothing deleted.": "Album na disku existuje, nič nemažem.",
    "Unknown operation.": "Neznáma operácia.",
    "JSON expected.": "Očakávam JSON.",
    "Bad JSON.": "Zlý JSON.",
    "POST required.": "Treba POST.",
    "Invalid request. Reload the page (F5).": "Neplatná požiadavka. Obnov stránku (F5).",
    # private galleries
    "Galleries are managed in the main gallery.": "Galérie sa spravujú v hlavnej galérii.",
    "The folder must be an absolute path.": "Priečinok musí byť zadaný celou cestou (začína /).",
    "The folder must be inside: {roots}.": "Priečinok musí byť vnútri: {roots}.",
    "The folder does not exist or cannot be read.": "Priečinok neexistuje alebo sa nedá čítať.",
    "Invalid domain: {host}.": "Neplatná doména: {host}.",
    "The domain {host} already belongs to another gallery.": "Doména {host} už patrí inej galérii.",
    "The name may contain lower-case letters, digits and dashes (max. 31).":
        "Meno môže obsahovať malé písmená, číslice a pomlčky (najviac 31).",
    "Such a gallery already exists.": "Taká galéria už existuje.",
    "Data of a gallery with this name already exist.": "Dáta galérie s týmto menom už existujú.",
    "No such gallery.": "Taká galéria neexistuje.",
    # share links
    "The link is not valid or has expired.": "Odkaz neplatí alebo vypršal.",
}


def pick(header: str) -> str:
    """Language from an Accept-Language style header; Slovak for sk and cs, otherwise English."""
    for part in (header or "").lower().replace(" ", "").split(","):
        code = part.split(";")[0][:2]
        if code in ("sk", "cs"):
            return "sk"
        if code:
            return "en"
    return "en"


def for_request(req) -> str:
    x = (req.headers.get("x-lang") or "").lower()
    if x in LANGS:
        return x
    from . import store  # lazy: store imports config only, but keep i18n importable alone
    d = store.get_setting("language", "auto") or "auto"
    return d if d in LANGS else pick(req.headers.get("accept-language", ""))


def set_lang(lang: str):
    _local.lang = lang if lang in LANGS else "en"


def lang() -> str:
    return getattr(_local, "lang", "en")


def tr(msg: str, lang_: str | None = None, **kw) -> str:
    out = SK.get(msg, msg) if (lang_ or lang()) == "sk" else msg
    return out.format(**kw) if kw else out
