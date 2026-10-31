"""Background clip library: scanning folders and caching clip durations.

Probing thousands of clips is slow, so results are cached in the user's cache folder,
keyed by path, size and modification time.
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor

from . import ffmpeg

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


def _cache_path():
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, "quran-video-editor", "clips.json")


def _load_cache():
    try:
        with open(_cache_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save_cache(cache):
    path = _cache_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cache, fh)
    os.replace(tmp, path)


def find_videos(folder, recursive=True):
    found = []
    if recursive:
        for root, _dirs, files in os.walk(folder):
            found += [os.path.join(root, f) for f in files]
    else:
        found = [os.path.join(folder, f) for f in os.listdir(folder)]
    return sorted(p for p in found if os.path.splitext(p)[1].lower() in VIDEO_EXTS)


def clip_infos(paths, workers=4):
    """Return [{"path", "duration", "width", "height"}] for the paths that are readable videos."""
    cache = _load_cache()
    keys = {}
    todo = []
    for path in paths:
        st = os.stat(path)
        keys[path] = f"{os.path.abspath(path)}|{st.st_size}|{int(st.st_mtime)}"
        if keys[path] not in cache:
            todo.append(path)

    def probe_one(path):
        try:
            info = ffmpeg.probe(path)
            return path, info if info["width"] and info["duration"] > 0 else None
        except Exception:
            return path, None

    if todo:
        with ThreadPoolExecutor(workers) as pool:
            for path, info in pool.map(probe_one, todo):
                cache[keys[path]] = info
        _save_cache(cache)

    clips = []
    for path in paths:
        info = cache.get(keys[path])
        if info:
            clips.append({"path": path, "duration": info["duration"],
                          "width": info["width"], "height": info["height"]})
    return clips


def collect(backgrounds):
    paths = list(backgrounds["files"])
    if backgrounds["folder"]:
        paths += find_videos(backgrounds["folder"], backgrounds["recursive"])
    if not paths:
        raise ValueError("no background clips: set backgrounds.folder or backgrounds.files")
    return clip_infos(paths)
