// SPDX-License-Identifier: GPL-3.0-or-later
"use strict";
// Talks to Picturestation over the DS photo API (docs/protocol.md) and the pairing endpoints (/api/tv/*).
// A packaged webOS app has no web origin, so the server answers CORS from anywhere without credentials;
// the session travels like the DS photo app's: X-SYNO-TOKEN header on calls, PHPSESSID in image URLs.
// Errors given to callbacks: {code: "network" | "bad" | "timeout" | "api", status, error}.

var API = {
  server: "",
  sid: "",

  load: function () {
    this.server = store("ps_server") || "";
    this.sid = store("ps_sid") || "";
  },
  save: function () {
    store("ps_server", this.server);
    store("ps_sid", this.sid);
  },

  post: function (path, params, cb) {
    var xhr = new XMLHttpRequest();
    var done = false;
    xhr.open("POST", this.server + path, true);
    xhr.setRequestHeader("Content-Type", "application/x-www-form-urlencoded");
    if (this.sid) xhr.setRequestHeader("X-SYNO-TOKEN", this.sid);
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
  call: function (script, api, method, params, cb) {
    var p = { api: api, method: method, version: "1" };
    for (var k in params) if (params.hasOwnProperty(k) && params[k] !== undefined && params[k] !== null) p[k] = params[k];
    this.post("/photo/webapi/" + script, p, function (err, j) {
      if (err) return cb(err);
      if (!j.success) return cb({ code: "api", error: j.error && j.error.code });
      cb(null, j.data || {});
    });
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

  video: function (item) {
    return this.server + "/photo/webapi/download.php?api=SYNO.PhotoStation.Download&method=getvideo&version=1&id="
      + encodeURIComponent(item.id) + "&variant=web" + (this.sid ? "&PHPSESSID=" + encodeURIComponent(this.sid) : "");
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
