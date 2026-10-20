#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Personal gallery: a separate Picturestation (own database, users, port) for one person's photos,
# e.g. a folder inside their DSM home. Run as root; safe to re-run.
#
#   picturestation-instance NAME SOURCE PORT "TITLE"
#     NAME    lower-case name, also the owner's login (the owner is the gallery administrator)
#     SOURCE  NFS export (server:/volume1/homes/alice/Photos) or a local folder
#   picturestation-instance alice nas.example.com:/volume1/homes/alice/Photos 8081 "Alice's photos"
#
# The owner's password is generated once and written to /root/picturestation-NAME.pass.
set -eu
[ $# -eq 4 ] || { sed -n '3,10p' "$0" >&2; exit 2; }
NAME=$1 SRC=$2 PORT=$3 TITLE=$4
case "$NAME" in *[!a-z0-9_-]*|"") echo "bad name: $NAME" >&2; exit 2 ;; esac
case "$PORT" in *[!0-9]*|"") echo "bad port: $PORT" >&2; exit 2 ;; esac
[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }

MNT=/mnt/picturestation/$NAME
DATA=/var/lib/picturestation-$NAME
ENVF=/etc/picturestation/$NAME.env
COOKIE=PS_$(echo "$NAME" | tr 'a-z-' 'A-Z_')

[ -f /opt/picturestation/picturestation/__main__.py ] || { echo "install Picturestation first (install.sh)" >&2; exit 1; }
[ -f /etc/systemd/system/picturestation@.service ] || { echo "picturestation@.service missing, re-run install.sh" >&2; exit 1; }

install -d -m 755 /mnt/picturestation "$MNT"
install -d -o picturestation -g picturestation -m 750 "$DATA"

if ! grep -q "[[:space:]]$MNT[[:space:]]" /etc/fstab; then
  case "$SRC" in
    /*) echo "$SRC $MNT none bind,ro,nofail 0 0" >> /etc/fstab ;;
    *:/*)
      command -v mount.nfs4 >/dev/null || apt-get -qq install -y nfs-common >/dev/null
      echo "$SRC $MNT nfs4 ro,hard,noatime,nofail,_netdev,x-systemd.automount,x-systemd.mount-timeout=30 0 0" >> /etc/fstab ;;
    *) echo "SOURCE must be server:/export or /local/folder" >&2; exit 2 ;;
  esac
  systemctl daemon-reload
  mount "$MNT" 2>/dev/null || true
fi
ls "$MNT" >/dev/null || { echo "cannot read $MNT (NFS permission on the NAS?)" >&2; exit 1; }

if [ ! -f "$ENVF" ]; then
  cat > "$ENVF" <<EOF
PICTURESTATION_ROOT=$MNT
PICTURESTATION_DATA=$DATA
PICTURESTATION_TITLE=$TITLE
PICTURESTATION_PORT=$PORT
PICTURESTATION_COOKIE=$COOKIE
PICTURESTATION_GEONAMES=/var/lib/picturestation/geonames
PICTURESTATION_INDEX_INTERVAL=3600
PICTURESTATION_THUMB_WORKERS=1
PICTURESTATION_LOG=INFO
PICTURESTATION_ACCESS_LOG=0
EOF
  # same trusted reverse proxies as the main gallery
  grep -h '^\(PICTURESTATION\|DSPHOTO\)_TRUSTED_PROXIES=' /etc/picturestation/picturestation.env 2>/dev/null \
    | tail -n 1 | sed 's/^DSPHOTO_/PICTURESTATION_/' >> "$ENVF" || true
  chmod 644 "$ENVF"
fi

systemctl daemon-reload
systemctl enable "picturestation@$NAME" >/dev/null 2>&1
systemctl restart "picturestation@$NAME"

if ! picturestation-user -i "$NAME" list | awk '{print $1}' | grep -qx "$NAME"; then
  PW=$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')
  (umask 077; printf '%s\n' "$PW" > "/root/picturestation-$NAME.pass")
  printf '%s\n' "$PW" | picturestation-user -i "$NAME" useradd "$NAME" --admin --stdin --note "owner" >/dev/null
  echo "owner $NAME, password in /root/picturestation-$NAME.pass"
fi
sleep 2
systemctl is-active "picturestation@$NAME"
