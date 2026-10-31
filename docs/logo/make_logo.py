# SPDX-License-Identifier: GPL-3.0-or-later
"""Logo of Picturestation, drawn with Pillow (see philosophy.md). Draws at high resolution and shrinks.

    python3 make_logo.py sheet        variants.png: four candidate marks, dark and light, with the wordmark
    python3 make_logo.py final NAME   the chosen mark (a, b, c or d) as app icons, favicon, header and splash
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(os.path.expanduser("~"), ".claude", "skills", "synced",
                     "cc380381-c4d6-4471-bc1f-a35bab5e45b7_c857adb3-0b0f-4f7d-bee4-fd306c09924a",
                     "canvas-design", "canvas-fonts")
NAVY = (15, 23, 42)
NAVY_LIGHT = (30, 41, 59)
PAPER = (246, 247, 250)
SKY = (74, 144, 226)
SKY_DEEP = (37, 99, 190)
HILL = (46, 125, 86)
HILL_DARK = (31, 92, 64)
AMBER = (245, 185, 66)
INK = (20, 26, 36)
S = 8  # supersampling


def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def landscape(d, box, sun=(0.70, 0.32), sun_r=0.11, hill=True):
    """A small landscape inside box (x0, y0, x1, y1): sky, sun, two hills."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    d.rectangle(box, fill=SKY)
    r = w * sun_r
    cx, cy = x0 + w * sun[0], y0 + h * sun[1]
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=AMBER)
    if hill:
        d.polygon([(x0, y1), (x0, y0 + h * .74), (x0 + w * .24, y0 + h * .50), (x0 + w * .46, y0 + h * .68),
                   (x0 + w * .66, y0 + h * .50), (x0 + w * .84, y0 + h * .64), (x1, y0 + h * .56), (x1, y1)], fill=HILL)
        d.polygon([(x0, y1), (x0, y0 + h * .86), (x0 + w * .32, y0 + h * .68), (x0 + w * .58, y0 + h * .84),
                   (x0 + w * .80, y0 + h * .72), (x1, y0 + h * .84), (x1, y1)], fill=HILL_DARK)


def mark_a(d, c):
    """A: monogram P whose bowl is a photograph. c = canvas size (1000 units scaled)."""
    u = c / 1000
    stroke = int(96 * u)
    rad = int(110 * u)
    bowl = (int(270 * u), int(190 * u), int(760 * u), int(610 * u))
    # stem of the P
    d.rounded_rectangle((bowl[0], bowl[1], bowl[0] + stroke, int(830 * u)), radius=stroke // 2, fill=PAPER)
    # bowl: frame
    d.rounded_rectangle(bowl, radius=rad, fill=PAPER)
    inner = (bowl[0] + stroke, bowl[1] + stroke, bowl[2] - stroke, bowl[3] - stroke)
    d.rounded_rectangle(inner, radius=max(1, rad - stroke), fill=SKY)
    # the picture, clipped to the inner rounded rectangle
    pic = Image.new("RGBA", (inner[2] - inner[0], inner[3] - inner[1]), (0, 0, 0, 0))
    landscape(ImageDraw.Draw(pic), (0, 0, pic.width, pic.height), sun=(0.68, 0.34), sun_r=0.13)
    mask = Image.new("L", pic.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, pic.width - 1, pic.height - 1), radius=max(1, rad - stroke), fill=255)
    d._image.paste(pic, (inner[0], inner[1]), mask)


def mark_b(d, c):
    """B: a photograph standing on a shelf (station)."""
    u = c / 1000
    stroke = int(62 * u)
    frame = (int(190 * u), int(170 * u), int(810 * u), int(640 * u))
    rad = int(70 * u)
    d.rounded_rectangle(frame, radius=rad, fill=PAPER)
    inner = (frame[0] + stroke, frame[1] + stroke, frame[2] - stroke, frame[3] - stroke)
    pic = Image.new("RGBA", (inner[2] - inner[0], inner[3] - inner[1]), (0, 0, 0, 0))
    landscape(ImageDraw.Draw(pic), (0, 0, pic.width, pic.height), sun=(0.72, 0.30), sun_r=0.10)
    mask = Image.new("L", pic.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, pic.width - 1, pic.height - 1), radius=max(1, rad - stroke), fill=255)
    d._image.paste(pic, (inner[0], inner[1]), mask)
    # the shelf: a stand and a base line
    d.rounded_rectangle((int(470 * u), int(660 * u), int(530 * u), int(760 * u)), radius=int(20 * u), fill=PAPER)
    d.rounded_rectangle((int(250 * u), int(760 * u), int(750 * u), int(812 * u)), radius=int(26 * u), fill=PAPER)


