// SPDX-License-Identifier: GPL-3.0-or-later
"use strict";
// Webova galeria nad API Photo Station (/photo/webapi). Rovnaki pouzivatelia a prava ako appka DS photo.

const BASE = window.PS_BASE || "";  // "" or "/~name" for a private gallery reached by path
const API = BASE + "/photo/webapi/";
const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
};

class ApiError extends Error {
  constructor(code) { super("API " + code); this.code = code; }
}

const S = {
  user: "", isAdmin: false, title: t("Photos"), canDownload: true, infoDownload: true, hideSearch: false,
  share: null, shareRoot: null, shareTitle: "", groupId: null, groupTitle: "", discover: null,
  view: null, albumId: null, query: "",
  offset: 0, total: 0, done: false, loading: false, seq: 0,
  media: [], lastMonth: "",
};

// ---------- API ----------
async function call(file, api, method, params = {}, version = 1) {
  if (S.share) params = { ...params, share: S.share };
  const body = new URLSearchParams({ api, method, version: String(version), ...params });
  const r = await fetch(API + file, { method: "POST", body, credentials: "same-origin", headers: { "X-Lang": LANG } });
  checkVersion(r);
  if (r.headers.get("x-request-error") === "error_timeout") {
    S.user = "";
    renderUser();
    throw new ApiError(106);
  }
  const j = await r.json();
  if (!j.success) throw new ApiError(j.error && j.error.code);
  return j.data;
}

// nova verzia galerie na serveri -> ponuknut obnovenie stranky
function checkVersion(r) {
  const v = r.headers.get("x-picturestation-version");
  if (!v || !window.PS_VERSION || v === window.PS_VERSION || document.getElementById("newVersion")) return;
  const bar = el("div", "newver");
  bar.id = "newVersion";
  bar.append(el("span", null, t("The gallery has been updated.") + " "));
  const b = el("button", "primary", t("Reload page"));
  b.type = "button";
  b.onclick = () => location.reload();
  bar.append(b);
  document.body.append(bar);
}

function hex(s) {
  return Array.from(new TextEncoder().encode(s), (b) => b.toString(16).padStart(2, "0")).join("");
}
function unhex(h) {
  const m = h.match(/../g) || [];
  return new TextDecoder().decode(new Uint8Array(m.map((x) => parseInt(x, 16))));
}
const albumPath = (id) => (id ? unhex(id.slice(6)) : "");
const albumIdOf = (path) => (path ? "album_" + hex(path) : "");

function thumbUrl(item, size) {
  const ts = (item.additional && item.additional.thumb_size) || {};
  const mt = (ts.small && ts.small.mtime) || "";
  let u = `${API}thumb.php?api=SYNO.PhotoStation.Thumb&method=get&version=1&id=${encodeURIComponent(item.id)}&size=${size}`;
  if (mt) u += "&mtime=" + mt;
  if (item.type === "album" && ts.sig) u += "&sig=" + ts.sig;
  if (S.share) u += "&share=" + encodeURIComponent(S.share);
  return u;
}
function downloadUrl(item, web) {
  const m = item.type === "video" ? "getvideo" : "getphoto";
  return `${API}download.php?api=SYNO.PhotoStation.Download&method=${m}&version=1&id=${encodeURIComponent(item.id)}` +
    (web ? "&variant=web" : "") + (S.share ? "&share=" + encodeURIComponent(S.share) : "");
}
const albumHref = (id) => (S.share ? `#/share/${encodeURIComponent(S.share)}/${id}` : "#/a/" + id);

// ---------- pomocne ----------
function fmtDuration(ms) {
  const s = Math.round((parseInt(ms, 10) || 0) / 1000);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(sec).padStart(2, "0");
}
function fmtSize(b) {
  if (!b) return "";
  return b > 1e9 ? (b / 1e9).toFixed(2) + " GB" : b > 1e6 ? (b / 1e6).toFixed(1) + " MB" : Math.round(b / 1e3) + " kB";
}
const monthFmt = new Intl.DateTimeFormat(LOCALE(), { month: "long", year: "numeric" });
function monthLabel(taken) {
  const d = new Date(taken.slice(0, 7) + "-01T00:00:00");
  return isNaN(d) ? t("No date") : monthFmt.format(d);
}
function fmtDate(taken) {
  const d = new Date(taken.replace(" ", "T"));
  return isNaN(d) ? taken : d.toLocaleString(LOCALE(), { dateStyle: "long", timeStyle: "short" });
}
function store(k, v) {
  try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; }
}

// ---------- pouzivatel ----------
function renderUser() {
  if (!S.user) S.isAdmin = false;
  $("adminTab").hidden = !S.isAdmin;
  $("userName").textContent = S.user || "";
  $("loginBtn").hidden = !!S.user;
  $("logoutBtn").hidden = !S.user;
}

function showLogin(msg) {
  const d = $("loginDlg");
  $("loginErr").hidden = !msg;
  $("loginErr").textContent = msg || "";
  $("loginTitle").textContent = S.title;
  if (!d.open) d.showModal();
  d.querySelector("input[name=username]").focus();
}

