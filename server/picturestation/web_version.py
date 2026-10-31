# SPDX-License-Identifier: GPL-3.0-or-later
"""Verzia webovej galerie = odtlacok jej suborov. Ked sa zmeni, otvorena stranka ponukne obnovenie."""
import hashlib
import os

from .config import env


def _find_web_dir() -> str:
    """Folder of the web gallery: PICTURESTATION_WEB_DIR, else web/ at the top of the repository
    (development, next to server/) or next to the package (installed: /opt/picturestation/web, Docker)."""
    forced = env("WEB_DIR")
    if forced:
        return forced
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(here, "..", "..", "web"), os.path.join(here, "..", "web")):
        if os.path.isfile(os.path.join(cand, "index.html")):
            return os.path.normpath(cand)
    raise RuntimeError("web gallery folder not found (web/index.html); set PICTURESTATION_WEB_DIR")


WEB_DIR = _find_web_dir()


def _compute() -> str:
    h = hashlib.sha1()
    for name in sorted(os.listdir(WEB_DIR)):
        p = os.path.join(WEB_DIR, name)
        if os.path.isfile(p):
            h.update(name.encode())
            with open(p, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()[:12]


VERSION = _compute()
