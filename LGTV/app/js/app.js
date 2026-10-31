// SPDX-License-Identifier: GPL-3.0-or-later
"use strict";
// Screens of the TV app: address of the server, pairing code, albums and photos, viewer with slideshow, settings.
// Everything is ES5 (Chromium 38 on webOS 3.x). Keys come from ui.js; the server from api.js.

var APP_VERSION = "0.1.2";
var COLS = 6, TILE = 290, GAP = 16, STEP = TILE + GAP, ROWS_VISIBLE = 3, PAGE = 400;
var INTERVALS = [3, 5, 8, 12, 20, 30];
var STATE = { title: "", user: "", interval: 8, noTimeline: false, sortBy: "filename", sortDir: "asc" };

function loadPrefs() {
  STATE.user = store("ps_user") || "";
  STATE.title = store("ps_title") || "";
  var iv = parseInt(store("ps_interval") || "0", 10);
  if (iv > 0) STATE.interval = iv;
}

function itemTitle(it) {
  return (it && it.info && (it.info.title || it.info.name)) || (it && it.name) || "";
}

// a lost session (removed under Settings, TV) sends the TV back to a new code
function apiFailed(err) {
  if (err && err.code === "timeout") {
    API.sid = "";
    API.save();
    UI.reset(pairScreen(t("The session has ended, a new code is needed.")));
    return true;
  }
  return false;
}

// ---------------- address of the server ----------------
function setupScreen(message) {
  var node = el("div", "screen center");
  node.appendChild(el("div", "logo", "Picturestation"));
  var form = el("div", "form");
  form.appendChild(el("div", "label", t("Address of your Picturestation")));
  var input = el("input", "field");
  input.type = "text";
  input.value = API.server || "";
  input.setAttribute("autocapitalize", "off");
  input.setAttribute("autocorrect", "off");
  input.setAttribute("spellcheck", "false");
  form.appendChild(input);
  form.appendChild(el("div", "muted", t("For example photos.example.com or 192.168.1.10")));
  var btn = el("div", "btn", t("Connect"));
  form.appendChild(btn);
  var err = el("div", "err", message || "");
  form.appendChild(err);
  node.appendChild(form);

  var editing = false, busy = false;
  var focus = new FocusList([input, btn], function (i) { if (i === 0) edit(); else connect(); });
  focus.pointer();
  function edit() { editing = true; input.focus(); }
  input.addEventListener("focus", function () { editing = true; focus.set(0); }, false);
  input.addEventListener("blur", function () { editing = false; }, false);

  function connect() {
    if (busy) return;
    var cands = serverCandidates(input.value);
    if (!cands.length) { err.textContent = t("Address of your Picturestation"); return; }
    busy = true;
    btn.textContent = t("Connecting…");
    err.textContent = "";
    tryNext(0, cands);
  }
  function tryNext(i, cands) {
    if (i >= cands.length) {
      busy = false;
      btn.textContent = t("Connect");
      err.textContent = t("The server did not answer. Check the address and the network.");
      return;
    }
    API.server = cands[i];
    API.call("query.php", "SYNO.API.Info", "query", { query: "all" }, function (e, d) {
      if (e && e.code === "network") return tryNext(i + 1, cands);
      busy = false;
      btn.textContent = t("Connect");
      if (e || !d["SYNO.PhotoStation.Auth"]) { err.textContent = t("This is not a Picturestation server."); return; }
      API.sid = "";
      API.save();
      UI.reset(pairScreen());
    });
  }

  return {
    node: node,
    onKey: function (code) {
      if (editing) {
        if (code === KEY.OK) { input.blur(); editing = false; connect(); return true; }
        if (code === KEY.BACK || code === KEY.ESC) { input.blur(); editing = false; return true; }
        return false;  // typing goes to the input (the TV shows its keyboard)
      }
      return focus.key(code);
    }
  };
}

