// SPDX-License-Identifier: GPL-3.0-or-later
"use strict";
// Talks to Picturestation over the DS photo API (docs/protocol.md) and the pairing endpoints (/api/tv/*).
// A packaged webOS app has no web origin, so the server answers CORS from anywhere without credentials;
// the session travels like the DS photo app's: X-SYNO-TOKEN header on calls, PHPSESSID in image URLs.
// The TV holds a list of paired galleries (base URL, session, user, title); one of them is active and
// API.server / API.sid mirror it. A gallery is the main gallery of a server or a private one (/~name).
// Errors given to callbacks: {code: "network" | "bad" | "timeout" | "api", status, error}.

var API = {
  galleries: [],
  active: 0,
  server: "",
  sid: "",

  load: function () {
    var list = null;
    try { list = JSON.parse(store("ps_galleries") || "null"); } catch (e) { list = null; }
    if (!list) {
      // versions up to 0.1.2 kept one server in ps_server/ps_sid/ps_user/ps_title
      list = [];
      var old = store("ps_server");
      if (old) list.push({ base: old, sid: store("ps_sid") || "", user: store("ps_user") || "", title: store("ps_title") || "" });
      store("ps_server", ""); store("ps_sid", ""); store("ps_user", ""); store("ps_title", "");
    }
    this.galleries = [];
    for (var i = 0; i < list.length; i++) {
      var g = list[i];
      if (g && g.base) this.galleries.push({ base: g.base, sid: g.sid || "", user: g.user || "", title: g.title || "" });
    }
    var a = parseInt(store("ps_active") || "0", 10);
    this.use(isNaN(a) ? 0 : a);
  },
  save: function () {
    store("ps_galleries", JSON.stringify(this.galleries));
    store("ps_active", String(this.active));
  },

  current: function () { return this.galleries[this.active] || null; },
  // makes gallery i the active one (out of range: the first)
  use: function (i) {
    if (i < 0 || i >= this.galleries.length) i = 0;
    this.active = i;
    var g = this.current();
    this.server = g ? g.base : "";
    this.sid = g ? g.sid : "";
  },
  // adds a gallery or replaces the one with the same base; returns its index
  upsert: function (g) {
    for (var i = 0; i < this.galleries.length; i++) {
      if (this.galleries[i].base === g.base) { this.galleries[i] = g; return i; }
    }
    this.galleries.push(g);
    return this.galleries.length - 1;
  },
  // forgets gallery i; the active index follows the remaining list
  remove: function (i) {
    if (i < 0 || i >= this.galleries.length) return;
    this.galleries.splice(i, 1);
    var a = this.active;
    if (a > i) a--; else if (a === i) a = Math.min(a, this.galleries.length - 1);
    this.use(Math.max(0, a));
  },
  setSid: function (sid) {
    var g = this.current();
    if (g) g.sid = sid;
    this.sid = sid;
  },

  // opts: {base, sid} override the active gallery (pairing, probing an address, logging a gallery out)
  post: function (path, params, cb, opts) {
    var base = opts && opts.base !== undefined ? opts.base : this.server;
    var sid = opts && opts.sid !== undefined ? opts.sid : this.sid;
    var xhr = new XMLHttpRequest();
    var done = false;
    xhr.open("POST", base + path, true);
    xhr.setRequestHeader("Content-Type", "application/x-www-form-urlencoded");
    if (sid) xhr.setRequestHeader("X-SYNO-TOKEN", sid);
    xhr.timeout = 25000;
    xhr.onreadystatechange = function () {
      if (xhr.readyState !== 4 || done) return;
      done = true;
      if (xhr.status === 0) return cb({ code: "network" });
      var j = null;
      try { j = JSON.parse(xhr.responseText); } catch (e) { j = null; }
      if (!j || typeof j !== "object") return cb({ code: "bad", status: xhr.status });
      if (xhr.getResponseHeader("x-request-error") === "error_timeout") return cb({ code: "timeout" });
      if (xhr.status >= 400) return cb({ code: "bad", status: xhr.status, error: j.error });
      cb(null, j);
    };
    xhr.ontimeout = function () { if (!done) { done = true; cb({ code: "network" }); } };
    xhr.onerror = function () { if (!done) { done = true; cb({ code: "network" }); } };
    xhr.send(encodeForm(params));
  },

  // DS photo API: cb(err, data)
  call: function (script, api, method, params, cb, opts) {
    var p = { api: api, method: method, version: "1" };
    for (var k in params) if (params.hasOwnProperty(k) && params[k] !== undefined && params[k] !== null) p[k] = params[k];
    this.post("/photo/webapi/" + script, p, function (err, j) {
      if (err) return cb(err);
      if (!j.success) return cb({ code: "api", error: j.error && j.error.code });
      cb(null, j.data || {});
    }, opts);
  },

  thumb: function (item, size) {
    var u = this.server + "/photo/webapi/thumb.php?api=SYNO.PhotoStation.Thumb&method=get&version=1&id="
      + encodeURIComponent(item.id) + "&size=" + size;
    var ts = item.additional && item.additional.thumb_size;
    if (ts && ts[size] && ts[size].mtime) u += "&mtime=" + encodeURIComponent(ts[size].mtime);
    if (ts && ts.sig) u += "&sig=" + encodeURIComponent(ts.sig);
    if (this.sid) u += "&PHPSESSID=" + encodeURIComponent(this.sid);
    return u;
  },

  // variant=tv: a sideways video (rotation flag, which the TV's player ignores) comes as an upright copy.
  // The motion of a Live Photo: API.video({ id: item.info.live })
  video: function (item) {
    return this.server + "/photo/webapi/download.php?api=SYNO.PhotoStation.Download&method=getvideo&version=1&id="
      + encodeURIComponent(item.id) + "&variant=tv" + (this.sid ? "&PHPSESSID=" + encodeURIComponent(this.sid) : "");
  }
};

function encodeForm(params) {
  var out = [];
  for (var k in params) if (params.hasOwnProperty(k)) out.push(encodeURIComponent(k) + "=" + encodeURIComponent(params[k]));
  return out.join("&");
}

// localStorage that never throws (private windows, broken storage)
function store(key, value) {
  try {
    if (value === undefined) return window.localStorage.getItem(key);
    if (value === null || value === "") window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, String(value));
  } catch (e) { /* no storage: the app asks again next time */ }
  return value;
}

// "photos.example.com/" -> ["https://photos.example.com", "http://photos.example.com"]; a scheme is kept as typed
function serverCandidates(typed) {
  var s = (typed || "").replace(/^\s+|\s+$/g, "").replace(/\/+$/, "");
  if (!s) return [];
  if (/^https?:\/\//i.test(s)) return [s];
  s = s.replace(/^\/+/, "");
  return ["https://" + s, "http://" + s];
}
