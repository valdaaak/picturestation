"""Spustenie servera: python3 -m picturestation"""
import logging
import os

import uvicorn

from .config import env


def main():
    logging.basicConfig(level=env("LOG", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run("picturestation.app:app",
                host=env("HOST", "0.0.0.0"),
                port=int(env("PORT", "80")),
                proxy_headers=True,
                forwarded_allow_ips=env("TRUSTED_PROXIES", "127.0.0.1"),
                log_config=None,
                access_log=env("ACCESS_LOG", "0") == "1")


if __name__ == "__main__":
    main()
