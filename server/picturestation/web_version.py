"""Verzia webovej galerie = odtlacok jej suborov. Ked sa zmeni, otvorena stranka ponukne obnovenie."""
import hashlib
import os

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")


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