$("loginForm").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = new FormData(ev.target);
  try {
    const d = await call("auth.php", "SYNO.PhotoStation.Auth", "login",
      { username: f.get("username"), password: f.get("password") });
    S.user = d.username;
    S.isAdmin = !!d.is_admin;
    S.canComment = !!d.allow_comment;
    renderUser();
    $("loginDlg").close();
    ev.target.reset();
    await loadInfo();
    route();
  } catch (e) {
    showLogin(e.code === 410 ? t("Too many attempts, try again in 10 minutes.") : t("Wrong user name or password."));
  }
});
$("loginCancel").onclick = () => $("loginDlg").close();
$("loginBtn").onclick = () => showLogin();
$("logoutBtn").onclick = async () => {
  try { await call("auth.php", "SYNO.PhotoStation.Auth", "logout"); } catch (e) { /* nic */ }
  S.user = "";
  renderUser();
  await loadInfo();
  try { S.canComment = !!(await call("auth.php", "SYNO.PhotoStation.Auth", "checkauth")).allow_comment; } catch (e) { S.canComment = false; }
  location.hash = "#/";
  route();
};

// ---------- navigacia ----------
function setTabs() {
  const tab = ["collection", "people", "group"].includes(S.view) ? "discover" : S.view;
  document.querySelectorAll(".tabs a").forEach((a) => a.classList.toggle("on", a.dataset.tab === tab));
  $("sortSel").hidden = S.view !== "album";
}

function crumbs() {
  const c = $("crumbs");
  c.replaceChildren();
  if (S.view === "timeline") { c.append(el("span", "cur", t("Timeline"))); return; }
  // cesta v Zbierkach: [ [nazov, odkaz|null], ... ]
  const trail = (parts) => {
    parts.forEach(([label, href], i) => {
      if (i) c.append(el("span", "sep", "/"));
      if (href && i < parts.length - 1) { const a = el("a", null, label); a.href = href; c.append(a); }
      else c.append(el("span", "cur", label));
    });
  };
  const Z = [t("Collections"), "#/x"];
  const KIND = { smart: [t("Smart albums"), "#/c/smart"], tags: [t("Tags"), "#/c/tags"], places: [t("Places"), "#/c/places"] };
  if (S.view === "people") { trail([Z, [t("People")]]); return; }
  if (S.view === "collection") {
    const p = [Z, KIND[S.collKind] || ["?"]];
    if (S.collKind === "places" && S.collArg) p.push([S.countryName || S.collArg]);
    trail(p);
    return;
  }
  if (S.view === "group") {
    const id = S.groupId || "", title = S.groupTitle || "…";
    if (id.startsWith("tag_p")) trail([Z, [t("People"), "#/people"], [title]]);
    else if (id.startsWith("smart_")) trail([Z, KIND.smart, [title]]);
    else if (id.startsWith("tag_g")) {
      // miesto: "cc|obec" v hex -> krajina z nazvu "Obec, Krajina"
      let cc = "";
      try { cc = unhex(id.slice(5)).split("|")[0]; } catch (e) { /* nic */ }
      const [place, ...country] = title.split(", ");
      trail([Z, KIND.places, [country.join(", ") || cc, "#/c/places/" + encodeURIComponent(cc)], [place]]);
    } else trail([Z, KIND.tags, [title]]);
    return;
  }
  if (S.view === "search") { c.append(el("span", "cur", t("Search: {q}", { q: S.query }))); return; }
  // v rezime zdielania zacina cesta zdielanym albumom
  const base = S.share ? albumPath(S.shareRoot) : "";
  const rootLabel = S.share ? S.shareTitle : t("Albums");
  const full = albumPath(S.albumId);
  const parts = (base ? full.slice(base.length) : full).split("/").filter(Boolean);
  if (!parts.length) { c.append(el("span", "cur", rootLabel)); return; }
  const root = el("a", null, rootLabel);
  root.href = S.share ? albumHref(S.shareRoot) : "#/";
  c.append(root);
  parts.forEach((p, i) => {
    c.append(el("span", "sep", "/"));
    if (i === parts.length - 1) c.append(el("span", "cur", p));
    else {
      const a = el("a", null, p);
      a.href = albumHref(albumIdOf((base ? base + "/" : "") + parts.slice(0, i + 1).join("/")));
      c.append(a);
    }
  });
  document.title = parts[parts.length - 1] + " · " + S.title;
}

