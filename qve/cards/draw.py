"""Drawing helpers for text cards (Pillow + libraqm for Arabic shaping).

Cards are drawn at 2x and scaled down, which gives smooth ornaments and lines.
Sizes passed to these helpers are in 1080p units; Canvas.u converts them to pixels.
"""

import functools
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, features

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")
SUPERSAMPLE = 2

# name -> (file, variable weight or None)
FONTS = {
    "amiri": ("Amiri-Regular.ttf", None),
    "amiri-bold": ("Amiri-Bold.ttf", None),
    "ruqaa": ("ArefRuqaa-Regular.ttf", None),
    "ruqaa-bold": ("ArefRuqaa-Bold.ttf", None),
    "cinzel": ("Cinzel[wght].ttf", 400),
    "montserrat": ("Montserrat[wght].ttf", 400),
}


def check_arabic_support():
    if not features.check("raqm"):
        raise RuntimeError(
            "Pillow has no libraqm, so Arabic text cannot be shaped. On Windows put "
            "fribidi-0.dll next to python.exe (see README); on Linux install libraqm."
        )


@functools.lru_cache(maxsize=64)
def font(name, size, weight=None):
    filename, default_weight = FONTS[name]
    f = ImageFont.truetype(os.path.join(FONT_DIR, filename), max(1, int(size)),
                           layout_engine=ImageFont.Layout.RAQM)
    if default_weight is not None:
        f.set_variation_by_axes([weight or default_weight])
    return f


def hex_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def mix(c1, c2, t):
    return tuple(round(a + (b - a) * t) for a, b in zip(c1, c2))


def is_arabic(text):
    return any("؀" <= ch <= "ۿ" or "ﭐ" <= ch <= "﻿" for ch in text)


def vertical_gradient(size, top, bottom):
    grad = Image.linear_gradient("L").resize(size)
    return Image.composite(Image.new("RGB", size, bottom), Image.new("RGB", size, top), grad)


def horizontal_fade(size, fade_left=True):
    """'L' mask that goes 0 -> 255 from the left edge (or the right edge)."""
    mask = Image.linear_gradient("L").rotate(90, expand=True).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    mask = mask.resize(size)
    return mask if fade_left else mask.transpose(Image.Transpose.FLIP_LEFT_RIGHT)


