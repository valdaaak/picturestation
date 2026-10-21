#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Picturestation installer for Debian 13 (trixie). Run as root from the source tree; safe to re-run.
#
#   install.sh [--photos DIR] [--nfs SERVER:/export] [--port N] [--title TEXT]
#              [--admin NAME] [--admin-pass-file FILE] [--update]
#
#   --photos DIR          folder with photos (default /mnt/photo)
#   --nfs SERVER:/export  mount this NFS export read-only at --photos (fstab, automount)
#   --port N              HTTP port (default 80)
#   --title TEXT          gallery title
#   --admin NAME          name of the first administrator (default admin)
#   --admin-pass-file F   write the generated admin password to F instead of printing it
#   --update              only install new code and restart services, keep settings
set -eu

SRC=$(cd "$(dirname "$0")/.." && pwd)
PHOTOS=/mnt/photo NFS="" PORT=80 TITLE=Picturestation ADMIN=admin PASSFILE="" UPDATE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --photos) PHOTOS=$2; shift 2 ;;
    --nfs) NFS=$2; shift 2 ;;
    --port) PORT=$2; shift 2 ;;
    --title) TITLE=$2; shift 2 ;;
    --admin) ADMIN=$2; shift 2 ;;
    --admin-pass-file) PASSFILE=$2; shift 2 ;;
    --update) UPDATE=1; shift ;;
    -h|--help) sed -n '3,15p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }
[ -f "$SRC/server/picturestation/app.py" ] || { echo "source tree not found in $SRC" >&2; exit 1; }
case "$PORT" in *[!0-9]*|"") echo "bad port: $PORT" >&2; exit 2 ;; esac
case "$PHOTOS" in /*) ;; *) echo "--photos must be an absolute path" >&2; exit 2 ;; esac

ETC=/etc/picturestation
DATA=/var/lib/picturestation
ENVF=$ETC/picturestation.env
U=picturestation

echo "== packages"
export DEBIAN_FRONTEND=noninteractive
PKGS="python3 python3-starlette python3-uvicorn python3-pil ffmpeg sqlite3 wget unzip ca-certificates"
[ -n "$NFS" ] && PKGS="$PKGS nfs-common"
apt-get -o DPkg::Lock::Timeout=600 -qq update >/dev/null
apt-get -o DPkg::Lock::Timeout=600 -qq install -y $PKGS >/dev/null

echo "== user and folders"
id "$U" >/dev/null 2>&1 || useradd --system --home-dir "$DATA" --shell /usr/sbin/nologin "$U"
install -d -o "$U" -g "$U" -m 750 "$DATA"
install -d -m 755 /opt/picturestation "$ETC"

# GeoNames (places with more than 500 inhabitants, CC BY 4.0) - downloaded once, then offline
G=$DATA/geonames
if [ ! -s "$G/cities500.txt" ]; then
  echo "== GeoNames"
  install -d -o "$U" -g "$U" "$G"
  wget -q -O "$G/cities500.zip" https://download.geonames.org/export/dump/cities500.zip
  wget -q -O "$G/countryInfo.txt" https://download.geonames.org/export/dump/countryInfo.txt
  unzip -o -q "$G/cities500.zip" -d "$G" && rm -f "$G/cities500.zip"
  chown -R "$U:$U" "$G"
fi

echo "== code"
rm -rf /opt/picturestation/picturestation
cp -r "$SRC/server/picturestation" /opt/picturestation/
find /opt/picturestation -name __pycache__ -prune -exec rm -rf {} +
install -m 644 "$SRC/install/picturestation.service" /etc/systemd/system/picturestation.service
install -m 644 "$SRC/install/picturestation@.service" /etc/systemd/system/picturestation@.service
install -m 755 "$SRC/install/instance.sh" /usr/local/sbin/picturestation-instance
install -m 755 "$SRC/install/picturestation-user" /usr/local/bin/picturestation-user

if [ "$UPDATE" = 0 ]; then
  if [ ! -f "$ENVF" ]; then
    echo "== settings $ENVF"
    sed -e "s#^PICTURESTATION_ROOT=.*#PICTURESTATION_ROOT=$PHOTOS#" \
        -e "s#^PICTURESTATION_PORT=.*#PICTURESTATION_PORT=$PORT#" \
        -e "s#^PICTURESTATION_TITLE=.*#PICTURESTATION_TITLE=$TITLE#" \
        "$SRC/install/picturestation.env.example" > "$ENVF"
    chmod 644 "$ENVF"
  fi
  if [ -n "$NFS" ] && ! grep -q "[[:space:]]$PHOTOS[[:space:]]" /etc/fstab; then
    echo "== NFS $NFS -> $PHOTOS (read-only)"
    install -d -m 755 "$PHOTOS"
    echo "$NFS $PHOTOS nfs4 ro,hard,noatime,nofail,_netdev,x-systemd.automount,x-systemd.mount-timeout=30 0 0" >> /etc/fstab
    systemctl daemon-reload
    systemctl restart remote-fs.target
  fi
fi

# small villages: full GeoNames dumps for the countries in PICTURESTATION_GEONAMES_COUNTRIES (e.g. SK,CZ),
# only populated places are kept; the gallery looks the places up again after a change
COUNTRIES=$(sed -n 's/^PICTURESTATION_GEONAMES_COUNTRIES=//p' "$ENVF" | tail -n 1 | tr 'a-z,' 'A-Z ')
for CC in $COUNTRIES; do
  case "$CC" in [A-Z][A-Z]) ;; *) echo "skipping bad country code: $CC" >&2; continue ;; esac
  # older files without municipalities (ADM3) are downloaded again
  [ -s "$G/$CC.txt" ] && grep -q "	ADM3	" "$G/$CC.txt" && continue
  echo "== GeoNames villages $CC"
  if wget -q -O "$G/$CC.zip" "https://download.geonames.org/export/dump/$CC.zip" \
     && unzip -o -q "$G/$CC.zip" "$CC.txt" -d "$G.tmp"; then
    awk -F'\t' '$7 == "P" || $8 == "ADM3"' "$G.tmp/$CC.txt" > "$G/$CC.txt"
    chown "$U:$U" "$G/$CC.txt"
  else
    echo "warning: download of $CC failed" >&2
  fi
  rm -rf "$G/$CC.zip" "$G.tmp"
done

# photo folder other than /mnt/photo: the unit needs to know it
ROOT=$(sed -n 's/^\(PICTURESTATION\|DSPHOTO\)_ROOT=//p' "$ENVF" | tail -n 1)
ROOT=${ROOT:-/mnt/photo}
if [ "$ROOT" != /mnt/photo ]; then
  install -d -m 755 /etc/systemd/system/picturestation.service.d
  printf '[Unit]\nRequiresMountsFor=%s\n\n[Service]\nReadOnlyPaths=\nReadOnlyPaths=%s\n' "$ROOT" "$ROOT" \
    > /etc/systemd/system/picturestation.service.d/photos.conf
else
  rm -f /etc/systemd/system/picturestation.service.d/photos.conf
fi
[ -d "$ROOT" ] || install -d -m 755 "$ROOT"

echo "== services"
systemctl daemon-reload
systemctl enable picturestation >/dev/null 2>&1
systemctl restart picturestation
for u in $(systemctl list-units --plain --no-legend 'picturestation@*.service' | awk '{print $1}'); do
  systemctl restart "$u"
done

if [ "$UPDATE" = 0 ] && ! /usr/local/bin/picturestation-user list | grep -v '^@' | grep -v '^ ' | grep -q .; then
  PW=$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')
  printf '%s\n' "$PW" | /usr/local/bin/picturestation-user useradd "$ADMIN" --admin --stdin >/dev/null
  if [ -n "$PASSFILE" ]; then
    (umask 077; printf '%s\n' "$PW" > "$PASSFILE")
    MSG="password in $PASSFILE"
  else
    MSG="password: $PW"
  fi
  echo "== administrator $ADMIN, $MSG"
fi

sleep 2
if systemctl is-active --quiet picturestation; then
  IP=$(hostname -I 2>/dev/null | awk '{print $1}')
  [ "$PORT" = 80 ] && URL="http://$IP/" || URL="http://$IP:$PORT/"
  VER=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' /opt/picturestation/picturestation/__init__.py)
  echo "== Picturestation $VER is running: $URL"
else
  echo "== service failed, see: journalctl -u picturestation" >&2
  exit 1
fi