// ---------------- pairing code ----------------
function pairScreen(message) {
  var node = el("div", "screen center");
  node.appendChild(el("div", "logo", "Picturestation"));
  node.appendChild(el("div", "label", t("Enter this code in Picturestation")));
  var code = el("div", "code", "······");
  node.appendChild(code);
  node.appendChild(el("div", "muted", t("In a browser open the gallery, Settings, TV, and allow this code under your name.")));
  var wait = el("div", "wait", message || t("Waiting for approval…"));
  node.appendChild(wait);
  var btn = el("div", "btn", t("Change address"));
  node.appendChild(btn);
  var focus = new FocusList([btn], function () { UI.reset(setupScreen()); });
  focus.pointer();

  var token = "", timer = null, alive = true, note = message || "";
  function later(fn, ms) { if (timer) clearTimeout(timer); timer = setTimeout(fn, ms); }
  function getCode() {
    API.post("/api/tv/code", { name: deviceName() }, function (e, d) {
      if (!alive) return;
      if (e || !d.code) {
        wait.textContent = e && e.code === "network" ? t("Network error, trying again…") : t("The server did not give a code. Trying again…");
        return later(getCode, 5000);
      }
      token = d.token;
      code.textContent = d.code;
      wait.textContent = note || t("Waiting for approval…");
      note = "";
      later(poll, 3000);
    });
  }
  function poll() {
    API.post("/api/tv/poll", { token: token }, function (e, d) {
      if (!alive) return;
      if (e) { wait.textContent = t("Network error, trying again…"); return later(poll, 5000); }
      if (d.status === "ok") {
        API.sid = d.sid;
        API.save();
        STATE.user = d.username || "";
        STATE.title = d.title || "";
        store("ps_user", STATE.user);
        store("ps_title", STATE.title);
        UI.reset(startScreen());
        return;
      }
      if (d.status === "pending") return later(poll, 3000);
      note = t("The code has expired, here is a new one.");
      getCode();
    });
  }
  return {
    node: node,
    enter: getCode,
    leave: function () { alive = false; if (timer) clearTimeout(timer); },
    onKey: function (c) { return focus.key(c); }
  };
}

// ---------------- start with a saved session ----------------
function startScreen() {
  var node = el("div", "screen center");
  node.appendChild(el("div", "logo", "Picturestation"));
  var msg = el("div", "wait", t("Connecting…"));
  node.appendChild(msg);
  var timer = null, alive = true;
  function retry() { msg.textContent = t("Network error, trying again…"); timer = setTimeout(go, 5000); }
  function go() {
    API.call("info.php", "SYNO.PhotoStation.Info", "getinfo", {}, function (e, d) {
      if (!alive) return;
      if (e) { if (!apiFailed(e)) retry(); return; }
      STATE.title = d.title || STATE.title;
      STATE.noTimeline = !!d.disable_timeline;
      STATE.sortBy = d.sort_by || "filename";
      STATE.sortDir = d.sort_direction || "asc";
      store("ps_title", STATE.title);
      API.call("auth.php", "SYNO.PhotoStation.Auth", "checkauth", {}, function (e2, a) {
        if (!alive) return;
        if (e2) { if (!apiFailed(e2)) retry(); return; }
        if (!a.username) {
          API.sid = "";
          API.save();
          UI.reset(pairScreen(t("The session has ended, a new code is needed.")));
          return;
        }
        STATE.user = a.username;
        store("ps_user", STATE.user);
        UI.reset(browseScreen(null));
      });
    });
  }
  return {
    node: node,
    enter: go,
    leave: function () { alive = false; if (timer) clearTimeout(timer); },
    onKey: function (code) {
      if (code === KEY.BACK || code === KEY.ESC) { UI.reset(setupScreen()); return true; }
      return false;
    }
  };
}

