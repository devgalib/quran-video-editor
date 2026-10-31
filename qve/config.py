"""Project / batch file loading.

A project file is JSON. It is either a single job, or a batch:

    {"defaults": {...job settings...}, "jobs": [{...overrides...}, ...]}

Every job is DEFAULTS <- defaults <- job, merged deeply (dicts merge, lists replace).
Relative paths are resolved against the folder of the project file.
"""

import copy
import json
import os
import string

DEFAULTS = {
    "quran_video": None,
    "output": "output/{surah_en} - {reciter}.mp4",
    # Text used by the cards: surah_ar, surah_en, surah_meaning, surah_number, reciter, channel
    "meta": {},
    "intro_seconds": 0,   # background + cards only, before the recitation starts
    "outro_seconds": 0,   # background only, after the recitation ends
    "quran_layer": {
        "key": "screen",          # "screen" for black backgrounds, "chromakey" for green screen
        "black_point": 0.06,      # screen: crush compression noise in the black background
        "key_color": "0x00FF00",  # chromakey only
        "similarity": 0.15,
        "blend": 0.08,
        "scale": 1.0,
    },
    "backgrounds": {
        "folder": None,
        "files": [],
        "recursive": True,
        "seed": None,             # set a number to get the same clip order every time
        "max_clip_seconds": 20,
        "min_clip_seconds": 4,
        "random_start": True,     # start long clips at a random point
        "dim": 0.35,              # 0 = untouched, 1 = black
        "blur": 0,                # gaussian sigma at 1080p, 0 = off
    },
    "transitions": {
        "duration": 1.0,
        "types": ["fade"],        # any FFmpeg xfade name: fade, dissolve, smoothleft, circleopen, ...
        "order": "random",        # or "cycle"
    },
    "cards": [],
    "video": {
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "encoder": "libx264",     # or h264_nvenc, h264_qsv, h264_amf
        "quality": 20,            # crf / cq: lower = better and bigger
        "preset": "veryfast",
        "threads": 4,
        "audio_bitrate": "192k",
    },
    "render": {
        "clips_per_chunk": 6,     # bounds memory: each chunk opens at most ~this many clips
        "low_priority": True,
        "keep_temp": False,
    },
}

def deep_merge(base, override):
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


class _Blank(dict):
    def __missing__(self, key):
        return ""


def fill(template, meta):
    """Format "{surah_en} - {reciter}" with meta; unknown keys become empty."""
    return string.Formatter().vformat(template, (), _Blank(meta))


def safe_filename(name):
    bad = '<>:"|?*' + "".join(chr(c) for c in range(32))
    cleaned = "".join("_" if ch in bad else ch for ch in name)
    return " ".join(cleaned.split()).strip(" .") or "video"


def _resolve(path, base_dir):
    if not path:
        return path
    path = os.path.expanduser(path)
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(base_dir, path))


def load_jobs(project_path):
    with open(project_path, encoding="utf-8") as fh:
        data = json.load(fh)
    base_dir = os.path.dirname(os.path.abspath(project_path))

    if "jobs" in data:
        shared = deep_merge(DEFAULTS, data.get("defaults", {}))
        raw_jobs = [deep_merge(shared, job) for job in data["jobs"]]
    else:
        raw_jobs = [deep_merge(DEFAULTS, data)]

    return [prepare_job(job, base_dir) for job in raw_jobs]


def prepare_job(job, base_dir):
    """Fill the output name from meta and make paths absolute. `job` is already merged with DEFAULTS."""
    job = copy.deepcopy(job)
    folder, name = os.path.split(fill(job["output"], job["meta"]))
    job["output"] = os.path.join(folder, safe_filename(name))
    job["quran_video"] = _resolve(job["quran_video"], base_dir)
    job["output"] = _resolve(job["output"], base_dir)
    job["backgrounds"]["folder"] = _resolve(job["backgrounds"]["folder"], base_dir)
    job["backgrounds"]["files"] = [_resolve(p, base_dir) for p in job["backgrounds"]["files"]]
    if not job["quran_video"]:
        raise ValueError("every job needs a quran_video")
    return job
