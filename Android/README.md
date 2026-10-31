# Picturestation for Android and Android TV

One app for phones, tablets and Android TV (one APK, Android 8.0 and later). It shows a Picturestation
gallery: albums, the newest photos, a full-screen viewer with zoom, slideshows, videos, the people on a
photo and the place, and sharing a photo to other apps. On a TV it is driven by the remote control.

## Pairing

The app never asks for a password. On the first start it asks for the address of the gallery, for
example `photos.example.com` (`https://` is tried first, then `http://`), and then shows a code of six
letters and digits. An administrator opens the gallery in a browser, goes to **Settings, TV**, enters the
code and chooses the user whose photos the device will see. The device stays signed in until it is removed
there, or until the gallery is removed under **Settings** in the app.

## Several galleries

One app can hold several paired galleries: the main gallery of a server and private galleries on it
(`photos.example.com/~name`), or galleries on different servers. **Settings, Add gallery** runs the same
address-and-code flow again; each gallery is approved by its own administrator in its own Settings, TV. The
other galleries appear as tiles next to "Latest photos" on the start screen, and the app remembers the one
shown last. A gallery whose device was removed on the server asks for a new code; the others stay.

## Build

Needs the Android SDK (platform 36) and a JDK 17 or later (the wrapper brings Gradle):

```sh
cd Android
./gradlew assembleDebug          # app/build/outputs/apk/debug/app-debug.apk
./gradlew assembleRelease        # needs a signing config, see below
```

`local.properties` holds `sdk.dir`. Icons and the TV banner come from the project's logo
(`docs/logo/make_logo.py`).

**Release signing.** `assembleRelease` signs the APK when `keystore.properties` exists next to
`settings.gradle.kts` (both it and `keystore/` stay out of git):

```
storeFile=keystore/picturestation-release.jks
storePassword=...
keyAlias=picturestation
keyPassword=...
```

Keep the keystore: an update is accepted only when it is signed with the same key as the installed app.
A debug build is signed with the SDK's debug key, so switching between debug and release means
uninstalling first (the pairing is then done again).

**Plain http.** The app tries `https://` first. When that fails for an address typed without a scheme,
it offers `http://` and uses it only after that choice, so that nobody on the way can downgrade the
connection unnoticed. Inside your own network http is fine.

## Install

- **Phone:** copy the APK to the phone and open it (allow installing from that app), or `adb install -r app-debug.apk`.
  The server can hand it out itself: put the APK into `DATA/app/` (`/var/lib/picturestation/app/`) and open
  `https://your-gallery/app/Picturestation.apk` on the phone.
- **Android TV:** turn on Developer options and network debugging on the TV, then
  `adb connect <tv-ip>:5555` and `adb install -r app-debug.apk`. The app appears in the TV's launcher with its banner.

## Updates

The app checks `https://your-gallery/app/version.json` after the start and under **Settings, Check for
updates**. A newer `versionCode` shows a bar with an Update button: the APK next to it is downloaded and
handed to Android's installer (the first time Android asks to allow installs from Picturestation). To
publish a version: raise `versionCode` and `versionName` in `app/build.gradle.kts`, build the release,
run `python3 publish.py some/folder` and put that folder's `Picturestation.apk` and `version.json` into
`DATA/app/` on the server.

## Tested

Android 16 emulators, phone and Android TV, against the demo library: pairing, albums, viewer with
swipe and zoom, video (upright, the player honours the rotation flag), slideshow, settings, sign-out.

## Remote control (TV)

| Key | Albums | Viewer |
|---|---|---|
| Arrows, OK | move, open | left / right: previous / next; OK: details and slideshow on, OK again: details and pause; up / down: details |
| Back | one level up | back to the album |
| Play/pause, Red | | start or stop the slideshow |
| Pause, Stop, Green | | pause |

A slideshow on a TV zooms every photo slowly from fitting the screen to filling it, so a portrait photo
ends edge to edge; a pause holds the zoom.

## Layout

- `app/src/main/kotlin/org/picturestation/app/data/` — the server: `Api` (DS photo API, pairing, URLs of thumbnails and videos), `Store` (the paired galleries with their sessions, encrypted; preferences), `Model` (items).
- `AppViewModel` — the screens as a stack, lists with paging, pairing, start-up, switching and removing galleries.
- `ui/` — Compose screens: address, code, albums, viewer (pager, zoom, Media3 video, slideshow), settings.

The server side is the same as for the LG TV app: the DS photo API with the session in the `X-SYNO-TOKEN`
header and `PHPSESSID` in image URLs, and `/api/tv/code` and `/api/tv/poll` for the pairing.