// ---------------- albums and photos ----------------
// where: null = root of the gallery, {latest: true} = newest photos, or an album item
function browseScreen(where) {
  var node = el("div", "screen");
  var head = el("div", "head");
  var title = el("div", "title");
  var count = el("div", "count");
  head.appendChild(title);
  head.appendChild(count);
  node.appendChild(head);
  var wrap = el("div", "gridwrap");
  var grid = el("div", "grid");
  wrap.appendChild(grid);
  node.appendChild(wrap);
  var msg = el("div", "message", t("Loading…"));
  node.appendChild(msg);

  var isRoot = !where, latest = !!(where && where.latest);
  title.textContent = isRoot ? (STATE.title || "Picturestation") : (latest ? t("Latest photos") : itemTitle(where));

  var entries = [];      // {kind, item, tile, img, src, media}
  var media = [];        // photos and videos in order, for the viewer
  var mediaIndex = [];   // media index -> entries index
  var total = 0, loaded = 0, loading = false, focus = -1, scrollRow = 0, alive = true, pendingMore = null, failed = false;

  function duration(item) {
    var s = Math.round((item.info && item.info.duration) || 0);
    return s ? Math.floor(s / 60) + ":" + (s % 60 < 10 ? "0" : "") + (s % 60) : "video";
  }

  function addEntry(kind, item) {
    var i = entries.length;
    var tile = el("div", "tile " + kind);
    tile.style.left = (i % COLS) * STEP + "px";
    tile.style.top = Math.floor(i / COLS) * STEP + "px";
    var ent = { kind: kind, item: item, tile: tile, img: null, src: "" };
    if (kind === "latest" || kind === "settings") {
      tile.className += " special";
      tile.appendChild(el("div", "glyph" + (kind === "settings" ? " gear" : "")));
      tile.appendChild(el("div", null, kind === "latest" ? t("Latest photos") : t("Settings")));
    } else {
      if (item.thumbnail_status && item.thumbnail_status !== "default") ent.src = API.thumb(item, "small");
      else tile.appendChild(el("div", "ph"));
      if (kind === "album") tile.appendChild(el("div", "cap", itemTitle(item)));
      if (kind === "video") tile.appendChild(el("div", "badge", duration(item)));
    }
    if (kind === "photo" || kind === "video") { ent.media = media.length; mediaIndex.push(i); media.push(item); }
    tile.addEventListener("mouseover", function () { setFocusIdx(i); }, false);
    tile.addEventListener("click", function () { setFocusIdx(i); activate(); }, false);
    entries.push(ent);
    grid.appendChild(tile);
  }

  function load() {
    if (loading || failed) return;
    loading = true;
    var cb = function (e, d) {
      loading = false;
      if (!alive) return;
      if (e) {
        if (apiFailed(e)) return;
        if (e.code === "network") { msg.textContent = t("Network error, trying again…"); msg.removeAttribute("hidden"); setTimeout(load, 5000); return; }
        failed = true;
        msg.textContent = e.code === "api" && e.error === 418 ? t("This album needs a password.") : t("The photo could not be loaded.");
        msg.removeAttribute("hidden");
        return;
      }
      var items = d.items || [];
      if (loaded === 0 && isRoot && !STATE.noTimeline) addEntry("latest", null);
      for (var i = 0; i < items.length; i++) {
        addEntry(items[i].type === "album" ? "album" : (items[i].type === "video" ? "video" : "photo"), items[i]);
      }
      loaded += items.length;
      total = Math.max(d.total || 0, loaded);
      if (loaded >= total && isRoot) addEntry("settings", null);
      msg.setAttribute("hidden", "");
      if (!entries.length) { msg.textContent = t("No photos here."); msg.removeAttribute("hidden"); }
      count.textContent = tn(total, "{n} item", "{n} items");
      if (focus < 0 && entries.length) setFocusIdx(0);
      loadVisible();
      if (pendingMore) { var f = pendingMore; pendingMore = null; f(); }
    };
    if (latest) {
      API.call("photo.php", "SYNO.PhotoStation.Photo", "list", { type: "photo,video", offset: loaded, limit: PAGE,
        sort_by: "takendate", sort_direction: "desc", additional: "thumb_size,video_codec" }, cb);
    } else {
      API.call("album.php", "SYNO.PhotoStation.Album", "list", { id: isRoot ? null : where.id, type: "album,photo,video",
        offset: loaded, limit: PAGE, sort_by: STATE.sortBy, sort_direction: STATE.sortDir,
        additional: "thumb_size,video_codec" }, cb);
    }
  }

  function setFocusIdx(i) {
    if (i < 0 || i >= entries.length || i === focus) return;
    if (focus >= 0) setFocus(entries[focus].tile, false);
    focus = i;
    setFocus(entries[i].tile, true);
    var row = Math.floor(i / COLS);
    if (row < scrollRow) scrollRow = row;
    else if (row > scrollRow + ROWS_VISIBLE - 1) scrollRow = row - ROWS_VISIBLE + 1;
    var y = -scrollRow * STEP;
    grid.style.webkitTransform = "translateY(" + y + "px)";
    grid.style.transform = "translateY(" + y + "px)";
    loadVisible();
    if (loaded < total && i >= entries.length - COLS * 2) load();
  }

  // thumbnails only around the visible rows; far away ones are dropped again (the TV has little memory)
  function loadVisible() {
    var first = Math.max(0, (scrollRow - 1) * COLS), last = Math.min(entries.length, (scrollRow + ROWS_VISIBLE + 1) * COLS);
    var far = COLS * 6;
    for (var i = 0; i < entries.length; i++) {
      var e = entries[i];
      if (!e.src) continue;
      if (i >= first && i < last) {
        if (!e.img) {
          e.img = el("img");
          e.img.onerror = function () { this.style.visibility = "hidden"; };
          e.img.src = e.src;
          e.tile.insertBefore(e.img, e.tile.firstChild);
        }
      } else if (e.img && (i < first - far || i >= last + far)) {
        e.tile.removeChild(e.img);
        e.img = null;
      }
    }
  }

  function activate() {
    var e = entries[focus];
    if (!e) return;
    if (e.kind === "latest") UI.push(browseScreen({ latest: true }));
    else if (e.kind === "settings") UI.push(settingsScreen());
    else if (e.kind === "album") UI.push(browseScreen(e.item));
    else UI.push(viewerScreen(self, e.media, false));
  }

  var self = {
    node: node,
    media: media,
    enter: load,
    leave: function () { alive = false; },
    hasMore: function () { return loaded < total; },
    more: function (cb) { if (loaded < total && alive) { pendingMore = cb; load(); } else cb(); },
    focusMedia: function (m) { if (mediaIndex[m] !== undefined) setFocusIdx(mediaIndex[m]); },
    onKey: function (code) {
      if (!entries.length) return false;
      if (code === KEY.LEFT) { setFocusIdx(focus - 1); return true; }
      if (code === KEY.RIGHT) { setFocusIdx(focus + 1); return true; }
      if (code === KEY.UP) { if (focus >= COLS) setFocusIdx(focus - COLS); return true; }
      if (code === KEY.DOWN) { setFocusIdx(Math.min(entries.length - 1, focus + COLS)); return true; }
      if (code === KEY.CH_UP) { setFocusIdx(Math.max(0, focus - COLS * ROWS_VISIBLE)); return true; }
      if (code === KEY.CH_DOWN) { setFocusIdx(Math.min(entries.length - 1, focus + COLS * ROWS_VISIBLE)); return true; }
      if (code === KEY.OK) { activate(); return true; }
      if ((code === KEY.PLAY || code === KEY.RED) && media.length) {  // the Magic Remote has no Play key
        var m = entries[focus].media;
        UI.push(viewerScreen(self, m === undefined ? 0 : m, true));
        return true;
      }
      return false;
    }
  };
  return self;
}

