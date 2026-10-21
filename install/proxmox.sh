#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Picturestation on Proxmox VE: creates a Debian 13 container (LXC, default) or VM and installs the gallery.
# Run as root on the Proxmox host:
#
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/valdaaak/picturestation/main/install/proxmox.sh)"
#
# Without options it asks a few questions. Non-interactive:
#
#   proxmox.sh --yes --type lxc --nfs nas.example.com:/volume1/photo --ip dhcp
#
#   --type lxc|vm         container (light, default) or virtual machine
#   --id N                guest id (default: next free)
#   --hostname NAME       default picturestation
#   --storage NAME        disk storage (default: first one that fits)
#   --bridge NAME         network bridge (default vmbr0)
#   --ip dhcp|CIDR        address, e.g. 192.168.1.50/24 (default dhcp)
#   --gw IP               gateway for a static address
#   --memory MB           default 2048
#   --cores N             default 2
#   --disk GB             default 8 (lxc) / 16 (vm)
#   --nfs SERVER:/export  photos from an NFS export, read-only (e.g. the Synology "photo" share)
#   --photos-host DIR     lxc only: photos from a folder on this host (read-only bind mount)
#   --port N              HTTP port inside the guest (default 80)
#   --repo URL --branch B source (default: GitHub, main)
#   --tarball FILE        install from a local source archive (tar.gz of the repository) instead of git
#   --yes                 do not ask, use the options and defaults
set -euo pipefail
# pct exec passes the host locale into the guest, where it may not exist (perl/apt warnings)
export LANG=C.UTF-8 LC_ALL=C.UTF-8

REPO=https://github.com/valdaaak/picturestation.git
BRANCH=main
TYPE=lxc ID="" HOSTNAME_=picturestation STORAGE="" BRIDGE=vmbr0 IP=dhcp GW="" MEMORY="" CORES=2 DISK=""
NFS="" PHOTOS_HOST="" PORT=80 TARBALL="" YES=0

die() { echo "error: $*" >&2; exit 1; }
say() { echo "== $*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --type) TYPE=$2; shift 2 ;;
    --id) ID=$2; shift 2 ;;
    --hostname) HOSTNAME_=$2; shift 2 ;;
    --storage) STORAGE=$2; shift 2 ;;
    --bridge) BRIDGE=$2; shift 2 ;;
    --ip) IP=$2; shift 2 ;;
    --gw) GW=$2; shift 2 ;;
    --memory) MEMORY=$2; shift 2 ;;
    --cores) CORES=$2; shift 2 ;;
    --disk) DISK=$2; shift 2 ;;
    --nfs) NFS=$2; shift 2 ;;
    --photos-host) PHOTOS_HOST=$2; shift 2 ;;
    --port) PORT=$2; shift 2 ;;
    --repo) REPO=$2; shift 2 ;;
    --branch) BRANCH=$2; shift 2 ;;
    --tarball) TARBALL=$(readlink -f "$2"); shift 2 ;;
    --yes|-y) YES=1; shift ;;
    -h|--help) sed -n '3,30p' "$0"; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

[ "$(id -u)" = 0 ] || die "run as root on the Proxmox host"
command -v pveversion >/dev/null || die "this is not a Proxmox VE host"

ask() {  # ask VAR "question" default
  local v
  v=$(whiptail --title "Picturestation" --inputbox "$2" 10 70 "$3" 3>&1 1>&2 2>&3) || die "cancelled"
  printf -v "$1" '%s' "$v"
}
if [ "$YES" = 0 ] && [ -t 0 ] && command -v whiptail >/dev/null; then
  TYPE=$(whiptail --title "Picturestation" --menu "Install into" 12 70 2 \
    lxc "Container (LXC) - light, recommended" vm "Virtual machine" 3>&1 1>&2 2>&3) || die "cancelled"
  ask HOSTNAME_ "Host name" "$HOSTNAME_"
  ask IP "IP address: dhcp, or static with prefix (192.168.1.50/24)" "$IP"
  if [ "$IP" != dhcp ]; then ask GW "Gateway" "$GW"; fi
  ask NFS "NFS export with photos, read-only (server:/volume1/photo), empty = later" "$NFS"
fi

