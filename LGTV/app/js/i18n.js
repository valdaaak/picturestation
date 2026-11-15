// SPDX-License-Identifier: GPL-3.0-or-later
"use strict";
// Texts of the TV app. Source strings in the code are English; I18N_SK maps them to Slovak.
// A list value = Slovak plural forms [1, 2-4, other] for tn(n, one, other), keyed by `other`.
// The TV's language decides (sk or cs -> Slovak), like the web gallery's automatic choice.
// server/tests/test_i18n.py checks that every t("...") of the app has a translation here.

var I18N_SK = {
  "Address of your Picturestation": "Adresa tvojho Picturestation",
  "For example photos.example.com or 192.168.1.10": "Napríklad fotky.priklad.sk alebo 192.168.1.10",
  "Connect": "Pripojiť",
  "Connecting…": "Pripájam…",
  "The server did not answer. Check the address and the network.": "Server neodpovedal. Skontroluj adresu a sieť.",
  "This is not a Picturestation server.": "Toto nie je server Picturestation.",
  "Enter this code in Picturestation": "Zadaj tento kód v Picturestation",
  "In a browser open the gallery, Settings, TV, and allow this code under your name.":
    "V prehliadači otvor galériu, Nastavenia, TV, a povoľ tento kód pod svojím menom.",
  "Waiting for approval…": "Čakám na povolenie…",
  "The code has expired, here is a new one.": "Kód vypršal, tu je nový.",
  "The server did not give a code. Trying again…": "Server nedal kód. Skúšam znova…",
  "Change address": "Zmeniť adresu",
  "The session has ended, a new code is needed.": "Prihlásenie skončilo, treba nový kód.",
  "Network error, trying again…": "Chyba siete, skúšam znova…",
  "Latest photos": "Najnovšie fotky",
  "Collections": "Zbierky",
  "People": "Ľudia",
  "Tags": "Tagy",
  "Places": "Miesta",
  "Settings": "Nastavenia",
  "No photos here.": "Tu nie sú žiadne fotky.",
  "This album needs a password.": "Tento album má heslo.",
  "Loading…": "Načítavam…",
  "{n} items": ["{n} položka", "{n} položky", "{n} položiek"],
  "No date": "Bez dátumu",
  "The video could not be played.": "Video sa nedá prehrať.",
  "The upright copy of this video is being prepared; playing the original for now.":
    "Otočená kópia videa sa pripravuje, zatiaľ hrá originál.",
  "The photo could not be loaded.": "Fotka sa nedá načítať.",
  "OK: details · Red: slideshow · Green: pause · Back: close":
    "OK: detaily · Červené: prezentácia · Zelené: pauza · Back: zavrieť",
  "Add gallery": "Pridať galériu",
  "Remove": "Odstrániť",
  "Press OK again to remove": "Stlač OK ešte raz na odstránenie",
  "Cancel": "Zrušiť",
  "Slideshow interval": "Interval prezentácie",
  "{n} seconds": ["{n} sekunda", "{n} sekundy", "{n} sekúnd"],
  "App version": "Verzia appky"
};

var LANG = "en";
var MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
  "November", "December"];

function initLang() {
  var l = (navigator.language || "").toLowerCase();
  LANG = (l.indexOf("sk") === 0 || l.indexOf("cs") === 0) ? "sk" : "en";
}

function fill(s, vars) {
  if (!vars) return s;
  for (var k in vars) if (vars.hasOwnProperty(k)) s = s.replace("{" + k + "}", vars[k]);
  return s;
}

function t(s, vars) {
  var r = s;
  if (LANG === "sk" && typeof I18N_SK[s] === "string") r = I18N_SK[s];
  return fill(r, vars);
}

function tn(n, one, other) {
  var r;
  if (LANG === "sk" && I18N_SK[other] && I18N_SK[other].length === 3) {
    var f = I18N_SK[other];
    r = n === 1 ? f[0] : (n >= 2 && n <= 4 ? f[1] : f[2]);
  } else {
    r = n === 1 ? one : other;
  }
  return fill(r, { n: n });
}

// "YYYY-MM-DD HH:MM:SS" from the API -> "20. 5. 2023 14:03" (sk) or "20 May 2023 14:03" (en)
function fmtDate(taken) {
  var m = /^(\d{4})-(\d\d)-(\d\d)(?: (\d\d):(\d\d))?/.exec(taken || "");
  if (!m) return t("No date");
  var d = parseInt(m[3], 10), mo = parseInt(m[2], 10), y = m[1];
  var time = m[4] ? " " + m[4] + ":" + m[5] : "";
  if (LANG === "sk") return d + ". " + mo + ". " + y + time;
  return d + " " + MONTHS_EN[mo - 1] + " " + y + time;
}
