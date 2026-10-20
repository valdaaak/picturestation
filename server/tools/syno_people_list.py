"""Zoznam osob v spolocnom priestore (len citanie). Heslo cez stdin.
python3 syno_people_list.py https://nas.example.com:5001 picturestation-sync < heslo"""
import json
import ssl
import sys
import urllib.parse
import urllib.request

base, user = sys.argv[1].rstrip("/"), sys.argv[2]
pw = sys.stdin.readline().strip()
ctx = ssl.create_default_context()


def call(api, method, version, sid=None, **params):
    data = {"api": api, "method": method, "version": str(version),
            **{k: (json.dumps(v) if isinstance(v, (list, dict, bool)) else str(v)) for k, v in params.items()}}
    if sid:
        data["_sid"] = sid
    req = urllib.request.Request(base + "/webapi/entry.cgi", data=urllib.parse.urlencode(data).encode(), method="POST")
    with urllib.request.urlopen(req, context=ctx, timeout=120) as r:
        return json.loads(r.read().decode())


sid = call("SYNO.API.Auth", "login", 6, account=user, passwd=pw, session="webui", format="sid")["data"]["sid"]
P = "SYNO.FotoTeam.Browse.Person"
r = call(P, "list", 1, sid, offset=0, limit=5000)
if not r.get("success"):
    print("Person.list:", r)
else:
    lst = r["data"]["list"]
    named = [x for x in lst if x.get("name")]
    print(f"osob {len(lst)}, pomenovanych {len(named)}")
    print("pomenovani:", [(x["name"], x.get("item_count")) for x in named][:60])
    print("ukazka zaznamu:", json.dumps(named[0] if named else lst[0], ensure_ascii=False)[:400])
    if named:
        pid = named[0]["id"]
        it = call("SYNO.FotoTeam.Browse.Item", "list", 1, sid, offset=0, limit=3, person_id=pid, additional=["folder"])
        print("fotky osoby:", json.dumps(it, ensure_ascii=False)[:800])
call("SYNO.API.Auth", "logout", 6, sid, session="webui")