function route() {
  const h = location.hash.replace(/^#/, "") || "/";
  closeViewer(true);
  if (h.startsWith("/admin")) {
    S.view = "admin";
    S.seq++;
    setTabs();
    $("gallery").hidden = true;
    document.title = t("Settings") + " · " + S.title;
    if (!S.isAdmin) { $("admin").hidden = true; showLogin(t("Settings are for administrators only.")); return; }
    Admin.show();
    return;
  }
  $("gallery").hidden = false;
  if (typeof Admin !== "undefined") Admin.hide();
  if (h.startsWith("/share/")) { routeShare(h.slice(7)); return; }
  setShareMode(null);
  if (h.startsWith("/x")) {
    S.view = "discover"; setTabs(); reset();
    $("crumbs").replaceChildren(el("span", "cur", t("Collections")));
    document.title = t("Collections") + " · " + S.title;
    $("editAlbumBtn").hidden = $("shareAlbumBtn").hidden = $("accessAlbumBtn").hidden = true;
    renderDiscover(S.seq);
    return;
  }
  if (h.startsWith("/c/")) {
    const [kind, arg] = h.slice(3).split("/");
    S.view = "collection"; S.collKind = kind; S.collArg = arg ? decodeURIComponent(arg) : "";
    setTabs(); reset(); crumbs();
    document.title = t("Collections") + " · " + S.title;
    $("editAlbumBtn").hidden = $("shareAlbumBtn").hidden = $("accessAlbumBtn").hidden = true;
    renderCollection(kind, S.collArg, S.seq);
    return;
  }
  if (h.startsWith("/people")) {
    S.view = "people"; setTabs(); reset(); crumbs();
    document.title = t("People") + " · " + S.title;
    $("editAlbumBtn").hidden = $("shareAlbumBtn").hidden = $("accessAlbumBtn").hidden = true;
    renderPeople(S.seq);
    return;
  }
  if (h.startsWith("/g/")) { S.view = "group"; S.groupId = decodeURIComponent(h.slice(3)); }
  else if (h.startsWith("/t")) { S.view = "timeline"; S.albumId = null; }
  else if (h.startsWith("/s/")) { S.view = "search"; S.query = decodeURIComponent(h.slice(3)); }
  else { S.view = "album"; S.albumId = h.startsWith("/a/") ? h.slice(3) : ""; }
  if (S.view !== "album") document.title = S.title;
  else if (!S.albumId) document.title = S.title;
  $("searchInput").value = S.view === "search" ? S.query : "";
  setTabs();
  crumbs();
  reset();
  $("editAlbumBtn").hidden = !(S.isAdmin && S.view === "album" && S.albumId);
  $("shareAlbumBtn").hidden = $("accessAlbumBtn").hidden = $("editAlbumBtn").hidden;
  if (S.view === "album" && S.albumId) loadAlbumHeader(S.seq);
  loadMore();
}

// ---------- zdielany odkaz ----------
const shareCache = {};

function setShareMode(token) {
  S.share = token;
  document.querySelector(".tabs").hidden = !!token;
  $("searchForm").hidden = !!token || S.hideSearch;
  if (!token) S.canDownload = S.infoDownload;
}

async function routeShare(rest) {
  const [tokRaw, sub] = rest.split("/");
  const token = decodeURIComponent(tokRaw || "");
  const seq = ++S.seq;
  let info = shareCache[token];
  if (!info) {
    try {
      const r = await fetch(BASE + "/api/share/" + encodeURIComponent(token));
      info = r.ok ? await r.json() : null;
    } catch (e) { info = null; }
    if (info) shareCache[token] = info;
  }
  if (seq !== S.seq) return;
  setShareMode(info ? token : null);
  reset();
  $("editAlbumBtn").hidden = $("shareAlbumBtn").hidden = $("accessAlbumBtn").hidden = true;
  if (!info) {
    S.view = "share"; setTabs();
    $("crumbs").replaceChildren(el("span", "cur", t("Shared link")));
    showEmpty(t("The link is not valid or has expired."));
    return;
  }
  S.shareTitle = info.title;
  S.canDownload = info.allow_download || S.isAdmin;
  document.title = info.title + " · " + S.title;
  if (info.kind === "album") {
    S.view = "album";
    S.shareRoot = info.id;
    S.albumId = sub || info.id;
    setTabs();
    crumbs();
    loadAlbumHeader(S.seq);
    loadMore();
    return;
  }
  // jedna fotka alebo video
  S.view = "share"; setTabs();
  $("crumbs").replaceChildren(el("span", "cur", info.title));
  try {
    const items = await call("photo.php", "SYNO.PhotoStation.Photo", "getinfo",
      { id: info.id, additional: "thumb_size,photo_exif,video_codec" });
    S.total = items.length; S.done = true;
    renderItems(items);
    openViewer(0);
  } catch (e) { showEmpty(t("The file could not be loaded.")); }
}

async function loadAlbumHeader(seq) {
  try {
    const d = await call("album.php", "SYNO.PhotoStation.Album", "getinfo", { id: S.albumId });
    if (seq !== S.seq || !d.items.length) return;
    const info = d.items[0].info;
    const cur = $("crumbs").querySelector(".cur");
    if (cur && info.title) { cur.textContent = info.title; document.title = info.title + " · " + S.title; }
    $("albumDesc").textContent = info.description || "";
    $("albumDesc").hidden = !info.description;
  } catch (e) { /* bez hlavicky */ }
}

$("unlockForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const pw = new FormData(e.target).get("password");
  try {
    await call("album.php", "SYNO.PhotoStation.Album", "list", { id: S.albumId, password: pw, offset: 0, limit: 1 });
    e.target.reset();
    route();
  } catch (err) {
    $("unlockErr").textContent = err.code === 410 ? t("Too many attempts, try again in 10 minutes.") : t("Wrong password.");
    $("unlockErr").hidden = false;
  }
});
$("editAlbumBtn").onclick = () => Admin.editAlbum(albumPath(S.albumId), () => route());
$("shareAlbumBtn").onclick = () => Admin.share(albumPath(S.albumId), "album");
$("accessAlbumBtn").onclick = () => Admin.albumAccess(albumPath(S.albumId));

function reset() {
  S.seq++;
  S.offset = 0; S.total = 0; S.done = false; S.loading = false; S.media = []; S.lastMonth = "";
  $("albums").replaceChildren();
  $("grid").replaceChildren();
  $("empty").hidden = true;
  $("count").textContent = "";
  $("unlockForm").hidden = true;
  $("unlockErr").hidden = true;
  $("albumDesc").hidden = true;
  $("discover").hidden = true;
  $("discover").replaceChildren();
  if (S.view === "group") loadGroupTitle(S.seq);
}

// ---------- objavit: chytre albumy, tagy, miesta ----------
async function loadGroupTitle(seq) {
  const id = S.groupId;
  try {
    const d = id.startsWith("smart_")
      ? (await call("smart_album.php", "SYNO.PhotoStation.SmartAlbum", "getinfo", { id })).smart_albums
      : (await call("tag.php", "SYNO.PhotoStation.Tag", "getinfo", { id })).tags;
    if (seq !== S.seq || !d.length) return;
    S.groupTitle = d[0].name;
    crumbs();
    document.title = S.groupTitle + " · " + S.title;
  } catch (e) { /* nic */ }
}

