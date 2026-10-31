"""Finding, probing and running FFmpeg."""

import json
import os
import shutil
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = ".exe" if os.name == "nt" else ""


def find_tool(name):
    """QVE_FFMPEG_DIR env var, then ./bin next to the app, then PATH."""
    candidates = []
    if os.environ.get("QVE_FFMPEG_DIR"):
        candidates.append(os.path.join(os.environ["QVE_FFMPEG_DIR"], name + EXE))
    candidates.append(os.path.join(ROOT, "bin", name + EXE))
    for path in candidates:
        if os.path.isfile(path):
            return path
    found = shutil.which(name)
    if not found:
        raise FileNotFoundError(
            f"{name} not found. Install FFmpeg, put it in {os.path.join(ROOT, 'bin')}, "
            "or set QVE_FFMPEG_DIR."
        )
    return found


def probe(path):
    """Return {"duration", "width", "height", "fps", "has_audio"} for a media file."""
    out = subprocess.run(
        [find_tool("ffprobe"), "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,width,height,avg_frame_rate",
         "-of", "json", path],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    info = {"duration": float(data["format"].get("duration") or 0),
            "width": 0, "height": 0, "fps": 0.0, "has_audio": False}
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and not info["width"]:
            info["width"], info["height"] = stream.get("width", 0), stream.get("height", 0)
            num, _, den = stream.get("avg_frame_rate", "0/1").partition("/")
            info["fps"] = float(num) / float(den) if float(den or 0) else 0.0
        elif stream.get("codec_type") == "audio":
            info["has_audio"] = True
    return info


def _popen_kwargs(low_priority):
    if not low_priority:
        return {}
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)}
    return {"preexec_fn": lambda: os.nice(10)}


class FFmpegError(RuntimeError):
    pass


class Cancelled(Exception):
    pass


def run(args, log_path, on_frame=None, low_priority=True, stop=None):
    """Run ffmpeg with `args` (without the binary). on_frame(n) gets the encoded frame count.

    stop: optional callable; when it returns True, ffmpeg is killed and Cancelled is raised.
    """
    cmd = [find_tool("ffmpeg"), "-hide_banner", "-nostdin", "-y", "-v", "error",
           "-progress", "pipe:1", "-nostats"] + args
    with open(log_path, "w", encoding="utf-8") as log:
        log.write(subprocess.list2cmdline(cmd) + "\n\n")
        log.flush()
        with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=log, text=True,
                              **_popen_kwargs(low_priority)) as proc:
            for line in proc.stdout:
                if stop and stop():
                    proc.kill()
                    raise Cancelled()
                if on_frame and line.startswith("frame="):
                    try:
                        on_frame(int(line[6:]))
                    except ValueError:
                        pass
        code = proc.returncode
    if code != 0:
        with open(log_path, encoding="utf-8", errors="replace") as log:
            tail = log.read()[-3000:]
        raise FFmpegError(f"ffmpeg failed (exit {code}). Log: {log_path}\n{tail}")


def list_hw_encoders():
    """Try a tiny encode with each hardware H.264 encoder; return the ones that work."""
    working = []
    for enc in ("h264_nvenc", "h264_qsv", "h264_amf"):
        result = subprocess.run(
            [find_tool("ffmpeg"), "-v", "error", "-f", "lavfi", "-i",
             "color=black:s=1280x720:r=30:d=0.2", "-c:v", enc, "-f", "null", "-"],
            capture_output=True,
        )
        if result.returncode == 0:
            working.append(enc)
    return working


def encoder_args(video):
    enc, q, threads = video["encoder"], str(video["quality"]), str(video["threads"])
    if enc == "libx264":
        return ["-c:v", "libx264", "-preset", video["preset"], "-crf", q,
                "-profile:v", "high", "-threads", threads]
    if enc == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", q, "-b:v", "0"]
    if enc == "h264_qsv":
        return ["-c:v", "h264_qsv", "-preset", "medium", "-global_quality", q]
    if enc == "h264_amf":
        return ["-c:v", "h264_amf", "-quality", "balanced", "-rc", "cqp",
                "-qp_i", q, "-qp_p", str(int(q) + 2)]
    raise ValueError(f"unknown encoder: {enc}")
