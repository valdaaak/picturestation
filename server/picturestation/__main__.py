# SPDX-License-Identifier: GPL-3.0-or-later
"""Spustenie servera: python3 -m picturestation"""
import logging
import os

import uvicorn

from . import __version__
from .config import env


def main():
    logging.basicConfig(level=env("LOG", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("picturestation").info("Picturestation %s", __version__)
    uvicorn.run("picturestation.app:app",
                host=env("HOST", "0.0.0.0"),
                port=int(env("PORT", "80")),
                proxy_headers=True,
                forwarded_allow_ips=env("TRUSTED_PROXIES", "127.0.0.1"),
                log_config=None,
                access_log=env("ACCESS_LOG", "0") == "1")


if __name__ == "__main__":
    main()