function groupCard(it, sub) {
  const a = el("a", "album");
  a.href = "#/g/" + encodeURIComponent(it.id);
  const cov = el("div", "cover");
  if (it.thumbnail_status !== "default") {
    const img = el("img"); img.loading = "lazy"; img.decoding = "async"; img.alt = "";
    img.src = thumbUrl(it, "small");
    cov.append(img);
  } else cov.classList.add("none");
  a.append(cov, el("div", "name", it.name), el("div", "sub", sub || tn(it.info.count, "{n} item", "{n} items")));
  return a;
}

// ---------- ludia ako priecinok v Albumoch ----------
let peopleCache = null, peopleCacheT = 0, peopleCacheUser = null;
async function getPeople() {
  if (peopleCache && Date.now() - peopleCacheT < 120000 && peopleCacheUser === S.user) return peopleCache;
  try {
    peopleCache = (await call("tag.php", "SYNO.PhotoStation.Tag", "list", { type: "people", limit: 5000 })).tags;
  } catch (e) { peopleCache = []; }
  peopleCacheT = Date.now();
  peopleCacheUser = S.user;
  return peopleCache;
}


async function renderPeople(seq) {
  const box = $("discover");
  box.hidden = false;
  $("spinner").hidden = false;
  const people = await getPeople();
  if (seq !== S.seq) return;
  $("spinner").hidden = true;
  box.replaceChildren();
  if (!people.length) { showEmpty(t("No people to show.")); return; }
  const g = el("div", "albums people");
  for (const p of people) g.append(groupCard(p));
  box.append(g);
  $("count").textContent = tn(people.length, "{n} person", "{n} people");
}

async function renderDiscover(seq) {
  const box = $("discover");
  box.hidden = false;
  $("spinner").hidden = false;
  S.collections = null;  // vstup do Zbierok = cerstve data
  const { smart, tags, places, people } = await getCollections();
  if (seq !== S.seq) return;
  $("spinner").hidden = true;
  box.replaceChildren();

  S.collections = { smart, tags, places, people, t: Date.now(), user: S.user };
  const byCount = (a, b) => (b.info.count || 0) - (a.info.count || 0);
  const g = el("div", "albums");
  // Zbierky: dlazdice Ludia / Tagy / Miesta (obsah po kliknuti), chytre albumy priamo pod nimi
  if (people.length) g.append(collageTile(t("People"), tn(people.length, "{n} person", "{n} people"), "#/people", people));
  g.append(collageTile(t("Tags"), tn(tags.length, "{n} tag", "{n} tags"), "#/c/tags", [...tags].sort(byCount)));
  if (places.length) {
    const countries = new Set(places.map((p) => p.info.cc));
    g.append(collageTile(t("Places"), tn(countries.size, "{n} country", "{n} countries"), "#/c/places",
      [...places].sort(byCount)));
  }

  // chytre albumy priamo v Zbierkach (hore), dlazdice Ludia/Tagy/Miesta na konci
  const hd = el("div", "disc-h");
  hd.append(el("h3", null, t("Smart albums")));
  if (S.isAdmin) {
    const nb = el("button", "link add", "+ " + t("New smart album")); nb.type = "button";
    nb.onclick = () => Admin.editSmart(null, S.discover, () => { S.collections = null; route(); });
    hd.append(nb);
  }
  box.append(hd);
  const gs = el("div", "albums");
  for (const s of smart) {
    const card = groupCard(s);
    if (S.isAdmin) {
      const e = el("button", "link edit", t("Edit")); e.type = "button";
      e.onclick = (ev) => { ev.preventDefault(); Admin.editSmart(s, S.discover, () => { S.collections = null; route(); }); };
      card.append(e);
    }
    gs.append(card);
  }
  if (!smart.length) gs.append(el("p", "muted", S.isAdmin
    ? t("A smart album shows photos by tags, place, period or type.") : t("None yet.")));
  box.append(gs);
  g.classList.add("coll-tiles");
  box.append(g);
}

// dlazdica s kolazou styroch titulnych fotiek (Ludia, Tagy, Miesta, Chytre albumy, krajina)
function collageTile(title, sub, href, items) {
  const a = el("a", "album people-tile");
  a.href = href;
  const cov = el("div", "cover collage");
  const withThumb = items.filter((x) => x.thumbnail_status !== "default").slice(0, 4);
  const relayout = () => {
    const n = cov.querySelectorAll("img").length;
    cov.classList.remove("n1", "n2", "n3", "n4", "none");
    cov.classList.add(n ? "n" + n : "none");  // rozlozenie podla poctu fotiek (1 az 4)
  };
  for (const it of withThumb) {
    const img = el("img"); img.loading = "lazy"; img.decoding = "async"; img.alt = "";
    img.onerror = () => { img.remove(); relayout(); };  // nenacitany nahlad (napr. video) z kolaze vyradit
    img.src = thumbUrl(it, "small");
    cov.append(img);
  }
  relayout();
  a.append(cov, el("div", "name", title), el("div", "sub", sub));
  return a;
}

// data zbierok (cache 1 min, aby preklikavanie bolo rychle)
async function getCollections() {
  const c = S.collections;
  if (c && Date.now() - c.t < 60000 && c.user === S.user) return c;
  let smart = [], tags = [], places = [], people = [];
  try {
    [smart, tags, places, people] = await Promise.all([
      call("smart_album.php", "SYNO.PhotoStation.SmartAlbum", "list").then((d) => d.smart_albums),
      call("tag.php", "SYNO.PhotoStation.Tag", "list", { type: "desc", limit: 5000 }).then((d) => d.tags),
      call("tag.php", "SYNO.PhotoStation.Tag", "list", { type: "geo", limit: 5000 }).then((d) => d.tags),
      call("tag.php", "SYNO.PhotoStation.Tag", "list", { type: "people", limit: 5000 }).then((d) => d.tags).catch(() => []),
    ]);
  } catch (e) { /* ciastocne */ }
  S.collections = { smart, tags, places, people, t: Date.now(), user: S.user };
  S.discover = { smart, tags, places };
  return S.collections;
}

