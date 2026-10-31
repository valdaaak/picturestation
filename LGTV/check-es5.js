// SPDX-License-Identifier: GPL-3.0-or-later
// The TV app must be ES5: webOS 3.x runs Chromium 38, which has no arrow functions, classes, let/const,
// template strings, fetch or promises worth relying on. Parses every script of the app as ES5 and
// checks that index.html loads them all. Run: npm run check
"use strict";
const fs = require("fs");
const path = require("path");
const acorn = require("acorn");

const app = path.join(__dirname, "app");
const html = fs.readFileSync(path.join(app, "index.html"), "utf8");
const loaded = [];
html.replace(/<script src="([^"]+)"/g, (m, src) => { loaded.push(src); return m; });
let bad = 0;
for (const name of fs.readdirSync(path.join(app, "js"))) {
  if (!name.endsWith(".js")) continue;
  const file = path.join(app, "js", name);
  try {
    acorn.parse(fs.readFileSync(file, "utf8"), { ecmaVersion: 5, sourceType: "script" });
    console.log("OK   " + name + " is ES5");
  } catch (e) {
    bad++;
    console.log("FAIL " + name + ": " + e.message);
  }
  if (loaded.indexOf("js/" + name) < 0) { bad++; console.log("FAIL index.html does not load js/" + name); }
}
const info = JSON.parse(fs.readFileSync(path.join(app, "appinfo.json"), "utf8"));
for (const f of ["main", "icon", "largeIcon", "splashBackground"]) {
  if (info[f] && !fs.existsSync(path.join(app, info[f]))) { bad++; console.log("FAIL appinfo.json " + f + ": missing " + info[f]); }
}
const pkg = JSON.parse(fs.readFileSync(path.join(__dirname, "package.json"), "utf8"));
const ipk = info.id + "_" + info.version + "_all.ipk";
if (pkg.scripts["install-tv"].indexOf(ipk) < 0) { bad++; console.log("FAIL package.json install-tv does not name " + ipk); }
console.log(bad ? "\nFAILED: " + bad : "\nall good");
process.exit(bad ? 1 : 0);
