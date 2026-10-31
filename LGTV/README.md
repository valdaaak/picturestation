# Picturestation for LG TVs

An app for LG TVs with webOS 3.0 or later (2016 models on). It shows a Picturestation gallery on the TV: albums, the newest photos, a full-screen viewer, slideshows and videos, driven by the remote control (the Magic Remote pointer works as well). The texts are in English and Slovak; the TV's language decides.

The app is installed through LG's **Developer Mode**, not from the LG Content Store. It talks to the server over the DS photo API, by HTTPS or HTTP.

## Pairing

The TV never asks for a password. On the first start the app asks for the address of the gallery, for example `photos.example.com` (`https://` is tried first, then `http://`), and then shows a code of six letters and digits. An administrator opens the gallery in a browser, goes to **Settings, TV**, enters the code and chooses the user whose photos the TV will see. The TV stays signed in until it is removed there, or until **Settings, Sign out of this TV** on the TV. A code waits 10 minutes; after that the TV shows a new one.

## What you need

- An LG TV with webOS 3.0 or later. The app is plain ES5 and 2014-era CSS because webOS 3.x runs Chromium 38.
- A free [LG Developer account](https://webostv.developer.lge.com/) and the **Developer Mode** app on the TV (search for it in the LG Content Store).
- Node.js on a PC in the same network. `npm install` in this folder brings the webOS CLI (the `ares-*` commands) and the ES5 checker.

## Build and install

1. On the TV, open **Developer Mode**, sign in with the LG Developer account and turn on **Dev Mode Status**; the TV restarts. Open the app again and turn on **Key Server**. Note the IP address of the TV and the passphrase shown in the app.
2. On the PC, in this folder:

   ```sh
   npm install
   npm run check                                   # every script parses as ES5, appinfo.json is complete
   npm run package                                 # dist/org.picturestation.tv_0.1.0_all.ipk
   npx ares-setup-device --add tv -i "host=192.168.1.50" -i "port=9922" -i "username=prisoner"
   npx ares-novacom --device tv --getkey           # asks for the passphrase from the Developer Mode app
   npm run install-tv
   npm run launch
   ```

   `npx ares-setup-device` without arguments asks the same questions one by one.
3. The app is in the TV's launcher from now on. `npm run inspect` opens the web inspector of the running app, where the TV's engine allows it.

**Developer Mode is limited in time** (1000 hours on current firmware; the Developer Mode app shows what is left and has an **Extend** button). When the time runs out, the TV removes the apps installed this way, and you install again. One LG Developer account is signed in on one TV at a time.

## Remote control

| Key | Albums | Viewer |
|---|---|---|
| Arrows, OK | move, open | previous / next; OK shows or hides the details |
| Back | one level up; on the first screen leaves the app | back to the album |
| Red, or Play | slideshow from the selected photo | start or stop the slideshow |
| Green, or Pause, Stop | | stop the slideshow, pause a video |
| Channel up / down | a page of tiles | |
| Rewind, Fast forward | | 10 s in a video, otherwise previous / next |

**Videos recorded sideways.** Phones record portrait videos lying on their side and only set a rotation flag, which the TV's player ignores. The server therefore keeps an upright copy of such videos (made by ffmpeg in the background, at most 1080p) and the app plays that one. Right after the server is installed or updated, the copies are still being made, newest folders first; until a copy exists the app plays the original and says so.

The Magic Remote has no Play and Pause keys (they are on its on-screen remote under the "…" key), so the red and green keys do the same. The slideshow interval is under **Settings** on the first screen (3 to 30 seconds). A video plays whole; in a slideshow the next item follows when it ends. Videos come the same way as in the browser: the MP4 original, or the conversion the NAS keeps in `@eaDir`.

## Development

The app also runs in a desktop browser: open `app/index.html` as a file. The server accepts the TV's session only from a webOS client (its user agent contains `WebAppManager`), so for a desktop test either set the browser's user agent to the TV's or stop at the pairing code. `server/tests/test_i18n.py` checks the translations of the app, `npm run check` parses every script as ES5 and checks `appinfo.json`. The icons and the splash screen are drawn by `tools/make_icons.py` (Pillow).

The server side of the app is small: the DS photo API answers CORS requests from any origin without credentials, a webOS client may send its session in the `X-SYNO-TOKEN` header and as `PHPSESSID` in image URLs, and `/api/tv/code` and `/api/tv/poll` do the pairing (`server/picturestation/pairing.py`).

## Not there yet

- Tags, places, people, smart albums and search. Albums and the newest photos are.
- Password-protected albums cannot be opened on the TV.
- Whether the TV's screensaver interrupts a long slideshow on webOS 3.x has not been verified on a TV yet.
