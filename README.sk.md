# Picturestation

**Fotogaléria kompatibilná s Photo Station 6 pre Synology DSM 7.** [English version](README.md)

Synology v DSM 7 zrušilo Photo Station. Synology Photos nemá práva na albumy pre skupiny ani albumy pre hostí s heslom a appka DS photo sa k nemu nepripojí. Picturestation to vracia. Je to malý server, ktorý číta priečinok s fotkami iba na čítanie a ponúka:

- **webovú galériu** s albumami, časovou osou, hľadaním, tagmi, miestami, ľuďmi a chytrými albumami, po slovensky aj po anglicky;
- **appku DS photo** (Android), ktorá sa k nemu pripojí ako k Photo Station 6;
- **práva ako v Photo Station**: používatelia, skupiny, hostia, albumy s heslom, vylúčené albumy, odkazy na zdieľanie s platnosťou;
- **ľudí zo Synology Photos**: rozpoznávanie tvárí ostáva v Synology Photos, Picturestation zobrazí pomenovaných ľudí;
- **náhľady**, ktoré už DSM vytvoril v `@eaDir`, a vlastnú vyrovnávaciu pamäť pre ostatné.

Fotky sa nikdy nemenia. Picturestation potrebuje len právo na čítanie. Svoje údaje (používateľov, práva, komentáre, náhľady) má v jednom priečinku.

Picturestation nie je produkt Synology a Synology ho nepodporuje. Synology, DSM, Photo Station, DS photo a Synology Photos sú ochranné známky Synology Inc.

## Inštalácia na Proxmox VE

V shelli Proxmox hostiteľa ako root:

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/valdaaak/picturestation/main/install/proxmox.sh)"
```

Inštalátor sa opýta, či chceš kontajner (LXC, predvolený) alebo virtuálny stroj, a potom na názov, IP adresu a NFS export s fotkami. Na konci vypíše adresu a heslo používateľa `admin`. Všetky voľby sú v `proxmox.sh --help`.

## Inštalácia na Debian 13

```sh
apt install git
git clone https://github.com/valdaaak/picturestation.git /opt/picturestation-src
sh /opt/picturestation-src/install/install.sh --nfs 192.168.1.10:/volume1/photo
```

## NFS na DSM

1. **Zapni NFS.** V Ovládacom paneli otvor Súborové služby, potom NFS, a zapni ho.
2. **Vytvor pravidlo.** V Ovládacom paneli otvor Zdieľaný priečinok, vyber `photo`, zvoľ Upraviť, potom Povolenia NFS, a vytvor pravidlo:
   - adresa Picturestation (pri kontajneri adresa Proxmox hostiteľa);
   - **Len na čítanie**;
   - Squash **Mapovať všetkých používateľov na admin**;
   - zapnuté **Povoliť používateľom prístup k pripojeným podpriečinkom**.
3. **Použi cestu pripojenia.** Dialóg ukáže cestu, napríklad `/volume1/photo`. Pri inštalácii ju zadaj v tvare `SERVER:/volume1/photo`.

## Ďalej

- **Ostatné témy** sú podrobne v [anglickom README](README.md):
  - HTTPS cez reverse proxy v DSM;
  - appka DS photo;
  - ľudia zo Synology Photos;
  - osobné galérie z domovských priečinkov;
  - prechod z Photo Station 6;
  - zálohovanie.
- **Galéria má jazyk podľa prehliadača.** Prepnúť ho môžeš vpravo hore. Predvolený jazyk nastavíš v Nastaveniach, v časti Všeobecné.

Licencia [GPL-3.0-or-later](LICENSE). Názvy miest pochádzajú z [GeoNames](https://www.geonames.org/) (CC BY 4.0).
