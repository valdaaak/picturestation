# Changelog

Versions follow [semantic versioning](https://semver.org/): MAJOR.MINOR.PATCH. Every release is a git tag `vX.Y.Z`. The Docker image carries the same version.

## Unreleased

- Sideways videos on the TV: phones record portrait videos lying on their side and only set a rotation flag, which the TV's player ignores. The server now records the flag in the video's metadata (`video_codec.rotation`) and keeps an upright copy of such videos (H.264/AAC, at most 1080p) in `DATA/video_tv/`, made by ffmpeg in the background at the lowest priority, one at a time; after a start it goes through the library once, newest folders first. The TV app asks for `variant=tv` and gets the copy, or the original with the header `X-Picturestation-Video: preparing` until it exists (`video_codec.tv_version`). Needs the ffmpeg package, which the installers bring.
- Android app (`Android/`): one APK for phones, tablets and Android TV (Android 8.0 and later). It pairs with a code like the LG TV app, browses albums and the newest photos, shows photos full screen with zoom, people and place, plays videos (the player honours the rotation flag), runs slideshows and shares a photo; on a TV it has a launcher banner and works with the remote. The session travels in a header; plain http is used only when the user asks for it.
- LG TV app (`LGTV/`): a webOS app for LG TVs from webOS 3.0 on, installed through LG's Developer Mode; it browses albums and plays photos, slideshows and videos from the server over the DS photo API. The TV is paired like a streaming app: it shows a code, the administrator enters it under Settings, TV, and chooses whose photos the TV sees; the TV stays signed in until it is removed there. For it the API answers CORS requests from any origin, without credentials (a browser session stays in its cookie and is never sent cross-site), and a packaged webOS app (User-Agent `WebAppManager`) carries its session like the DS photo app: `X-SYNO-TOKEN` header, `PHPSESSID` in image URLs.
- Repository layout: the web gallery moved from `server/picturestation/web` to `web/` at the top of the repository. The installers and the Docker image put it in `/opt/picturestation/web`; `PICTURESTATION_WEB_DIR` points the server elsewhere. An update with `install.sh --update` handles it; a hand-made copy of the code must now include `web/` too.
- Viewer: typing a comment no longer triggers the viewer keys ("i" hid the details panel, arrows switched the photo).
- Access editor: "Allow all inside" allows an album and removes the principal's own rules in its sub-albums in one step (a confirmation lists them); group rules stay. After Allow/Exclude the album list and the Settings page stay where they were scrolled.
- Live Photos: an iPhone photo (HEIC/JPG) and its short .MOV with the same name in the same folder are one item. The video is left out of albums, the timeline, search and collections; the photo has a LIVE badge, its motion plays in the grid when the mouse rests on it, and over the photo in the viewer (mouse over LIVE, or a tap). The video can be downloaded from the photo details and goes with the photo in a share link. Videos longer than 5 seconds stay separate. Settings, General: on by default, can be turned off per gallery.
- Search for names with an underscore (for example IMG_1234) found nothing.
- EXIF from HEIC/HEIF and RAW photos (iPhone and camera raw) via exiftool, when it is installed: date, GPS/place, dimensions, camera and keywords. Thumbnails for these still come from the NAS (@eaDir). Needs the libimage-exiftool-perl package, now in the installers and the Docker image.
- Security hardening (pre-release audit): a share link or an unlocked album no longer bypasses a password-protected sub-album inside it; ready-made @eaDir thumbnails/videos are served only when they really resolve inside the gallery's photo root (a symlink in a user-writable archive cannot read outside it); the session cookie gets the Secure flag over HTTPS; the session id is accepted from the URL only for the DS photo app, never a browser; webapi responses send X-Content-Type-Options, pages send X-Frame-Options; paths with NUL/control bytes are rejected cleanly; a dead NFS gallery folder no longer exhausts the folder-check pool; per-gallery cover caches are no longer flushed across tenants.
- Private galleries: any number of separate photo archives in one server, managed by the main gallery's administrator under Settings, Galleries. Each has its own users, rights, thumbnails and database, and is reached at /~name/ or at its own domain. They replace the per-gallery services (`picturestation-instance`) of 0.1.0.
- Faster Collections page. Covers of tags, places, people and smart albums are remembered from the lists, the library list is rebuilt in the background and warmed up at start, and permissions are evaluated once per folder.
- Places also for villages below 500 inhabitants. `PICTURESTATION_GEONAMES_COUNTRIES=SK,CZ` downloads the full GeoNames lists of those countries, with populated places only and without city sections. Settlements are named after their municipality, so a part of a village shows the village name. After the place data changes, the gallery looks up the places of all photos again, once.
- The installers wait up to 10 minutes for the package manager lock, for example while unattended upgrades run, instead of stopping.

## 0.1.0 – 2026-10-21

First version.

- **DS photo app.** The Photo Station 6 API is supported: albums, timeline, tags, places, smart albums, comments, covers, thumbnails, downloads and video.
- **Web gallery.** It has albums, a timeline, search, a viewer with details, and collections of smart albums, tags, places and people. The interface is in English and Slovak.
- **Rights.** Users, groups and guests are supported. Album access is shown as a tree with allowed and excluded albums, and it can also be set per album. Albums can have passwords, and share links can expire.
- **Restrictions.** Downloads, GPS, camera details, comments, timeline and search can be limited, and photos in the root can be made public.
- **Tags and places.** Tags come from file keywords (IPTC/XMP). Places are looked up offline from GPS with GeoNames.
- **People from Synology Photos.** They are synchronised through a read-only service account.
- **Moved folders.** A move is recognised by the files, and rights, titles, covers, tags, comments, links and smart albums are carried over.
- **Importers.** Rights can be imported from Photo Station 6, and tags and albums from Synology Photos.
- **Personal galleries.** A separate instance can run for one person's folder.
- **Installation.** There are installers for Debian 13 and for Proxmox VE (LXC or VM), a Docker image and a compose example.
