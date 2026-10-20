"use strict";
// Nastavenia pre admina: pouzivatelia, skupiny, prava na albumy, host, vseobecne.

const Admin = (() => {
  let st = null;          // posledny stav zo servera
  let tab = "users";

  async function req(op, body) {
    const opt = body === undefined
      ? { credentials: "same-origin" }
      : { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body) };
    const url = "/api/admin/" + op + (body === undefined && op === "albums" ? "" : "");
    const r = await fetch(url, opt);
    checkVersion(r);
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || "Chyba " + r.status);
    return j;
  }
  async function albumsOf(path) {
    const r = await fetch("/api/admin/albums?path=" + encodeURIComponent(path), { credentials: "same-origin" });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || "Chyba");
    return j;
  }

  const root = () => $("admin");
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
    let t = $("admToast");
    if (!t) { t = h("div", { id: "admToast", class: "toast" }); document.body.append(t); }
    t.textContent = msg;
    t.classList.toggle("bad", !!bad);
    t.hidden = false;
    clearTimeout(toastT);
    toastT = setTimeout(() => { t.hidden = true; }, bad ? 6000 : 2500);
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

  const pathLabel = (p) => (p ? p : "Celá knižnica");

  function grantList(type, name, grants) {
    const ul = h("ul", { class: "grants" });
    const allow = grants.filter((g) => !g.deny), deny = grants.filter((g) => g.deny);
    if (!allow.length) ul.append(h("li", { class: "muted" }, type === "guest" ? "Bez prihlásenia nevidno nič." : "Žiadne albumy."));
    // pri vela pravidlach (napr. prenos z Photo Station) len suhrn; podrobnosti v editore
    const many = grants.length > 15;
    if (many) {
      ul.append(h("li", { class: "muted" }, `${allow.length} povolených albumov, ${deny.length} vylúčených. ` +
        "Podrobnosti v editore prístupu."));
    }
    for (const g of many ? allow.slice(0, 15) : [...allow, ...deny]) {
      ul.append(h("li", { class: g.deny ? "deny" : "" },
        h("span", { class: "path" }, pathLabel(g.path)),
        g.deny ? h("span", { class: "tag bad" }, "vylúčený") : null,
        h("button", { class: "x", type: "button", title: g.deny ? "Zrušiť vylúčenie" : "Odobrať prístup",
          onclick: () => act("revoke", { type, name, path: g.path }, g.deny ? "Vylúčenie zrušené." : "Prístup odobratý.") }, "×")));
    }
    if (many && allow.length > 15) ul.append(h("li", { class: "muted" }, `… a ďalších ${allow.length - 15} povolených`));
    ul.append(h("li", null,
      h("button", { class: "primary small", type: "button", onclick: () => accessEditor(type, name) }, "Upraviť prístup")));
    return ul;
  }

  // ---------- pristup z pohladu albumu ----------
  function albumAccess(path) {
    const list = h("div", { class: "pick-list acc-list" });
    let changed = false;
    const d = openDlg(h("div", { class: "adm-form acc" },
      h("h3", null, "Prístup k albumu " + path.split("/").pop()),
      h("p", { class: "muted" }, "Kto tento album vidí. Povolenie platí aj pre podalbumy, vylúčenie ho skryje, " +
        "aj keď je povolený nadradený album. Admini vidia všetko."),
      list,
      h("div", { class: "row" }, h("span", { class: "grow" }),
        h("button", { type: "button", class: "primary", onclick: () => d.close() }, "Hotovo"))));
    d.addEventListener("close", () => { if (changed && !root().hidden) load(); });

    const badge = (s) => {
      const t = { yes: ["vidí", "ok"], path: ["len cesta ďalej", "mid"], no: ["nevidí", "off"] }[s.effective] || ["?", "off"];
      return h("span", { class: "acc-badge " + t[1] }, t[0]);
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
          btns.push(h("button", { type: "button", class: "link add", onclick: () => set("grant", {}, "Povolené.") }, "Povoliť"));
        if (p.rule !== "deny")
          btns.push(h("button", { type: "button", class: "link danger", onclick: () => set("grant", { deny: true }, "Vylúčené.") }, "Vylúčiť"));
        if (p.rule)
          btns.push(h("button", { type: "button", class: "link", onclick: () => set("revoke", {}, "Pravidlo zrušené.") }, "Zrušiť pravidlo"));
        const tag = p.rule === "allow" ? h("span", { class: "tag acc" }, "povolené")
          : p.rule === "deny" ? h("span", { class: "tag bad" }, "vylúčené") : null;
        return h("div", { class: "acc-row" },
          h("div", { class: "acc-name" }, h("strong", null, p.label), " ", tag,
            p.via ? h("div", { class: "muted" }, p.via) : null),
          badge(p), h("span", { class: "acc-btns" }, btns));
      }));
    }
    refresh();
  }

  // ---------- editor pristupu (strom albumov) ----------
  function accessEditor(type, name) {
    const who = type === "guest" ? "Bez prihlásenia" : type === "group" ? "Skupina " + name : name;
    const crumbsEl = h("div", { class: "pick-crumbs" });
    const head = h("div", { class: "acc-head" });
    const list = h("div", { class: "pick-list acc-list" });
    let cur = "", changed = false;
    const d = openDlg(h("div", { class: "adm-form acc" },
      h("h3", null, "Prístup: " + who),
      h("p", { class: "muted" }, "Povolenie platí pre album aj všetky podalbumy. Vylúčením skryješ album vo vnútri povoleného. " +
        "Rozhoduje najkonkrétnejšie pravidlo."),
      crumbsEl, head, list,
      h("div", { class: "row" }, h("span", { class: "grow" }),
        h("button", { type: "button", class: "primary", onclick: () => d.close() }, "Hotovo"))));
    d.addEventListener("close", () => { if (changed) load(); });

    const badge = (s) => {
      const t = { all: ["vidí všetko", "ok"], yes: ["vidí", "ok"], path: ["len cesta ďalej", "mid"], no: ["nevidí", "off"] }[s.effective];
      return h("span", { class: "acc-badge " + t[1] }, t[0]);
    };
    const ruleTag = (s) => s.rule === "allow" ? h("span", { class: "tag acc" }, "povolené")
      : s.rule === "deny" ? h("span", { class: "tag bad" }, "vylúčené") : null;

    function buttons(path, s) {
      if (s.effective === "all") return null;
      const b = (label, cls, fn) => h("button", { type: "button", class: "link " + cls, onclick: fn }, label);
      const set = async (body, msg) => { try { await req(body.deny === undefined && body.revoke ? "revoke" : "grant", body); changed = true; toast(msg); go(cur); } catch (e) { toast(e.message, true); } };
      const out = [];
      // Povolit len ak ho este nevidi (alebo je vylucene); zdedene povolenie netreba opakovat
      if (s.rule === "deny" || (s.rule !== "allow" && s.effective !== "yes"))
        out.push(b("Povoliť", "add", () => set({ type, name, path }, "Povolené.")));
      if (s.rule !== "deny" && path !== "") out.push(b("Vylúčiť", "danger", () => set({ type, name, path, deny: true }, "Vylúčené.")));
      if (s.rule) out.push(b("Zrušiť pravidlo", "", () => set({ type, name, path, revoke: true }, "Pravidlo zrušené.")));
      return h("span", { class: "acc-btns" }, out);
    }

    async function go(path) {
      list.replaceChildren(h("div", { class: "spinner" }));
      let r;
      try { r = await req("access_view", { type, name, path }); }
      catch (e) { list.replaceChildren(h("p", { class: "err" }, e.message)); return; }
      cur = r.path;
      const parts = cur ? cur.split("/") : [];
      crumbsEl.replaceChildren(h("button", { type: "button", class: "link", onclick: () => go("") }, "Celá knižnica"),
        ...parts.map((p, i) => [h("span", { class: "sep" }, " / "),
          h("button", { type: "button", class: "link", onclick: () => go(parts.slice(0, i + 1).join("/")) }, p)]).flat());
      head.replaceChildren(h("div", { class: "acc-row cur" },
        h("div", { class: "acc-name" }, h("strong", null, cur ? parts[parts.length - 1] : "Celá knižnica"), " ", ruleTag(r.self),
          r.self.via ? h("div", { class: "muted" }, r.self.via) : null),
        badge(r.self), buttons(cur, r.self)));
      list.replaceChildren(...(r.albums.length ? r.albums.map((a) => h("div", { class: "acc-row" },
        h("div", { class: "acc-name" },
          h("button", { type: "button", class: "link open", onclick: () => go(a.path) }, a.name), " ", ruleTag(a),
          a.via ? h("div", { class: "muted" }, a.via) : null),
        badge(a), buttons(a.path, a)))
        : [h("p", { class: "muted" }, `Žiadne podalbumy (${r.files} fotiek a videí).`)]));
    }
    go("");
  }

  function draw() {
    const tabs = [["users", "Používatelia"], ["groups", "Skupiny"], ["guest", "Bez prihlásenia"],
      ["shares", "Zdieľania"], ["moves", "Presuny"], ["general", "Všeobecné"]];
    const nav = h("nav", { class: "adm-tabs" }, tabs.map(([k, label]) =>
      h("button", { type: "button", class: k === tab ? "on" : "", onclick: () => { tab = k; draw(); } }, label)));
    const body = { users: drawUsers, groups: drawGroups, guest: drawGuest, general: drawGeneral,
      shares: () => { const w = h("div", { class: "adm-body" }); drawShares(w); return w; },
      moves: () => { const w = h("div", { class: "adm-body" }); drawMoves(w); return w; } }[tab]();
    root().replaceChildren(h("h2", { class: "adm-h" }, "Nastavenia"), nav, body);
  }

  // ---------- pouzivatelia ----------
  function drawUsers() {
    const wrap = h("div", { class: "adm-body" });
    const form = h("form", { class: "adm-new", onsubmit: async (e) => {
      e.preventDefault();
      const f = new FormData(e.target);
      if (await act("user_create", { username: f.get("username"), password: f.get("password"),
        note: f.get("note"), admin: f.get("admin") === "on" }, "Používateľ vytvorený.")) e.target.reset();
    } },
      h("strong", null, "Nový používateľ"),
      h("input", { name: "username", placeholder: "Meno", required: true, autocomplete: "off" }),
      h("input", { name: "password", type: "password", placeholder: "Heslo (min. 8 znakov)", required: true,
        minlength: "8", autocomplete: "new-password" }),
      h("input", { name: "note", placeholder: "Poznámka" }),
      h("label", { class: "chk" }, h("input", { type: "checkbox", name: "admin" }), "admin"),
      h("button", { class: "primary", type: "submit" }, "Pridať"));
    wrap.append(form);
    for (const u of st.users) {
      const flags = [u.admin && h("span", { class: "tag acc" }, "admin"), u.disabled && h("span", { class: "tag bad" }, "zablokovaný")];
      const card = h("section", { class: "card" + (u.disabled ? " off" : "") },
        h("div", { class: "card-h" },
          h("div", null, h("strong", null, u.username), " ", flags, u.note ? h("div", { class: "muted" }, u.note) : null),
          h("div", { class: "card-a" },
            h("button", { class: "link", type: "button", onclick: () => editUser(u) }, "Upraviť"))),
        u.admin ? h("p", { class: "muted" }, "Admin vidí všetky albumy.") : h("div", null,
          u.groups.length ? h("p", { class: "muted" }, "Skupiny: " + u.groups.join(", ")) : null,
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
      h("label", null, "Poznámka", h("input", { name: "note", value: u.note })),
      h("label", null, "Nové heslo", h("input", { name: "password", type: "password", minlength: "8",
        placeholder: "nechaj prázdne = bez zmeny", autocomplete: "new-password" })),
      h("label", { class: "chk" }, h("input", { type: "checkbox", name: "admin", checked: u.admin }), "admin (vidí všetko a môže meniť nastavenia)"),
      h("label", { class: "chk" }, h("input", { type: "checkbox", name: "disabled", checked: u.disabled }), "zablokovaný"),
      st.groups.length ? h("fieldset", null, h("legend", null, "Skupiny"), groups) : null,
      h("div", { class: "row" },
        h("button", { type: "button", class: "link danger", onclick: async () => {
          if (!confirm(`Naozaj zmazať používateľa ${u.username}?`)) return;
          if (await act("user_delete", { username: u.username }, "Používateľ zmazaný.")) dlg.close();
        } }, "Zmazať"),
        h("span", { class: "grow" }),
        h("button", { type: "button", class: "link", onclick: () => dlg.close() }, "Zrušiť"),
        h("button", { type: "submit", class: "primary" }, "Uložiť")));
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(f);
      const body = { username: u.username, note: fd.get("note"), admin: fd.get("admin") === "on",
        disabled: fd.get("disabled") === "on", groups: fd.getAll("g") };
      if (fd.get("password")) body.password = fd.get("password");
      if (await act("user_update", body, "Uložené.")) dlg.close();
    });
    const dlg = openDlg(f);
  }

  // ---------- skupiny ----------
  function drawGroups() {
    const wrap = h("div", { class: "adm-body" });
    wrap.append(h("form", { class: "adm-new", onsubmit: async (e) => {
      e.preventDefault();
      const f = new FormData(e.target);
      if (await act("group_create", { name: f.get("name"), note: f.get("note") }, "Skupina vytvorená.")) e.target.reset();
    } },
      h("strong", null, "Nová skupina"),
      h("input", { name: "name", placeholder: "Názov", required: true }),
      h("input", { name: "note", placeholder: "Poznámka" }),
      h("button", { class: "primary", type: "submit" }, "Pridať")));
    if (!st.groups.length) wrap.append(h("p", { class: "muted" },
      "Skupina zjednoduší práva: albumy priradíš skupine a ľudí do nej len pridáš."));
    for (const g of st.groups) {
      wrap.append(h("section", { class: "card" },
        h("div", { class: "card-h" },
          h("div", null, h("strong", null, g.name), g.note ? h("div", { class: "muted" }, g.note) : null),
          h("div", { class: "card-a" }, h("button", { class: "link", type: "button", onclick: () => editGroup(g) }, "Upraviť"))),
        h("p", { class: "muted" }, "Členovia: " + (g.members.length ? g.members.join(", ") : "nikto")),
        grantList("group", g.name, g.grants)));
    }
    return wrap;
  }

  function editGroup(g) {
    const users = st.users.map((u) => h("label", { class: "chk" },
      h("input", { type: "checkbox", name: "m", value: u.username, checked: g.members.includes(u.username) }), u.username));
    const f = h("form", { method: "dialog", class: "adm-form" },
      h("h3", null, "Skupina " + g.name),
      h("label", null, "Poznámka", h("input", { name: "note", value: g.note })),
      h("fieldset", null, h("legend", null, "Členovia"), users),
      h("div", { class: "row" },
        h("button", { type: "button", class: "link danger", onclick: async () => {
          if (!confirm(`Zmazať skupinu ${g.name}? Členom zostanú ich vlastné práva.`)) return;
          if (await act("group_delete", { name: g.name }, "Skupina zmazaná.")) dlg.close();
        } }, "Zmazať"),
        h("span", { class: "grow" }),
        h("button", { type: "button", class: "link", onclick: () => dlg.close() }, "Zrušiť"),
        h("button", { type: "submit", class: "primary" }, "Uložiť")));
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(f);
      if (await act("group_update", { name: g.name, note: fd.get("note"), members: fd.getAll("m") }, "Uložené.")) dlg.close();
    });
    const dlg = openDlg(f);
  }

  // ---------- host ----------
  function drawGuest() {
    const rootChk = h("input", { type: "checkbox", checked: !!st.settings.root_files_public,
      onchange: (e) => act("settings", { root_files_public: e.target.checked },
        e.target.checked ? "Fotky v koreni sú verejné." : "Fotky v koreni už nie sú verejné.") });
    return h("div", { class: "adm-body" },
      h("p", { class: "muted" }, "Albumy, ktoré uvidí ktokoľvek bez prihlásenia, v galérii aj v appke DS photo. " +
        "Ak je zoznam prázdny, bez prihlásenia nevidno nič."),
      h("section", { class: "card" },
        h("label", { class: "chk block" }, rootChk,
          h("span", null, "Fotky a videá priamo v koreni sú verejné",
            h("span", { class: "muted" }, " (len súbory v koreni, albumy ostávajú podľa svojich práv)")))),
      h("section", { class: "card" }, grantList("guest", "", st.guest.grants)));
  }

  // ---------- vseobecne ----------
  const FLAGS = [
    ["allow_download_user", "Prihlásení môžu sťahovať originály fotiek"],
    ["allow_download_guest", "Hostia bez prihlásenia môžu sťahovať originály fotiek"],
    ["hide_gps", "Skryť polohu (GPS) pred všetkými okrem admina"],
    ["hide_detail_user", "Skryť údaje z fotoaparátu pred prihlásenými"],
    ["hide_detail_guest", "Skryť údaje z fotoaparátu pred hosťami"],
    ["disable_timeline", "Vypnúť časovú os"],
    ["disable_search", "Vypnúť vyhľadávanie"],
    ["allow_comment_user", "Prihlásení môžu komentovať"],
    ["allow_comment_guest", "Hostia bez prihlásenia môžu komentovať (s menom, max. 20 za hodinu z jednej adresy)"],
    ["root_files_public", "Fotky a videá priamo v koreni sú verejné (albumy nie)"],
    ["people_for_guest", "Hostia bez prihlásenia vidia mená ľudí na fotkách (zo Synology Photos)"],
  ];

  function drawGeneral() {
    const f = h("form", { class: "card adm-form", onsubmit: async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const body = { title: fd.get("title"), root_album_order: fd.get("root_album_order") };
      for (const [k] of FLAGS) body[k] = fd.get(k) === "on";
      if (await act("settings", body, "Uložené.")) {
        S.title = fd.get("title") || "Fotky";
        $("brand").textContent = S.title;
      }
    } },
      h("label", null, "Názov galérie (hlavička webu, prihlasovanie v appke)",
        h("input", { name: "title", value: st.settings.title || "" })),
      h("label", null, "Zoradenie albumov v koreni",
        h("select", { name: "root_album_order" },
          h("option", { value: "desc", selected: st.settings.root_album_order === "desc" }, "od najnovších (roky a dátumy zostupne, ostatné za nimi)"),
          h("option", { value: "asc", selected: st.settings.root_album_order !== "desc" }, "od najstarších (A–Z)"))),
      h("fieldset", null, h("legend", null, "Obmedzenia (na admina sa nevzťahujú)"),
        FLAGS.map(([k, label]) => h("label", { class: "chk block" },
          h("input", { type: "checkbox", name: k, checked: !!st.settings[k] }), h("span", null, label)))),
      h("p", { class: "muted" }, "Zákaz sťahovania platí pre originály fotiek. Videá sa dajú prehrať, " +
        "preto ich appka aj web stiahnuť vedia vždy."),
      h("div", { class: "row" }, h("span", { class: "grow" }), h("button", { type: "submit", class: "primary" }, "Uložiť")));
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
    const choose = h("button", { type: "button", class: "primary" }, "Vybrať");
    const d = openDlg(h("div", { class: "adm-form pick" },
      h("h3", null, title || "Vyber album"),
      h("p", { class: "muted" }, hint || "Prístup platí pre album aj všetky jeho podalbumy."),
      crumbsEl, list,
      h("div", { class: "row" }, h("span", { class: "grow" }),
        h("button", { type: "button", class: "link", onclick: () => d.close() }, "Zrušiť"), choose)));
    choose.onclick = () => { d.close(); onPick(cur); };

    async function go(path) {
      list.replaceChildren(h("div", { class: "spinner" }));
      let r;
      try { r = await albumsOf(path); } catch (e) { list.replaceChildren(h("p", { class: "err" }, e.message)); return; }
      cur = r.path;
      choose.textContent = "Vybrať: " + pathLabel(cur);
      const parts = cur ? cur.split("/") : [];
      crumbsEl.replaceChildren(h("button", { type: "button", class: "link", onclick: () => go("") }, "Celá knižnica"),
        ...parts.map((p, i) => [h("span", { class: "sep" }, " / "),
          h("button", { type: "button", class: "link", onclick: () => go(parts.slice(0, i + 1).join("/")) }, p)]).flat());
      list.replaceChildren(...(r.albums.length ? r.albums.map((a) =>
        h("button", { type: "button", class: "pick-item", onclick: () => go(cur ? cur + "/" + a : a) }, a))
        : [h("p", { class: "muted" }, `Žiadne podalbumy (${r.files} fotiek a videí).`)]));
    }
    go("");
  }

  // ---------- album ----------
  async function setCover(rel) {
    const parts = rel.split("/").slice(0, -1);
    if (!parts.length) { toast("Fotka v koreni nepatrí do žiadneho albumu.", true); return; }
    // vsetky albumy, do ktorych fotka patri (najblizsi prvy): titulku mozno dat aj nadradenemu albumu
    const albums = parts.map((_, i) => parts.slice(0, parts.length - i).join("/"));
    const apply = async (path) => {
      try {
        await req("album_set", { path, cover: rel });
        toast(`Titulná fotka nastavená pre album ${path.split("/").pop()}.`);
        return true;
      } catch (e) { toast(e.message, true); return false; }
    };
    if (albums.length === 1) { apply(albums[0]); return; }
    const d = openDlg(h("div", { class: "adm-form" },
      h("h3", null, "Titulná fotka pre album"),
      h("p", { class: "muted" }, "Fotku môžeš nastaviť ako titulnú pre album, v ktorom je, alebo pre ktorýkoľvek nadradený."),
      h("div", { class: "cover-pick" }, albums.map((p, i) => h("button", { type: "button", class: i ? "link add" : "primary",
        onclick: async () => { if (await apply(p)) d.close(); } }, p.split("/").pop() + (i ? "" : " (tento album)")))),
      h("div", { class: "row" }, h("span", { class: "grow" }),
        h("button", { type: "button", class: "link", onclick: () => d.close() }, "Zrušiť"))));
  }

  async function editAlbum(path, onSaved) {
    let a;
    try {
      const r = await fetch("/api/admin/album_get?path=" + encodeURIComponent(path), { credentials: "same-origin" });
      a = await r.json();
      if (!r.ok) throw new Error(a.error || "Chyba");
    } catch (e) { toast(e.message, true); return; }
    const pwInput = h("input", { name: "password", type: "password", autocomplete: "new-password",
      placeholder: a.has_password ? "nechaj prázdne = ponechať heslo" : "heslo albumu (min. 4 znaky)" });
    const pwRow = h("label", null, "Heslo albumu", pwInput);
    const radio = (v, label, hint) => h("label", { class: "chk block" },
      h("input", { type: "radio", name: "mode", value: v, checked: a.mode === v,
        onchange: () => { pwRow.hidden = v !== "password"; } }),
      h("span", null, label, h("span", { class: "muted" }, " " + hint)));
    pwRow.hidden = a.mode !== "password";
    const who = [...a.users, ...a.groups.map((g) => "skupina " + g)];
    const coverInfo = a.cover ? "nastavená v galérii" : a.ea_cover ? "pôvodná z Photo Station" : "prvá fotka v albume";
    const f = h("form", { method: "dialog", class: "adm-form" },
      h("h3", null, "Album " + path.split("/").pop()),
      h("label", null, "Názov", h("input", { name: "title", value: a.title, placeholder: path.split("/").pop() })),
      h("label", null, "Popis", h("textarea", { name: "description", rows: "3" }, a.description)),
      h("label", null, "Zoradenie podalbumov",
        h("select", { name: "album_order" },
          h("option", { value: "asc", selected: a.album_order !== "desc" }, "od najstarších (A–Z)"),
          h("option", { value: "desc", selected: a.album_order === "desc" }, "od najnovších"))),
      h("fieldset", null, h("legend", null, "Prístup"),
        radio("private", "Súkromný", "len prihlásení s právom"),
        radio("public", "Verejný", "uvidí ho ktokoľvek aj bez prihlásenia"),
        radio("password", "S heslom", "ktokoľvek, kto pozná heslo"),
        pwRow),
      h("p", { class: "muted" }, "Právo priamo na tento album majú: " + (who.length ? who.join(", ") : "nikto okrem adminov") +
        (a.excluded.length ? ". Vylúčený je pre: " + a.excluded.join(", ") : "") +
        ". Práva a vylúčenia nastavíš v Nastaveniach."),
      h("p", { class: "muted" }, "Titulná fotka: " + coverInfo + ". Zmeníš ju v prehliadači fotky tlačidlom Titulná. ",
        a.cover ? h("button", { type: "button", class: "link add", onclick: async () => {
          try { await req("album_set", { path, cover: "" }); toast("Titulná fotka vrátená na pôvodnú."); d.close(); onSaved && onSaved(); }
          catch (e) { toast(e.message, true); }
        } }, "Vrátiť pôvodnú") : null),
      h("div", { class: "row" }, h("span", { class: "grow" }),
        h("button", { type: "button", class: "link", onclick: () => d.close() }, "Zrušiť"),
        h("button", { type: "submit", class: "primary" }, "Uložiť")));
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(f);
      const body = { path, title: fd.get("title"), description: fd.get("description"), mode: fd.get("mode"),
        album_order: fd.get("album_order") };
      if (body.mode === "password" && fd.get("password")) body.password = fd.get("password");
      try {
        await req("album_set", body);
        toast("Album uložený.");
        d.close();
        onSaved && onSaved();
      } catch (err) { toast(err.message, true); }
    });
    const d = openDlg(f);
  }

  // ---------- zdielanie ----------
  const shareUrl = (token) => location.origin + "/s/" + token;
  const fmtDay = (ts) => new Date(ts * 1000).toLocaleDateString("sk");

  function copyBox(url) {
    const inp = h("input", { value: url, readonly: true, class: "copy-in", onclick: (e) => e.target.select() });
    return h("div", { class: "copy" }, inp,
      h("button", { type: "button", class: "primary", onclick: async () => {
        try { await navigator.clipboard.writeText(url); toast("Odkaz skopírovaný."); }
        catch (e) { inp.select(); document.execCommand("copy"); toast("Odkaz skopírovaný."); }
      } }, "Kopírovať"));
  }

  function share(path, kind) {
    const label = kind === "album" ? "album " + path.split("/").pop() : path.split("/").pop();
    const result = h("div");
    const f = h("form", { method: "dialog", class: "adm-form" },
      h("h3", null, "Zdieľať " + label),
      h("p", { class: "muted" }, kind === "album"
        ? "Kto dostane odkaz, uvidí tento album aj jeho podalbumy bez prihlásenia."
        : "Kto dostane odkaz, uvidí túto položku bez prihlásenia."),
      h("label", null, "Platnosť", h("select", { name: "days" },
        h("option", { value: "0" }, "bez obmedzenia"), h("option", { value: "7" }, "7 dní"),
        h("option", { value: "30", selected: true }, "30 dní"), h("option", { value: "90" }, "90 dní"),
        h("option", { value: "365" }, "1 rok"))),
      h("label", { class: "chk block" }, h("input", { type: "checkbox", name: "dl" }),
        h("span", null, "povoliť sťahovanie originálov fotiek")),
      h("label", null, "Poznámka (pre teba, komu si odkaz poslal)", h("input", { name: "note" })),
      result,
      h("div", { class: "row" }, h("span", { class: "grow" }),
        h("button", { type: "button", class: "link", onclick: () => d.close() }, "Zavrieť"),
        h("button", { type: "submit", class: "primary" }, "Vytvoriť odkaz")));
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
      wrap.append(h("p", { class: "muted" }, "Zatiaľ žiadne odkazy. Vytvoríš ich tlačidlom Zdieľať v albume alebo pri fotke."));
      return;
    }
    for (const s of list) {
      const exp = s.expires ? (s.expired ? "vypršal " : "platí do ") + fmtDay(s.expires) : "bez obmedzenia";
      wrap.append(h("section", { class: "card" + (s.expired ? " off" : "") },
        h("div", { class: "card-h" },
          h("div", null, h("strong", null, s.path), " ", h("span", { class: "tag" }, s.kind === "album" ? "album" : s.kind === "video" ? "video" : "fotka"),
            h("div", { class: "muted" }, `${exp} · vytvoril ${s.created_by || "?"} ${fmtDay(s.created)}` +
              (s.allow_download ? " · sťahovanie povolené" : "") + (s.note ? " · " + s.note : ""))),
          h("div", { class: "card-a" }, h("button", { type: "button", class: "link danger", onclick: () => {
            if (confirm("Zrušiť tento odkaz? Kto ho má, už sa nedostane dnu.")) act("share_delete", { token: s.token }, "Odkaz zrušený.");
          } }, "Zrušiť"))),
        s.expired ? null : copyBox(shareUrl(s.token))));
    }
  }

  // ---------- presuny albumov ----------
  async function drawMoves(wrap) {
    let s;
    try { s = await req("moves_state"); } catch (e) { wrap.append(h("p", { class: "err" }, e.message)); return; }
    wrap.append(h("p", { class: "muted" }, "Keď na disku presunieš alebo premenuješ priečinok, galéria to pri najbližšom " +
      "indexovaní (každých 30 minút) spozná podľa rovnakých súborov a prenesie práva, vylúčenia, titulky, titulnú fotku, " +
      "tagy, komentáre, odkazy aj chytré albumy. Kým sa to stane, vylúčený album ostane skrytý aj na novom mieste."));

    const remap = (old) => pickAlbum(async (p) => {
      if (!p) { toast("Vyber album.", true); return; }
      await act("moves_remap", { old, new: p }, "Prenesené na " + p + ".");
      tab = "moves"; draw();
    }, "Kam sa album presunul?", "Všetko nastavené pre „" + old + "“ sa prenesie na vybraný album.");

    if (s.pending.length) {
      const sec = h("section", { class: "card" }, h("strong", null, "Nejednoznačné presuny"),
        h("p", { class: "muted" }, "Index našiel viac priečinkov s rovnakými súbormi. Vyber ten správny."));
      for (const p of s.pending) {
        sec.append(h("div", { class: "acc-row" }, h("div", { class: "acc-name" }, p.old),
          h("span", { class: "acc-btns" }, p.candidates.map((c) => h("button", { type: "button", class: "link add",
            onclick: async () => { await act("moves_remap", { old: p.old, new: c }, "Prenesené."); tab = "moves"; draw(); } }, "→ " + c)))));
      }
      wrap.append(sec);
    }

    const oc = h("section", { class: "card" }, h("strong", null, "Nastavenia pre albumy, ktoré už nie sú na disku"));
    if (!s.orphans.length) oc.append(h("p", { class: "muted" }, "Žiadne. Všetky nastavenia patria existujúcim albumom."));
    for (const o of s.orphans) {
      const what = [o.rules && `${o.rules} pravidiel`, o.props && "vlastnosti albumu", o.shares && `${o.shares} odkazov`,
        o.smart && `${o.smart} chytrých albumov`, o.nested && `+ ${o.nested} podalbumov`].filter(Boolean).join(", ");
      oc.append(h("div", { class: "acc-row" },
        h("div", { class: "acc-name" }, h("strong", null, o.path), h("div", { class: "muted" }, what)),
        h("span", null),
        h("span", { class: "acc-btns" },
          h("button", { type: "button", class: "link add", onclick: () => remap(o.path) }, "Presunuté kam…"),
          h("button", { type: "button", class: "link danger", onclick: async () => {
            if (!confirm(`Zmazať všetky nastavenia pre „${o.path}“?`)) return;
            await act("orphan_delete", { path: o.path }, "Zmazané."); tab = "moves"; draw();
          } }, "Zmazať"))));
    }
    wrap.append(oc);

    const hc = h("section", { class: "card" }, h("strong", null, "História presunov"));
    if (!s.history.length) hc.append(h("p", { class: "muted" }, "Zatiaľ žiadne."));
    for (const m of s.history) {
      hc.append(h("div", { class: "muted" }, `${fmtDay(m.created)} · ${m.old} → ${m.new}` +
        (m.kind === "manual" ? " (ručne)" : " (automaticky)")));
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
    const pathLbl = h("span", null, path || "všetky albumy");
    const tagBox = tags.length ? h("fieldset", null, h("legend", null, "Tagy (stačí jeden)"),
      tags.map((t) => h("label", { class: "chk" }, h("input", { type: "checkbox", name: "tag", value: t.id.slice(4),
        checked: (c.tags || []).includes(+t.id.slice(4)) }), t.name))) : h("p", { class: "muted" }, "Tagy zatiaľ nie sú.");
    const ctryBox = countries.length ? h("fieldset", null, h("legend", null, "Krajiny"),
      countries.map(([cc, n]) => h("label", { class: "chk" }, h("input", { type: "checkbox", name: "cc", value: cc,
        checked: (c.countries || []).includes(cc) }), n))) : null;
    const placeSel = places.length ? h("label", null, "Miesta (Ctrl/Cmd pre viac)",
      h("select", { name: "place", multiple: true, size: "6" }, places.map((p) => {
        const k = placeKey(p.id);
        return h("option", { value: k, selected: (c.places || []).includes(k) }, `${p.name} (${p.info.count})`);
      }))) : null;
    const types = c.types || [];
    const typeVal = types.length === 1 ? types[0] : "all";
    const f = h("form", { method: "dialog", class: "adm-form" },
      h("h3", null, s ? "Upraviť chytrý album" : "Nový chytrý album"),
      h("label", null, "Názov", h("input", { name: "name", required: true, value: s ? s.name : "" })),
      tagBox, ctryBox, placeSel,
      h("div", { class: "two" },
        h("label", null, "Od", h("input", { type: "date", name: "date_from", value: c.date_from || "" })),
        h("label", null, "Do", h("input", { type: "date", name: "date_to", value: c.date_to || "" }))),
      h("fieldset", null, h("legend", null, "Typ"),
        [["all", "fotky aj videá"], ["photo", "len fotky"], ["video", "len videá"]].map(([v, l]) =>
          h("label", { class: "chk" }, h("input", { type: "radio", name: "types", value: v, checked: typeVal === v }), l))),
      h("p", { class: "muted" }, "Len z albumu: ", pathLbl, " ",
        h("button", { type: "button", class: "link add", onclick: () => pickAlbum((p) => { path = p; pathLbl.textContent = p || "všetky albumy"; }) }, "zmeniť")),
      h("div", { class: "row" },
        s ? h("button", { type: "button", class: "link danger", onclick: async () => {
          if (!confirm("Zmazať chytrý album? Fotky ostanú.")) return;
          try { await req("smart_delete", { id: s.id }); toast("Zmazané."); d.close(); onSaved && onSaved(); }
          catch (e) { toast(e.message, true); }
        } }, "Zmazať") : null,
        h("span", { class: "grow" }),
        h("button", { type: "button", class: "link", onclick: () => d.close() }, "Zrušiť"),
        h("button", { type: "submit", class: "primary" }, "Uložiť")));
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(f);
      const t = fd.get("types");
      const crit = {
        tags: fd.getAll("tag").map(Number), countries: fd.getAll("cc"),
        places: placeSel ? [...f.querySelector("select[name=place]").selectedOptions].map((o) => o.value) : [],
        date_from: fd.get("date_from") || "", date_to: fd.get("date_to") || "",
        types: t === "all" ? [] : [t], path,
      };
      try {
        await req("smart_save", { id: s ? s.id : null, name: fd.get("name"), criteria: crit });
        toast("Chytrý album uložený.");
        d.close();
        onSaved && onSaved();
      } catch (err) { toast(err.message, true); }
    });
    const d = openDlg(f);
  }

  return { show, hide: () => { root().hidden = true; }, editAlbum, setCover, share, editSmart, albumAccess };
})();
