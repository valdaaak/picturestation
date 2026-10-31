# SPDX-License-Identifier: GPL-3.0-or-later
"""Icons and splash screen of the TV app, drawn with Pillow so that they can be regenerated.

    python3 tools/make_icons.py            (run in LGTV/)

Writes app/icon.png (80x80), app/largeIcon.png (130x130) and app/splash.png (1920x1080): a small stack of
photos, the top one a landscape with a sun, on the app's dark blue tile. Everything is drawn at 4x and
shrunk, because Pillow draws shapes without anti-aliasing."""
import os

from PIL import Image, ImageDraw, ImageFilter

BG_TOP = (34, 48, 68)
BG_BOTTOM = (17, 20, 24)
FRAME = (246, 247, 250)
SKY_TOP = (84, 160, 228)
SKY_BOTTOM = (176, 214, 246)
HILL_BACK = (96, 150, 110)
HILL_FRONT = (58, 118, 78)
SUN = (255, 206, 84)
SUN_GLOW = (255, 230, 150)
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app")


def gradient(size, top, bottom):
    w, h = size
    im = Image.new("RGB", (1, h))
    px = im.load()
    for y in range(h):
        f = y / max(1, h - 1)
        px[0, y] = tuple(int(top[i] + (bottom[i] - top[i]) * f) for i in range(3))
    return im.resize((w, h))


def photo(w, h, landscape=True):
    """One photo: white frame, inside a sky with a sun and two hills (or a plain light grey for the ones behind)."""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=int(w * 0.045), fill=FRAME + (255,))
    b = int(w * 0.075)
    iw, ih = w - 2 * b, h - 2 * b
    if not landscape:
        d.rectangle((b, b, b + iw, b + ih), fill=(214, 220, 228, 255))
        return im
    im.paste(gradient((iw, ih), SKY_TOP, SKY_BOTTOM), (b, b))
    d = ImageDraw.Draw(im)
    # sun with a soft glow
    cx, cy, r = b + iw * 0.7, b + ih * 0.32, iw * 0.11
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((cx - r * 1.8, cy - r * 1.8, cx + r * 1.8, cy + r * 1.8), fill=SUN_GLOW + (120,))
    glow = glow.filter(ImageFilter.GaussianBlur(r * 0.6))
    im.alpha_composite(glow)
    d = ImageDraw.Draw(im)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=SUN + (255,))
    # hills
    x0, y0, x1, y1 = b, b, b + iw, b + ih
    d.polygon([(x0, y1), (x0, y0 + ih * 0.78), (x0 + iw * 0.22, y0 + ih * 0.5), (x0 + iw * 0.42, y0 + ih * 0.68),
               (x0 + iw * 0.62, y0 + ih * 0.46), (x0 + iw * 0.8, y0 + ih * 0.62), (x1, y0 + ih * 0.52), (x1, y1)],
              fill=HILL_BACK + (255,))
    d.polygon([(x0, y1), (x0, y0 + ih * 0.88), (x0 + iw * 0.3, y0 + ih * 0.66), (x0 + iw * 0.55, y0 + ih * 0.84),
               (x0 + iw * 0.78, y0 + ih * 0.7), (x1, y0 + ih * 0.86), (x1, y1)], fill=HILL_FRONT + (255,))
    return im


def stack(size):
    """Three photos fanned out on a transparent canvas of `size` px (drawn at 4x)."""
    s = 4
    c = size * s
    canvas = Image.new("RGBA", (c, c), (0, 0, 0, 0))
    pw, ph = int(c * 0.66), int(c * 0.5)
    for angle, dx, dy, landscape in ((-14, -0.03, 0.02, False), (8, 0.04, 0.0, False), (0, 0.0, -0.02, True)):
        p = photo(pw, ph, landscape)
        shadow = Image.new("RGBA", p.size, (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle((0, 0, pw - 1, ph - 1), radius=int(pw * 0.045), fill=(0, 0, 0, 110))
        for layer, off in ((shadow.filter(ImageFilter.GaussianBlur(c * 0.02)), c * 0.015), (p, 0)):
            layer = layer.rotate(angle, resample=Image.BICUBIC, expand=True)
            x = int((c - layer.width) / 2 + dx * c)
            y = int((c - layer.height) / 2 + dy * c + off)
            canvas.alpha_composite(layer, (x, y))
    return canvas.resize((size, size), Image.LANCZOS)


def tile(size):
    """App icon: rounded dark blue tile with the stack."""
    s = 4
    c = size * s
    im = Image.new("RGBA", (c, c), (0, 0, 0, 0))
    mask = Image.new("L", (c, c), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, c - 1, c - 1), radius=int(c * 0.2), fill=255)
    im.paste(gradient((c, c), BG_TOP, BG_BOTTOM), (0, 0), mask)
    im = im.resize((size, size), Image.LANCZOS)
    im.alpha_composite(stack(size))
    return im


def splash():
    w, h = 1920, 1080
    im = Image.new("RGB", (w, h), BG_BOTTOM)
    im.paste(gradient((w, h), BG_TOP, BG_BOTTOM), (0, 0))
    art = stack(560)
    im.paste(art, ((w - art.width) // 2, (h - art.height) // 2 - 70), art)
    # the name, in Pillow's default font scaled up (no font files needed)
    text = Image.new("L", (300, 40), 0)
    ImageDraw.Draw(text).text((2, 2), "Picturestation", fill=255)
    bbox = text.getbbox()
    text = text.crop(bbox).resize(((bbox[2] - bbox[0]) * 5, (bbox[3] - bbox[1]) * 5), Image.NEAREST)
    im.paste(FRAME, ((w - text.width) // 2, h // 2 + 230), text)
    im.save(os.path.join(HERE, "splash.png"))


if __name__ == "__main__":
    tile(80).save(os.path.join(HERE, "icon.png"))
    tile(130).save(os.path.join(HERE, "largeIcon.png"))
    tile(512).save(os.path.join(HERE, "..", "tools", "icon-preview.png"))
    splash()
    print("icon.png, largeIcon.png, splash.png written to", os.path.normpath(HERE))
