// SPDX-License-Identifier: GPL-3.0-or-later
"use strict";
// Screens, remote control keys and small DOM helpers. A screen is {node, enter(), leave(), pause(), resume(),
// onKey(code, event) -> true when handled}. UI keeps a stack of screens; Back pops, Back on the last one
// leaves the app (webOS: PalmSystem.platformBack).

var KEY = {
  LEFT: 37, UP: 38, RIGHT: 39, DOWN: 40, OK: 13,
  BACK: 461,        // webOS Back; appinfo.json has disableBackHistoryAPI so the app gets it
  ESC: 27,          // Back when trying the app in a desktop browser
  PLAY: 415, PAUSE: 19, STOP: 413, REW: 412, FF: 417,
  RED: 403, GREEN: 404, YELLOW: 405, BLUE: 406,
  CH_UP: 33, CH_DOWN: 34
};

function el(tag, cls, text) {
  var e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = text;
  return e;
}

function setFocus(node, on) {
  if (!node) return;
  if (on) node.className += " focus";
  else node.className = node.className.replace(/(^|\s)focus(?=\s|$)/g, "").replace(/\s+/g, " ").replace(/^\s|\s$/g, "");
}

var UI = {
  stack: [],
  root: null,
  toastTimer: null,

  init: function () {
    this.root = document.getElementById("app");
    var self = this;
    document.addEventListener("keydown", function (e) { self.key(e); }, false);
  },

  top: function () { return this.stack.length ? this.stack[this.stack.length - 1] : null; },

  push: function (screen) {
    var cur = this.top();
    if (cur) { if (cur.pause) cur.pause(); cur.node.setAttribute("hidden", ""); }
    this.stack.push(screen);
    this.root.appendChild(screen.node);
    if (screen.enter) screen.enter();
  },

  pop: function () {
    var s = this.stack.pop();
    if (!s) return;
    if (s.leave) s.leave();
    if (s.node.parentNode) s.node.parentNode.removeChild(s.node);
    var cur = this.top();
    if (cur) { cur.node.removeAttribute("hidden"); if (cur.resume) cur.resume(); }
  },

  // replace the whole stack with one screen (after pairing, sign-out, address change)
  reset: function (screen) {
    while (this.stack.length) this.pop();
    this.push(screen);
  },

  key: function (e) {
    var cur = this.top();
    if (!cur) return;
    var code = e.keyCode;
    if (cur.onKey && cur.onKey(code, e) === true) { e.preventDefault(); return; }
    if (code === KEY.BACK || code === KEY.ESC) {
      e.preventDefault();
      if (this.stack.length > 1) this.pop();
      else exitApp();
    } else if (code >= KEY.LEFT && code <= KEY.DOWN) {
      e.preventDefault();  // never scroll the page
    }
  },

  toast: function (msg, ms) {
    var node = document.getElementById("toast");
    node.textContent = msg;
    node.removeAttribute("hidden");
    if (this.toastTimer) clearTimeout(this.toastTimer);
    this.toastTimer = setTimeout(function () { node.setAttribute("hidden", ""); }, ms || 4000);
  }
};

function exitApp() {
  if (window.PalmSystem && window.PalmSystem.platformBack) window.PalmSystem.platformBack();
}

// name of this TV for the pairing list: "LG 55UH8507-ZA"
function deviceName() {
  try {
    var d = JSON.parse(window.PalmSystem.deviceInfo);
    if (d && d.modelName) return "LG " + d.modelName;
  } catch (e) { /* not on webOS */ }
  return window.PalmSystem ? "LG TV" : "Browser";
}

// a vertical list of focusable rows/buttons: index, move, activate
function FocusList(nodes, onActivate) {
  this.nodes = nodes;
  this.index = 0;
  this.onActivate = onActivate;
  setFocus(nodes[0], true);
}
FocusList.prototype.move = function (delta) {
  var n = this.index + delta;
  if (n < 0 || n >= this.nodes.length) return false;
  setFocus(this.nodes[this.index], false);
  this.index = n;
  setFocus(this.nodes[n], true);
  return true;
};
FocusList.prototype.set = function (i) {
  if (i === this.index) return;
  setFocus(this.nodes[this.index], false);
  this.index = i;
  setFocus(this.nodes[i], true);
};
FocusList.prototype.key = function (code) {
  if (code === KEY.UP) return this.move(-1) || true;
  if (code === KEY.DOWN) return this.move(1) || true;
  if (code === KEY.OK) { this.onActivate(this.index, this.nodes[this.index]); return true; }
  return false;
};
FocusList.prototype.pointer = function () {
  // the Magic Remote pointer: hovering focuses, clicking activates
  var self = this;
  function bind(i) {
    self.nodes[i].addEventListener("mouseover", function () { self.set(i); }, false);
    self.nodes[i].addEventListener("click", function () { self.set(i); self.onActivate(i, self.nodes[i]); }, false);
  }
  for (var i = 0; i < this.nodes.length; i++) bind(i);
};