// obsah jednej zbierky: c/smart, c/tags, c/places, c/places/<cc>
async function renderCollection(kind, arg, seq) {
  const box = $("discover");
  box.hidden = false;
  $("spinner").hidden = false;
  const c = await getCollections();
  if (seq !== S.seq) return;
  $("spinner").hidden = true;
  box.replaceChildren();
  const g = el("div", "albums");
  const byCount = (a, b) => (b.info.count || 0) - (a.info.count || 0);
  let n = 0;
  if (kind === "smart") {
    if (S.isAdmin) {
      const nb = el("button", "link add", "+ " + t("New smart album")); nb.type = "button";
      nb.onclick = () => Admin.editSmart(null, S.discover, () => { S.collections = null; route(); });
      box.append(el("div", "disc-h"));
      box.lastChild.append(nb);
    }
    for (const s of c.smart) {
      const card = groupCard(s);
      if (S.isAdmin) {
        const e = el("button", "link edit", t("Edit")); e.type = "button";
        e.onclick = (ev) => { ev.preventDefault(); Admin.editSmart(s, S.discover, () => { S.collections = null; route(); }); };
        card.append(e);
      }
      g.append(card);
    }
    n = c.smart.length;
    if (!n) box.append(el("p", "muted", S.isAdmin
      ? t("A smart album shows photos by tags, place, period or type.") : t("None yet.")));
  } else if (kind === "tags") {
    for (const tg of [...c.tags].sort((a, b) => a.name.localeCompare(b.name, LOCALE()))) g.append(groupCard(tg));
    n = c.tags.length;
    if (!n) box.append(el("p", "muted", S.isAdmin ? t("Add tags to a photo in the Info panel.") : t("None yet.")));
  } else if (kind === "places" && !arg) {
    const groups = new Map();
    for (const p of c.places) {
      if (!groups.has(p.info.cc)) groups.set(p.info.cc, { name: p.info.country, items: [], count: 0 });
      const gr = groups.get(p.info.cc);
      gr.items.push(p); gr.count += p.info.count || 0;
    }
    const list = [...groups.entries()].sort((a, b) => b[1].count - a[1].count);
    for (const [cc, gr] of list) {
      g.append(collageTile(gr.name, tn(gr.items.length, "{n} place", "{n} places") + " · " + tn(gr.count, "{n} photo", "{n} photos"),
        "#/c/places/" + encodeURIComponent(cc), gr.items.sort(byCount)));
    }
    n = list.length;
    box.append(g);
    box.append(el("p", "muted attr", t("Place names: GeoNames (CC BY 4.0)")));
    $("count").textContent = tn(n, "{n} country", "{n} countries");
    return;
  } else if (kind === "places") {
    const items = c.places.filter((p) => p.info.cc === arg).sort(byCount);
    if (items.length) S.countryName = items[0].info.country;
    for (const p of items) g.append(groupCard({ ...p, name: p.name.split(", ")[0] }));
    n = items.length;
    crumbs();
  }
  box.append(g);
  $("count").textContent = n ? tn(n, "{n} item", "{n} items") : "";
}

async function loadMore() {
  // dočítavanie len v zoznamoch fotiek; Zbierky, Ľudia a Nastavenia majú vlastný obsah
  if (!["album", "timeline", "search", "group"].includes(S.view)) return;
  if (S.loading || S.done) return;
  S.loading = true;
  const seq = S.seq;
  $("spinner").hidden = false;
  const limit = S.view === "album" ? 120 : 200;
  const add = "thumb_size,photo_exif,video_codec";
  try {
    let data;
    if (S.view === "group") {
      const p = { type: "photo,video", offset: S.offset, limit, sort_by: "takendate", sort_direction: "desc", additional: add };
      p[S.groupId.startsWith("smart_") ? "filter_smart" : "filter_tag"] = S.groupId;
      data = await call("photo.php", "SYNO.PhotoStation.Photo", "list", p);
    } else if (S.view === "timeline") {
      data = await call("photo.php", "SYNO.PhotoStation.Photo", "list", { type: "photo,video",
        offset: S.offset, limit, sort_by: "takendate", sort_direction: "desc", additional: add });
    } else if (S.view === "search") {
      data = await call("album.php", "SYNO.PhotoStation.Album", "list", { type: "album,photo,video",
        recursive: "true", keyword: S.query, offset: S.offset, limit, additional: add });
    } else {
      const [sb, sd] = (store("sort") || "takendate|asc").split("|");
      const p = { type: "album,photo,video", offset: S.offset, limit, sort_by: sb, sort_direction: sd, additional: add };
      if (S.albumId) p.id = S.albumId;
      data = await call("album.php", "SYNO.PhotoStation.Album", "list", p);
    }
    if (seq !== S.seq) return;
    S.total = data.total;
    S.offset += data.items.length;
    S.done = data.items.length === 0 || S.offset >= S.total;
    renderItems(data.items);
    $("count").textContent = S.total ? tn(S.total, "{n} item", "{n} items") : "";
    if (!S.total) showEmpty();
  } catch (e) {
    if (seq !== S.seq) return;
    S.done = true;
    if (e.code === 106) showLogin(t("Your session has expired."));
    else if (e.code === 416) { $("unlockForm").hidden = false; $("unlockForm").querySelector("input").focus(); }
    else if (e.code === 410) showEmpty(t("Too many wrong passwords, try again in 10 minutes."));
    else if (e.code === 417) showEmpty(t("You do not have access to this album."));
    else showEmpty(t("The content could not be loaded."));
  } finally {
    if (seq === S.seq) {
      S.loading = false;
      $("spinner").hidden = true;
      // ak stranka este nie je plna, nacitaj dalsie
      if (!S.done && $("sentinel").getBoundingClientRect().top < innerHeight + 600) loadMore();
    }
  }
}

