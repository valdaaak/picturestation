# SPDX-License-Identifier: GPL-3.0-or-later
"""Miesta z GPS offline: najblizsia obec z GeoNames (cities500 + countryInfo, CC BY 4.0).

Subory sa stiahnu raz do DATA_DIR/geonames (deploy.sh). Ziadne suradnice neodchadzaju von.
"""
import logging
import math
import os
import threading

from . import config, i18n

log = logging.getLogger("picturestation.geo")
# viac galerii na jednej VM zdiela jeden adresar (PICTURESTATION_GEONAMES)
GEO_DIR = config.env("GEONAMES") or os.path.join(config.DATA_DIR, "geonames")
MAX_KM = 25.0

_lock = threading.Lock()
_grid = None       # (lat_bucket, lon_bucket) -> [(lat, lon, name, cc)]
_countries = {}    # cc -> nazov krajiny
_failed = False

# Slovenske nazvy najcastejsich krajin (GeoNames ma anglicke).
SK_COUNTRY = {
    "SK": "Slovensko", "CZ": "Česko", "AT": "Rakúsko", "HU": "Maďarsko", "PL": "Poľsko", "DE": "Nemecko",
    "HR": "Chorvátsko", "IT": "Taliansko", "ES": "Španielsko", "FR": "Francúzsko", "GR": "Grécko",
    "SI": "Slovinsko", "CH": "Švajčiarsko", "GB": "Spojené kráľovstvo", "US": "USA", "EG": "Egypt",
    "TR": "Turecko", "UA": "Ukrajina", "RO": "Rumunsko", "BG": "Bulharsko", "PT": "Portugalsko",
    "NL": "Holandsko", "BE": "Belgicko", "DK": "Dánsko", "SE": "Švédsko", "NO": "Nórsko", "ME": "Čierna Hora",
    "MT": "Malta", "CY": "Cyprus", "TN": "Tunisko", "TH": "Thajsko", "AE": "Spojené arabské emiráty",
    "BB": "Barbados", "GD": "Grenada", "LC": "Svätá Lucia", "MQ": "Martinik", "VC": "Svätý Vincent a Grenadíny",
    "IQ": "Irak", "VN": "Vietnam", "MV": "Maldivy", "MX": "Mexiko", "DO": "Dominikánska republika",
}


def available() -> bool:
    return os.path.isfile(os.path.join(GEO_DIR, "cities500.txt"))


# Full country dumps (e.g. SK.txt from download.geonames.org/export/dump/SK.zip) add small villages that
# cities500 leaves out. Only populated places, without city sections and historical or abandoned places.
PLACE_CODES = {"PPL", "PPLA", "PPLA2", "PPLA3", "PPLA4", "PPLA5", "PPLC", "PPLF", "PPLG", "PPLL", "PPLR", "PPLS"}


def country_files() -> list:
    try:
        names = os.listdir(GEO_DIR)
    except OSError:
        return []
    return sorted(n for n in names if len(n) == 6 and n.endswith(".txt") and n[:2].isalpha() and n[:2].isupper())


def signature() -> str:
    """Changes when the place data changes (then places of all photos are looked up again)."""
    parts = []
    for n in ["cities500.txt"] + country_files():
        try:
            st = os.stat(os.path.join(GEO_DIR, n))
            parts.append(f"{n}:{st.st_size}")
        except OSError:
            pass
    return f"{MAX_KM}|" + ",".join(parts)


def _add(grid, c, name):
    try:
        lat, lon = float(c[4]), float(c[5])
    except ValueError:
        return False
    grid.setdefault((int(math.floor(lat)), int(math.floor(lon))), []).append((lat, lon, name, c[8]))
    return True


def _read_cities(path, grid, skip_cc):
    """cities500: towns and villages over 500 inhabitants, except countries that have a full dump."""
    n = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            c = line.rstrip("\r\n").split("\t")
            if len(c) > 8 and c[8] not in skip_cc and _add(grid, c, c[1]):
                n += 1
    return n


def _read_country(path, grid):
    """Full country dump: every populated place, named after its municipality (ADM3, e.g. a Slovak obec),
    so that a settlement such as Misuty shows as Donovaly."""
    rows, municipality = [], {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            c = line.rstrip("\r\n").split("\t")
            if len(c) < 13:
                continue
            if c[6] == "A" and c[7] == "ADM3":
                municipality[(c[10], c[11], c[12])] = c[1]
            elif c[6] == "P" and c[7] in PLACE_CODES:
                rows.append(c)
    n = 0
    for c in rows:
        name = municipality.get((c[10], c[11], c[12])) if c[12] else None
        if _add(grid, c, name or c[1]):
            n += 1
    return n


def _load():
    global _grid, _failed
    with _lock:
        if _grid is not None or _failed:
            return
        try:
            grid = {}
            full = country_files()
            n = _read_cities(os.path.join(GEO_DIR, "cities500.txt"), grid, {f[:2] for f in full})
            extra = {f[:2]: _read_country(os.path.join(GEO_DIR, f), grid) for f in full}
            ci = os.path.join(GEO_DIR, "countryInfo.txt")
            if os.path.isfile(ci):
                with open(ci, encoding="utf-8") as fh:
                    for line in fh:
                        if line.startswith("#"):
                            continue
                        c = line.rstrip("\r\n").split("\t")
                        if len(c) > 4:
                            _countries[c[0]] = c[4]
            _grid = grid
            log.info("GeoNames loaded: %d places%s", n,
                     "".join(f", {k} full list {v}" for k, v in extra.items()))
        except OSError as e:
            log.warning("GeoNames not available: %s", e)
            _failed = True


def country_name(cc: str) -> str:
    """Country name in the language of the current request (i18n.lang())."""
    if i18n.lang() == "sk" and cc in SK_COUNTRY:
        return SK_COUNTRY[cc]
    if not _countries and available():
        _load()  # nazvy krajin sa nacitaju aj bez predosleho hladania miesta (napr. po restarte)
    return _countries.get(cc) or cc


def lookup(lat: float, lon: float):
    """(obec, kod krajiny) alebo None, ak v okruhu MAX_KM nic nie je."""
    if not available():
        return None
    _load()
    if not _grid:
        return None
    best, best_d = None, MAX_KM
    bl, bo = int(math.floor(lat)), int(math.floor(lon))
    coslat = math.cos(math.radians(lat))
    for dl in (-1, 0, 1):
        for do in (-1, 0, 1):
            for clat, clon, name, cc in _grid.get((bl + dl, bo + do), ()):
                dx = (clon - lon) * 111.32 * coslat
                dy = (clat - lat) * 110.57
                d = math.hypot(dx, dy)
                if d < best_d:
                    best, best_d = (name, cc), d
    return best