def mark_c(d, c):
    """C: viewfinder. Four corner brackets, a sun and a horizon."""
    u = c / 1000
    stroke = int(64 * u)
    arm = int(190 * u)
    x0, y0, x1, y1 = int(190 * u), int(190 * u), int(810 * u), int(810 * u)
    r = stroke // 2
    for (ax, ay, dx, dy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        d.rounded_rectangle((min(ax, ax + dx * arm), min(ay, ay + dy * stroke), max(ax, ax + dx * arm), max(ay, ay + dy * stroke)), radius=r, fill=PAPER)
        d.rounded_rectangle((min(ax, ax + dx * stroke), min(ay, ay + dy * arm), max(ax, ax + dx * stroke), max(ay, ay + dy * arm)), radius=r, fill=PAPER)
    sr = int(96 * u)
    cx, cy = int(600 * u), int(420 * u)
    d.ellipse((cx - sr, cy - sr, cx + sr, cy + sr), fill=AMBER)
    # horizon: one soft hill, two cubic Bezier segments (the same control points as web/logo.svg),
    # stroked by stamping circles so that there are no joint seams
    for seg in HORIZON:
        p = [(x * u, y * u) for x, y in seg]
        prev = None
        for i in range(0, 161):
            t = i / 160
            mt = 1 - t
            x = mt ** 3 * p[0][0] + 3 * mt * mt * t * p[1][0] + 3 * mt * t * t * p[2][0] + t ** 3 * p[3][0]
            y = mt ** 3 * p[0][1] + 3 * mt * mt * t * p[1][1] + 3 * mt * t * t * p[2][1] + t ** 3 * p[3][1]
            if prev is None or (x - prev[0]) ** 2 + (y - prev[1]) ** 2 >= (r * 0.15) ** 2:
                d.ellipse((x - r, y - r, x + r, y + r), fill=PAPER)
                prev = (x, y)


# the hill line of mark C: P0, C1, C2, P3 of two cubic segments, in 1000-unit space
HORIZON = [((300, 650), (390, 650), (440, 545), (505, 545)), ((505, 545), (570, 545), (640, 640), (700, 650))]


def mark_d(d, c):
    """D: two photographs, the front one a landscape (a station holds many pictures)."""
    u = c / 1000
    stroke = int(58 * u)
    rad = int(64 * u)
    back = (int(300 * u), int(170 * u), int(840 * u), int(600 * u))
    d.rounded_rectangle(back, radius=rad, fill=NAVY_LIGHT)
    d.rounded_rectangle((back[0] + stroke, back[1] + stroke, back[2] - stroke, back[3] - stroke), radius=rad - stroke, fill=NAVY)
    front = (int(160 * u), int(330 * u), int(700 * u), int(780 * u))
    d.rounded_rectangle(front, radius=rad, fill=PAPER)
    inner = (front[0] + stroke, front[1] + stroke, front[2] - stroke, front[3] - stroke)
    pic = Image.new("RGBA", (inner[2] - inner[0], inner[3] - inner[1]), (0, 0, 0, 0))
    landscape(ImageDraw.Draw(pic), (0, 0, pic.width, pic.height), sun=(0.72, 0.30), sun_r=0.11)
    mask = Image.new("L", pic.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, pic.width - 1, pic.height - 1), radius=max(1, rad - stroke), fill=255)
    d._image.paste(pic, (inner[0], inner[1]), mask)


MARKS = {"a": mark_a, "b": mark_b, "c": mark_c, "d": mark_d}


