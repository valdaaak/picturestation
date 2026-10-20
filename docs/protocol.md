# Photo Station 6 protocol, as used by the DS photo app

This page describes the HTTP interface that the DS photo mobile app (Android 3.12.x) expects from Photo Station 6.8.9.
Picturestation implements it so that the app keeps working with DSM 7, where Photo Station no longer exists.

The description was written for interoperability, from the publicly available Photo Station 6.8.9-3483 package and the DS photo 3.12.6 app on archive.synology.com.
No Synology code is part of this project. Names in parentheses point to the original source files and classes, for anyone who wants to verify a detail.

## 1. Transport

- **URL.** The app calls `http(s)://<host>:<port>[/~<user>]/photo/webapi/<path>`. It takes `<path>` from the SYNO.API.Info response (field `path`).
- **API calls** are `POST` with `application/x-www-form-urlencoded`. They always carry `api`, `method` and `version`, plus parameters. The `X-SYNO-TOKEN: <sid>` header can be ignored.
- **Thumbnails and downloads** are `GET`, with the parameters in the query string and `PHPSESSID=<sid>` in the URL.
- **Session.** Login sets the `PHPSESSID` cookie. The app reads the session id only from a cookie with exactly that name, not from the JSON response (`AbsConnectionManager.getSessionId`).
- **Response.** The content type is `text/plain; charset=utf-8` and the body is JSON:
  - success: `{"success":true,"data":{...}}`, with `data` omitted when it is null;
  - error: `{"success":false,"error":{"code":N}}`, still with HTTP 200.
- **HTTP 404, 405 or 500 during login** makes the app show a "download Synology Photos" dialog (`NaviToDownloadKailashHelper`). The server therefore always answers 200 with a JSON error.
- **An expired session** is signalled by the header `x-request-error: error_timeout`. The app then logs in again.
- **HTTPS.** The app checks the certificate fingerprint and asks the user on the first connection (`Common.setVerifyCertFingerprint`).

## 2. Error codes

These come from `webapi.inc.php` and `sdk/WebAPI.inc.php`.

| Code | Meaning |
|---|---|
| 100 | unknown error |
| 101 | bad request |
| 102 | no such API |
| 103 | no such method |
| 104 | version not supported |
| 105 | no permission |
| 106 | session timeout |
| 406 | not allowed |
| 407 | wrong user name or password |
| 410 | too many login attempts |
| 416 | wrong album password |
| 501 | thumbnail, bad parameters |
| 502 | thumbnail, access denied |
| 504 | thumbnail, file does not exist |
| 506 | download, bad parameters |

## 3. Login sequence

This is `WebApiConnectionManager.login`.

1. **`query.php`**, SYNO.API.Info `query` v1, with `query=all`.
   - It returns `data` as a map `"<api>": {"path":"x.php","minVersion":1,"maxVersion":N}` for every API.
   - The app refuses to call an API that is not listed.
2. **`auth.php`**, SYNO.PhotoStation.Auth `login` v1, with `username` and `password`.
   - It sets the `PHPSESSID` cookie.
   - `data` contains `sid, username, reg_syno_user, is_admin, allow_comment, permission{browse,upload,manage}, enable_face_recog, allow_public_share, allow_download, show_detail`.
3. **`info.php`**, SYNO.PhotoStation.Info `getinfo` v1. Its `data` corresponds to `PhotoStationInfoVo`:
   - `version` is a numeric string, for example `"3483"`. The app parses it with `Integer.valueOf` and enables features from 2115, 2124 and 2700 on.
   - The other fields are `version_string, title, hide_search, home_category, sort_by, sort_direction, allow_download_orig, allow_download_album, allow_social_share, allow_social_upload, allow_social_upload_guest, support_large_file, hide_gps_from_normal_user, folder_sort_only_name, external_host_quickconnect, virtual_tag{people_tag,geo_tag,desc_tag}`.
   - If `home_category` is not empty, the app immediately calls Category `getinfo`.
4. **`auth.php`**, SYNO.PhotoStation.Auth `checkauth` v1. It returns the same `data` as login. An empty `username` means the app has to log in again.

## 4. Item ids

These come from `sdk/WebAPI.php EncodeItemId` and `photoutil.php`. Ids describe themselves, so the server does not need an id table.

- **Album:** `album_` + hex(relative album path), for example `album_323031332d3038`. The root has id null.
- **Photo:** `photo_` + hex(folder path) + `_` + hex(file name). A folder in the root is hex("/") = `2f`.
- **Video:** `video_`, otherwise the same as a photo.
- **Picturestation additions:**
  - `tag_<n>` is a tag;
  - `tag_g<hex(country|place)>` is a place;
  - `tag_p<id>` is a person;
  - `smart_<n>` is a smart album.

## 5. Browsing

### Album list

`album.php`, SYNO.PhotoStation.Album `list` v1.

