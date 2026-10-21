#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Container start: data folder for PUID/PGID, GeoNames on first start, first administrator, then the server.
set -eu
DATA=${PICTURESTATION_DATA:-/data}
PUID=${PUID:-1000}
PGID=${PGID:-1000}

if [ "$(id -u)" = 0 ]; then
  getent group "$PGID" >/dev/null || groupadd -g "$PGID" picturestation
  getent passwd "$PUID" >/dev/null || useradd -u "$PUID" -g "$PGID" -d "$DATA" -s /usr/sbin/nologin -M picturestation
  mkdir -p "$DATA"
  # only the top folder and our own subfolders, never the photos
  chown "$PUID:$PGID" "$DATA"
  for d in thumbs faces geonames; do
    [ ! -d "$DATA/$d" ] || find "$DATA/$d" \( ! -user "$PUID" -o ! -group "$PGID" \) -exec chown "$PUID:$PGID" {} +
  done
  for f in "$DATA"/*.sqlite*; do [ ! -e "$f" ] || chown "$PUID:$PGID" "$f"; done
  exec setpriv --reuid="$PUID" --regid="$PGID" --init-groups "$0" "$@"
fi

[ -r "${PICTURESTATION_ROOT:-/photos}" ] || echo "warning: photo folder ${PICTURESTATION_ROOT:-/photos} is not readable" >&2

# place names (GeoNames, CC BY 4.0), downloaded once; PICTURESTATION_GEONAMES_DOWNLOAD=0 turns it off
G=${PICTURESTATION_GEONAMES:-$DATA/geonames}
if [ ! -s "$G/cities500.txt" ] && [ "${PICTURESTATION_GEONAMES_DOWNLOAD:-1}" = 1 ]; then
  echo "downloading GeoNames place names (once)"
  mkdir -p "$G"
  if wget -q -O "$G/cities500.zip" https://download.geonames.org/export/dump/cities500.zip \
     && wget -q -O "$G/countryInfo.txt" https://download.geonames.org/export/dump/countryInfo.txt \
     && unzip -o -q "$G/cities500.zip" -d "$G"; then
    rm -f "$G/cities500.zip"
  else
    echo "warning: GeoNames download failed, places stay off until the next start" >&2
    rm -f "$G/cities500.zip" "$G/cities500.txt"
  fi
fi

# small villages for the countries in PICTURESTATION_GEONAMES_COUNTRIES (e.g. SK,CZ), populated places only
for CC in $(printf '%s' "${PICTURESTATION_GEONAMES_COUNTRIES:-}" | tr 'a-z,' 'A-Z '); do
  case "$CC" in [A-Z][A-Z]) ;; *) echo "skipping bad country code: $CC" >&2; continue ;; esac
  [ -s "$G/$CC.txt" ] && continue
  echo "downloading GeoNames villages $CC (once)"
  mkdir -p "$G.tmp"
  if wget -q -O "$G.tmp/$CC.zip" "https://download.geonames.org/export/dump/$CC.zip" \
     && unzip -o -q "$G.tmp/$CC.zip" "$CC.txt" -d "$G.tmp"; then
    awk -F'\t' '$7 == "P"' "$G.tmp/$CC.txt" > "$G/$CC.txt"
  else
    echo "warning: download of $CC failed" >&2
  fi
  rm -rf "$G.tmp"
done

# first administrator: PICTURESTATION_ADMIN_PASSWORD, otherwise a random password printed once
if ! python3 -m picturestation.cli list | grep -v '^@' | grep -v '^ ' | grep -q .; then
  NAME=${PICTURESTATION_ADMIN_USER:-admin}
  PW=${PICTURESTATION_ADMIN_PASSWORD:-}
  if [ -z "$PW" ]; then
    PW=$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')
    (umask 077; printf '%s\n' "$PW" > "$DATA/admin-password.txt")
    echo "============================================================"
    echo " first administrator: $NAME   password: $PW"
    echo " (also in $DATA/admin-password.txt - delete it after you change the password)"
    echo "============================================================"
  fi
  printf '%s\n' "$PW" | python3 -m picturestation.cli useradd "$NAME" --admin --stdin >/dev/null
fi

if [ $# -gt 0 ]; then exec "$@"; fi
exec python3 -m picturestation
