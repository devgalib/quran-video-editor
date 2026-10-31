"""Card templates. Each draws a full-frame transparent overlay.

fields:  surah_ar, surah_en, surah_meaning, surah_number, reciter, channel,
         bismillah, translation (bismillah cards)
options: accent (hex colour), backdrop (0..1 darkness behind the text),
         position ("top" / "bottom", corner template only)
"""

from .draw import Canvas, divider, hex_rgb, mix, spacer, stack, text

BISMILLAH = "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ"
BISMILLAH_EN = "In the name of Allah, the Most Gracious, the Most Merciful"
WHITE = (255, 255, 255)


def _palette(options):
    accent = hex_rgb(options.get("accent", "#E3B85C"))
    return accent, (mix(accent, WHITE, 0.55), mix(accent, (0, 0, 0), 0.12))


def royal(c, f, o):
    """Centred, gold Arabic title with glow, ornament and engraved-style English."""
    accent, gold = _palette(o)
    c.backdrop(960, 540, 1500, 760, o.get("backdrop", 0.6))
    number = f.get("surah_number")
    stack(c, [
        text(c, f"Surah {number}", "montserrat", 22, accent, weight=600, tracking=9,
             uppercase=True, shadow=None) if number else None,
        spacer(c, 14) if number else None,
        text(c, f["surah_ar"], "amiri-bold", 128, gradient=gold,
             glow=(accent, 22, 0.45)) if f.get("surah_ar") else None,
        spacer(c, 14),
        divider(c, 560, accent + (235,)),
        spacer(c, 26),
        text(c, f["surah_en"], "cinzel", 62, WHITE, weight=600, tracking=5) if f.get("surah_en") else None,
        spacer(c, 12) if f.get("surah_meaning") else None,
        text(c, f["surah_meaning"], "montserrat", 26, WHITE, weight=400, tracking=2,
             opacity=0.8) if f.get("surah_meaning") else None,
        spacer(c, 46) if f.get("reciter") else None,
        text(c, "Recited by", "montserrat", 19, accent, weight=600, tracking=7,
             uppercase=True, shadow=None) if f.get("reciter") else None,
        spacer(c, 12) if f.get("reciter") else None,
        text(c, f["reciter"], "montserrat", 40, WHITE, weight=600) if f.get("reciter") else None,
    ], cy=530)
    if f.get("channel"):
        stack(c, [divider(c, 220, accent + (200,), style="dots"), spacer(c, 8),
                  text(c, f["channel"], "montserrat", 20, WHITE, weight=500, tracking=8,
                       uppercase=True, opacity=0.75)], top=965)


def minimal(c, f, o):
    """Quiet and modern: light English title, small Arabic, thin accent rule."""
    accent, _ = _palette(o)
    c.backdrop(960, 540, 1300, 560, o.get("backdrop", 0.4))
    stack(c, [
        text(c, f["surah_ar"], "amiri", 60, WHITE, opacity=0.9) if f.get("surah_ar") else None,
        spacer(c, 4),
        text(c, f["surah_en"], "montserrat", 96, WHITE, weight=250, tracking=3) if f.get("surah_en") else None,
        spacer(c, 30),
        divider(c, 140, accent + (255,), style="line", thickness=2.4),
        spacer(c, 30),
        text(c, f["reciter"], "montserrat", 28, WHITE, weight=500, tracking=8, uppercase=True,
             opacity=0.9) if f.get("reciter") else None,
        spacer(c, 16) if f.get("channel") else None,
        text(c, f["channel"], "montserrat", 19, accent, weight=500, tracking=6, uppercase=True,
             shadow=None) if f.get("channel") else None,
    ], cy=540)


def frame(c, f, o):
    """Dark glass panel with a double gold border and corner diamonds."""
    accent, gold = _palette(o)
    x0, y0, x1, y1 = 420, 250, 1500, 830
    c.backdrop(960, 540, 1500, 900, o.get("backdrop", 0.35))
    c.panel((x0, y0, x1, y1), 22, (14, 18, 24), (4, 6, 10), 0.72, border=accent + (230,), border_width=2.2)
    c.rect_outline((x0 + 14, y0 + 14, x1 - 14, y1 - 14), accent + (110,), width=1, radius=12)
    for cx, cy in ((x0 + 14, y0 + 14), (x1 - 14, y0 + 14), (x0 + 14, y1 - 14), (x1 - 14, y1 - 14)):
        c.diamond(cx, cy, 7, accent + (255,))
    stack(c, [
        text(c, f["surah_ar"], "ruqaa-bold", 118, gradient=gold, glow=(accent, 18, 0.3))
        if f.get("surah_ar") else None,
        spacer(c, 6),
        divider(c, 420, accent + (230,)),
        spacer(c, 22),
        text(c, f["surah_en"], "cinzel", 54, WHITE, weight=600, tracking=4) if f.get("surah_en") else None,
        spacer(c, 34) if f.get("reciter") else None,
        text(c, f["reciter"], "montserrat", 34, WHITE, weight=500, opacity=0.95) if f.get("reciter") else None,
    ], cy=515)
    if f.get("channel"):
        stack(c, [text(c, f["channel"], "montserrat", 17, accent, weight=600, tracking=7,
                       uppercase=True, shadow=None)], cy=y1 - 46)


