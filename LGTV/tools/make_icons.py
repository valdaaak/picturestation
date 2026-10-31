# SPDX-License-Identifier: GPL-3.0-or-later
"""Icons and splash screen of the TV app, drawn with Pillow so that they can be regenerated.

    python3 tools/make_icons.py            (run in LGTV/)

Writes app/icon.png (80x80), app/largeIcon.png (130x130) and app/splash.png (1920x1080): a photo frame
with a hill and a sun on the app's dark background."""
import os

from PIL import Image, ImageDraw

BG = (17, 20, 24)
FRAME = (236, 239, 244)
SKY = (58, 128, 196)
HILL = (76, 160, 96)
SUN = (250, 200, 70)
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app")


def picture(draw, x, y, w, h, scale=1.0):
    """A framed landscape at (x, y) of w x h pixels."""
    r = max(2, int(10 * scale))
    draw.rounded_rectangle((x, y, x + w, y + h), radius=r, fill=FRAME)
    b = max(2, int(w * 0.07))
    ix, iy, iw, ih = x + b, y + b, w - 2 * b, h - 2 * b
    draw.rectangle((ix, iy, ix + iw, iy + ih), fill=SKY)
    sr = int(iw * 0.13)
    draw.ellipse((ix + iw * 0.66 - sr, iy + ih * 0.3 - sr, ix + iw * 0.66 + sr, iy + ih * 0.3 + sr), fill=SUN)
    hill = [(ix, iy + ih), (ix, iy + ih * 0.72), (ix + iw * 0.3, iy + ih * 0.45), (ix + iw * 0.55, iy + ih * 0.68),
            (ix + iw * 0.75, iy + ih * 0.55), (ix + iw, iy + ih * 0.8), (ix + iw, iy + ih)]
    draw.polygon(hill, fill=HILL)


def icon(size, name, transparent):
    s = 4  # draw big, then shrink: Pillow has no anti-aliasing for shapes
    im = Image.new("RGBA", (size * s, size * s), (0, 0, 0, 0) if transparent else BG + (255,))
    d = ImageDraw.Draw(im)
    m = int(size * s * 0.1)
    picture(d, m, int(size * s * 0.2), size * s - 2 * m, int(size * s * 0.6), scale=size * s / 400)
    im = im.resize((size, size), Image.LANCZOS)
    im.save(os.path.join(HERE, name))


def splash():
    w, h = 1920, 1080
    s = 2
    im = Image.new("RGB", (w * s, h * s), BG)
    d = ImageDraw.Draw(im)
    pw, ph = 420 * s, 300 * s
    picture(d, (w * s - pw) // 2, (h * s - ph) // 2 - 60 * s, pw, ph, scale=2.5)
    im = im.resize((w, h), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    # the name, in Pillow's default font scaled up (no font files needed)
    text = Image.new("L", (300, 40), 0)
    ImageDraw.Draw(text).text((2, 2), "Picturestation", fill=255)
    bbox = text.getbbox()
    text = text.crop(bbox).resize(((bbox[2] - bbox[0]) * 5, (bbox[3] - bbox[1]) * 5), Image.NEAREST)
    im.paste(FRAME, ((w - text.width) // 2, h // 2 + 110), text)
    im.save(os.path.join(HERE, "splash.png"))


if __name__ == "__main__":
    icon(80, "icon.png", True)
    icon(130, "largeIcon.png", True)
    splash()
    print("icon.png, largeIcon.png, splash.png written to", os.path.normpath(HERE))
