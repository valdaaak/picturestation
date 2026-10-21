# Changelog

Versions follow [semantic versioning](https://semver.org/): MAJOR.MINOR.PATCH. Every release is a git tag `vX.Y.Z`. The Docker image carries the same version.

## Unreleased

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
