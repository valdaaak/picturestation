# Specifikacia protokolu pre DSphoto-server (MVP: prehliadanie)

Zdroj: Photo Station 6.8.9-3483 (PHP webapi) + DS photo Android 3.12.6-508 (jadx).
Odkazy na subory su relativne k `_rozbor/pkg/photo/` (PHP) a `_rozbor/apk_src/sources/com/synology/dsphoto/` (appka).

## 1. Transport
- URL: `http(s)://<host>:<port>[/~<user>]/photo/webapi/<path>`; `<path>` appka berie z odpovede SYNO.API.Info (pole `path`).
- Volania API: **POST**, `application/x-www-form-urlencoded`, vzdy `api`, `method`, `version` + parametre.
  Hlavicka `X-SYNO-TOKEN: <PHPSESSID>` (staci ignorovat).
- Nahlady a stahovanie: **GET** s parametrami v query stringu a `PHPSESSID=<sid>` v URL (nie len v cookie).
- Session: cookie `PHPSESSID` nastavena pri logine. Appka cita sid len z cookie store, nie z JSON.
- Odpoved: `Content-Type: text/plain; charset=utf-8`, telo JSON:
  - uspech `{"success":true,"data":{...}}` (pole `data` sa vynecha, ak je null)
  - chyba  `{"success":false,"error":{"code":N}}` s HTTP 200.
- **HTTP 404/405/500 pocas loginu = appka ukaze dialog "stiahnite Synology Photos"** (NaviToDownloadKailashHelper).
  Server preto vzdy vracia 200 s JSON chybou.
- Vyprsana session: hlavicka `x-request-error: error_timeout` -> appka sa prihlasi znova.
- Appka pri HTTPS kontroluje odtlacok certifikatu (Common.setVerifyCertFingerprint) - pri prvom pripojeni sa pyta pouzivatela.

## 2. Chybove kody (webapi.inc.php, sdk/WebAPI.inc.php)
100 unknown, 101 bad request, 102 no such API, 103 no such method, 104 version, 105 no permission,
106 session timeout, 407 zle meno/heslo, 406 bez opravnenia, 410 vela pokusov, 416 zle heslo albumu,
501 thumb bad params, 502 thumb access deny, 504 thumb file not exists, 506 download bad params.

## 3. Prihlasovacia sekvencia (WebApiConnectionManager.login)
1. `query.php` SYNO.API.Info `query` v1, `query=all`
   -> `data`: mapa `"<api>": {"path":"x.php","minVersion":1,"maxVersion":N}` pre vsetky API.
   Appka odmietne volat API, ktore tu nie je. Uplny zoznam: `webapi/PhotoStation.api` + SYNO.API.Info -> query.php.
2. `auth.php` SYNO.PhotoStation.Auth `login` v1, `username`, `password`
   -> nastavit cookie PHPSESSID; `data`:
   `sid, username, reg_syno_user, is_admin, allow_comment, permission{browse,upload,manage}, enable_face_recog, allow_public_share, allow_download, show_detail`
3. `info.php` SYNO.PhotoStation.Info `getinfo` v1 -> `data` (PhotoStationInfoVo):
   `version` (ciselny string, napr. "3483"; appka robi Integer.valueOf; funkcie su zapnute od 2115/2124/2700),
   `version_string, title, hide_search, home_category ("" = ziadna), sort_by, sort_direction,
   allow_download_orig, allow_download_album, allow_social_share:false, allow_social_upload:false,
   allow_social_upload_guest:false, support_large_file:true, hide_gps_from_normal_user:false,
   folder_sort_only_name, external_host_quickconnect:"", virtual_tag{people_tag:false,geo_tag:false,desc_tag:false}`.
   Pri `home_category` != "" appka hned vola Category getinfo -> MVP posiela "".
4. `auth.php` SYNO.PhotoStation.Auth `checkauth` v1 -> rovnake `data` ako login. Prazdne `username` = relogin.

## 4. ID poloziek (sdk/WebAPI.php EncodeItemId, photoutil.php)
- album: `album_` + hex(relativna cesta albumu), napr. `album_323031332d3038` ; koren = id null.
- fotka: `photo_` + hex(cesta priecinka) + `_` + hex(meno suboru); priecinok v koreni = hex("/") = `2f`.
- video: `video_` ... rovnako ako fotka.
- Server si nemusi drzat databazu ID - ID je samopopisne.