def corner(c, f, o):
    """Compact tag in the top (or bottom) left corner, out of the way of the recitation text."""
    accent, gold = _palette(o)
    blocks = [
        text(c, f["surah_ar"], "amiri-bold", 46, gradient=gold, shadow=(0, 2, 4, 0.6))
        if f.get("surah_ar") else None,
        spacer(c, 6),
        text(c, f["surah_en"], "cinzel", 40, WHITE, weight=700, tracking=3) if f.get("surah_en") else None,
        spacer(c, 10),
        text(c, f["reciter"], "montserrat", 26, WHITE, weight=500, opacity=0.9) if f.get("reciter") else None,
        spacer(c, 12) if f.get("channel") else None,
        text(c, f["channel"], "montserrat", 16, accent, weight=600, tracking=6, uppercase=True,
             shadow=None) if f.get("channel") else None,
    ]
    blocks = [b for b in blocks if b is not None]
    height = sum(b.height for b in blocks) / c.u
    top = 70 if o.get("position", "top") == "top" else 1080 - 70 - height
    c.fade_bar((60, top - 22, 900, top + height + 22), (0, 0, 0, 255), opacity=o.get("backdrop", 0.65))
    c.bar((60, top - 22, 66, top + height + 22), accent + (255,))
    stack(c, blocks, top=top, align="left", x=96)


def bismillah(c, f, o):
    """Large Bismillah with a soft gold glow and the English meaning."""
    accent, gold = _palette(o)
    c.backdrop(960, 540, 1700, 640, o.get("backdrop", 0.5))
    translation = f.get("translation", BISMILLAH_EN)
    stack(c, [
        text(c, f.get("bismillah", BISMILLAH), "amiri", 120, gradient=(WHITE, gold[0]),
             glow=(accent, 26, 0.55)),
        spacer(c, 16),
        divider(c, 460, accent + (230,)),
        spacer(c, 22) if translation else None,
        text(c, translation, "montserrat", 26, WHITE, weight=400, tracking=2, opacity=0.85)
        if translation else None,
    ], cy=530)


def bismillah_frame(c, f, o):
    """Bismillah in gold inside an ornamental panel."""
    accent, gold = _palette(o)
    x0, y0, x1, y1 = 260, 330, 1660, 750
    c.backdrop(960, 540, 1800, 700, o.get("backdrop", 0.35))
    c.panel((x0, y0, x1, y1), 26, (14, 18, 24), (4, 6, 10), 0.7, border=accent + (230,), border_width=2.2)
    c.rect_outline((x0 + 14, y0 + 14, x1 - 14, y1 - 14), accent + (110,), width=1, radius=14)
    for cx, cy in ((x0 + 14, y0 + 14), (x1 - 14, y0 + 14), (x0 + 14, y1 - 14), (x1 - 14, y1 - 14)):
        c.diamond(cx, cy, 7, accent + (255,))
    translation = f.get("translation", BISMILLAH_EN)
    stack(c, [
        text(c, f.get("bismillah", BISMILLAH), "amiri-bold", 104, gradient=gold, glow=(accent, 18, 0.35)),
        spacer(c, 12),
        divider(c, 380, accent + (230,), style="dots"),
        spacer(c, 18) if translation else None,
        text(c, translation, "montserrat", 23, WHITE, weight=400, tracking=2, opacity=0.85)
        if translation else None,
    ], cy=532)


TEMPLATES = {
    "royal": royal,
    "minimal": minimal,
    "frame": frame,
    "corner": corner,
    "bismillah": bismillah,
    "bismillah_frame": bismillah_frame,
}


def render_image(template, fields, options, width, height):
    if template not in TEMPLATES:
        raise ValueError(f"unknown template '{template}'. Available: {', '.join(TEMPLATES)}")
    canvas = Canvas(width, height)
    TEMPLATES[template](canvas, fields, options)
    return canvas.result()


def render(template, fields, options, width, height, path):
    render_image(template, fields, options, width, height).save(path)
