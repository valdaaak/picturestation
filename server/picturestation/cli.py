"""Sprava pouzivatelov a prav:  python3 -m picturestation.cli <prikaz> ...

  list                                   pouzivatelia a ich prava
  useradd MENO [--admin] [--note TEXT]   novy pouzivatel (heslo sa opyta)
  passwd MENO                            zmena hesla
  userdel MENO                           zmazanie (aj s pravami a sessions)
  disable MENO | enable MENO             zablokovanie / odblokovanie
  admin MENO on|off                      admin vidi vsetko
  grant MENO CESTA                       pristup k albumu (aj podalbumom); CESTA '' alebo / = vsetko
  exclude MENO CESTA                     vylucenie albumu z povoleneho (najkonkretnejsie pravidlo vyhrava)
  revoke MENO CESTA                      odobratie pravidla (povolenia aj vylucenia)
  albums [CESTA]                         vypis albumov v priecinku (pomoc pri grant)

Host (bez prihlasenia) = pouzivatel @guest, prava mu das cez grant @guest CESTA.
Heslo sa da poslat aj cez stdin:  echo heslo | python3 -m picturestation.cli passwd MENO --stdin
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
        pw = getpass.getpass("Heslo: ")
        if pw != getpass.getpass("Heslo znova: "):
            sys.exit("Hesla sa nezhoduju.")
    if len(pw) < 8:
        sys.exit("Heslo musi mat aspon 8 znakov.")
    return pw


def _need_user(name):
    if name == store.GUEST:
        return
    if store.get_user(name) is None:
        sys.exit(f"Pouzivatel {name} neexistuje.")


def _path(p: str) -> str:
    try:
        rel = ids.clean_rel(p)
    except ids.BadId:
        sys.exit(f"Neplatna cesta: {p}")
    if not os.path.isdir(ids.abs_path(rel)):
        print(f"Upozornenie: album '{rel}' teraz neexistuje (pravo sa ulozi aj tak).", file=sys.stderr)
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
            flags = [f for f, on in (("admin", u["admin"]), ("ZABLOKOVANY", u["disabled"])) if on]
            print(f"{u['username']}{' [' + ', '.join(flags) + ']' if flags else ''}{'  - ' + u['note'] if u['note'] else ''}")
            for g in grants:
                if g["username"].lower() == u["username"].lower():
                    print(f"    {'- ' if g['deny'] else ''}{g['path'] or '/ (vsetko)'}{' (vyluceny)' if g['deny'] else ''}")
        gg = [g for g in grants if g["username"] == store.GUEST]
        print(f"{store.GUEST} (bez prihlasenia){'' if gg else ' - nema pristup nikam'}")
        for g in gg:
            print(f"    {g['path'] or '/ (vsetko)'}")
    elif args.cmd == "useradd":
        if args.name.startswith("@") or not args.name.strip():
            sys.exit("Neplatne meno.")
        if store.get_user(args.name):
            sys.exit("Pouzivatel uz existuje.")
        db.execute("INSERT INTO users(username, pw_hash, admin, note) VALUES (?,?,?,?)",
                   (args.name, store.hash_pw(_password(args)), int(args.admin), args.note))
        print(f"Vytvoreny {args.name}{' (admin)' if args.admin else ''}.")
    elif args.cmd == "passwd":
        _need_user(args.name)
        db.execute("UPDATE users SET pw_hash=? WHERE username=?", (store.hash_pw(_password(args)), args.name))
        db.execute("DELETE FROM sessions WHERE username=?", (args.name,))
        print("Heslo zmenene, stare prihlasenia zrusene.")
    elif args.cmd == "userdel":
        _need_user(args.name)
        for t in ("users", "access", "sessions"):
            db.execute(f"DELETE FROM {t} WHERE username=?", (args.name,))
        print(f"Zmazany {args.name}.")
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
        print("OK" if n else "Take pravo nemal.")
    elif args.cmd == "albums":
        from . import media
        dirs, files = media.list_dir(_path(args.path))
        for d in dirs:
            print(d["rel"])
        print(f"({len(dirs)} albumov, {len(files)} fotiek/videi priamo v '{args.path or '/'}')")


if __name__ == "__main__":
    main()
