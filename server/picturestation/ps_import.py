# SPDX-License-Identifier: GPL-3.0-or-later
"""Import povodnych prav z databazy Photo Station (pg_dump --data-only).

  python3 -m picturestation.ps_import EXPORT.sql            # nanecisto: len vypise, co by spravil
  python3 -m picturestation.ps_import EXPORT.sql --apply --passwords-out SUBOR

Photo Station pravo do podalbumov nededila (kazdy album mal vlastny zoznam), u nas sa povolenie dedi.
Presne preto: povolit najvyssie povolene albumy a vylucit podalbumy, ktore dany pouzivatel v PS nemal.
Verejne albumy sa neprenasaju, tie urci admin sam.
Existujuce pravidla a pouzivatelia sa neprepisuju.
"""
import argparse
import collections
import os
import secrets
import string
import sys

from . import ids, store

BS = chr(92)


def _unescape(v):
    if v == BS + "N":
        return None
    out, i = [], 0
    while i < len(v):
        c = v[i]
        if c == BS and i + 1 < len(v):
            out.append({"t": "\t", "n": "\n", "r": "\r", BS: BS}.get(v[i + 1], v[i + 1]))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def load(path):
    tables = collections.defaultdict(list)
    cur = cols = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("COPY "):
                cur = line.split()[1].split(".")[-1]
                cols = line[line.index("(") + 1:line.index(")")].replace(" ", "").split(",")
                continue
            if line == BS + ".":
                cur = None
                continue
            if cur:
                tables[cur].append(dict(zip(cols, (_unescape(x) for x in line.split("\t")))))
    return tables


def _visible(q, rules):
    best = None
    for p, d in rules.items():
        if q == p or q.startswith(p + "/"):
            if best is None or len(p) > best[0]:
                best = (len(p), d)
    return best is not None and not best[1]


def compress(paths, all_paths):
    """Mnozina albumov (bez dedenia) -> (povolit, vylucit) pre model s dedenim.
    Od korena: kde sa viditelnost lisi od zelanej, pridat pravidlo. Rodicia su vyrieseni pred detmi."""
    rules = {}
    for q in sorted(all_paths, key=lambda x: (x.count("/"), x)):
        want, vis = q in paths, _visible(q, rules)
        if want and not vis:
            rules[q] = False
        elif vis and not want:
            rules[q] = True
    return {p for p, d in rules.items() if not d}, {p for p, d in rules.items() if d}


