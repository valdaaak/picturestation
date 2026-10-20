# SPDX-License-Identifier: GPL-3.0-or-later
"""User and rights management:  picturestation-user <command> ...

  list                                   users and their rights
  useradd NAME [--admin] [--note TEXT]   new user (asks for the password)
  passwd NAME                            change password
  userdel NAME                           delete (with rights and sessions)
  disable NAME | enable NAME             block / unblock
  admin NAME on|off                      administrators see everything
  grant NAME PATH                        access to an album (and its sub-albums); PATH '' or / = everything
  exclude NAME PATH                      exclude an album from an allowed one (the most specific rule wins)
  revoke NAME PATH                       remove a rule (allow or exclude)
  albums [PATH]                          list albums in a folder (helps with grant)

Guests (not signed in) are the user @guest, give them rights with: grant @guest PATH.
The password can also come from stdin:  echo password | picturestation-user passwd NAME --stdin
"""
import argparse
import getpass
import os
import sys

from . import ids, store


def _password(args) -> str:
    if args.stdin:
        pw = sys.stdin.readline().rstrip("\r\n")
    else:
        pw = getpass.getpass("Password: ")
        if pw != getpass.getpass("Password again: "):
            sys.exit("Passwords do not match.")
    if len(pw) < 8:
        sys.exit("Password must have at least 8 characters.")
    return pw


def _need_user(name):
    if name == store.GUEST:
        return
    if store.get_user(name) is None:
        sys.exit(f"User {name} does not exist.")


def _path(p: str) -> str:
    try:
        rel = ids.clean_rel(p)
    except ids.BadId:
        sys.exit(f"Invalid path: {p}")
    if not os.path.isdir(ids.abs_path(rel)):
        print(f"Warning: album '{rel}' does not exist now (the rule is saved anyway).", file=sys.stderr)
    return rel


def main(argv=None):
    ap = argparse.ArgumentParser(prog="picturestation.cli", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    a = sub.add_parser("useradd"); a.add_argument("name"); a.add_argument("--admin", action="store_true")
    a.add_argument("--note", default=""); a.add_argument("--stdin", action="store_true")
    a = sub.add_parser("passwd"); a.add_argument("name"); a.add_argument("--stdin", action="store_true")
    a = sub.add_parser("userdel"); a.add_argument("name")
    a = sub.add_parser("disable"); a.add_argument("name")
    a = sub.add_parser("enable"); a.add_argument("name")
    a = sub.add_parser("admin"); a.add_argument("name"); a.add_argument("state", choices=["on", "off"])
    a = sub.add_parser("grant"); a.add_argument("name"); a.add_argument("path")
    a = sub.add_parser("exclude"); a.add_argument("name"); a.add_argument("path")
    a = sub.add_parser("revoke"); a.add_argument("name"); a.add_argument("path")
    a = sub.add_parser("albums"); a.add_argument("path", nargs="?", default="")
    args = ap.parse_args(argv)
    db = store.db()

    if args.cmd == "list":
        users = db.execute("SELECT * FROM users ORDER BY username").fetchall()
        grants = db.execute("SELECT * FROM access ORDER BY username, path").fetchall()
        for u in users:
            flags = [f for f, on in (("admin", u["admin"]), ("DISABLED", u["disabled"])) if on]
            print(f"{u['username']}{' [' + ', '.join(flags) + ']' if flags else ''}{'  - ' + u['note'] if u['note'] else ''}")
            for g in grants:
                if g["username"].lower() == u["username"].lower():
                    print(f"    {'- ' if g['deny'] else ''}{g['path'] or '/ (everything)'}{' (excluded)' if g['deny'] else ''}")
        gg = [g for g in grants if g["username"] == store.GUEST]
        print(f"{store.GUEST} (not signed in){'' if gg else ' - no access anywhere'}")
        for g in gg:
            print(f"    {g['path'] or '/ (everything)'}")
    elif args.cmd == "useradd":
        if args.name.startswith("@") or not args.name.strip():
            sys.exit("Invalid name.")
        if store.get_user(args.name):
            sys.exit("User already exists.")
        db.execute("INSERT INTO users(username, pw_hash, admin, note) VALUES (?,?,?,?)",
                   (args.name, store.hash_pw(_password(args)), int(args.admin), args.note))
        print(f"Created {args.name}{' (admin)' if args.admin else ''}.")
    elif args.cmd == "passwd":
        _need_user(args.name)
        db.execute("UPDATE users SET pw_hash=? WHERE username=?", (store.hash_pw(_password(args)), args.name))
        db.execute("DELETE FROM sessions WHERE username=?", (args.name,))
        print("Password changed, old sessions removed.")
    elif args.cmd == "userdel":
        _need_user(args.name)
        for t in ("users", "access", "sessions"):
            db.execute(f"DELETE FROM {t} WHERE username=?", (args.name,))
        print(f"Deleted {args.name}.")
    elif args.cmd in ("disable", "enable"):
        _need_user(args.name)
        db.execute("UPDATE users SET disabled=? WHERE username=?", (int(args.cmd == "disable"), args.name))
        if args.cmd == "disable":
            db.execute("DELETE FROM sessions WHERE username=?", (args.name,))
        print("OK")
    elif args.cmd == "admin":
        _need_user(args.name)
        db.execute("UPDATE users SET admin=? WHERE username=?", (int(args.state == "on"), args.name))
        print("OK")
    elif args.cmd in ("grant", "exclude"):
        _need_user(args.name)
        db.execute("INSERT OR REPLACE INTO access(username, path, deny) VALUES (?,?,?)",
                   (args.name, _path(args.path), int(args.cmd == "exclude")))
        print("OK")
    elif args.cmd == "revoke":
        _need_user(args.name)
        n = db.execute("DELETE FROM access WHERE username=? AND path=?", (args.name, ids.clean_rel(args.path))).rowcount
        print("OK" if n else "No such rule.")
    elif args.cmd == "albums":
        from . import media
        dirs, files = media.list_dir(_path(args.path))
        for d in dirs:
            print(d["rel"])
        print(f"({len(dirs)} albums, {len(files)} photos/videos directly in '{args.path or '/'}')")


if __name__ == "__main__":
    main()