case "$TYPE" in lxc|vm) ;; *) die "--type must be lxc or vm" ;; esac
[ -z "$PHOTOS_HOST" ] || [ "$TYPE" = lxc ] || die "--photos-host works only with --type lxc"
[ -z "$NFS" ] || [ -z "$PHOTOS_HOST" ] || die "use --nfs or --photos-host, not both"
case "$NFS" in ""|*:/*) ;; *) die "--nfs must look like server:/export" ;; esac
[ -n "$ID" ] || ID=$(pvesh get /cluster/nextid)
[ -n "$MEMORY" ] || MEMORY=2048
[ -n "$DISK" ] || { [ "$TYPE" = lxc ] && DISK=8 || DISK=16; }
if [ "$IP" = dhcp ]; then NETIP="ip=dhcp"; else NETIP="ip=$IP${GW:+,gw=$GW}"; fi
if [ -z "$STORAGE" ]; then
  want=$([ "$TYPE" = lxc ] && echo rootdir || echo images)
  STORAGE=$(pvesm status -content "$want" 2>/dev/null | awk 'NR>1 && $3=="active" && !f {print $1; f=1}')
  [ -n "$STORAGE" ] || die "no active storage for $want, use --storage"
fi
[ -z "$TARBALL" ] || [ -f "$TARBALL" ] || die "tarball not found: $TARBALL"

# source code: a local archive or a fresh git checkout, packed for transfer into the guest
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
if [ -n "$TARBALL" ]; then
  cp "$TARBALL" "$WORK/src.tar.gz"
else
  command -v git >/dev/null || apt-get -o DPkg::Lock::Timeout=600 -qq install -y git >/dev/null
  say "downloading $REPO ($BRANCH)"
  git clone -q --depth 1 -b "$BRANCH" "$REPO" "$WORK/src"
  tar -czf "$WORK/src.tar.gz" -C "$WORK/src" --exclude=.git .
fi
case "$(tar -tzf "$WORK/src.tar.gz")" in *install/install.sh*) ;; *) die "the source archive has no install/install.sh" ;; esac

INSTALL_ARGS="--port $PORT --admin-pass-file /root/picturestation-admin.pass"

# NFS on the host, handed to the container read-only (an unprivileged container cannot mount NFS)
host_nfs() {
  local mnt=/mnt/picturestation-$ID
  command -v mount.nfs4 >/dev/null || apt-get -o DPkg::Lock::Timeout=600 -qq install -y nfs-common >/dev/null
  install -d -m 755 "$mnt"
  if ! grep -q "[[:space:]]$mnt[[:space:]]" /etc/fstab; then
    echo "$NFS $mnt nfs4 ro,hard,noatime,nofail,_netdev 0 0" >> /etc/fstab
  fi
  systemctl daemon-reload
  mountpoint -q "$mnt" || mount "$mnt" || die "cannot mount $NFS (NFS permission for this host on the NAS?)"
  # guests start after network file systems (nofail: an unreachable NAS does not block them)
  install -d /etc/systemd/system/pve-guests.service.d
  printf '[Unit]\nAfter=remote-fs.target\n' > /etc/systemd/system/pve-guests.service.d/picturestation-nfs.conf
  systemctl daemon-reload
  PHOTOS_HOST=$mnt
}

create_lxc() {
  local tstore tmpl
  tstore=$(pvesm status -content vztmpl 2>/dev/null | awk 'NR>1 && $3=="active" && !f {print $1; f=1}')
  [ -n "$tstore" ] || die "no storage for container templates"
  pveam update >/dev/null 2>&1 || true
  tmpl=$(pveam available --section system | awk '$2 ~ /^debian-13-standard_.*_amd64/ {print $2}' | sort -V | tail -n 1)
  [ -n "$tmpl" ] || die "Debian 13 template not found (pveam available)"
  case "$(pveam list "$tstore")" in
    *"$tmpl"*) ;;
    *) say "downloading template $tmpl"; pveam download "$tstore" "$tmpl" >/dev/null ;;
  esac

  [ -z "$NFS" ] || host_nfs
  say "creating container $ID ($HOSTNAME_)"
  pct create "$ID" "$tstore:vztmpl/$tmpl" --hostname "$HOSTNAME_" --memory "$MEMORY" --swap 512 --cores "$CORES" \
    --rootfs "$STORAGE:$DISK" --net0 "name=eth0,bridge=$BRIDGE,$NETIP" --unprivileged 1 --features nesting=1 \
    --onboot 1 --ostype debian >/dev/null
  if [ -n "$PHOTOS_HOST" ]; then
    [ -d "$PHOTOS_HOST" ] || die "folder not found: $PHOTOS_HOST"
    pct set "$ID" --mp0 "$PHOTOS_HOST,mp=/mnt/photo,ro=1"
  fi
  pct start "$ID"
  say "waiting for the network"
  for _ in $(seq 60); do
    pct exec "$ID" -- getent hosts deb.debian.org >/dev/null 2>&1 && break
    sleep 2
  done
  pct exec "$ID" -- getent hosts deb.debian.org >/dev/null 2>&1 || die "the container has no network/DNS"
  pct push "$ID" "$WORK/src.tar.gz" /root/picturestation-src.tar.gz
  say "installing Picturestation (a few minutes)"
  pct exec "$ID" -- bash -c "set -e; rm -rf /opt/picturestation-src; mkdir -p /opt/picturestation-src
    tar -xzf /root/picturestation-src.tar.gz -C /opt/picturestation-src; rm /root/picturestation-src.tar.gz
    sh /opt/picturestation-src/install/install.sh $INSTALL_ARGS"
  PASS=$(pct exec "$ID" -- cat /root/picturestation-admin.pass 2>/dev/null || true)
  ADDR=$(pct exec "$ID" -- hostname -I | awk '{print $1}')
}

guest() {  # run a command in the VM through the guest agent, print its stdout
  qm guest exec "$ID" --timeout 0 -- "$@" 2>/dev/null | python3 -c 'import json,sys
d = json.load(sys.stdin); sys.stdout.write(d.get("out-data", "")); sys.exit(d.get("exitcode", 1))'
}

create_vm() {
  local img=/var/lib/vz/template/cache/debian-13-genericcloud-amd64.qcow2 snip snipdir key b64
  snip=$(pvesm status -content snippets 2>/dev/null | awk 'NR>1 && $3=="active" && !f {print $1; f=1}')
  if [ -z "$snip" ]; then
    if [ "$YES" = 1 ] || whiptail --yesno "Storage 'local' does not allow snippets (needed for cloud-init). Enable it?" 9 70; then
      pvesm set local --content "$(awk '/^dir: local$/ {f=1; next} f && /content/ && !d {print $2; d=1}' /etc/pve/storage.cfg),snippets"
      snip=local
    else
      die "a storage with the snippets content type is needed"
    fi
  fi
  snipdir=$(pvesm path "$snip:snippets/x" | sed 's#/x$##')
  install -d "$snipdir"
  if [ ! -s "$img" ] || [ -n "$(find "$img" -mtime +30)" ]; then
    say "downloading the Debian 13 cloud image"
    wget -q -O "$img.part" https://cloud.debian.org/images/cloud/trixie/latest/debian-13-genericcloud-amd64.qcow2
    mv "$img.part" "$img"
  fi
  b64=$(base64 -w0 "$WORK/src.tar.gz")
  local nfsarg=""
  [ -z "$NFS" ] || nfsarg="--nfs $NFS"
  cat > "$snipdir/picturestation-$ID.yaml" <<EOF
#cloud-config
package_update: true
packages: [qemu-guest-agent]
write_files:
  - path: /root/picturestation-src.tar.gz
    encoding: b64
    permissions: '0600'
    content: $b64
runcmd:
  - [systemctl, enable, --now, qemu-guest-agent]
  - [sh, -c, "mkdir -p /opt/picturestation-src && tar -xzf /root/picturestation-src.tar.gz -C /opt/picturestation-src && rm /root/picturestation-src.tar.gz"]
  - [sh, -c, "sh /opt/picturestation-src/install/install.sh $INSTALL_ARGS $nfsarg > /root/picturestation-install.log 2>&1"]
EOF
  say "creating virtual machine $ID ($HOSTNAME_)"
  qm create "$ID" --name "$HOSTNAME_" --memory "$MEMORY" --cores "$CORES" --cpu host --ostype l26 \
    --net0 "virtio,bridge=$BRIDGE" --scsihw virtio-scsi-single --agent enabled=1 --onboot 1 \
    --serial0 socket --vga serial0 >/dev/null
  qm set "$ID" --scsi0 "$STORAGE:0,import-from=$img,discard=on" >/dev/null
  qm resize "$ID" scsi0 "${DISK}G" >/dev/null
  qm set "$ID" --ide2 "$STORAGE:cloudinit" --boot order=scsi0 --ipconfig0 "$NETIP" \
    --cicustom "vendor=$snip:snippets/picturestation-$ID.yaml" >/dev/null
  key=$(find /root/.ssh -maxdepth 1 -name 'id_*.pub' 2>/dev/null | sort | sed -n 1p)
  [ -z "$key" ] || qm set "$ID" --sshkeys "$key" >/dev/null
  qm start "$ID"
  say "installing Picturestation inside the VM (5-10 minutes)"
  for _ in $(seq 180); do
    if guest test -s /root/picturestation-admin.pass >/dev/null 2>&1 \
       || guest grep -q "Picturestation is running\|service failed" /root/picturestation-install.log >/dev/null 2>&1; then
      break
    fi
    sleep 5
  done
  guest tail -n 3 /root/picturestation-install.log || true
  PASS=$(guest cat /root/picturestation-admin.pass || true)
  ADDR=$(guest hostname -I | awk '{print $1}' || true)
}

if [ "$TYPE" = lxc ]; then create_lxc; else create_vm; fi

URL="http://${ADDR:-<address>}$([ "$PORT" = 80 ] || echo ":$PORT")/"
echo
echo "Picturestation ($TYPE $ID) : $URL"
if [ -n "${PASS:-}" ]; then
  echo "administrator: admin, password: $PASS"
  echo "(also in /root/picturestation-admin.pass inside the guest; change it in Settings > Users)"
else
  echo "the installation did not finish, see /root/picturestation-install.log in the guest" >&2
  exit 1
fi
[ -n "$NFS$PHOTOS_HOST" ] || echo "no photo folder yet: mount your photos at /mnt/photo in the guest"