- **Parameters:**
  - `id` (missing means the root), `offset`, `limit` (usually 120), `recursive=false`;
  - `type` is `album` or `album,video,photo`;
  - `sort_by`, `sort_direction`, `force_update`, and optionally `password`;
  - `additional=album_permission,thumb_size,photo_exif,video_quality,video_codec,album_sorting,file_location,album_createdate`.
- **Response:** `data` is `{"items":[...], "total":N, "offset":N}`. Albums come first, then photos and videos.
- **Album `getinfo`** takes `id` and `additional=thumb_size`. The album item is in `data.items[0]`.

### Photo list

`photo.php`, SYNO.PhotoStation.Photo `list` v1. It serves the timeline, smart albums and tags.

- **Parameters:**
  - `filter_album`, `filter_smart` or `filter_tag`;
  - `type=photo,video`, `offset`, `limit`, `sort_by=takendate`, `sort_direction=desc`;
  - `additional=photo_exif,video_codec,video_quality,thumb_size,takendate`.
- **Response:** the same shape as the album list.
- **Photo `getinfo`** takes `id`. Here `data` is an **array** of items (`PhotoVo: List<BasicItem> data`).

### Item shape

These come from `vos/BasicItem.java`, `albumutil.php FormAlbum` and `photoutil.php`.

```
{ "id": "...", "type": "album|photo|video", "thumbnail_status": "small,large" | "default",
  "info": { ... }, "additional": { ... } }
```

- **Album `info`:** `sharepath, name, title, description, hits, type ("public"|"private"|"password"), conversion, allow_comment`.
- **Album `additional`:**
  - `album_permission{browse,upload,manage}`;
  - `album_sorting{sort_by,sort_direction,sort_customized}`;
  - `file_location` (the same as sharepath), `album_createdate` (unix seconds), `thumb_size{small,large,sig}`.

  For an album with a cover, the app appends `&sig=<thumb_size.sig>`, where sig = hex(cover photo path).
- **Photo `info`:** `name, title, description, createdate, takendate ("YYYY-MM-DD HH:MM:SS"), size, resolutionx, resolutiony, rotated, rating, gps`.
- **Photo `additional.photo_exif`:** `takendate, camera, camera_model, exposure, aperture, iso, gps{lat,lng}, focal_length, lens, flash`.
- **Video `info`:** `name, title, description, createdate, takendate, size, duration, gps, rating`.
- **Video `additional`:**
  - `video_codec{container,vcodec,acodec,resolutionx,resolutiony,video_bitrate,audio_bitrate}`;
  - `video_quality: []`.
- **`additional.thumb_size`:** `{"small":{"resolutionx","resolutiony","mtime"}, "large":{...}, "preview":{...}}`.

### thumbnail_status

This comes from `ImageItem.setThumbs` and `albumutil.php GetThumbStatus`.

- `small` makes the app request `id=<id>&size=small&mtime=<mtime>`.
- `preview`, without `small`, makes it request `size=preview`.
- `large` makes it request `id=<id>&size=large&mtime=<mtime>`.
- `default` means there is no thumbnail, and the app shows an icon.

## 6. Thumbnails

`thumb.php`, SYNO.PhotoStation.Thumb `get` v1, over GET.

- **Parameters:** `id`, `size` (small, large or preview), `mtime`, `sig` (for albums) and `PHPSESSID`.
- **Sizes**, from `syno_defines.php`:

  | Size | Photo Station name |
  |---|---|
  | small, 320 px | THUMB_M |
  | large, 1280 px | THUMB_XL |
  | preview, 160 px | THUMB_PREVIEW |

- **Album thumbnail.** It is the cover photo, or the first photo when no cover is set.
- **Headers:** `Content-Type: image/jpeg`, `Cache-Control: max-age=604800` and `Last-Modified`. The server supports 304 responses.
- **Ready-made thumbnails.** DSM keeps them in `<folder>/@eaDir/<file>/SYNOPHOTO_THUMB_{M,XL,PREVIEW}.jpg`, and Photo Station used the older `SYNOPHOTO:THUMB_*` names. Picturestation uses them when they exist and otherwise generates its own cache.

## 7. Originals and video

`download.php`, SYNO.PhotoStation.Download, over GET.

- **`getphoto`** takes `id=<id>&size=original&mtime=...&PHPSESSID=...`. It returns the file and supports HTTP Range.
- **`getvideo`** works the same way. The app fetches video over the **plain HTTP port** (`getVideoServerUrlPrefix`).

## 8. Other APIs

- **Implemented:** Auth, Info, Album, Photo, Thumb, Download, Cover, Comment, Tag and SmartAlbum.
- **Answered with an empty list:** Category, SharedAlbum, PhotoTag `list` and Timeline `getindex`. The app calls these and expects a valid answer.
- **Everything else, including File upload and all edits of albums and photos,** returns error 105. Picturestation never writes to the photo folder.

Album and photo list responses must be complete even for APIs the server does not offer. Otherwise the app crashes while parsing.
