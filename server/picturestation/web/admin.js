// SPDX-License-Identifier: GPL-3.0-or-later
"use strict";
// Nastavenia pre admina: pouzivatelia, skupiny, prava na albumy, host, vseobecne.

const Admin = (() => {
  let st = null;          // posledny stav zo servera
  let tab = "users";

  async function req(op, body) {
    const opt = body === undefined
      ? { credentials: "same-origin", headers: { "X-Lang": LANG } }
      : { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-Lang": LANG },
          body: JSON.stringify(body) };
    const url = "/api/admin/" + op + (body === undefined && op === "albums" ? "" : "");
    const r = await fetch(url, opt);
    checkVersion(r);
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || t("Error") + " " + r.status);
    return j;
  }
  async function albumsOf(path) {
    const r = await fetch("/api/admin/albums?path=" + encodeURIComponent(path), { credentials: "same-origin", headers: { "X-Lang": LANG } });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || t("Error"));
    return j;
  }

  const root = () => $("admin");
  const principalLabel = (p) => p.type === "group" ? t("Group {name}", { name: p.name })
    : p.type === "guest" ? t("Without signing in") : p.name + (p.disabled ? " (" + t("disabled") + ")" : "");
  function viaText(v) {
    if (v.admin) return t("administrator sees everything");
    const where = v.path || t("the whole library");
    let s = v.deny ? t("excluded in {path}", { path: where }) : t("allowed via {path}", { path: where });
    if (v.groups && v.groups.length) s += " (" + t("group {names}", { names: v.groups.join(", ") }) + ")";
    return s;
  }
  function h(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "class") e.className = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else if (v === true) e.setAttribute(k, "");
      else if (v !== false && v != null) e.setAttribute(k, v);
    }
    for (const c of kids.flat()) if (c != null && c !== false) e.append(c.nodeType ? c : String(c));
    return e;
  }

  let toastT = null;
  function toast(msg, bad) {
    let box = $("admToast");
    if (!box) { box = h("div", { id: "admToast", class: "toast" }); document.body.append(box); }
    box.textContent = msg;
    box.classList.toggle("bad", !!bad);
    box.hidden = false;
    clearTimeout(toastT);
    toastT = setTimeout(() => { box.hidden = true; }, bad ? 6000 : 2500);
  }

  async function act(op, body, okMsg) {
    try {
      await req(op, body);
      if (okMsg) toast(okMsg);
      await load();
      return true;
    } catch (e) {
      toast(e.message, true);
      return false;
    }
  }

  async function load() {
    st = await req("state");
    draw();
  }

  async function show() {
    root().hidden = false;
    root().replaceChildren(h("div", { class: "spinner" }));
    try { await load(); } catch (e) {
      root().replaceChildren(h("p", { class: "empty" }, e.message));
    }
  }

  const pathLabel = (p) => (p ? p : t("Whole library"));

  function grantList(type, name, grants) {
    const ul = h("ul", { class: "grants" });
    const allow = grants.filter((g) => !g.deny), deny = grants.filter((g) => g.deny);
    if (!allow.length) ul.append(h("li", { class: "muted" }, type === "guest" ? t("Nothing is visible without signing in.") : t("No albums.")));
    // pri vela pravidlach (napr. prenos z Photo Station) len suhrn; podrobnosti v editore
    const many = grants.length > 15;
    if (many) {
      ul.append(h("li", { class: "muted" }, t("{a} allowed albums, {d} excluded.", { a: allow.length, d: deny.length }) + " " +
        t("Details in the access editor.")));
    }
    for (const g of many ? allow.slice(0, 15) : [...allow, ...deny]) {
      ul.append(h("li", { class: g.deny ? "deny" : "" },
        h("span", { class: "path" }, pathLabel(g.path)),
        g.deny ? h("span", { class: "tag bad" }, t("excluded ")) : null,
        h("button", { class: "x", type: "button", title: g.deny ? t("Cancel exclusion") : t("Remove access"),
          onclick: () => act("revoke", { type, name, path: g.path }, g.deny ? t("Exclusion cancelled.") : t("Access removed.")) }, "×")));
    }
    if (many && allow.length > 15) ul.append(h("li", { class: "muted" }, t("… and {n} more allowed", { n: allow.length - 15 })));
    ul.append(h("li", null,
      h("button", { class: "primary small", type: "button", onclick: () => accessEditor(type, name) }, t("Edit access"))));
    return ul;
  }

  // ---------- pristup z pohladu albumu ----------
  function albumAccess(path) {
    const list = h("div", { class: "pick-list acc-list" });
    let changed = false;
    const d = openDlg(h("div", { class: "adm-form acc" },
      h("h3", null, t("Access to album {name}", { name: path.split("/").pop() })),
      h("p", { class: "muted" }, t("Who can see this album. Allowing also covers sub-albums, excluding hides it even when a parent album is "
        + "allowed. Administrators see everything.")),
      list,
      h("div", { class: "row" }, h("span", { class: "grow" }),
        h("button", { type: "button", class: "primary", onclick: () => d.close() }, t("Done")))));
    d.addEventListener("close", () => { if (changed && !root().hidden) load(); });

    const badge = (s) => {
      const lbl = { yes: [t("sees"), "ok"], path: [t("only the path through"), "mid"], no: [t("does not see"), "off"] }[s.effective] || ["?", "off"];
      return h("span", { class: "acc-badge " + lbl[1] }, lbl[0]);
    };
    async function refresh() {
      list.replaceChildren(h("div", { class: "spinner" }));
      let r;
      try { r = await req("album_access", { path }); }
      catch (e) { list.replaceChildren(h("p", { class: "err" }, e.message)); return; }
      list.replaceChildren(...r.principals.map((p) => {
        const set = async (op, body, msg) => {
          try { await req(op, { type: p.type, name: p.name, path, ...body }); changed = true; toast(msg); refresh(); }
          catch (e) { toast(e.message, true); }
        };
        const btns = [];
        if (p.rule === "deny" || (p.rule !== "allow" && p.effective !== "yes"))
          btns.push(h("button", { type: "button", class: "link add", onclick: () => set("grant", {}, t("Allowed.")) }, t("Allow")));
        if (p.rule !== "deny")
          btns.push(h("button", { type: "button", class: "link danger", onclick: () => set("grant", { deny: true }, t("Excluded.")) }, t("Exclude")));
        if (p.rule)
          btns.push(h("button", { type: "button", class: "link", onclick: () => set("revoke", {}, t("Rule removed.")) }, t("Remove rule")));
        const tag = p.rule === "allow" ? h("span", { class: "tag acc" }, t("allowed"))
          : p.rule === "deny" ? h("span", { class: "tag bad" }, t("excluded")) : null;
        return h("div", { class: "acc-row" },
          h("div", { class: "acc-name" }, h("strong", null, principalLabel(p)), " ", tag,
            p.via ? h("div", { class: "muted" }, viaText(p.via)) : null),
          badge(p), h("span", { class: "acc-btns" }, btns));
      }));
    }
    refresh();
  }

  // ---------- editor pristupu (strom albumov) ----------
  function accessEditor(type, name) {
    const who = type === "guest" ? t("Without signing in") : type === "group" ? t("Group {name}", { name }) : name;
    const crumbsEl = h("div", { class: "pick-crumbs" });
    const head = h("div", { class: "acc-head" });
    const list = h("div", { class: "pick-list acc-list" });
    let cur = "", changed = false;
    const d = openDlg(h("div", { class: "adm-form acc" },
      h("h3", null, t("Access: {who}", { who })),
      h("p", { class: "muted" }, t("Allowing covers the album and all its sub-albums. Excluding hides an album inside an allowed one. "
        + "The most specific rule wins.")),
      crumbsEl, head, list,
      h("div", { class: "row" }, h("span", { class: "grow" }),
        h("button", { type: "button", class: "primary", onclick: () => d.close() }, t("Done")))));
    d.addEventListener("close", () => { if (changed) load(); });

    const badge = (s) => {
      const lbl = { all: [t("sees everything"), "ok"], yes: [t("sees"), "ok"], path: [t("only the path through"), "mid"], no: [t("does not see"), "off"] }[s.effective];
      return h("span", { class: "acc-badge " + lbl[1] }, lbl[0]);
    };
    const ruleTag = (s) => s.rule === "allow" ? h("span", { class: "tag acc" }, t("allowed"))
      : s.rule === "deny" ? h("span", { class: "tag bad" }, t("excluded")) : null;

    function buttons(path, s) {
      if (s.effective === "all") return null;
      const b = (label, cls, fn) => h("button", { type: "button", class: "link " + cls, onclick: fn }, label);
      const set = async (body, msg) => { try { await req(body.deny === undefined && body.revoke ? "revoke" : "grant", body); changed = true; toast(msg); go(cur); } catch (e) { toast(e.message, true); } };
      const out = [];
      // Povolit len ak ho este nevidi (alebo je vylucene); zdedene povolenie netreba opakovat
      if (s.rule === "deny" || (s.rule !== "allow" && s.effective !== "yes"))
        out.push(b(t("Allow"), "add", () => set({ type, name, path }, t("Allowed."))));
      if (s.rule !== "deny" && path !== "") out.push(b(t("Exclude"), "danger", () => set({ type, name, path, deny: true }, t("Excluded."))));
      if (s.rule) out.push(b(t("Remove rule"), "", () => set({ type, name, path, revoke: true }, t("Rule removed."))));
      return h("span", { class: "acc-btns" }, out);
    }

    async function go(path) {
      list.replaceChildren(h("div", { class: "spinner" }));
      let r;
      try { r = await req("access_view", { type, name, path }); }
      catch (e) { list.replaceChildren(h("p", { class: "err" }, e.message)); return; }
      cur = r.path;
      const parts = cur ? cur.split("/") : [];
      crumbsEl.replaceChildren(h("button", { type: "button", class: "link", onclick: () => go("") }, t("Whole library")),
        ...parts.map((p, i) => [h("span", { class: "sep" }, " / "),
          h("button", { type: "button", class: "link", onclick: () => go(parts.slice(0, i + 1).join("/")) }, p)]).flat());
      head.replaceChildren(h("div", { class: "acc-row cur" },
        h("div", { class: "acc-name" }, h("strong", null, cur ? parts[parts.length - 1] : t("Whole library")), " ", ruleTag(r.self),
          r.self.via ? h("div", { class: "muted" }, viaText(r.self.via)) : null),
        badge(r.self), buttons(cur, r.self)));
      list.replaceChildren(...(r.albums.length ? r.albums.map((a) => h("div", { class: "acc-row" },
        h("div", { class: "acc-name" },
          h("button", { type: "button", class: "link open", onclick: () => go(a.path) }, a.name), " ", ruleTag(a),
          a.via ? h("div", { class: "muted" }, viaText(a.via)) : null),
        badge(a), buttons(a.path, a)))
        : [h("p", { class: "muted" }, t("No sub-albums ({n} photos and videos).", { n: r.files }))]));
    }
    go("");
  }

  function draw() {
    const tabs = [["users", t("Users")], ["groups", t("Groups")], ["guest", t("Without signing in")],
      ["shares", t("Shares")], ["moves", t("Moves")], ["general", t("General")]];
    const nav = h("nav", { class: "adm-tabs" }, tabs.map(([k, label]) =>
      h("button", { type: "button", class: k === tab ? "on" : "", onclick: () => { tab = k; draw(); } }, label)));
    const body = { users: drawUsers, groups: drawGroups, guest: drawGuest, general: drawGeneral,
      shares: () => { const w = h("div", { class: "adm-body" }); drawShares(w); return w; },
      moves: () => { const w = h("div", { class: "adm-body" }); drawMoves(w); return w; } }[tab]();
    root().replaceChildren(h("h2", { class: "adm-h" }, t("Settings")), nav, body);
  }

  // ---------- pouzivatelia ----------
  function drawUsers() {
    const wrap = h("div", { class: "adm-body" });
    const form = h("form", { class: "adm-new", onsubmit: async (e) => {
      e.preventDefault();
      const f = new FormData(e.target);
      if (await act("user_create", { username: f.get("username"), password: f.get("password"),
        note: f.get("note"), admin: f.get("admin") === "on" }, t("User created."))) e.target.reset();
    } },
      h("strong", null, t("New user")),
      h("input", { name: "username", placeholder: t("Name"), required: true, autocomplete: "off" }),
      h("input", { name: "password", type: "password", placeholder: t("Password (min. 8 characters)"), required: true,
        minlength: "8", autocomplete: "new-password" }),
      h("input", { name: "note", placeholder: t("Note") }),
      h("label", { class: "chk" }, h("input", { type: "checkbox", name: "admin" }), "admin"),
      h("button", { class: "primary", type: "submit" }, t("Add")));
    wrap.append(form);
    for (const u of st.users) {
      const flags = [u.admin && h("span", { class: "tag acc" }, "admin"), u.disabled && h("span", { class: "tag bad" }, t("disabled"))];
      const card = h("section", { class: "card" + (u.disabled ? " off" : "") },
        h("div", { class: "card-h" },
          h("div", null, h("strong", null, u.username), " ", flags, u.note ? h("div", { class: "muted" }, u.note) : null),
          h("div", { class: "card-a" },
            h("button", { class: "link", type: "button", onclick: () => editUser(u) }, t("Edit")))),
        u.admin ? h("p", { class: "muted" }, t("An administrator sees all albums.")) : h("div", null,
          u.groups.length ? h("p", { class: "muted" }, t("Groups: {list}", { list: u.groups.join(", ") })) : null,
          grantList("user", u.username, u.grants)));
      wrap.append(card);
    }
    return wrap;
  }

  function editUser(u) {
    const groups = st.groups.map((g) => h("label", { class: "chk" },
      h("input", { type: "checkbox", name: "g", value: g.name, checked: u.groups.includes(g.name) }), g.name));
    const f = h("form", { method: "dialog", class: "adm-form" },
      h("h3", null, u.username),
      h("label", null, t("Note"), h("input", { name: "note", value: u.note })),
      h("label", null, t("New password"), h("input", { name: "password", type: "password", minlength: "8",
        placeholder: t("leave empty = no change"), autocomplete: "new-password" })),
      h("label", { class: "chk" }, h("input", { type: "checkbox", name: "admin", checked: u.admin }), t("admin (sees everything and can change settings)")),
      h("label", { class: "chk" }, h("input", { type: "checkbox", name: "disabled", checked: u.disabled }), t("disabled")),
      st.groups.length ? h("fieldset", null, h("legend", null, t("Groups")), groups) : null,
      h("div", { class: "row" },
        h("button", { type: "button", class: "link danger", onclick: async () => {
          if (!confirm(t("Really delete user {name}?", { name: u.username }))) return;
          if (await act("user_delete", { username: u.username }, t("User deleted."))) dlg.close();
        } }, t("Delete")),
        h("span", { class: "grow" }),
        h("button", { type: "button", class: "link", onclick: () => dlg.close() }, t("Cancel")),
        h("button", { type: "submit", class: "primary" }, t("Save"))));
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(f);
      const body = { username: u.username, note: fd.get("note"), admin: fd.get("admin") === "on",
        disabled: fd.get("disabled") === "on", groups: fd.getAll("g") };
      if (fd.get("password")) body.password = fd.get("password");
      if (await act("user_update", body, t("Saved."))) dlg.close();
    });
    const dlg = openDlg(f);
  }

  // ---------- skupiny ----------
  function drawGroups() {
    const wrap = h("div", { class: "adm-body" });
    wrap.append(h("form", { class: "adm-new", onsubmit: async (e) => {
      e.preventDefault();
      const f = new FormData(e.target);
      if (await act("group_create", { name: f.get("name"), note: f.get("note") }, t("Group created."))) e.target.reset();
    } },
      h("strong", null, t("New group")),
      h("input", { name: "name", placeholder: t("Title"), required: true }),
      h("input", { name: "note", placeholder: t("Note") }),
      h("button", { class: "primary", type: "submit" }, t("Add"))));
    if (!st.groups.length) wrap.append(h("p", { class: "muted" },
      t("Groups make rights simpler: assign albums to a group, then just add people to it.")));
    for (const g of st.groups) {
      wrap.append(h("section", { class: "card" },
        h("div", { class: "card-h" },
          h("div", null, h("strong", null, g.name), g.note ? h("div", { class: "muted" }, g.note) : null),
          h("div", { class: "card-a" }, h("button", { class: "link", type: "button", onclick: () => editGroup(g) }, t("Edit")))),
        h("p", { class: "muted" }, t("Members: {list}", { list: g.members.length ? g.members.join(", ") : t("nobody") })),
        grantList("group", g.name, g.grants)));
    }
    return wrap;
  }

  function editGroup(g) {
    const users = st.users.map((u) => h("label", { class: "chk" },
      h("input", { type: "checkbox", name: "m", value: u.username, checked: g.members.includes(u.username) }), u.username));
    const f = h("form", { method: "dialog", class: "adm-form" },
      h("h3", null, t("Group {name}", { name: g.name })),
      h("label", null, t("Note"), h("input", { name: "note", value: g.note })),
      h("fieldset", null, h("legend", null, t("Members")), users),
      h("div", { class: "row" },
        h("button", { type: "button", class: "link danger", onclick: async () => {
          if (!confirm(t("Delete group {name}? Members keep their own rights.", { name: g.name }))) return;
          if (await act("group_delete", { name: g.name }, t("Group deleted."))) dlg.close();
        } }, t("Delete")),
        h("span", { class: "grow" }),
        h("button", { type: "button", class: "link", onclick: () => dlg.close() }, t("Cancel")),
        h("button", { type: "submit", class: "primary" }, t("Save"))));
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(f);
      if (await act("group_update", { name: g.name, note: fd.get("note"), members: fd.getAll("m") }, t("Saved."))) dlg.close();
    });
    const dlg = openDlg(f);
  }

  // ---------- host ----------
  function drawGuest() {
    const rootChk = h("input", { type: "checkbox", checked: !!st.settings.root_files_public,
      onchange: (e) => act("settings", { root_files_public: e.target.checked },
        e.target.checked ? t("Photos in the root are public.") : t("Photos in the root are no longer public.")) });
    return h("div", { class: "adm-body" },
      h("p", { class: "muted" }, t("Albums anyone can see without signing in, in the gallery and in the DS photo app. If the list is empty, "
        + "nothing is visible without signing in.")),
      h("section", { class: "card" },
        h("label", { class: "chk block" }, rootChk,
          h("span", null, t("Photos and videos directly in the root are public"),
            h("span", { class: "muted" }, " (" + t("only files in the root, albums keep their own rights") + ")")))),
      h("section", { class: "card" }, grantList("guest", "", st.guest.grants)));
  }

  // ---------- vseobecne ----------
  const FLAGS = [
    ["allow_download_user", t("Signed-in users can download original photos")],
    ["allow_download_guest", t("Guests without signing in can download original photos")],
    ["hide_gps", t("Hide location (GPS) from everyone except administrators")],
    ["hide_detail_user", t("Hide camera details from signed-in users")],
    ["hide_detail_guest", t("Hide camera details from guests")],
    ["disable_timeline", t("Turn off the timeline")],
    ["disable_search", t("Turn off search")],
    ["allow_comment_user", t("Signed-in users can comment")],
    ["allow_comment_guest", t("Guests without signing in can comment (with a name, max. 20 per hour from one address)")],
    ["root_files_public", t("Photos and videos directly in the root are public (albums are not)")],
    ["people_for_guest", t("Guests without signing in see names of people in photos (from Synology Photos)")],
  ];

  function drawGeneral() {
    const f = h("form", { class: "card adm-form", onsubmit: async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const body = { title: fd.get("title"), root_album_order: fd.get("root_album_order"), language: fd.get("language") };
      for (const [k] of FLAGS) body[k] = fd.get(k) === "on";
      if (await act("settings", body, t("Saved."))) {
        S.title = fd.get("title") || t("Photos");
        $("brand").textContent = S.title;
        if (body.language !== st.settings.language && !storedLang()) location.reload();
      }
    } },
      h("label", null, t("Gallery name (web header, app sign-in)"),
        h("input", { name: "title", value: st.settings.title || "" })),
      h("label", null, t("Order of albums in the root"),
        h("select", { name: "root_album_order" },
          h("option", { value: "desc", selected: st.settings.root_album_order === "desc" }, t("newest first (years and dates descending, the rest after them)")),
          h("option", { value: "asc", selected: st.settings.root_album_order !== "desc" }, t("oldest first (A–Z)")))),
      h("label", null, t("Default language of the gallery"),
        h("select", { name: "language" }, [["auto", t("by browser")], ["en", "English"], ["sk", "Slovenčina"]].map(([v, l]) =>
          h("option", { value: v, selected: (st.settings.language || "auto") === v }, l)))),
      h("fieldset", null, h("legend", null, t("Restrictions (do not apply to administrators)")),
        FLAGS.map(([k, label]) => h("label", { class: "chk block" },
          h("input", { type: "checkbox", name: k, checked: !!st.settings[k] }), h("span", null, label)))),
      h("p", { class: "muted" }, t("The download ban applies to original photos. Videos can be played, so the app and the web can always "
        + "download them.")),
      h("div", { class: "row" }, h("span", { class: "grow" }), h("button", { type: "submit", class: "primary" }, t("Save"))));
    return h("div", { class: "adm-body" }, f);
  }

  // ---------- dialogy ----------
  function openDlg(content) {
    const d = h("dialog", { class: "adm-dlg" }, content);
    d.addEventListener("close", () => d.remove());
    document.body.append(d);
    d.showModal();
    return d;
  }

  function pickAlbum(onPick, title, hint) {
    let cur = "";
    const list = h("div", { class: "pick-list" });
    const crumbsEl = h("div", { class: "pick-crumbs" });
    const choose = h("button", { type: "button", class: "primary" }, t("Select"));
    const d = openDlg(h("div", { class: "adm-form pick" },
      h("h3", null, title || t("Choose an album")),
      h("p", { class: "muted" }, hint || t("Access covers the album and all its sub-albums.")),
      crumbsEl, list,
      h("div", { class: "row" }, h("span", { class: "grow" }),
        h("button", { type: "button", class: "link", onclick: () => d.close() }, t("Cancel")), choose)));
    choose.onclick = () => { d.close(); onPick(cur); };

    async function go(path) {
      list.replaceChildren(h("div", { class: "spinner" }));
      let r;
      try { r = await albumsOf(path); } catch (e) { list.replaceChildren(h("p", { class: "err" }, e.message)); return; }
      cur = r.path;
      choose.textContent = t("Select: {name}", { name: pathLabel(cur) });
      const parts = cur ? cur.split("/") : [];
      crumbsEl.replaceChildren(h("button", { type: "button", class: "link", onclick: () => go("") }, t("Whole library")),
        ...parts.map((p, i) => [h("span", { class: "sep" }, " / "),
          h("button", { type: "button", class: "link", onclick: () => go(parts.slice(0, i + 1).join("/")) }, p)]).flat());
      list.replaceChildren(...(r.albums.length ? r.albums.map((a) =>
        h("button", { type: "button", class: "pick-item", onclick: () => go(cur ? cur + "/" + a : a) }, a))
        : [h("p", { class: "muted" }, t("No sub-albums ({n} photos and videos).", { n: r.files }))]));
    }
    go("");
  }

  // ---------- album ----------
  async function setCover(rel) {
    const parts = rel.split("/").slice(0, -1);
    if (!parts.length) { toast(t("A photo in the root does not belong to any album."), true); return; }
    // vsetky albumy, do ktorych fotka patri (najblizsi prvy): titulku mozno dat aj nadradenemu albumu
    const albums = parts.map((_, i) => parts.slice(0, parts.length - i).join("/"));
    const apply = async (path) => {
      try {
        await req("album_set", { path, cover: rel });
        toast(t("Cover photo set for album {name}.", { name: path.split("/").pop() }));
        return true;
      } catch (e) { toast(e.message, true); return false; }
    };
    if (albums.length === 1) { apply(albums[0]); return; }
    const d = openDlg(h("div", { class: "adm-form" },
      h("h3", null, t("Cover photo for album")),
      h("p", { class: "muted" }, t("You can set the photo as the cover of its album or of any parent album.")),
      h("div", { class: "cover-pick" }, albums.map((p, i) => h("button", { type: "button", class: i ? "link add" : "primary",
        onclick: async () => { if (await apply(p)) d.close(); } }, p.split("/").pop() + (i ? "" : " (" + t("this album") + ")")))),
      h("div", { class: "row" }, h("span", { class: "grow" }),
        h("button", { type: "button", class: "link", onclick: () => d.close() }, t("Cancel")))));
  }

  async function editAlbum(path, onSaved) {
    let a;
    try {
      const r = await fetch("/api/admin/album_get?path=" + encodeURIComponent(path), { credentials: "same-origin", headers: { "X-Lang": LANG } });
      a = await r.json();
      if (!r.ok) throw new Error(a.error || t("Error"));
    } catch (e) { toast(e.message, true); return; }
    const pwInput = h("input", { name: "password", type: "password", autocomplete: "new-password",
      placeholder: a.has_password ? t("leave empty = keep the password") : t("album password (min. 4 characters)") });
    const pwRow = h("label", null, t("Album password"), pwInput);
    const radio = (v, label, hint) => h("label", { class: "chk block" },
      h("input", { type: "radio", name: "mode", value: v, checked: a.mode === v,
        onchange: () => { pwRow.hidden = v !== "password"; } }),
      h("span", null, label, h("span", { class: "muted" }, " " + hint)));
    pwRow.hidden = a.mode !== "password";
    const who = [...a.users, ...a.groups.map((g) => t("group {name}", { name: g }))];
    const coverInfo = a.cover ? t("set in the gallery") : a.ea_cover ? t("original from Photo Station") : t("first photo in the album");
    const f = h("form", { method: "dialog", class: "adm-form" },
      h("h3", null, t("Album {name}", { name: path.split("/").pop() })),
      h("label", null, t("Title"), h("input", { name: "title", value: a.title, placeholder: path.split("/").pop() })),
      h("label", null, t("Description"), h("textarea", { name: "description", rows: "3" }, a.description)),
      h("label", null, t("Order of sub-albums"),
        h("select", { name: "album_order" },
          h("option", { value: "asc", selected: a.album_order !== "desc" }, t("oldest first (A–Z)")),
          h("option", { value: "desc", selected: a.album_order === "desc" }, t("newest first")))),
      h("fieldset", null, h("legend", null, t("Access")),
        radio("private", t("Private"), t("only signed-in users with a right")),
        radio("public", t("Public"), t("anyone can see it, even without signing in")),
        radio("password", t("With password"), t("anyone who knows the password")),
        pwRow),
      h("p", { class: "muted" }, t("Direct rights to this album: {list}.", { list: who.length ? who.join(", ") : t("nobody except administrators") }) +
        (a.excluded.length ? " " + t("Excluded for: {list}.", { list: a.excluded.join(", ") }) : "") +
        " " + t("Rights and exclusions are set in Settings.")),
      h("p", { class: "muted" }, t("Cover photo: {what}. Change it in the photo viewer with the Cover button.", { what: coverInfo }) + " ",
        a.cover ? h("button", { type: "button", class: "link add", onclick: async () => {
          try { await req("album_set", { path, cover: "" }); toast(t("Cover photo reset to the original.")); d.close(); onSaved && onSaved(); }
          catch (e) { toast(e.message, true); }
        } }, t("Reset to original")) : null),
      h("div", { class: "row" }, h("span", { class: "grow" }),
        h("button", { type: "button", class: "link", onclick: () => d.close() }, t("Cancel")),
        h("button", { type: "submit", class: "primary" }, t("Save"))));
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(f);
      const body = { path, title: fd.get("title"), description: fd.get("description"), mode: fd.get("mode"),
        album_order: fd.get("album_order") };
      if (body.mode === "password" && fd.get("password")) body.password = fd.get("password");
      try {
        await req("album_set", body);
        toast(t("Album saved."));
        d.close();
        onSaved && onSaved();
      } catch (err) { toast(err.message, true); }
    });
    const d = openDlg(f);
  }

  // ---------- zdielanie ----------
  const shareUrl = (token) => location.origin + "/s/" + token;
  const fmtDay = (ts) => new Date(ts * 1000).toLocaleDateString(LOCALE());

  function copyBox(url) {
    const inp = h("input", { value: url, readonly: true, class: "copy-in", onclick: (e) => e.target.select() });
    return h("div", { class: "copy" }, inp,
      h("button", { type: "button", class: "primary", onclick: async () => {
        try { await navigator.clipboard.writeText(url); toast(t("Link copied.")); }
        catch (e) { inp.select(); document.execCommand("copy"); toast(t("Link copied.")); }
      } }, t("Copy")));
  }

  function share(path, kind) {
    const label = kind === "album" ? t("album {name}", { name: path.split("/").pop() }) : path.split("/").pop();
    const result = h("div");
    const f = h("form", { method: "dialog", class: "adm-form" },
      h("h3", null, t("Share {what}", { what: label })),
      h("p", { class: "muted" }, kind === "album"
        ? t("Whoever gets the link sees this album and its sub-albums without signing in.")
        : t("Whoever gets the link sees this item without signing in.")),
      h("label", null, t("Valid for"), h("select", { name: "days" },
        h("option", { value: "0" }, t("no limit")), h("option", { value: "7" }, t("7 days")),
        h("option", { value: "30", selected: true }, t("30 days")), h("option", { value: "90" }, t("90 days")),
        h("option", { value: "365" }, t("1 year")))),
      h("label", { class: "chk block" }, h("input", { type: "checkbox", name: "dl" }),
        h("span", null, t("allow downloading original photos"))),
      h("label", null, t("Note (for you, who you sent the link to)"), h("input", { name: "note" })),
      result,
      h("div", { class: "row" }, h("span", { class: "grow" }),
        h("button", { type: "button", class: "link", onclick: () => d.close() }, t("Close")),
        h("button", { type: "submit", class: "primary" }, t("Create link"))));
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(f);
      try {
        const r = await req("share_create", { path, days: +fd.get("days"), allow_download: fd.get("dl") === "on",
          note: fd.get("note") });
        result.replaceChildren(copyBox(shareUrl(r.token)));
        f.querySelector("button[type=submit]").hidden = true;
      } catch (err) { toast(err.message, true); }
    });
    const d = openDlg(f);
  }

  async function drawShares(wrap) {
    let list;
    try { list = (await req("share_list")).shares; } catch (e) { wrap.append(h("p", { class: "err" }, e.message)); return; }
    if (!list.length) {
      wrap.append(h("p", { class: "muted" }, t("No links yet. Create them with the Share button in an album or at a photo.")));
      return;
    }
    for (const s of list) {
      const exp = s.expires ? (s.expired ? t("expired {date}", { date: fmtDay(s.expires) }) : t("valid until {date}", { date: fmtDay(s.expires) })) : t("no limit");
      wrap.append(h("section", { class: "card" + (s.expired ? " off" : "") },
        h("div", { class: "card-h" },
          h("div", null, h("strong", null, s.path), " ", h("span", { class: "tag" }, s.kind === "album" ? t("album") : s.kind === "video" ? t("video") : t("photo")),
            h("div", { class: "muted" }, `${exp} · ` + t("created by {who} {date}", { who: s.created_by || "?", date: fmtDay(s.created) }) +
              (s.allow_download ? " · " + t("download allowed") : "") + (s.note ? " · " + s.note : ""))),
          h("div", { class: "card-a" }, h("button", { type: "button", class: "link danger", onclick: () => {
            if (confirm(t("Cancel this link? Whoever has it can no longer get in."))) act("share_delete", { token: s.token }, t("Link cancelled."));
          } }, t("Cancel")))),
        s.expired ? null : copyBox(shareUrl(s.token))));
    }
  }

  // ---------- presuny albumov ----------
  async function drawMoves(wrap) {
    let s;
    try { s = await req("moves_state"); } catch (e) { wrap.append(h("p", { class: "err" }, e.message)); return; }
    wrap.append(h("p", { class: "muted" }, t("When you move or rename a folder on disk, the gallery recognises it at the next indexing (every 30 minutes) "
      + "by the same files and carries over rights, exclusions, titles, the cover photo, tags, comments, links and "
      + "smart albums. Until then an excluded album stays hidden at its new place too.")));

    const remap = (old) => pickAlbum(async (p) => {
      if (!p) { toast(t("Choose an album."), true); return; }
      await act("moves_remap", { old, new: p }, t("Moved to {path}.", { path: p }));
      tab = "moves"; draw();
    }, t("Where did the album move?"), t("Everything set for “{path}” moves to the chosen album.", { path: old }));

    if (s.pending.length) {
      const sec = h("section", { class: "card" }, h("strong", null, t("Ambiguous moves")),
        h("p", { class: "muted" }, t("The index found several folders with the same files. Choose the right one.")));
      for (const p of s.pending) {
        sec.append(h("div", { class: "acc-row" }, h("div", { class: "acc-name" }, p.old),
          h("span", { class: "acc-btns" }, p.candidates.map((c) => h("button", { type: "button", class: "link add",
            onclick: async () => { await act("moves_remap", { old: p.old, new: c }, t("Moved.")); tab = "moves"; draw(); } }, "→ " + c)))));
      }
      wrap.append(sec);
    }

    const oc = h("section", { class: "card" }, h("strong", null, t("Settings for albums that are no longer on disk")));
    if (!s.orphans.length) oc.append(h("p", { class: "muted" }, t("None. All settings belong to existing albums.")));
    for (const o of s.orphans) {
      const what = [o.rules && tn(o.rules, "{n} rule", "{n} rules"), o.props && t("album properties"),
        o.shares && tn(o.shares, "{n} link", "{n} links"), o.smart && tn(o.smart, "{n} smart album", "{n} smart albums"),
        o.nested && "+ " + tn(o.nested, "{n} sub-album", "{n} sub-albums")].filter(Boolean).join(", ");
      oc.append(h("div", { class: "acc-row" },
        h("div", { class: "acc-name" }, h("strong", null, o.path), h("div", { class: "muted" }, what)),
        h("span", null),
        h("span", { class: "acc-btns" },
          h("button", { type: "button", class: "link add", onclick: () => remap(o.path) }, t("Moved where…")),
          h("button", { type: "button", class: "link danger", onclick: async () => {
            if (!confirm(t("Delete all settings for “{path}”?", { path: o.path }))) return;
            await act("orphan_delete", { path: o.path }, t("Deleted.")); tab = "moves"; draw();
          } }, t("Delete")))));
    }
    wrap.append(oc);

    const hc = h("section", { class: "card" }, h("strong", null, t("Move history")));
    if (!s.history.length) hc.append(h("p", { class: "muted" }, t("None yet.")));
    for (const m of s.history) {
      hc.append(h("div", { class: "muted" }, `${fmtDay(m.created)} · ${m.old} → ${m.new}` +
        (m.kind === "manual" ? " (" + t("manual") + ")" : " (" + t("automatic") + ")")));
    }
    wrap.append(hc);
  }

  // ---------- chytre albumy ----------
  const placeKey = (id) => {   // tag_g<hex> -> "cc|obec"
    const hx = id.slice(5);
    return new TextDecoder().decode(new Uint8Array((hx.match(/../g) || []).map((x) => parseInt(x, 16))));
  };

  function editSmart(s, disc, onSaved) {
    const c = (s && s.info.criteria) || {};
    const tags = (disc && disc.tags) || [], places = (disc && disc.places) || [];
    const countries = [...new Map(places.map((p) => [p.info.cc, p.info.country])).entries()];
    let path = c.path || "";
    const pathLbl = h("span", null, path || t("all albums"));
    const tagBox = tags.length ? h("fieldset", null, h("legend", null, t("Tags (any one)")),
      tags.map((tg) => h("label", { class: "chk" }, h("input", { type: "checkbox", name: "tag", value: tg.id.slice(4),
        checked: (c.tags || []).includes(+tg.id.slice(4)) }), tg.name))) : h("p", { class: "muted" }, t("No tags yet."));
    const ctryBox = countries.length ? h("fieldset", null, h("legend", null, t("Countries")),
      countries.map(([cc, n]) => h("label", { class: "chk" }, h("input", { type: "checkbox", name: "cc", value: cc,
        checked: (c.countries || []).includes(cc) }), n))) : null;
    const placeSel = places.length ? h("label", null, t("Places (Ctrl/Cmd for more)"),
      h("select", { name: "place", multiple: true, size: "6" }, places.map((p) => {
        const k = placeKey(p.id);
        return h("option", { value: k, selected: (c.places || []).includes(k) }, `${p.name} (${p.info.count})`);
      }))) : null;
    const types = c.types || [];
    const typeVal = types.length === 1 ? types[0] : "all";
    const f = h("form", { method: "dialog", class: "adm-form" },
      h("h3", null, s ? t("Edit smart album") : t("New smart album")),
      h("label", null, t("Title"), h("input", { name: "name", required: true, value: s ? s.name : "" })),
      tagBox, ctryBox, placeSel,
      h("div", { class: "two" },
        h("label", null, t("From"), h("input", { type: "date", name: "date_from", value: c.date_from || "" })),
        h("label", null, t("To"), h("input", { type: "date", name: "date_to", value: c.date_to || "" }))),
      h("fieldset", null, h("legend", null, t("Type")),
        [["all", t("photos and videos")], ["photo", t("photos only")], ["video", t("videos only")]].map(([v, l]) =>
          h("label", { class: "chk" }, h("input", { type: "radio", name: "types", value: v, checked: typeVal === v }), l))),
      h("p", { class: "muted" }, t("Only from album:") + " ", pathLbl, " ",
        h("button", { type: "button", class: "link add", onclick: () => pickAlbum((p) => { path = p; pathLbl.textContent = p || t("all albums"); }) }, t("change"))),
      h("div", { class: "row" },
        s ? h("button", { type: "button", class: "link danger", onclick: async () => {
          if (!confirm(t("Delete the smart album? The photos stay."))) return;
          try { await req("smart_delete", { id: s.id }); toast(t("Deleted.")); d.close(); onSaved && onSaved(); }
          catch (e) { toast(e.message, true); }
        } }, t("Delete")) : null,
        h("span", { class: "grow" }),
        h("button", { type: "button", class: "link", onclick: () => d.close() }, t("Cancel")),
        h("button", { type: "submit", class: "primary" }, t("Save"))));
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(f);
      const ty = fd.get("types");
      const crit = {
        tags: fd.getAll("tag").map(Number), countries: fd.getAll("cc"),
        places: placeSel ? [...f.querySelector("select[name=place]").selectedOptions].map((o) => o.value) : [],
        date_from: fd.get("date_from") || "", date_to: fd.get("date_to") || "",
        types: ty === "all" ? [] : [ty], path,
      };
      try {
        await req("smart_save", { id: s ? s.id : null, name: fd.get("name"), criteria: crit });
        toast(t("Smart album saved."));
        d.close();
        onSaved && onSaved();
      } catch (err) { toast(err.message, true); }
    });
    const d = openDlg(f);
  }

  return { show, hide: () => { root().hidden = true; }, editAlbum, setCover, share, editSmart, albumAccess };
})();