function showEmpty(msg) {
  const e = $("empty");
  e.hidden = false;
  if (msg) e.textContent = msg;
  else if (!S.user && S.view === "album" && !S.albumId) {
    e.replaceChildren(el("span", null, t("Nothing to show.") + " "));
    const b = el("button", "link", t("Sign in"));
    b.onclick = () => showLogin();
    e.append(b);
  } else e.textContent = S.view === "search" ? t("Nothing found.") : t("The album is empty.");
}

function renderItems(items) {
  const albums = $("albums"), grid = $("grid");
  for (const it of items) {
    if (it.type === "album") {
      const a = el("a", "album");
      a.href = albumHref(it.id);
      const cov = el("div", "cover");
      if (it.thumbnail_status !== "default") {
        const img = el("img");
        img.loading = "lazy"; img.decoding = "async"; img.alt = "";
        img.src = thumbUrl(it, "small");
        cov.append(img);
      } else cov.classList.add(it.info.locked ? "locked" : "none");
      a.append(cov, el("div", "name", it.info.title || it.info.name));
      if (it.info.type === "password") a.querySelector(".name").append(el("span", "tag", t("password")));
      else if (it.info.type === "public" && S.isAdmin) a.querySelector(".name").append(el("span", "tag acc", t("public")));
      if (S.view === "search") a.append(el("div", "sub", it.info.sharepath));
      albums.append(a);
      continue;
    }
    if (S.view === "timeline") {
      const m = (it.info.takendate || "").slice(0, 7);
      if (m !== S.lastMonth) {
        S.lastMonth = m;
        grid.append(el("h3", "month", monthLabel(it.info.takendate || "")));
      }
    }
    const idx = S.media.length;
    S.media.push(it);
    const tile = el("button", "tile");
    tile.type = "button";
    tile.title = it.info.name;
    const img = el("img");
    img.loading = "lazy"; img.decoding = "async"; img.alt = it.info.name;
    img.onload = () => img.classList.add("ok");
    img.onerror = () => img.classList.add("ok");
    if (it.thumbnail_status !== "default") img.src = thumbUrl(it, "small");
    tile.append(img);
    if (it.type === "video") tile.append(el("span", "badge", fmtDuration(it.info.duration)));
    tile.onclick = () => openViewer(idx);
    grid.append(tile);
  }
}

new IntersectionObserver((e) => { if (e[0].isIntersecting) loadMore(); }, { rootMargin: "800px" })
  .observe($("sentinel"));

$("sortSel").value = store("sort") || "takendate|asc";
$("sortSel").onchange = (e) => { store("sort", e.target.value); route(); };
$("searchForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = $("searchInput").value.trim();
  location.hash = q ? "#/s/" + encodeURIComponent(q) : "#/";
});
addEventListener("hashchange", route);

// ---------- prehliadac ----------
let vIdx = -1, vPushed = false;

function openViewer(i) {
  $("viewer").hidden = false;
  document.body.style.overflow = "hidden";
  if (!vPushed) { history.pushState({ viewer: 1 }, ""); vPushed = true; }
  show(i);
}

function closeViewer(fromRoute) {
  if ($("viewer").hidden) return;
  const v = $("vVideo");
  v.pause(); v.removeAttribute("src"); v.load();
  $("viewer").hidden = true;
  document.body.style.overflow = "";
  if (vPushed && !fromRoute) { vPushed = false; history.back(); }
  vPushed = false;
}

function show(i) {
  if (i < 0 || i >= S.media.length) return;
  vIdx = i;
  const it = S.media[i];
  const img = $("vImg"), vid = $("vVideo"), msg = $("vMsg");
  // albumy idu zo servera ako prve, takze pocet fotiek/videi = celkom - albumy
  const mediaTotal = S.done ? S.media.length : Math.max(S.media.length, S.total - $("albums").children.length);
  $("vTitle").textContent = `${it.info.title || it.info.name}  ·  ${i + 1} / ${mediaTotal}`;
  $("vCoverBtn").hidden = !S.isAdmin || !!S.share;
  $("vShareBtn").hidden = !S.isAdmin || !!S.share;
  $("vDownload").hidden = it.type !== "video" && !S.canDownload;
  $("vDownload").href = downloadUrl(it, false);
  $("vDownload").setAttribute("download", it.info.name);
  msg.hidden = true;
  if (it.type === "video") {
    img.hidden = true; img.removeAttribute("src");
    vid.hidden = false;
    vid.poster = thumbUrl(it, "large");
    vid.src = downloadUrl(it, true);
  } else {
    vid.pause(); vid.removeAttribute("src"); vid.hidden = true;
    img.hidden = false;
    img.src = thumbUrl(it, "large");
    img.alt = it.info.name;
  }
  $("vPrev").style.visibility = i > 0 ? "visible" : "hidden";
  $("vNext").style.visibility = i < S.media.length - 1 || !S.done ? "visible" : "hidden";
  renderInfo(it);
  // prednacitanie susedov
  for (const j of [i + 1, i - 1]) {
    const n = S.media[j];
    if (n && n.type !== "video") new Image().src = thumbUrl(n, "large");
  }
  // blizko konca nacitaj dalsiu stranu
  if (S.media.length - i < 10) loadMore();
}

