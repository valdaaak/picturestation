# SPDX-License-Identifier: GPL-3.0-or-later
"""Demo photo library with generated landscapes (dates and GPS in EXIF), for trying Picturestation out.

    python3 make_demo.py /tmp/picturestation-demo
"""
import math
import os
import random
import sys

from PIL import Image, ImageDraw, ImageFilter

ALBUMS = [
    # folder, date, (lat, lng) or None, palette
    ("2023/2023-05-20 Vienna", "2023:05:20", (48.2085, 16.3721), "spring"),
    ("2024/2024-02-10 Snow", "2024:02:10", (49.1795, 20.0880), "winter"),
    ("2024/2024-07-14 Mountains", "2024:07:14", (47.4210, 10.9850), "summer"),
    ("2024/2024-08-02 Seaside", "2024:08:02", (43.5081, 16.4402), "sea"),
    ("2025/2025-01-03 Winter walk", "2025:01:03", (48.1482, 17.1067), "winter"),
    ("2025/2025-06-21 Midsummer", "2025:06:21", (59.3293, 18.0686), "evening"),
    ("Family", None, None, "spring"),
]
PALETTES = {
    "spring": ((120, 180, 240), (230, 240, 250), [(70, 140, 70), (40, 100, 50), (30, 70, 40)], (255, 230, 120)),
    "summer": ((60, 130, 220), (200, 225, 250), [(110, 120, 140), (80, 95, 110), (50, 90, 60)], (255, 240, 170)),
    "sea": ((40, 120, 210), (180, 220, 245), [(30, 110, 160), (20, 80, 130), (230, 210, 160)], (255, 250, 200)),
    "winter": ((150, 170, 200), (235, 240, 248), [(220, 228, 238), (190, 200, 215), (120, 130, 150)], (255, 255, 240)),
    "evening": ((40, 30, 90), (250, 150, 90), [(60, 50, 80), (40, 35, 60), (25, 20, 40)], (255, 200, 120)),
}


def landscape(w, h, pal, rnd):
    top, bottom, layers, sun = pal
    im = Image.new("RGB", (w, h))
    px = ImageDraw.Draw(im)
    for y in range(h):
        k = y / h
        px.line([(0, y), (w, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * k) for i in range(3)))
    d = ImageDraw.Draw(im)
    sx, sy, r = rnd.randint(w // 5, w * 4 // 5), rnd.randint(h // 8, h // 3), rnd.randint(h // 18, h // 10)
    d.ellipse([sx - r, sy - r, sx + r, sy + r], fill=sun)
    im = im.filter(ImageFilter.GaussianBlur(2))
    d = ImageDraw.Draw(im)
    for n, col in enumerate(layers):
        base = h * (0.45 + 0.17 * n)
        amp = h * (0.16 - 0.04 * n)
        ph, fr = rnd.random() * 6, rnd.uniform(1.5, 4.0)
        pts = [(0, h)]
        for x in range(0, w + 20, 20):
            y = base - amp * (0.6 * math.sin(fr * x / w * 3.1 + ph) + 0.4 * math.sin(fr * 2.3 * x / w * 3.1 + ph * 1.7))
            pts.append((x, y + rnd.uniform(-4, 4)))
        pts.append((w, h))
        d.polygon(pts, fill=col)
    return im


def exif(date, gps, n):
    ex = Image.Exif()
    ex[0x010F] = "Picturestation"
    ex[0x0110] = "Demo Camera"
    if date:
        ex.get_ifd(0x8769)[0x9003] = f"{date} {10 + n % 8:02d}:{(n * 7) % 60:02d}:00"
    if gps:
        lat, lng = gps

        def dms(v):
            v = abs(v)
            d, m = int(v), int((v - int(v)) * 60)
            return (float(d), float(m), round(((v - d) * 60 - m) * 60, 2))
        g = ex.get_ifd(0x8825)
        g[1], g[2], g[3], g[4] = ("N" if lat >= 0 else "S"), dms(lat), ("E" if lng >= 0 else "W"), dms(lng)
    return ex.tobytes()


def main(root):
    rnd = random.Random(42)
    n = 0
    for folder, date, gps, pal in ALBUMS:
        os.makedirs(os.path.join(root, folder), exist_ok=True)
        for i in range(rnd.randint(6, 10)):
            portrait = i % 4 == 3
            w, h = (1067, 1600) if portrait else (1600, 1067)
            im = landscape(w, h, PALETTES[pal], rnd)
            im.save(os.path.join(root, folder, f"IMG_{1000 + n}.jpg"), "JPEG", quality=85, exif=exif(date, gps, n))
            n += 1
    for i in range(2):
        landscape(1600, 1067, PALETTES["summer"], rnd).save(
            os.path.join(root, f"IMG_{9000 + i}.jpg"), "JPEG", quality=85, exif=exif("2025:09:01", None, i))
    print(f"{n + 2} photos in {root}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "picturestation-demo")
