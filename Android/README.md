# Picturestation for Android and Android TV

One app for phones, tablets and Android TV (one APK, Android 8.0 and later). It shows a Picturestation
gallery: albums, the newest photos, a full-screen viewer with zoom, slideshows, videos, the people on a
photo and the place, and sharing a photo to other apps. On a TV it is driven by the remote control.

## Pairing

The app never asks for a password. On the first start it asks for the address of the gallery, for
example `photos.example.com` (`https://` is tried first, then `http://`), and then shows a code of six
letters and digits. An administrator opens the gallery in a browser, goes to **Settings, TV**, enters the
code and chooses the user whose photos the device will see. The device stays signed in until it is removed
there, or until **Settings, Sign out of this device** in the app.

## Build

Needs the Android SDK (platform 36) and a JDK 17 or later (the wrapper brings Gradle):

```sh
cd Android
./gradlew assembleDebug          # app/build/outputs/apk/debug/app-debug.apk
./gradlew assembleRelease        # needs a signing config, see below
```

`local.properties` holds `sdk.dir`. Icons and the TV banner come from the project's logo
(`docs/logo/make_logo.py`).

## Install

- **Phone:** copy the APK to the phone and open it (allow installing from that app), or `adb install -r app-debug.apk`.
- **Android TV:** turn on Developer options and network debugging on the TV, then
  `adb connect <tv-ip>:5555` and `adb install -r app-debug.apk`. The app appears in the TV's launcher with its banner.

## Remote control (TV)

| Key | Albums | Viewer |
|---|---|---|
| Arrows, OK | move, open | previous / next; OK shows or hides the details |
| Back | one level up | back to the album |
| Play/pause, Red | | start or stop the slideshow |
| Pause, Stop, Green | | pause |

## Layout

- `app/src/main/kotlin/org/picturestation/app/data/` — the server: `Api` (DS photo API, pairing, URLs of thumbnails and videos), `Store` (server, session, preferences; encrypted), `Model` (items).
- `AppViewModel` — the screens as a stack, lists with paging, pairing, start-up, sign-out.
- `ui/` — Compose screens: address, code, albums, viewer (pager, zoom, Media3 video, slideshow), settings.

The server side is the same as for the LG TV app: the DS photo API with the session in the `X-SYNO-TOKEN`
header and `PHPSESSID` in image URLs, and `/api/tv/code` and `/api/tv/poll` for the pairing.
