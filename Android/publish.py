# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare a release of the Android app for the server's /app/ folder.

    python3 publish.py DIR        copies the signed release APK into DIR as Picturestation.apk and writes
                                  DIR/version.json (versionCode, versionName from app/build.gradle.kts)

Then put DIR's two files into DATA/app on the server (/var/lib/picturestation/app/). The app on the phones
and TVs checks version.json at start and offers the update."""
import hashlib
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APK = os.path.join(HERE, "app", "build", "outputs", "apk", "release", "app-release.apk")


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    gradle = open(os.path.join(HERE, "app", "build.gradle.kts"), encoding="utf-8").read()
    code = int(re.search(r"versionCode\s*=\s*(\d+)", gradle).group(1))
    name = re.search(r'versionName\s*=\s*"([^"]+)"', gradle).group(1)
    if not os.path.exists(APK):
        sys.exit("no release APK; run ./gradlew assembleRelease first")
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    shutil.copyfile(APK, os.path.join(out, "Picturestation.apk"))
    with open(APK, "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()   # the app checks the download against it
    with open(os.path.join(out, "version.json"), "w", encoding="utf-8") as fh:
        json.dump({"versionCode": code, "versionName": name, "apk": "Picturestation.apk", "sha256": sha}, fh)
    print(f"Picturestation {name} (versionCode {code}) in {out}")


if __name__ == "__main__":
    main()
