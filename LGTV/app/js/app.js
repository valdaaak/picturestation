// SPDX-License-Identifier: GPL-3.0-or-later
"use strict";
// Screens of the TV app: address of the server, pairing code, albums and photos, viewer with slideshow, settings.
// Everything is ES5 (Chromium 38 on webOS 3.x). Keys come from ui.js; the server from api.js.

var APP_VERSION = "0.1.5";
var COLS = 6, TILE = 290, GAP = 16, STEP = TILE + GAP, ROWS_VISIBLE = 3, PAGE = 400;
var INTERVALS = [3, 5, 8, 12, 20, 30];
// pendingBase: the gallery address the setup and pairing screens work on
var STATE = { title: "", user: "", interval: 8, noTimeline: false, sortBy: "filename", sortDir: "asc", pendingBase: "" };

function loadPrefs() {
  var g = API.current();
  STATE.user = g ? g.user : "";
  STATE.title = g ? g.title : "";
  var iv = parseInt(store("ps_interval") || "0", 10);
  if (iv > 0) STATE.interval = iv;
}

// ---------------- galleries ----------------
// Setup and Pair can be left when a screen lies below them (adding a gallery) or another paired gallery exists
function otherGallery() {
  for (var i = 0; i < API.galleries.length; i++) {
    var g = API.galleries[i];
    if (g.sid && g.base !== STATE.pendingBase) return i;
  }
  return -1;
}
function canCancel() { return UI.stack.length > 1 || otherGallery() >= 0; }
function cancelSetup() {
  if (UI.stack.length > 1) { UI.pop(); return; }
  var i = otherGallery();
  if (i >= 0) switchGallery(i);
}
// the screen on top gives way to another (Setup -> Pair), below it the rest of the stack stays
function swapTo(screen) {
  if (UI.stack.length > 1) { UI.pop(); UI.push(screen); } else UI.reset(screen);
}
function changeAddress() { swapTo(setupScreen()); }
function switchGallery(i) {
  API.use(i);
  API.save();
  loadPrefs();
  UI.reset(startScreen());
}
function removeGallery(i) {
  var g = API.galleries[i];
  if (!g) return;
  if (g.sid) API.call("auth.php", "SYNO.PhotoStation.Auth", "logout", {}, function () { /* the server forgets the TV */ }, { base: g.base, sid: g.sid });
  var wasActive = i === API.active;
  API.remove(i);
  API.save();
  if (!API.galleries.length) { STATE.pendingBase = ""; UI.reset(setupScreen()); }
  else if (wasActive) switchGallery(API.active);
  else { loadPrefs(); UI.pop(); UI.push(settingsScreen()); }
}

function itemTitle(it) {
  return (it && it.info && (it.info.title || it.info.name)) || (it && it.name) || "";
}