def tile(which, size, bg=NAVY, rounded=True):
    """The mark on a square tile of `size` px."""
    c = size * S
    im = Image.new("RGBA", (c, c), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if bg is not None:
        if rounded:
            d.rounded_rectangle((0, 0, c - 1, c - 1), radius=int(c * 0.22), fill=bg)
        else:
            d.rectangle((0, 0, c, c), fill=bg)
    MARKS[which](d, c)
    return im.resize((size, size), Image.LANCZOS)


def wordmark(height, color, bold=False):
    """'Picturestation' as an image of the given cap height."""
    f = font("Outfit-Bold.ttf" if bold else "Outfit-Regular.ttf", height * S)
    text = "Picturestation"
    spacing = int(height * S * 0.02)
    # draw letter by letter for tracking
    widths = [f.getlength(ch) for ch in text]
    w = int(sum(widths) + spacing * (len(text) - 1))
    asc, desc = f.getmetrics()
    im = Image.new("RGBA", (w + 4, asc + desc), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = 0
    for ch, cw in zip(text, widths):
        d.text((x, 0), ch, font=f, fill=color)
        x += cw + spacing
    return im.resize((im.width // S, im.height // S), Image.LANCZOS)


def lockup(which, bg, fg, height=120, bold=False):
    """Mark beside the wordmark, on bg."""
    m = tile(which, height, bg=None)
    wm = wordmark(int(height * 0.42), fg, bold)
    gap = height // 5
    im = Image.new("RGBA", (m.width + gap + wm.width + 2, height), bg + (255,))
    im.alpha_composite(m, (0, 0))
    im.alpha_composite(wm, (m.width + gap, (height - wm.height) // 2))
    return im


def sheet():
    rows = []
    label_font = font("DMMono-Regular.ttf", 22)
    for which in "abcd":
        row = Image.new("RGBA", (1700, 320), (236, 238, 242, 255))
        d = ImageDraw.Draw(row)
        d.rectangle((0, 0, 850, 320), fill=NAVY + (255,))
        d.text((24, 20), which.upper(), font=label_font, fill=(140, 150, 170))
        row.alpha_composite(tile(which, 240), (80, 40))
        row.alpha_composite(tile(which, 130), (360, 95))
        row.alpha_composite(tile(which, 80), (520, 120))
        row.alpha_composite(tile(which, 40), (630, 140))
        row.alpha_composite(lockup(which, NAVY, PAPER, 56), (380, 240))
        row.alpha_composite(lockup(which, (236, 238, 242), INK, 110, bold=False), (900, 50))
        row.alpha_composite(lockup(which, (236, 238, 242), INK, 60, bold=True), (900, 200))
        rows.append(row)
    out = Image.new("RGBA", (1700, 320 * 4 + 60), (255, 255, 255, 255))
    for i, r in enumerate(rows):
        out.alpha_composite(r, (0, i * 320))
    d = ImageDraw.Draw(out)
    d.text((24, 320 * 4 + 18), "A monogram P as a photo  |  B photo on a shelf  |  C viewfinder  |  D two photos", font=label_font, fill=(90, 96, 110))
    out.save(os.path.join(HERE, "variants.png"))
    print("variants.png")


def final(which):
    out = os.path.join(HERE, "final")
    os.makedirs(out, exist_ok=True)
    for size in (80, 130, 400, 512, 1024):
        tile(which, size).save(os.path.join(out, f"icon-{size}.png"))
    for size in (16, 32, 48, 180, 192):
        tile(which, size).save(os.path.join(out, f"favicon-{size}.png"))
    tile(which, 1024, bg=None).save(os.path.join(out, "mark-1024.png"))
    lockup(which, NAVY, PAPER, 200).save(os.path.join(out, "lockup-dark.png"))
    lockup(which, (255, 255, 255), INK, 200).save(os.path.join(out, "lockup-light.png"))
    wordmark(120, PAPER).save(os.path.join(out, "wordmark-dark.png"))
    wordmark(120, INK).save(os.path.join(out, "wordmark-light.png"))
    # TV splash
    w, h = 1920, 1080
    sp = Image.new("RGBA", (w, h), NAVY + (255,))
    m = tile(which, 420, bg=None)
    sp.alpha_composite(m, ((w - m.width) // 2, 230))
    wm = wordmark(72, PAPER)
    sp.alpha_composite(wm, ((w - wm.width) // 2, 700))
    sp.convert("RGB").save(os.path.join(out, "splash-1920x1080.png"))
    print("final assets in", out)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "final":
        final(sys.argv[2])
    else:
        sheet()