def verify(paths, allow, deny, all_paths):
    """Kontrola: vysledok s dedenim == povodna mnozina pre vsetky albumy."""
    rules = {**{p: False for p in allow}, **{p: True for p in deny}}
    return [q for q in all_paths if _visible(q, rules) != (q in paths)]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("export")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--passwords-out")
    a = ap.parse_args(argv)
    T = load(a.export)
    db = store.db()

    shares = {s["shareid"]: s for s in T["photo_share"]}
    exists = {}
    for s in T["photo_share"]:
        try:
            exists[s["sharename"]] = os.path.isdir(ids.abs_path(s["sharename"]))
        except ids.BadId:
            exists[s["sharename"]] = False
    ps_paths = {p for p, ok in exists.items() if ok}
    missing = sorted(p for p, ok in exists.items() if not ok)
    # aj priecinky, ktore vznikli az po Photo Station (z indexu) - v PS ich nikto okrem admina nevidel
    disk_dirs = set()
    for r in db.execute("SELECT path FROM meta"):
        d = r["path"].rsplit("/", 1)[0] if "/" in r["path"] else ""
        while d:
            disk_dirs.add(d)
            d = d.rsplit("/", 1)[0] if "/" in d else ""
    all_paths = ps_paths | disk_dirs
    print(f"Albumy v PS: {len(exists)}, existuju na disku: {len(ps_paths)}, chybaju: {len(missing)}; "
          f"priecinkov na disku spolu (z indexu): {len(all_paths)}, novych od PS: {len(all_paths - ps_paths)}")

    users = {u["userid"]: u for u in T["photo_user"]}
    groups = {g["groupid"]: g["groupname"] for g in T["photo_group"]}
    per = collections.defaultdict(set)
    for r in T["photo_access_right"]:
        s = shares.get(r["shareid"])
        u = users.get(r["userid"])
        if s and u and u["admin"] != "t":
            per[("user", u["username"])].add(s["sharename"])
    for r in T["photo_group_permission"]:
        s = shares.get(r["shareid"])
        if s and r["groupid"] in groups:
            per[("group", groups[r["groupid"]])].add(s["sharename"])
    # verejne albumy sa NEprenasaju (rozhodnutie admina 2026-10-20) - len prava prihlasenych a skupin

    passwords = []
    # pouzivatelia
    for u in T["photo_user"]:
        name = u["username"]
        if u["admin"] == "t":
            print(f"  pouzivatel {name}: admin v PS - preskakujem (admin uz existuje)")
            continue
        if store.get_user(name):
            print(f"  pouzivatel {name}: uz existuje - nemenim")
            continue
        pw = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
        passwords.append((name, pw))
        print(f"  pouzivatel {name}: zalozim (nove heslo)")
        if a.apply:
            db.execute("INSERT INTO users(username, pw_hash, admin, disabled, note) VALUES (?,?,0,?,?)",
                       (name, store.hash_pw(pw), int(u["disabled"] == "t"), "z Photo Station"))
    # skupiny a clenovia
    for gid, gname in groups.items():
        members = [users[m["userid"]]["username"] for m in T["photo_user_group"]
                   if m["groupid"] == gid and m["userid"] in users]
        new = not db.execute("SELECT 1 FROM groups WHERE name=?", (gname,)).fetchone()
        print(f"  skupina {gname}: {'zalozim' if new else 'existuje'}, clenovia {members}")
        if a.apply:
            if new:
                db.execute("INSERT INTO groups VALUES (?,?)", (gname, "z Photo Station"))
            for m in members:
                if store.get_user(m):
                    db.execute("INSERT OR IGNORE INTO group_members VALUES (?,?)", (gname, m))
    # prava
    total_a = total_d = 0
    for (kind, name), paths in sorted(per.items()):
        paths = {p for p in paths if p in all_paths}
        allow, deny = compress(paths, all_paths)
        bad = verify(paths, allow, deny, all_paths)
        pr = store.GUEST if kind == "guest" else (store.GROUP_PREFIX + name if kind == "group" else name)
        existing = {r["path"] for r in db.execute("SELECT path FROM access WHERE username=?", (pr,))}
        label = {"guest": "bez prihlasenia", "group": "skupina " + name, "user": name}[kind]
        print(f"  {label}: albumov v PS {len(paths)} -> povolit {len(allow)}, vylucit {len(deny)}"
              f"{', KONTROLA ZLYHALA na ' + str(len(bad)) if bad else ', kontrola OK'}"
              f"{', uz ma ' + str(len(existing)) + ' vlastnych pravidiel (nemenim ich)' if existing else ''}")
        if bad:
            print("     rozdiely:", bad[:5])
        total_a += len(allow)
        total_d += len(deny)
        if a.apply and not bad:
            for p in allow:
                if p not in existing:
                    db.execute("INSERT OR IGNORE INTO access(username, path, deny) VALUES (?,?,0)", (pr, p))
            for p in deny:
                if p not in existing:
                    db.execute("INSERT OR IGNORE INTO access(username, path, deny) VALUES (?,?,1)", (pr, p))
    # titulky a popisy
    n_props = 0
    for s in T["photo_share"]:
        p = s["sharename"]
        if p in all_paths and (s["title"] or s["description"]):
            cur = store.album_props(p)
            if cur and (cur["title"] or cur["description"]):
                continue
            n_props += 1
            if a.apply:
                db.execute("INSERT INTO album_props(path, title, description) VALUES (?,?,?) "
                           "ON CONFLICT(path) DO UPDATE SET title=COALESCE(title, excluded.title), "
                           "description=COALESCE(description, excluded.description)",
                           (p, s["title"] or None, s["description"] or None))
    print(f"Titulky/popisy albumov na prenos: {n_props}")
    print(f"Spolu pravidiel: povolit {total_a}, vylucit {total_d}")
    if missing:
        print("Albumy z PS, ktore uz na disku nie su (preskocene), prvych 10:", missing[:10])
    if a.apply and a.passwords_out and passwords:
        old = os.umask(0o077)
        with open(a.passwords_out, "w", encoding="utf-8") as fh:
            fh.write("Nove hesla pouzivatelov prenesenych z Photo Station\n")
            for n, pw in passwords:
                fh.write(f"{n}: {pw}\n")
        os.umask(old)
        print("Hesla zapisane do", a.passwords_out)
    print("HOTOVO" if a.apply else "NANECISTO - nic sa nezapisalo (pridaj --apply)")


if __name__ == "__main__":
    main(sys.argv[1:])
