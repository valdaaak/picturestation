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


def _load():
    global _grid, _failed
    with _lock:
        if _grid is not None or _failed:
            return
        try:
            grid = {}
            n = 0
            with open(os.path.join(GEO_DIR, "cities500.txt"), encoding="utf-8") as fh:
                for line in fh:
                    c = line.split("\t")
                    try:
                        lat, lon = float(c[4]), float(c[5])
                    except (IndexError, ValueError):
                        continue
                    grid.setdefault((int(math.floor(lat)), int(math.floor(lon))), []).append(
                        (lat, lon, c[1], c[8]))
                    n += 1
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
            log.info("GeoNames nacitane: %d obci", n)
        except OSError as e:
            log.warning("GeoNames nedostupne: %s", e)
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