// ---------------- viewer and slideshow ----------------
function viewerScreen(browse, index, autoplay) {
  var node = el("div", "screen viewer");
  var stage = el("div");
  node.appendChild(stage);
  var spinner = el("div", "loading");
  node.appendChild(spinner);
  var counter = el("div", "corner counter");
  node.appendChild(counter);
  var playTag = el("div", "corner play hide");  // a play triangle while the slideshow runs
  playTag.appendChild(el("span", "tri"));
  node.appendChild(playTag);
  var ov = el("div", "ov");
  var name = el("div", "name"), meta = el("div", "meta");
  ov.appendChild(name);
  ov.appendChild(meta);
  ov.appendChild(el("div", "hint", t("OK: details · Red: slideshow · Green: pause · Back: close")));
  node.appendChild(ov);

  var list = browse.media;
  var cur = -1, playing = false, timer = null, hideTimer = null, alive = true, current = null, preloads = [];

  function clearStage() {
    if (timer) { clearTimeout(timer); timer = null; }
    if (current) {
      if (current.tagName === "VIDEO") { try { current.pause(); current.removeAttribute("src"); current.load(); } catch (e) { /* gone */ } }
      if (current.parentNode) current.parentNode.removeChild(current);
      current = null;
    }
  }

  function preload(i) {
    if (i < 0 || i >= list.length || list[i].type === "video") return;
    var im = new Image();
    im.src = API.thumb(list[i], "large");
    preloads.push(im);
    if (preloads.length > 4) preloads.shift();
  }

  function schedule() {
    if (timer) clearTimeout(timer);
    timer = null;
    if (!playing || !alive || document.hidden) return;
    timer = setTimeout(function () { show(cur + 1); }, STATE.interval * 1000);
  }

  function show(i) {
    if (!alive) return;
    if (i < 0) i = list.length - 1;
    if (i >= list.length) {
      if (browse.hasMore()) { browse.more(function () { show(i < list.length ? i : 0); }); return; }
      i = 0;
    }
    cur = i;
    var item = list[i];
    clearStage();
    spinner.removeAttribute("hidden");
    if (item.type === "video") {
      var v = el("video", "full");
      v.setAttribute("autoplay", "");
      v.addEventListener("playing", function () { spinner.setAttribute("hidden", ""); }, false);
      v.addEventListener("ended", function () { if (playing) show(cur + 1); }, false);
      v.addEventListener("error", function () {
        spinner.setAttribute("hidden", "");
        UI.toast(t("The video could not be played."));
        if (playing) timer = setTimeout(function () { show(cur + 1); }, 2000);
      }, false);
      v.src = API.video(item);
      stage.appendChild(v);
      current = v;
      var vc = item.additional && item.additional.video_codec;
      if (vc && (vc.rotation === 90 || vc.rotation === 180 || vc.rotation === 270) && vc.tv_version !== "ready") {
        UI.toast(t("The upright copy of this video is being prepared; playing the original for now."), 6000);
      }
    } else {
      var im = el("img", "full");
      im.onload = function () { spinner.setAttribute("hidden", ""); schedule(); };
      im.onerror = function () {
        spinner.setAttribute("hidden", "");
        UI.toast(t("The photo could not be loaded."));
        schedule();
      };
      im.src = API.thumb(item, "large");
      stage.appendChild(im);
      current = im;
      preload(i + 1);
      preload(i - 1);
    }
    counter.textContent = (i + 1) + " / " + list.length + (browse.hasMore() ? "+" : "");
    name.textContent = itemTitle(item);
    meta.textContent = fmtDate(item.info && item.info.takendate);
    showOverlay();
    browse.focusMedia(i);
  }

  function showOverlay() {
    setFocus(ov, false);
    ov.className = "ov";
    counter.className = "corner counter";
    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = setTimeout(hideOverlay, 3500);
  }
  function hideOverlay() {
    ov.className = "ov hide";
    counter.className = "corner counter hide";
  }
  function toggleOverlay() {
    if (ov.className.indexOf("hide") >= 0) showOverlay(); else { if (hideTimer) clearTimeout(hideTimer); hideOverlay(); }
  }

  function setPlaying(on) {
    playing = on;
    playTag.className = "corner play" + (on ? "" : " hide");
    if (current && current.tagName === "VIDEO") { if (on) current.play(); else current.pause(); }
    if (on) schedule(); else if (timer) { clearTimeout(timer); timer = null; }
  }

  function seek(delta) {
    if (current && current.tagName === "VIDEO") {
      try { current.currentTime = Math.max(0, current.currentTime + delta); } catch (e) { /* not seekable */ }
      return true;
    }
    return false;
  }

  // the Magic Remote pointer: left third = previous, right third = next, middle = details; wheel = next/previous
  node.addEventListener("click", function (e) {
    if (e.clientX < 500) show(cur - 1); else if (e.clientX > 1420) show(cur + 1); else toggleOverlay();
  }, false);
  node.addEventListener("mousemove", function () { if (ov.className.indexOf("hide") >= 0) showOverlay(); }, false);
  node.addEventListener("wheel", function (e) { show(cur + (e.deltaY > 0 ? 1 : -1)); e.preventDefault(); }, false);
  function onVisibility() { if (!document.hidden) schedule(); }
  document.addEventListener("visibilitychange", onVisibility, false);

  return {
    node: node,
    enter: function () { show(index); if (autoplay) setPlaying(true); },
    leave: function () {
      alive = false;
      clearStage();
      if (hideTimer) clearTimeout(hideTimer);
      document.removeEventListener("visibilitychange", onVisibility, false);
    },
    onKey: function (code) {
      if (code === KEY.LEFT || code === KEY.REW && !seek(-10)) { show(cur - 1); return true; }
      if (code === KEY.RIGHT || code === KEY.FF && !seek(10)) { show(cur + 1); return true; }
      if (code === KEY.REW || code === KEY.FF) return true;
      if (code === KEY.OK) {
        if (current && current.tagName === "VIDEO") { if (current.paused) current.play(); else current.pause(); }
        toggleOverlay();
        return true;
      }
      if (code === KEY.PLAY || code === KEY.RED) { setPlaying(!playing); return true; }
      if (code === KEY.PAUSE || code === KEY.STOP || code === KEY.GREEN) { setPlaying(false); return true; }
      if (code === KEY.UP || code === KEY.DOWN) { toggleOverlay(); return true; }
      return false;
    }
  };
}

