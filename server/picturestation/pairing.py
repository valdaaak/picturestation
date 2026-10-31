# SPDX-License-Identifier: GPL-3.0-or-later
"""Pairing of the LG TV app (LGTV/) with a user, like a streaming app: the TV shows a code, the gallery's
administrator enters it under Settings, TV, and chooses whose photos the TV sees. The TV then holds a
long-lived device session (tables sessions + devices), which the administrator can remove there.

  POST /api/tv/code  name=<device model>  -> {"code": "K7M3PX", "token": "<secret>", "expires_in": 600}
  POST /api/tv/poll  token=<secret>       -> {"status": "pending"}
                                          |  {"status": "ok", "sid": ..., "username": ..., "title": ...}  (once)
                                          |  {"status": "unknown"}  (expired, never existed, or already handed out)

Both answer CORS requests from any origin, without credentials (the TV app is a packaged web app without an
origin). The code is only shown on the TV; the token never leaves the TV. Codes wait 10 minutes.
Pending codes live in memory, per gallery; after a server restart the TV simply asks for a new one."""
import json
import secrets
import threading
import time
from urllib.parse import parse_qsl

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from . import config, store

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O and 1/I: the code is read off a screen
CODE_LEN = 6
CODE_TTL = 600         # seconds a code waits for the administrator
MAX_PENDING = 200      # per gallery
MAX_PER_CLIENT = 5     # per client address: a further request replaces that client's oldest code
CORS = {"Access-Control-Allow-Origin": "*",  # also on every DS photo API answer (app.py)
        "Access-Control-Expose-Headers": "x-request-error, x-picturestation-version"}
_lock = threading.Lock()
_pending: dict = {}    # (gallery name, code) -> {"token", "name", "ip", "created", "sid", "username"}


def _purge(now: float):
    for k in [k for k, v in _pending.items() if now - v["created"] > CODE_TTL]:
        del _pending[k]


def new_code(name: str, ip: str):
    """A fresh code for a TV. None when the gallery already has too many waiting codes."""
    g = config.current().name
    now = time.time()
    with _lock:
        _purge(now)
        mine = sorted((k for k, v in _pending.items() if k[0] == g and v["ip"] == ip), key=lambda k: _pending[k]["created"])
        for k in mine[:max(0, len(mine) + 1 - MAX_PER_CLIENT)]:
            del _pending[k]
        if sum(1 for k in _pending if k[0] == g) >= MAX_PENDING:
            return None
        while True:
            code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))
            if (g, code) not in _pending:
                break
        token = secrets.token_hex(16)
        _pending[(g, code)] = {"token": token, "name": name, "ip": ip, "created": now, "sid": None, "username": None}
    return {"code": code, "token": token, "expires_in": CODE_TTL}


def normalize_code(code: str) -> str:
    return (code or "").upper().replace(" ", "").replace("-", "")


def approve(code: str, username: str) -> dict:
    """Administrator: the TV that shows `code` becomes a device of `username`. KeyError when the code is not waiting."""
    g = config.current().name
    with _lock:
        _purge(time.time())
        e = _pending.get((g, normalize_code(code)))
        if e is None or e["sid"]:
            raise KeyError(code)
        e["sid"], e["username"] = store.new_device_session(username, e["name"]), username
        return {"name": e["name"], "username": username}


def poll(token: str) -> dict:
    g = config.current().name
    if not isinstance(token, str) or len(token) != 32 or not token.isalnum():
        return {"status": "unknown"}
    with _lock:
        _purge(time.time())
        for k, e in list(_pending.items()):
            if k[0] == g and secrets.compare_digest(e["token"], token):
                if not e["sid"]:
                    return {"status": "pending"}
                del _pending[k]  # the session is handed out exactly once
                return {"status": "ok", "sid": e["sid"], "username": e["username"],
                        "title": store.get_setting("title", store.default_title())}
    return {"status": "unknown"}


async def tv_api(req: Request):
    if req.method == "OPTIONS":
        return Response(status_code=204, headers={**CORS, "Access-Control-Allow-Methods": "POST, OPTIONS",
                                                  "Access-Control-Allow-Headers": "Content-Type",
                                                  "Access-Control-Max-Age": "86400"})
    p = dict(req.query_params)
    ctype = req.headers.get("content-type", "")
    if ctype.startswith("application/x-www-form-urlencoded"):
        p.update(parse_qsl((await req.body()).decode("utf-8", "replace"), keep_blank_values=True))
    elif ctype.startswith("application/json"):
        try:
            body = json.loads(await req.body() or b"{}")
        except ValueError:
            body = None
        if isinstance(body, dict):
            p.update({k: str(v) for k, v in body.items()})
    op = req.path_params["op"]
    if op == "code":
        name = " ".join((p.get("name") or "").split())[:60] or "TV"
        ip = req.client.host if req.client else ""
        res = await run_in_threadpool(new_code, name, ip)
        if res is None:
            return JSONResponse({"error": "too many waiting codes, try again later"}, status_code=429, headers=CORS)
        return JSONResponse(res, headers=CORS)
    if op == "poll":
        return JSONResponse(await run_in_threadpool(poll, p.get("token") or ""), headers=CORS)
    return JSONResponse({"error": "unknown operation"}, status_code=404, headers=CORS)