## 5. Prehliadanie
### Album list (album.php, SYNO.PhotoStation.Album `list` v1)
Parametre: `id` (chyba = koren), `offset`, `limit` (120), `recursive=false`, `type` ("album" | "album,video,photo"),
`sort_by`, `sort_direction`, `additional=album_permission,thumb_size,photo_exif,video_quality,video_codec,album_sorting,file_location,album_createdate`,
`force_update`, volitelne `password`.
Odpoved `data`: `{"items":[...], "total":N, "offset":N}`; poradie: najprv albumy, potom fotky/videa.

### Album getinfo: `id`, `additional=thumb_size` -> `data.items[0]` = polozka albumu.

### Photo list (photo.php, SYNO.PhotoStation.Photo `list` v1)
Timeline/smart: `filter_album|filter_smart|filter_tag`, `type=photo,video`, `offset`, `limit`, `sort_by=takendate`,
`sort_direction=desc`, `additional=photo_exif,video_codec,video_quality,thumb_size,takendate`. Odpoved ako Album list.
Photo `getinfo`: `id` -> `data` = **pole** poloziek (PhotoVo: `List<BasicItem> data`).

### Tvar polozky (vos/BasicItem.java, albumutil.php FormAlbum, photoutil.php)
```
{ "id": "...", "type": "album|photo|video", "thumbnail_status": "small,large" | "default",
  "info": { ... }, "additional": { ... } }
```
- album `info`: `sharepath, name, title, description, hits, type ("public"|"private"|"password"), conversion, allow_comment`
- album `additional`: `album_permission{browse,upload,manage}`, `album_sorting{sort_by,sort_direction,sort_customized}`,
  `file_location` (= sharepath), `album_createdate` (unix s), `thumb_size{small,large,sig}`.
  Pre album s nahladom appka pripaja `&sig=<thumb_size.sig>`; sig = hex(cesta titulnej fotky).
- photo `info`: `name, title, description, createdate, takendate ("YYYY-MM-DD HH:MM:SS"), size, resolutionx, resolutiony, rotated, rating, gps?`
- photo `additional.photo_exif`: `takendate, camera, camera_model, exposure, aperture, iso, gps{lat,lng}, focal_length, lens, flash`
- video `info`: `name, title, description, createdate, takendate, size, duration, gps, rating`;
  `additional.video_codec{container,vcodec,acodec,resolutionx,resolutiony,video_bitrate,audio_bitrate}`, `video_quality: []`
- `additional.thumb_size`: `{"small":{"resolutionx","resolutiony","mtime"}, "large":{...}, "preview"?:{...}}`

### thumbnail_status (ImageItem.setThumbs, albumutil.php GetThumbStatus)
- obsahuje `small` -> appka vytvori URL `id=<id>&size=small&mtime=<mtime>`
- obsahuje `preview` (a nie small) -> `size=preview`
- obsahuje `large` -> `id=<id>&size=large&mtime=<mtime>`
- `default` = bez nahladu (appka ukaze ikonku).
MVP: vzdy `"small,large"`, nahlady generuje server.

## 6. Nahlady: thumb.php, SYNO.PhotoStation.Thumb `get` v1 (GET)
Parametre: `id`, `size` = small|large|preview, `mtime`, `sig` (album), `PHPSESSID`.
- small = 320 px (THUMB_M), large = 1280 px (THUMB_XL), preview = 160 px (THUMB_PREVIEW) - kratsia strana (syno_defines.php).
- Album: nahlad titulnej fotky (prva fotka v albume, ak nie je urcena).
- Hlavicky: `Content-Type: image/jpeg`, `Cache-Control: max-age=604800`, `Last-Modified`, podpora 304.
- Original berie hotove nahlady z `<priecinok>/@eaDir/<subor>/SYNOPHOTO_THUMB_{M,XL,PREVIEW}.jpg`.
  Ci ich Synology Photos na DSM 7 vytvara s rovnakymi menami, **neoverene** (SMB @eaDir skryva).
  Server preto generuje vlastnu cache a hotove subory pouzije, len ak existuju.

## 7. Original a video: download.php, SYNO.PhotoStation.Download (GET)
- `getphoto`: `id=<id>&size=original&mtime=...&PHPSESSID=...` -> subor, podpora HTTP Range.
- `getvideo`: rovnako; appka berie video cez **nesifrovany HTTP port** (getVideoServerUrlPrefix).

## 8. Mimo MVP (appka ich vola, server zatial vrati chybu 103/105)
Upload (File), Album create/edit/delete/move, Photo edit/delete/copy, Comment, Tag, PhotoTag, Category,
SmartAlbum, SharedAlbum, Cover, Timeline getindex. Zoznam: `api_volania_appky.txt`.
Pozor: Album/Photo list odpovede musia byt korektne aj bez tychto API, inak appka spadne pri parsovani.