class Canvas:
    def __init__(self, width, height):
        self.out_size = (width, height)
        self.u = height / 1080 * SUPERSAMPLE
        self.w, self.h = width * SUPERSAMPLE, height * SUPERSAMPLE
        self.img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))

    def px(self, value):
        return int(round(value * self.u))

    def paste(self, layer, x, y):
        x, y = int(x), int(y)
        if x < 0 or y < 0:  # alpha_composite refuses negative positions
            layer = layer.crop((max(0, -x), max(0, -y), layer.width, layer.height))
            x, y = max(0, x), max(0, y)
        self.img.alpha_composite(layer, (x, y))

    def result(self):
        return self.img.resize(self.out_size, Image.Resampling.LANCZOS)

    # ---- backgrounds -------------------------------------------------------------------

    def backdrop(self, cx, cy, width, height, opacity=0.5):
        """Soft dark ellipse that keeps text readable on busy footage."""
        small = 8
        layer = Image.new("L", (self.w // small, self.h // small), 0)
        rx, ry = self.px(width) / 2 / small, self.px(height) / 2 / small
        sx, sy = self.px(cx) / small, self.px(cy) / small
        ImageDraw.Draw(layer).ellipse((sx - rx, sy - ry, sx + rx, sy + ry), fill=int(255 * opacity))
        layer = layer.filter(ImageFilter.GaussianBlur(min(rx, ry) * 0.45))
        alpha = layer.resize((self.w, self.h), Image.Resampling.BICUBIC)
        shade = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        shade.putalpha(alpha)
        self.img.alpha_composite(shade)

    def panel(self, box, radius, fill_top, fill_bottom, opacity, border=None, border_width=2):
        x0, y0, x1, y1 = [self.px(v) for v in box]
        size = (x1 - x0, y1 - y0)
        mask = Image.new("L", size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1),
                                               radius=self.px(radius), fill=int(255 * opacity))
        layer = vertical_gradient(size, fill_top, fill_bottom).convert("RGBA")
        layer.putalpha(mask)
        self.paste(layer, x0, y0)
        if border:
            ImageDraw.Draw(self.img).rounded_rectangle(
                (x0, y0, x1, y1), radius=self.px(radius), outline=border,
                width=max(1, self.px(border_width)))

    def rect_outline(self, box, color, width=1, radius=0):
        x0, y0, x1, y1 = [self.px(v) for v in box]
        ImageDraw.Draw(self.img).rounded_rectangle(
            (x0, y0, x1, y1), radius=self.px(radius), outline=color, width=max(1, self.px(width)))

    def diamond(self, cx, cy, r, color):
        x, y, r = self.px(cx), self.px(cy), self.px(r)
        ImageDraw.Draw(self.img).polygon([(x, y - r), (x + r, y), (x, y + r), (x - r, y)], fill=color)

    def bar(self, box, color):
        ImageDraw.Draw(self.img).rectangle([self.px(v) for v in box], fill=color)

    def fade_bar(self, box, color, opacity=1.0, fade_left=False):
        """Rectangle that fades out towards the right (or left)."""
        x0, y0, x1, y1 = [self.px(v) for v in box]
        size = (x1 - x0, y1 - y0)
        mask = horizontal_fade(size, fade_left=not fade_left).point(lambda v: int(v * opacity))
        layer = Image.new("RGBA", size, color)
        layer.putalpha(mask)
        self.paste(layer, x0, y0)


class Block:
    """A rendered element with its own size; laid out by `stack`."""

    def __init__(self, image, pad=0):
        self.image, self.pad = image, pad

    @property
    def width(self):
        return self.image.width - 2 * self.pad

    @property
    def height(self):
        return self.image.height - 2 * self.pad


def text(canvas, value, font_name, size, color=(255, 255, 255), weight=None, tracking=0,
         gradient=None, opacity=1.0, glow=None, shadow=(0, 3, 6, 0.55), uppercase=False):
    """Render one line of text into a Block.

    gradient: (top_rgb, bottom_rgb)    glow: (rgb, blur, strength)
    shadow:   (dx, dy, blur, opacity)  tracking: letter spacing (Latin only)
    """
    if uppercase:
        value = value.upper()
    f = font(font_name, canvas.px(size), weight)
    rtl = is_arabic(value)
    kw = {"direction": "rtl", "language": "ar"} if rtl else {}
    track = 0 if rtl else canvas.px(tracking)

    if track:
        advances = [f.getlength(ch) for ch in value]
        boxes = [f.getbbox(ch, anchor="ls") for ch in value]
        positions, x = [], 0.0
        for adv in advances:
            positions.append(x)
            x += adv + track
        bbox = (min(p + b[0] for p, b in zip(positions, boxes)), min(b[1] for b in boxes),
                max(p + b[2] for p, b in zip(positions, boxes)), max(b[3] for b in boxes))
    else:
        bbox = f.getbbox(value, anchor="ls", **kw)

    pad = canvas.px(40)
    w, h = int(bbox[2] - bbox[0]) + 2 * pad, int(bbox[3] - bbox[1]) + 2 * pad
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    ox, oy = pad - bbox[0], pad - bbox[1]
    if track:
        for ch, p in zip(value, positions):
            draw.text((ox + p, oy), ch, font=f, fill=255, anchor="ls")
    else:
        draw.text((ox, oy), value, font=f, fill=255, anchor="ls", **kw)

    if gradient:
        fill_img = Image.new("RGB", (w, h), gradient[1])
        ink = vertical_gradient((w, int(bbox[3] - bbox[1]) or 1), *gradient)
        fill_img.paste(ink, (0, pad))
    else:
        fill_img = Image.new("RGB", (w, h), color)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    if shadow:
        dx, dy, blur, strength = shadow
        sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        sh.putalpha(ImageChops.offset(mask, canvas.px(dx), canvas.px(dy))
                    .filter(ImageFilter.GaussianBlur(canvas.px(blur)))
                    .point(lambda v: int(v * strength)))
        out.alpha_composite(sh)
    if glow:
        rgb, blur, strength = glow
        gl = Image.new("RGBA", (w, h), rgb + (0,))
        gl.putalpha(mask.filter(ImageFilter.GaussianBlur(canvas.px(blur))).point(
            lambda v: min(255, int(v * strength))))
        out.alpha_composite(gl)

    body = fill_img.convert("RGBA")
    body.putalpha(mask if opacity >= 1 else mask.point(lambda v: int(v * opacity)))
    out.alpha_composite(body)
    return Block(out, pad)


def divider(canvas, width, color, style="diamond", thickness=1.6):
    """Ornamental line: fades out to both ends, with an ornament in the middle."""
    w, h = canvas.px(width), canvas.px(30)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cy, cx, t = h // 2, w // 2, max(1, canvas.px(thickness))
    gap = canvas.px(26 if style != "line" else 0)
    for x0, x1, fade_left in ((0, cx - gap, True), (cx + gap, w, False)):
        if x1 - x0 <= 0:
            continue
        seg = Image.new("RGBA", (x1 - x0, t), color)
        seg.putalpha(horizontal_fade((x1 - x0, t), fade_left))
        layer.alpha_composite(seg, (x0, cy - t // 2))
    draw = ImageDraw.Draw(layer)
    if style == "diamond":
        r = canvas.px(7)
        draw.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=color)
        for side in (-1, 1):
            d = canvas.px(16) * side
            s = canvas.px(3)
            draw.polygon([(cx + d, cy - s), (cx + d + s, cy), (cx + d, cy + s), (cx + d - s, cy)],
                         fill=color)
    elif style == "dots":
        for i in (-1, 0, 1):
            r = canvas.px(3.5 if i == 0 else 2.2)
            x = cx + i * canvas.px(14)
            draw.ellipse((x - r, cy - r, x + r, cy + r), fill=color)
    return Block(layer)


def spacer(canvas, height):
    return Block(Image.new("RGBA", (1, max(1, canvas.px(height))), (0, 0, 0, 0)))


def stack(canvas, blocks, cy=None, top=None, align="center", x=None):
    """Lay blocks out vertically, centred on cy (1080p units) or starting at top."""
    blocks = [b for b in blocks if b is not None]
    total = sum(b.height for b in blocks)
    y = canvas.px(top) if top is not None else canvas.px(cy) - total / 2
    for b in blocks:
        if align == "center":
            bx = canvas.w / 2 - b.width / 2 if x is None else canvas.px(x) - b.width / 2
        elif align == "left":
            bx = canvas.px(x)
        else:
            bx = canvas.px(x) - b.width
        canvas.paste(b.image, bx - b.pad, y - b.pad)
        y += b.height
    return total / canvas.u