$("vVideo").addEventListener("error", () => {
  const it = S.media[vIdx];
  if (!it || it.type !== "video" || !$("vVideo").getAttribute("src")) return;
  const m = $("vMsg");
  m.replaceChildren(el("span", null, t("The browser cannot play this video.") + " "));
  const a = el("a", null, t("Download original"));
  a.href = downloadUrl(it, false);
  m.append(a);
  m.hidden = false;
});

function renderInfo(it) {
  const box = $("vInfo");
  const ex = (it.additional && it.additional.photo_exif) || {};
  const vc = (it.additional && it.additional.video_codec) || {};
  const rows = [
    [t("File"), it.info.name],
    [t("Date"), it.info.takendate ? fmtDate(it.info.takendate) : ""],
    [t("Dimensions"), it.info.resolutionx ? `${it.info.resolutionx} × ${it.info.resolutiony}` : ""],
    [t("Size"), fmtSize(it.info.size)],
    [t("Duration"), it.type === "video" ? fmtDuration(it.info.duration) : ""],
    [t("Camera"), [ex.camera, ex.camera_model].filter(Boolean).join(" ")],
    [t("Lens"), ex.lens], [t("Exposure"), ex.exposure], [t("Aperture"), ex.aperture],
    ["ISO", ex.iso || ""], [t("Focal length"), ex.focal_length],
    [t("Codec"), it.type === "video" ? [vc.vcodec, vc.acodec].filter(Boolean).join(" / ") : ""],
    [t("Album"), (it.additional && it.additional.file_location || "").split("/").slice(0, -1).join("/")],
  ];
  const dl = el("dl");
  for (const [k, v] of rows) {
    if (!v) continue;
    dl.append(el("dt", null, k), el("dd", null, String(v)));
  }
  const gps = ex.gps || it.info.gps;
  if (gps && (gps.lat || gps.lng)) {
    const a = el("a", null, `${(+gps.lat).toFixed(5)}, ${(+gps.lng).toFixed(5)}`);
    a.href = `https://www.openstreetmap.org/?mlat=${gps.lat}&mlon=${gps.lng}#map=16/${gps.lat}/${gps.lng}`;
    a.target = "_blank"; a.rel = "noopener";
    dl.append(el("dt", null, t("Location")), el("dd").appendChild(a).parentNode);
  }
  if (it.info.place && !S.share) {
    const a = el("a", null, it.info.place);
    a.href = "#/g/" + encodeURIComponent(it.info.place_id);
    a.onclick = () => closeViewer(true);
    const dd = el("dd"); dd.append(a);
    dl.append(el("dt", null, t("Place")), dd);
  }
  const tbox = el("div", "item-tags");
  const cbox = el("div", "comments");
  box.replaceChildren(dl, tbox, cbox);
  loadItemTags(it, tbox);
  loadComments(it, cbox);
}

// ---------- tagy pri fotke ----------
let tagNames = null;
async function loadItemTags(it, box) {
  let tags = [], people = [];
  try {
    const d = await call("photo.php", "SYNO.PhotoStation.Photo", "getinfo", { id: it.id, additional: "tags" });
    tags = (d[0] && d[0].info.tags) || [];
    people = (d[0] && d[0].info.people) || [];
  } catch (e) { return; }
  if (S.media[vIdx] !== it) return;
  box.replaceChildren();
  if (people.length) {
    box.append(el("h4", null, t("In this photo")));
    const pc = el("div", "chips");
    for (const p of people) {
      const c = el("span", "chip person");
      const a = el("a", null, p.name);
      a.href = S.share ? "#" : "#/g/" + encodeURIComponent(p.id);
      a.onclick = () => closeViewer(true);
      c.append(a);
      pc.append(c);
    }
    box.append(pc);
  }
  if (!tags.length && !S.isAdmin) return;
  box.append(el("h4", null, t("Tags")));
  const chips = el("div", "chips");
  for (const tg of tags) {
    const c = el("span", "chip");
    const a = el("a", null, tg.name);
    a.href = S.share ? "#" : "#/g/" + encodeURIComponent(tg.id);
    a.onclick = () => closeViewer(true);
    c.append(a);
    if (S.isAdmin) {
      const x = el("button", "x", "×"); x.type = "button"; x.title = t("Remove tag");
      x.onclick = async () => { await adminPost("tag_remove", { path: it.additional.file_location, tag: tg.id }); loadItemTags(it, box); };
      c.append(x);
    }
    chips.append(c);
  }
  box.append(chips);
  if (!S.isAdmin) return;
  if (!tagNames) {
    try { tagNames = (await (await fetch(BASE + "/api/admin/tag_names", { credentials: "same-origin" })).json()).tags; } catch (e) { tagNames = []; }
  }
  const f = el("form", "tag-form");
  const inp = el("input"); inp.placeholder = t("Add tag"); inp.setAttribute("list", "tagList"); inp.maxLength = 64;
  let dl = $("tagList");
  if (!dl) { dl = el("datalist"); dl.id = "tagList"; document.body.append(dl); }
  dl.replaceChildren(...tagNames.map((n) => { const o = el("option"); o.value = n; return o; }));
  f.append(inp);
  f.onsubmit = async (e) => {
    e.preventDefault();
    const name = inp.value.trim();
    if (!name) return;
    if (await adminPost("tag_add", { path: it.additional.file_location, name })) {
      if (!tagNames.includes(name)) tagNames.push(name);
      loadItemTags(it, box);
    }
  };
  box.append(f);
}

