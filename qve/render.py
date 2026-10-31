"""Rendering a job: plan the timeline, render it chunk by chunk, then join and add audio.

Why chunks: FFmpeg opens every input of a command at once, and 50 open 1080p clips need
~3.5 GB of RAM. Each chunk opens only a handful of clips, so memory stays well under 1 GB.
Chunks are cut where a single clip is on screen (never inside a transition), are encoded
with identical settings, and are joined without re-encoding. Finished chunks are kept, so
a stopped render resumes where it left off.
"""

import hashlib
import json
import os
import random
import shutil
import time

from . import cards, ffmpeg, library
from .cards.draw import check_arabic_support
from .config import safe_filename
from .timeline import plan_backgrounds, plan_chunks


def _sec(frames, fps):
    return f"{frames / fps:.6f}"


class Job:
    def __init__(self, job, limit_seconds=None):
        self.cfg = job
        v = job["video"]
        self.w, self.h, self.fps = int(v["width"]), int(v["height"]), int(v["fps"])
        if not os.path.isfile(job["quran_video"]):
            raise FileNotFoundError(f"recitation video not found: {job['quran_video']}")
        folder = job["backgrounds"]["folder"]
        if folder and not os.path.isdir(folder):
            raise FileNotFoundError(f"background clip folder not found: {folder}")
        self.quran = ffmpeg.probe(job["quran_video"])
        self.intro = round(job["intro_seconds"] * self.fps)
        self.quran_frames = int(self.quran["duration"] * self.fps)
        self.total = self.intro + self.quran_frames + round(job["outro_seconds"] * self.fps)
        if limit_seconds:
            self.total = min(self.total, round(limit_seconds * self.fps))
        self.trans = max(1, round(job["transitions"]["duration"] * self.fps))
        self.output = job["output"]
        stem = safe_filename(os.path.splitext(os.path.basename(self.output))[0])
        self.tmp = os.path.join(os.path.dirname(self.output) or ".", ".qve-tmp", stem)

    # ---- planning ------------------------------------------------------------------------

    def _state(self):
        """Persist the random seed so a resumed render picks the same clips."""
        path = os.path.join(self.tmp, "state.json")
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            state = {"seed": random.randrange(1 << 30)}
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(state, fh)
            return state

    def plan(self):
        os.makedirs(self.tmp, exist_ok=True)
        bg = dict(self.cfg["backgrounds"])
        if bg["seed"] is None:
            bg["seed"] = self._state()["seed"]
        clips = library.collect(bg)
        tr = self.cfg["transitions"]
        self.uses = plan_backgrounds(clips, self.total, self.fps, self.trans, bg,
                                     tr["types"], tr["order"])
        self.chunks = plan_chunks(self.uses, self.total, self.fps, self.trans,
                                  self.cfg["render"]["clips_per_chunk"])
        self.cards = self._render_cards()

    def _render_cards(self):
        out = []
        if self.cfg["cards"]:
            check_arabic_support()
        for card in self.cfg["cards"]:
            fields = {**self.cfg["meta"], **card.get("fields", {})}
            options = card.get("options", {})
            key = json.dumps([card["template"], fields, options, self.w, self.h], sort_keys=True,
                             ensure_ascii=False)
            path = os.path.join(self.tmp, f"card_{hashlib.sha1(key.encode()).hexdigest()[:12]}.png")
            if not os.path.exists(path):
                cards.render(card["template"], fields, options, self.w, self.h, path)
            start_s = card.get("start", 0)
            if start_s < 0:  # negative: seconds before the end
                start_s = self.total / self.fps + start_s
            start = round(start_s * self.fps)
            length = min(round(card.get("duration", 6) * self.fps), self.total - start)
            if length > 0:
                out.append({"path": path, "start": start, "length": length,
                            "fade": card.get("fade", 0.8), "animation": card.get("animation", "rise")})
        return out

    # ---- one chunk -----------------------------------------------------------------------

    def chunk_args(self, chunk):
        fps, w, h, n = self.fps, self.w, self.h, chunk.length
        args, graph = [], []

        for i, item in enumerate(chunk.items):
            args += ["-threads", "2", "-ss", f"{item.src_in:.3f}",
                     "-t", f"{item.length / fps + 1:.3f}", "-i", item.path]
            graph.append(
                f"[{i}:v]fps={fps},setpts=PTS-STARTPTS,"
                f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,"
                f"format=yuv420p,tpad=stop=-1:stop_mode=clone,trim=end_frame={item.length},"
                f"setpts=PTS-STARTPTS[b{i}]")
        prev = "b0"
        for i, item in enumerate(chunk.items[1:], start=1):
            graph.append(f"[{prev}][b{i}]xfade=transition={item.transition}:"
                         f"duration={_sec(self.trans, fps)}:offset={_sec(item.offset, fps)}[x{i}]")
            prev = f"x{i}"

        bg = self.cfg["backgrounds"]
        post = []
        if bg["dim"]:
            k = 1 - float(bg["dim"])
            post.append(f"lutyuv=y='(val-16)*{k:.3f}+16':u='(val-128)*{k:.3f}+128':"
                        f"v='(val-128)*{k:.3f}+128'")
        if bg["blur"]:
            post.append(f"gblur=sigma={bg['blur'] * h / 1080:.2f}")
        graph.append(f"[{prev}]{','.join(post) or 'null'}[bg]")
        main, idx = "bg", len(chunk.items)

        # Quran layer, if the recitation is on screen during this chunk
        q_from = chunk.start - self.intro
        if q_from < self.quran_frames and chunk.end > self.intro:
            layer = self.cfg["quran_layer"]
            keyed = layer["key"] == "chromakey"
            pad_color = layer["key_color"] if keyed else "black"
            pad = max(0, -q_from)
            seek = max(0, q_from) / fps
            qw = round(w * layer["scale"] / 2) * 2
            qh = round(h * layer["scale"] / 2) * 2
            args += ["-threads", "2", "-ss", f"{seek:.3f}", "-t", f"{n / fps + 1:.3f}",
                     "-i", self.cfg["quran_video"]]
            graph.append(
                f"[{idx}:v]fps={fps},setpts=PTS-STARTPTS,"
                f"scale={qw}:{qh}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={pad_color},setsar=1,format=yuv420p,"
                f"tpad=start={pad}:stop=-1:color={pad_color},trim=end_frame={n}[fg]")
            idx += 1
            if keyed:
                graph.append(f"[fg]chromakey=color={layer['key_color']}:similarity={layer['similarity']}:"
                             f"blend={layer['blend']}[fgk]")
                graph.append("[bg][fgk]overlay=format=auto[m]")
            else:
                t = float(layer["black_point"]) * 255
                lut = f"'clip((val-{t:.1f})*255/{255 - t:.1f},0,255)'"
                graph.append(f"[fg]format=gbrp,lutrgb=r={lut}:g={lut}:b={lut}[fgr]")
                graph.append("[bg]format=gbrp[bgr]")
                graph.append("[bgr][fgr]blend=all_mode=screen,format=yuv420p[m]")
            main = "m"

        # Text cards
        for j, card in enumerate(self.cards):
            lo, hi = max(card["start"], chunk.start), min(card["start"] + card["length"], chunk.end)
            if lo >= hi:
                continue
            fade = min(card["fade"], card["length"] / fps / 2)
            card_s = card["length"] / fps
            skip = lo - card["start"]
            delay = card["start"] - chunk.start
            args += ["-i", card["path"]]
            graph.append(
                f"[{idx}:v]format=rgba,loop=loop={card['length'] - 1}:size=1:start=0,"
                f"settb=1/{fps},setpts=N,"
                f"fade=t=in:st=0:d={fade:.3f}:alpha=1,"
                f"fade=t=out:st={card_s - fade:.3f}:d={fade:.3f}:alpha=1,"
                f"trim=start_frame={skip}:end_frame={skip + hi - lo},"
                f"setpts=PTS-STARTPTS+{max(0, delay)}[k{j}]")
            idx += 1
            y = "0"
            if card["animation"] == "rise":
                s, d, r = delay / fps, fade * 1.6, 28 * h / 1080
                y = f"'if(lt(t-{s:.3f},{d:.3f}),{r:.1f}*pow(1-max(t-{s:.3f},0)/{d:.3f},3),0)'"
            graph.append(f"[{main}][k{j}]overlay=x=0:y={y}:eval=frame:eof_action=pass[c{j}]")
            main = f"c{j}"

        graph.append(f"[{main}]format=yuv420p[out]")
        threads = str(self.cfg["video"]["threads"])
        args += ["-filter_complex", ";".join(graph), "-filter_complex_threads", threads,
                 "-map", "[out]", "-an", "-frames:v", str(n), "-r", str(fps),
                 "-pix_fmt", "yuv420p"] + ffmpeg.encoder_args(self.cfg["video"])
        return args

    # ---- whole job -----------------------------------------------------------------------

    def run(self, report=print, progress=None, stop=None):
        """report(msg, end) gets text lines; progress(fraction, speed, eta_seconds) gets numbers."""
        self.plan()
        low = self.cfg["render"]["low_priority"]
        done_frames, started = 0, time.time()
        report(f"{os.path.basename(self.output)}: {self.total / self.fps:.0f}s, "
               f"{len(self.uses)} clips, {len(self.chunks)} chunks, {len(self.cards)} cards")

        files = []
        for chunk in self.chunks:
            args = self.chunk_args(chunk)
            digest = hashlib.sha1(json.dumps(args, ensure_ascii=False).encode()).hexdigest()[:10]
            path = os.path.join(self.tmp, f"chunk_{chunk.index:04d}_{digest}.mp4")
            files.append(path)
            if not os.path.exists(path):
                part = path[:-4] + ".part.mp4"
                t0, base = time.time(), done_frames

                def on_frame(frame, base=base, t0=t0, chunk=chunk):
                    done = base + frame
                    elapsed = time.time() - started
                    speed = frame / self.fps / max(time.time() - t0, 1e-3)
                    eta = elapsed / max(done, 1) * (self.total - done) if done else 0
                    if progress:
                        progress(done / self.total, speed, eta)
                    report(f"  chunk {chunk.index + 1}/{len(self.chunks)}  "
                           f"{100 * done / self.total:5.1f}%  {speed:4.1f}x  ETA {eta:4.0f}s", end="\r")

                ffmpeg.run(args + [part], path[:-4] + ".log", on_frame, low, stop)
                os.replace(part, path)
            done_frames += chunk.length

        self._finish(files, low, stop)
        report(f"  done in {time.time() - started:.0f}s -> {self.output}" + " " * 20)
        if not self.cfg["render"]["keep_temp"]:
            shutil.rmtree(self.tmp, ignore_errors=True)
            try:
                os.rmdir(os.path.dirname(self.tmp))
            except OSError:
                pass

    def _finish(self, files, low, stop=None):
        listing = os.path.join(self.tmp, "chunks.txt")
        with open(listing, "w", encoding="utf-8") as fh:
            for f in files:
                escaped = os.path.abspath(f).replace("'", "'\\''")
                fh.write(f"file '{escaped}'\n")
        os.makedirs(os.path.dirname(self.output) or ".", exist_ok=True)
        final_tmp = os.path.join(self.tmp, "final.mp4")
        args = ["-f", "concat", "-safe", "0", "-i", listing]
        if self.quran["has_audio"]:
            delay = round(self.intro / self.fps * 1000)
            args += ["-i", self.cfg["quran_video"], "-filter_complex",
                     f"[1:a]adelay=delays={delay}:all=1,apad[a]",
                     "-map", "0:v", "-map", "[a]", "-c:a", "aac",
                     "-b:a", self.cfg["video"]["audio_bitrate"]]
        args += ["-c:v", "copy", "-t", _sec(self.total, self.fps), "-movflags", "+faststart", final_tmp]
        ffmpeg.run(args, os.path.join(self.tmp, "final.log"), None, low, stop)
        os.replace(final_tmp, self.output)
