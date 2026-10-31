"""MCP server: lets Claude (or any MCP client) drive the editor.

Run with `python -m qve mcp` (stdio). A "project" argument is the same dict as a project
JSON file (see qve/config.py DEFAULTS); missing settings use the defaults. Renders run in
the background, one at a time: start_render returns at once, render_status reports progress.

Nothing may print to stdout here: stdout is the MCP channel.
"""

import io
import json
import os
import threading
import time
import uuid

from mcp.server.mcpserver import Image, MCPServer

from . import cards, ffmpeg, library, preview
from .config import DEFAULTS, deep_merge, prepare_job
from .gui.surahs import SURAHS

server = MCPServer(
    "quran-video-editor",
    instructions=(
        "Makes Quran recitation videos: background clips with smooth transitions, the recitation "
        "video keyed on top (black background via screen blend, or green screen), text cards, "
        "original audio, 1080p30 H.264. Typical flow: find_surah -> scan_clips -> preview_frame "
        "(check the look) -> start_render with test_seconds=30 -> start_render -> render_status "
        "until done. Paths should be absolute."
    ),
)

_jobs = {}
_lock = threading.Lock()


def _job(project, project_dir=None):
    merged = deep_merge(DEFAULTS, project or {})
    return prepare_job(merged, project_dir or os.getcwd())


@server.tool()
def default_project() -> dict:
    """All project settings with their default values. Use it as a template for `project`."""
    return DEFAULTS


@server.tool()
def list_templates() -> list[dict]:
    """Text card templates usable in project["cards"][i]["template"]."""
    return [{"name": n, "description": (fn.__doc__ or "").strip()} for n, fn in cards.TEMPLATES.items()]


@server.tool()
def find_surah(query: str) -> list[dict]:
    """Look up surahs by number or name (e.g. "55", "rahman", "الملك"). Returns meta fields ready for
    project["meta"]: surah_number, surah_en, surah_ar, surah_meaning."""
    q = query.strip().lower().replace("-", "").replace("'", "")
    out = []
    for n, en, ar, meaning in SURAHS:
        hay = f"{n} {en} {ar} {meaning}".lower().replace("-", "").replace("'", "")
        if q == str(n) or (not q.isdigit() and q in hay):
            out.append({"surah_number": n, "surah_en": f"Surah {en}", "surah_ar": f"سورة {ar}",
                        "surah_meaning": meaning})
    return out


@server.tool()
def inspect_video(path: str) -> dict:
    """Duration (seconds), size, frame rate and whether it has audio."""
    return ffmpeg.probe(path)


@server.tool()
def scan_clips(folder: str) -> dict:
    """Probe every video in a background clip folder (cached for later renders)."""
    clips = library.clip_infos(library.find_videos(folder))
    return {"count": len(clips),
            "total_minutes": round(sum(c["duration"] for c in clips) / 60, 1),
            "clips": [{"file": os.path.relpath(c["path"], folder), "seconds": round(c["duration"], 1),
                       "size": f"{c['width']}x{c['height']}"} for c in clips[:200]]}


@server.tool()
def preview_frame(project: dict, seconds: float = 3.0, clip: str = "", project_dir: str = "") -> Image:
    """A still of the finished video at `seconds` (background, keyed recitation, cards), 960x540.
    `clip` picks the background clip to show (default: the first in the folder)."""
    job = _job(project, project_dir or None)
    if not clip:
        files = list(job["backgrounds"]["files"])
        if job["backgrounds"]["folder"]:
            files += library.find_videos(job["backgrounds"]["folder"])
        clip = files[0] if files else None
    q_dur = ffmpeg.probe(job["quran_video"])["duration"] if job["quran_video"] else 0
    im = preview.compose(job, seconds, clip, q_dur)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return Image(data=buf.getvalue(), format="jpeg")


@server.tool()
def save_project(project: dict, path: str) -> str:
    """Save a project as JSON (it opens in the desktop app and works with `python -m qve render`)."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(deep_merge(DEFAULTS, project), fh, ensure_ascii=False, indent=2)
    return path


def _run(state, job, limit):
    from .render import Job

    def report(msg, end="\n"):
        if end == "\n" and msg.strip():
            state["log"].append(msg.strip())
            del state["log"][:-40]

    def progress(fraction, speed, eta):
        state.update(progress=round(fraction * 100, 1), speed=round(speed, 2), eta_seconds=round(eta))

    try:
        Job(job, limit).run(report, progress, lambda: state["cancel"])
    except ffmpeg.Cancelled:
        state["state"] = "cancelled"
    except Exception as exc:
        state.update(state="failed", error=str(exc))
    else:
        state.update(state="done", progress=100.0, eta_seconds=0)
    state["finished_at"] = time.time()


@server.tool()
def start_render(project: dict, test_seconds: float = 0, overwrite: bool = False,
                 project_dir: str = "") -> dict:
    """Start rendering in the background and return a job id at once. test_seconds > 0 renders only
    the start (saved as "<name> (test).mp4"). A stopped or cancelled render resumes from its last
    finished part when started again. Only one render runs at a time."""
    with _lock:
        busy = [j for j in _jobs.values() if j["state"] == "running"]
        if busy:
            raise RuntimeError(f"render {busy[0]['id']} is still running; wait or cancel it first")
        job = _job(project, project_dir or None)
        if test_seconds:
            stem, ext = os.path.splitext(job["output"])
            job["output"] = f"{stem} (test){ext}"
        if os.path.exists(job["output"]) and not overwrite and not test_seconds:
            raise FileExistsError(f"{job['output']} exists; pass overwrite=true to replace it")
        state = {"id": uuid.uuid4().hex[:8], "state": "running", "output": job["output"],
                 "progress": 0.0, "speed": None, "eta_seconds": None, "error": None,
                 "log": [], "cancel": False, "started_at": time.time()}
        _jobs[state["id"]] = state
        threading.Thread(target=_run, args=(state, job, test_seconds or None), daemon=True).start()
    return {"job_id": state["id"], "output": job["output"]}


@server.tool()
def render_status(job_id: str = "") -> dict:
    """Progress of a render (the latest one if job_id is empty): state running/done/failed/cancelled,
    progress %, speed (x real time), eta_seconds, output path, error, recent log lines."""
    if not _jobs:
        return {"state": "none"}
    state = _jobs.get(job_id) or max(_jobs.values(), key=lambda s: s["started_at"])
    out = {k: v for k, v in state.items() if k != "cancel"}
    out["elapsed_seconds"] = round((state.get("finished_at") or time.time()) - state["started_at"])
    out["log"] = state["log"][-8:]
    return out


@server.tool()
def cancel_render(job_id: str = "") -> dict:
    """Stop a running render (the latest one if job_id is empty)."""
    running = [s for s in _jobs.values() if s["state"] == "running" and (not job_id or s["id"] == job_id)]
    for s in running:
        s["cancel"] = True
    return {"cancelled": [s["id"] for s in running]}


def main():
    server.run("stdio")