async function adminPost(op, body) {
  const r = await fetch(BASE + "/api/admin/" + op, { method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-Lang": LANG }, body: JSON.stringify(body) });
  if (!r.ok) { alert(((await r.json().catch(() => ({}))).error) || t("Error")); return false; }
  return true;
}

// ---------- komentare ----------
async function loadComments(it, box) {
  let list = [];
  try { list = (await call("comment.php", "SYNO.PhotoStation.Comment", "list", { id: it.id })).comments; }
  catch (e) { return; }
  if (S.media[vIdx] !== it) return;
  $("vInfoBtn").textContent = list.length ? `Info · ${list.length}` : "Info";
  box.replaceChildren(el("h4", null, list.length ? t("Comments ({n})", { n: list.length }) : t("Comments")));
  for (const c of list) {
    const row = el("div", "cmt");
    const head = el("div", "cmt-h");
    head.append(el("strong", null, c.name), el("span", "muted", " " + fmtDate(c.date)));
    if (S.isAdmin) {
      const x = el("button", "x", "×");
      x.type = "button"; x.title = t("Delete comment");
      x.onclick = async () => {
        if (!confirm(t("Delete the comment?"))) return;
        const r = await fetch(BASE + "/api/admin/comment_delete", { method: "POST", credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-Lang": LANG }, body: JSON.stringify({ id: c.id }) });
        if (r.ok) loadComments(it, box);
      };
      head.append(x);
    }
    row.append(head, el("p", null, c.comment));
    box.append(row);
  }
  if (!S.canComment) {
    if (!list.length) box.append(el("p", "muted", t("No comments yet.")));
    return;
  }
  const f = el("form", "cmt-form");
  if (!S.user) {
    const n = el("input"); n.name = "name"; n.placeholder = t("Your name"); n.required = true; n.maxLength = 64;
    f.append(n);
  }
  const ta = el("textarea"); ta.name = "comment"; ta.rows = 2; ta.placeholder = t("Write a comment"); ta.required = true; ta.maxLength = 2000;
  const b = el("button", "primary", t("Add")); b.type = "submit";
  f.append(ta, b);
  f.onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(f);
    try {
      await call("comment.php", "SYNO.PhotoStation.Comment", "create",
        { id: it.id, name: fd.get("name") || "", email: "", comment: fd.get("comment") });
      loadComments(it, box);
    } catch (err) {
      alert(err.code === 493 ? t("Too many comments, try again later.") : t("The comment could not be saved."));
    }
  };
  box.append(f);
}

async function next() {
  if (vIdx < S.media.length - 1) show(vIdx + 1);
  else if (!S.done) { await loadMore(); if (vIdx < S.media.length - 1) show(vIdx + 1); }
}
const prev = () => show(vIdx - 1);

$("vCoverBtn").onclick = () => {
  const it = S.media[vIdx];
  const rel = it && it.additional && it.additional.file_location;
  if (rel) Admin.setCover(rel);
};
$("vShareBtn").onclick = () => {
  const it = S.media[vIdx];
  const rel = it && it.additional && it.additional.file_location;
  if (rel) Admin.share(rel, it.type);
};
$("vNext").onclick = next;
$("vPrev").onclick = prev;
$("vClose").onclick = () => closeViewer(false);
$("vInfoBtn").onclick = () => { $("vInfo").hidden = !$("vInfo").hidden; store("info", $("vInfo").hidden ? "0" : "1"); };
$("vInfo").hidden = store("info") !== "1";
addEventListener("popstate", () => { if (!$("viewer").hidden) { vPushed = false; closeViewer(true); } });
addEventListener("keydown", (e) => {
  if ($("viewer").hidden || e.target.tagName === "INPUT") return;
  if (e.key === "ArrowRight") next();
  else if (e.key === "ArrowLeft") prev();
  else if (e.key === "Escape") closeViewer(false);
  else if (e.key === "i") $("vInfoBtn").click();
});
let tx = null, ty = null;
$("vStage").addEventListener("touchstart", (e) => { tx = e.touches[0].clientX; ty = e.touches[0].clientY; }, { passive: true });
$("vStage").addEventListener("touchend", (e) => {
  if (tx == null) return;
  const dx = e.changedTouches[0].clientX - tx, dy = e.changedTouches[0].clientY - ty;
  tx = null;
  if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.5) (dx < 0 ? next : prev)();
  else if (dy > 90 && Math.abs(dy) > Math.abs(dx) * 1.5) closeViewer(false);
});
$("vImg").addEventListener("click", (e) => {
  const r = e.target.getBoundingClientRect();
  (e.clientX - r.left < r.width / 3 ? prev : next)();
});

// ---------- start ----------
async function loadInfo() {
  try {
    const info = await call("info.php", "SYNO.PhotoStation.Info", "getinfo");
    S.title = info.title || t("Photos");
    S.infoDownload = S.canDownload = info.allow_download_orig !== false;
    S.hideSearch = !!info.hide_search;
    $("brand").textContent = S.title;
    document.title = S.title;
    document.querySelector('.tabs a[data-tab="timeline"]').hidden = !!info.disable_timeline;
    $("searchForm").hidden = S.hideSearch || !!S.share;
  } catch (e) { /* nic */ }
}

(async function init() {
  await loadInfo();
  try {
    const a = await call("auth.php", "SYNO.PhotoStation.Auth", "checkauth");
    S.user = a.username || "";
    S.isAdmin = !!a.is_admin;
    S.canComment = !!a.allow_comment;
  } catch (e) { S.user = ""; }
  renderUser();
  route();
})();
