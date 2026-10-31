"""Still previews: one composed frame at time t, built with Pillow instead of a render.

It follows what render.py does (dim, blur, screen blend / chroma key, card fade and rise)
closely enough to judge the look in a fraction of a second.
"""

import functools
import json
import subprocess
from io import BytesIO

from PIL import Image, ImageChops, ImageEnhance, ImageFilter

from . import cards, ffmpeg


@functools.lru_cache(maxsize=48)
def grab_frame(path, t, w, h, vf_extra=""):
    """Frame of `path` at t seconds, scaled to cover w x h. vf_extra is appended to the filter."""
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}" + vf_extra
    out = subprocess.run(
        [ffmpeg.find_tool("ffmpeg"), "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", path,
         "-frames:v", "1", "-vf", vf, "-f", "image2pipe", "-vcodec", "png", "-"],
        capture_output=True,
    ).stdout
    if not out:
        return None
    return Image.open(BytesIO(out)).convert("RGBA")


@functools.lru_cache(maxsize=32)
def _card(template, fields_json, options_json, w, h):
    return cards.render_image(template, json.loads(fields_json), json.loads(options_json), w, h)


def card_image(card, meta, w, h):
    fields = {**meta, **card.get("fields", {})}
    return _card(card["template"], json.dumps(fields, sort_keys=True, ensure_ascii=False),
                 json.dumps(card.get("options", {}), sort_keys=True), w, h)


def compose(job, t, bg_clip, quran_duration, size=(960, 540)):
    """Return an RGB image of the finished video at t seconds. `job` is a merged job dict."""
    w, h = size
    frame = Image.new("RGBA", size, (0, 0, 0, 255))

    if bg_clip:
        bg = grab_frame(bg_clip, 2.0, w, h)
        if bg:
            opts = job["backgrounds"]
            if opts["blur"]:
                bg = bg.filter(ImageFilter.GaussianBlur(opts["blur"] * h / 1080))
            if opts["dim"]:
                bg = ImageEnhance.Brightness(bg).enhance(1 - opts["dim"])
            frame = bg

    q_t = t - job["intro_seconds"]
    layer = job["quran_layer"]
    if job["quran_video"] and 0 <= q_t < quran_duration:
        if layer["key"] == "chromakey":
            fg = grab_frame(job["quran_video"], round(q_t, 2), w, h,
                            f",chromakey={layer['key_color']}:{layer['similarity']}:{layer['blend']},format=rgba")
            if fg:
                frame = Image.alpha_composite(frame, fg)
        else:
            fg = grab_frame(job["quran_video"], round(q_t, 2), w, h)
            if fg:
                cut = float(layer["black_point"]) * 255
                fg = fg.convert("RGB").point(lambda v: max(0, min(255, int((v - cut) * 255 / (255 - cut)))))
                frame = ImageChops.screen(frame.convert("RGB"), fg).convert("RGBA")

    total = job["intro_seconds"] + quran_duration + job["outro_seconds"]
    for card in job["cards"]:
        start = card.get("start", 0)
        if start < 0:
            start += total
        dur = card.get("duration", 6)
        local = t - start
        if not 0 <= local < dur:
            continue
        fade = min(card.get("fade", 0.8), dur / 2)
        alpha = min(1.0, local / fade if fade else 1, (dur - local) / fade if fade else 1)
        img = card_image(card, job["meta"], w, h)
        if alpha < 1:
            img = img.copy()
            img.putalpha(img.getchannel("A").point(lambda v, a=alpha: int(v * a)))
        dy = 0
        if card.get("animation", "rise") == "rise" and fade:
            d = fade * 1.6
            if local < d:
                dy = int(28 * h / 1080 * (1 - local / d) ** 3)
        frame = frame.copy()
        frame.alpha_composite(img.crop((0, 0, w, h - dy)), (0, dy))

    return frame.convert("RGB")