// a lost session (removed under Settings, TV) sends the TV back to a new code
function apiFailed(err) {
  if (err && err.code === "timeout") {
    API.setSid("");
    API.save();
    STATE.pendingBase = API.server;
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
  input.value = STATE.pendingBase || "";
  input.setAttribute("autocapitalize", "off");
  input.setAttribute("autocorrect", "off");
  input.setAttribute("spellcheck", "false");
  form.appendChild(input);
  form.appendChild(el("div", "muted", t("For example photos.example.com or 192.168.1.10")));
  var btn = el("div", "btn", t("Connect"));
  form.appendChild(btn);
  var err = el("div", "err", message || "");
  form.appendChild(err);
  var cancel = null;
  if (canCancel()) { cancel = el("div", "btn", t("Cancel")); form.appendChild(cancel); }
  node.appendChild(form);

  var editing = false, busy = false;
  var focus = new FocusList(cancel ? [input, btn, cancel] : [input, btn], function (i) {
    if (i === 0) edit(); else if (i === 1) connect(); else cancelSetup();
  });
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
    var base = cands[i];
    API.call("query.php", "SYNO.API.Info", "query", { query: "all" }, function (e, d) {
      if (e && e.code === "network") return tryNext(i + 1, cands);
      busy = false;
      btn.textContent = t("Connect");
      if (e || !d["SYNO.PhotoStation.Auth"]) { err.textContent = t("This is not a Picturestation server."); return; }
      STATE.pendingBase = base;
      swapTo(pairScreen());
    }, { base: base, sid: "" });
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
  node.appendChild(el("div", "muted", STATE.pendingBase.replace(/^https:\/\//, "")));
  node.appendChild(el("div", "muted", t("In a browser open the gallery, Settings, TV, and allow this code under your name.")));
  var wait = el("div", "wait", message || t("Waiting for approval…"));
  node.appendChild(wait);
  var btn = el("div", "btn", t("Change address"));
  node.appendChild(btn);
  var btns = [btn];
  if (canCancel()) { var cancel = el("div", "btn", t("Cancel")); node.appendChild(cancel); btns.push(cancel); }
  var focus = new FocusList(btns, function (i) { if (i === 0) changeAddress(); else cancelSetup(); });
  focus.pointer();

  var base = STATE.pendingBase;
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
    }, { base: base, sid: "" });
  }
  function poll() {
    API.post("/api/tv/poll", { token: token }, function (e, d) {
      if (!alive) return;
      if (e) { wait.textContent = t("Network error, trying again…"); return later(poll, 5000); }
      if (d.status === "ok") {
        // the gallery joins the list (or replaces its old entry) and becomes the active one
        API.use(API.upsert({ base: base, sid: d.sid, user: d.username || "", title: d.title || "" }));
        API.save();
        loadPrefs();
        UI.reset(startScreen());
        return;
      }
      if (d.status === "pending") return later(poll, 3000);
      note = t("The code has expired, here is a new one.");
      getCode();
    }, { base: base, sid: "" });
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
    var g = API.current();
    if (!g) { STATE.pendingBase = ""; UI.reset(setupScreen()); return; }
    STATE.pendingBase = g.base;
    if (!g.sid) { UI.reset(pairScreen()); return; }
    API.call("info.php", "SYNO.PhotoStation.Info", "getinfo", {}, function (e, d) {
      if (!alive) return;
      if (e) { if (!apiFailed(e)) retry(); return; }
      STATE.title = d.title || STATE.title;
      STATE.noTimeline = !!d.disable_timeline;
      STATE.sortBy = d.sort_by || "filename";
      STATE.sortDir = d.sort_direction || "asc";
      g.title = STATE.title;
      API.save();
      API.call("auth.php", "SYNO.PhotoStation.Auth", "checkauth", {}, function (e2, a) {
        if (!alive) return;
        if (e2) { if (!apiFailed(e2)) retry(); return; }
        if (!a.username) {
          API.setSid("");
          API.save();
          UI.reset(pairScreen(t("The session has ended, a new code is needed.")));
          return;
        }
        STATE.user = a.username;
        g.user = STATE.user;
        API.save();
        UI.reset(browseScreen(null));
      });
    });
  }
  return {
    node: node,
    enter: go,
    leave: function () { alive = false; if (timer) clearTimeout(timer); },
    onKey: function (code) {
      if (code === KEY.BACK || code === KEY.ESC) { changeAddress(); return true; }
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
    if (kind === "latest" || kind === "settings" || kind === "gallery") {
      tile.className += " special" + (kind === "gallery" ? " gallery" : "");
      tile.appendChild(el("div", "glyph" + (kind === "settings" ? " gear" : "")));
      var label = kind === "latest" ? t("Latest photos") : (kind === "settings" ? t("Settings")
        : (item.title || item.base.replace(/^https:\/\//, "")));   // another paired gallery
      tile.appendChild(el("div", null, label));
    } else {
      if (item.thumbnail_status && item.thumbnail_status !== "default") ent.src = API.thumb(item, "small");
      else tile.appendChild(el("div", "ph"));
      if (kind === "album") tile.appendChild(el("div", "cap", itemTitle(item)));
      if (kind === "video") tile.appendChild(el("div", "badge", duration(item)));
      if (kind === "photo" && item.info && item.info.live) tile.appendChild(el("div", "badge", "LIVE"));
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
      if (loaded === 0 && isRoot) {
        for (var gi = 0; gi < API.galleries.length; gi++) {
          if (gi !== API.active) addEntry("gallery", { index: gi, title: API.galleries[gi].title, base: API.galleries[gi].base });
        }
      }
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

  // Live Photo: when the focus rests on its tile, the motion plays once, muted. The short wait keeps a quick run
  // over the grid from downloading many clips; only one plays at a time.
  var liveTimer = null, liveVid = null, paused = false;   // paused: another screen (the viewer) is on top
  function stopLive() {
    if (liveTimer) { clearTimeout(liveTimer); liveTimer = null; }
    if (liveVid) {
      try { liveVid.pause(); liveVid.removeAttribute("src"); liveVid.load(); } catch (e) { /* gone */ }
      if (liveVid.parentNode) liveVid.parentNode.removeChild(liveVid);
      liveVid = null;
    }
  }
  function startLive(e) {
    stopLive();
    if (paused || !e || e.kind !== "photo" || !e.item.info || !e.item.info.live) return;
    liveTimer = setTimeout(function () {
      liveTimer = null;
      var v = el("video", "live");
      v.muted = true;
      v.setAttribute("muted", "");
      v.setAttribute("autoplay", "");
      v.addEventListener("playing", function () { v.className = "live on"; }, false);
      v.addEventListener("ended", stopLive, false);
      v.addEventListener("error", stopLive, false);
      v.src = API.video({ id: e.item.info.live });
      e.tile.appendChild(v);
      liveVid = v;
    }, 300);
  }

  function setFocusIdx(i) {
    if (i < 0 || i >= entries.length || i === focus) return;
    if (focus >= 0) setFocus(entries[focus].tile, false);
    focus = i;
    setFocus(entries[i].tile, true);
    startLive(entries[i]);
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
    stopLive();
    if (e.kind === "latest") UI.push(browseScreen({ latest: true }));
    else if (e.kind === "gallery") switchGallery(e.item.index);
    else if (e.kind === "settings") UI.push(settingsScreen());
    else if (e.kind === "album") UI.push(browseScreen(e.item));
    else UI.push(viewerScreen(self, e.media, false));
  }

  var self = {
    node: node,
    media: media,
    enter: load,
    leave: function () { alive = false; stopLive(); },
    pause: function () { paused = true; stopLive(); },
    resume: function () { paused = false; },
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
  var playTag = el("div", "corner play hide");  // a play triangle while the slideshow runs, two bars when paused
  playTag.appendChild(el("span", "tri"));
  playTag.appendChild(el("span", "bars"));
  node.appendChild(playTag);
  var tagTimer = null;
  function showTag(state, ms) {
    // state: "playing" | "paused" | "" ; ms > 0 hides it again after that time
    if (tagTimer) { clearTimeout(tagTimer); tagTimer = null; }
    playTag.className = "corner play" + (state ? " " + state : " hide");
    if (state && ms) tagTimer = setTimeout(function () { playTag.className = "corner play hide"; }, ms);
  }
  var ov = el("div", "ov");
  var name = el("div", "name"), meta = el("div", "meta"), who = el("div", "who");
  ov.appendChild(name);
  ov.appendChild(meta);
  ov.appendChild(who);  // people on the photo (from Synology Photos) and the place
  var details = {};
  function fetchDetails(i, item) {
    function apply(info) {
      if (cur !== i) return;
      var parts = [];
      if (info.people && info.people.length) parts.push(info.people.map(function (p) { return p.name; }).join(", "));
      if (info.place) parts.push(info.place);
      who.textContent = parts.join("   ·   ");
    }
    if (details[item.id]) { apply(details[item.id]); return; }
    API.call("photo.php", "SYNO.PhotoStation.Photo", "getinfo", { id: item.id, additional: "tags" }, function (e, d) {
      if (e || !d || !d[0] || !d[0].info) return;
      details[item.id] = d[0].info;
      apply(d[0].info);
    });
  }
  ov.appendChild(el("div", "hint", t("OK: details · Red: slideshow · Green: pause · Back: close")));
  node.appendChild(ov);

  var list = browse.media;
  var cur = -1, playing = false, timer = null, hideTimer = null, alive = true, current = null, preloads = [];
  var firstShow = true, liveV = null;

  // Live Photo: the motion plays once over the photo when the viewer moves to it (arrows, slideshow), muted;
  // the photo opened from the grid only goes full screen (its motion played in the grid already)
  function stopLiveV() {
    if (!liveV) return;
    try { liveV.pause(); liveV.removeAttribute("src"); liveV.load(); } catch (e) { /* gone */ }
    if (liveV.parentNode) liveV.parentNode.removeChild(liveV);
    liveV = null;
  }
  function playLiveV(item) {
    stopLiveV();
    var v = el("video", "full live");
    v.muted = true;
    v.setAttribute("muted", "");
    v.setAttribute("autoplay", "");
    v.addEventListener("playing", function () { v.className = "full live on"; }, false);
    v.addEventListener("ended", stopLiveV, false);
    v.addEventListener("error", stopLiveV, false);
    v.src = API.video({ id: item.info.live });
    stage.appendChild(v);
    liveV = v;
  }

  function clearStage() {
    if (timer) { clearTimeout(timer); timer = null; }
    stopLiveV();
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
      im.onload = function () { spinner.setAttribute("hidden", ""); zoomStart(im); schedule(); };
      im.onerror = function () {
        spinner.setAttribute("hidden", "");
        UI.toast(t("The photo could not be loaded."));
        schedule();
      };
      im.src = API.thumb(item, "large");
      stage.appendChild(im);
      current = im;
      if (!firstShow && item.info && item.info.live) playLiveV(item);
      preload(i + 1);
      preload(i - 1);
    }
    firstShow = false;
    counter.textContent = (i + 1) + " / " + list.length + (browse.hasMore() ? "+" : "");
    name.textContent = itemTitle(item);
    meta.textContent = fmtDate(item.info && item.info.takendate);
    who.textContent = "";
    fetchDetails(i, item);
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

  // slideshow zoom: the photo grows slowly from fitting the screen to filling it (a portrait photo ends
  // edge to edge) over the slide's time; a pause holds the zoom, the next photo starts fitted again
  function coverScale(im) {
    var w = im.naturalWidth, h = im.naturalHeight;
    if (!w || !h) return 1;
    return Math.max(1920 / w, 1080 / h) / Math.min(1920 / w, 1080 / h);
  }
  function currentScale(im) {
    var cs = window.getComputedStyle(im);
    var m = /matrix\(([^,]+),/.exec(cs.webkitTransform || cs.transform || "");
    return m ? parseFloat(m[1]) : 1;
  }
  function zoomStart(im) {
    if (!playing || !im || im.tagName !== "IMG") return;
    var k = coverScale(im);
    if (k < 1.02) return;
    var a = currentScale(im);
    if (a >= k) return;
    var secs = STATE.interval * (k - a) / (k - 1);
    im.style.webkitTransition = "-webkit-transform " + secs + "s linear";
    im.style.transition = "transform " + secs + "s linear";
    void im.offsetWidth;  // a reflow, so the transition runs from the scale shown now
    im.style.webkitTransform = "scale(" + k + ")";
    im.style.transform = "scale(" + k + ")";
  }
  function zoomHold(im) {
    if (!im || im.tagName !== "IMG") return;
    var a = currentScale(im);
    im.style.webkitTransition = "none";
    im.style.transition = "none";
    im.style.webkitTransform = "scale(" + a + ")";
    im.style.transform = "scale(" + a + ")";
  }

  function setPlaying(on) {
    var was = playing;
    playing = on;
    var video = current && current.tagName === "VIDEO";
    if (video) { if (on) current.play(); else current.pause(); }
    else if (on) zoomStart(current); else zoomHold(current);
    if (on) showTag("playing", 0);
    else if (video) showTag("paused", 0);          // the frozen frame stays marked
    else if (was) showTag("paused", 3000);         // a stopped slideshow of photos: brief note
    else showTag("", 0);
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
        if (current && current.tagName === "VIDEO") {
          if (current.paused) { current.play(); showTag(playing ? "playing" : "", 0); }
          else { current.pause(); showTag("paused", 0); }
        }
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
  var focusNodes = [], acts = [];   // one row and one action per entry, in order
  function add(label, value, act, fn) {
    var r = row(label, value, act);
    focusNodes.push(r);
    acts.push(fn || null);
    return r;
  }
  // the paired galleries: OK twice on a row removes that gallery (the server forgets the TV there)
  var armed = -1;
  function galleryRow(gi) {
    var g = API.galleries[gi];
    var r = add(g.title || g.base.replace(/^https:\/\//, ""), (g.user ? g.user + " · " : "") + t("Remove"), true, function () {
      if (armed === gi) { armed = -1; removeGallery(gi); }
      else { armed = gi; r.lastChild.textContent = t("Press OK again to remove"); }
    });
    if (gi === API.active) r.className += " active";
  }
  for (var gi = 0; gi < API.galleries.length; gi++) galleryRow(gi);
  add(t("Add gallery"), "", true, function () { STATE.pendingBase = ""; UI.push(setupScreen()); });
  var rInt = add(t("Slideshow interval"), "◀ " + intervalText() + " ▶", true, function () { changeInterval(1); });
  add(t("App version"), APP_VERSION, false, null);
  node.appendChild(rows);

  function changeInterval(d) {
    var k = INTERVALS.indexOf(STATE.interval);
    if (k < 0) k = 2;
    k = (k + d + INTERVALS.length) % INTERVALS.length;
    STATE.interval = INTERVALS[k];
    store("ps_interval", STATE.interval);
    rInt.lastChild.textContent = "◀ " + intervalText() + " ▶";
  }
  var focus = new FocusList(focusNodes, function (i) { if (acts[i]) acts[i](); });
  focus.pointer();
  return {
    node: node,
    onKey: function (code) {
      if (focusNodes[focus.index] === rInt && (code === KEY.LEFT || code === KEY.RIGHT)) { changeInterval(code === KEY.RIGHT ? 1 : -1); return true; }
      return focus.key(code);
    }
  };
}

// ---------------- Developer Mode ----------------
// The app is installed through LG's Developer Mode, which ends after 1000 hours and then removes the app.
// Launching the Developer Mode app with extend=true (what `ares-launch com.palmdts.devmode -p extend=true`
// does) renews the session in the background; the Picturestation app stays on screen. At most once a day.
function extendDevMode() {
  var KEY_EXT = "ps_devmode_extended", now = Date.now(), last = 0;
  try { last = parseInt(localStorage.getItem(KEY_EXT) || "0", 10) || 0; } catch (e) { /* no storage: try anyway */ }
  if (now - last < 24 * 3600 * 1000 || typeof PalmServiceBridge === "undefined") return;
  try {
    var bridge = new PalmServiceBridge();
    bridge.onservicecallback = function (msg) {
      var ok = false;
      try { ok = JSON.parse(msg).returnValue === true; } catch (e) { /* not JSON */ }
      if (ok) { try { localStorage.setItem(KEY_EXT, String(now)); } catch (e) { /* ignore */ } }
    };
    bridge.call("luna://com.webos.applicationManager/launch",
      JSON.stringify({ id: "com.palmdts.devmode", params: { extend: true } }));
  } catch (e) { /* not on a TV, or the call is not allowed: nothing to do */ }
}

// ---------------- start ----------------
function main() {
  extendDevMode();
  initLang();
  UI.init();
  API.load();
  loadPrefs();
  if (!API.galleries.length) UI.push(setupScreen());
  else UI.push(startScreen());   // a gallery without a session goes on to the pairing code
}
document.addEventListener("DOMContentLoaded", main, false);