// ---------------- settings ----------------
function settingsScreen() {
  var node = el("div", "screen center");
  node.appendChild(el("div", "logo", t("Settings")));
  var rows = el("div", "rows");
  function row(label, value, act) {
    var r = el("div", "row" + (act ? " act" : ""));
    r.appendChild(el("div", "k", label));
    r.appendChild(el("div", "v", value));
    rows.appendChild(r);
    return r;
  }
  function intervalText() { return tn(STATE.interval, "{n} second", "{n} seconds"); }
  var rServer = row(t("Server"), API.server, false);
  var rUser = row(t("Signed in as"), STATE.user || "–", false);
  var rInt = row(t("Slideshow interval"), "◀ " + intervalText() + " ▶", true);
  var rOut = row(t("Sign out of this TV"), "", true);
  var rSrv = row(t("Change server"), "", true);
  var rVer = row(t("App version"), APP_VERSION, false);
  node.appendChild(rows);

  function changeInterval(d) {
    var k = INTERVALS.indexOf(STATE.interval);
    if (k < 0) k = 2;
    k = (k + d + INTERVALS.length) % INTERVALS.length;
    STATE.interval = INTERVALS[k];
    store("ps_interval", STATE.interval);
    rInt.lastChild.textContent = "◀ " + intervalText() + " ▶";
  }
  function signOut() {
    API.call("auth.php", "SYNO.PhotoStation.Auth", "logout", {}, function () { /* the server forgets the TV */ });
    API.sid = "";
    API.save();
    STATE.user = "";
    store("ps_user", "");
    UI.reset(pairScreen());
  }
  var focus = new FocusList([rServer, rUser, rInt, rOut, rSrv, rVer], function (i) {
    if (i === 2) changeInterval(1);
    else if (i === 3) signOut();
    else if (i === 4) UI.reset(setupScreen());
  });
  focus.pointer();
  return {
    node: node,
    onKey: function (code) {
      if (focus.index === 2 && (code === KEY.LEFT || code === KEY.RIGHT)) { changeInterval(code === KEY.RIGHT ? 1 : -1); return true; }
      return focus.key(code);
    }
  };
}

// ---------------- start ----------------
function main() {
  initLang();
  UI.init();
  API.load();
  loadPrefs();
  if (!API.server) UI.push(setupScreen());
  else if (!API.sid) UI.push(pairScreen());
  else UI.push(startScreen());
}
document.addEventListener("DOMContentLoaded", main, false);
