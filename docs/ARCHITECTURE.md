# Architecture

```
qve/
  config.py        project/batch JSON: defaults, deep merge, path resolution
  library.py       background clip discovery + cached ffprobe results
  timeline.py      clip placement and chunk planning (pure, frame-exact, unit tested)
  render.py        builds one FFmpeg filter graph per chunk, runs them, joins the result
  preview.py       one composed still frame with Pillow, for the live preview
  ffmpeg.py        locating, probing and running FFmpeg (progress, cancel, low priority)
  cards/           text card templates (Pillow + libraqm for Arabic shaping) and bundled fonts
  gui/             PySide6 desktop app
  mcp_server.py    MCP server over stdio
  cli.py           command line
```

## Render pipeline

1. **Plan the timeline** (`timeline.plan_backgrounds`). Everything is counted in whole output frames.
   Clips are taken in a shuffled order (all clips are used before any repeats, never the same clip
   twice in a row). Clip *i* starts `transition` frames before clip *i-1* ends; that overlap is the
   `xfade` transition. The last clip is cut to end exactly at the last frame, and a clip is never
   left on screen for less than about a second.
2. **Cut into chunks** (`timeline.plan_chunks`). Every `clips_per_chunk` clips (default 6), the
   timeline is cut in the middle of a clip's *solo* part, where no transition is running.
3. **Render each chunk** (`render.Job.chunk_args`): one FFmpeg command whose filter graph is
   - each clip: seek, `fps`, scale-to-cover and crop, pad with its last frame if it runs short, trim
     to its frame count;
   - chained `xfade`s at frame-exact offsets, then dim (`lutyuv`) and optional `gblur`;
   - the recitation video, seeked to the chunk's time, padded with black (or the key colour) for the
     intro and outro, then either
     - **screen blend** in RGB (`blend=all_mode=screen` on `gbrp`): black becomes transparent, white
       and coloured text stay bright, and anti-aliased letter edges stay smooth; a small black point
       lift (`lutrgb`) hides compression noise in the "black", or
     - **chroma key** (`chromakey` + `overlay`) for green screens;
   - each card PNG overlapping the chunk, looped in memory (`loop`), faded with `fade:alpha=1`,
     and overlaid with an optional rising `y` expression.
4. **Join** the chunks with the concat demuxer (`-c:v copy`) and add the recitation audio, delayed by
   the intro (`adelay`) and padded to the full length (`apad`).

Chunk files are named by a hash of their FFmpeg arguments and written to `.part` files first, so an
interrupted render resumes with the chunks that already finished. The random seed is stored in the
temp folder, so a resumed render picks the same clips.

## Why chunks

FFmpeg opens and decodes every input of a command at once. Measured on 1080p H.264 clips:

| Clips in one command | Peak memory |
|---|---|
| 10 | 0.9 GB |
| 50 | 3.5 GB |

A 10-minute video needs about 40–60 clips, which would not fit next to a browser on an 8 GB laptop.
With chunks of 6 clips, peak memory stays around 1 GB for any length.

Cutting at a solo part means no transition is ever split across two files. The chunks are encoded
with identical settings and each starts with a keyframe, so joining them needs no re-encode, and the
frame-to-frame difference at a join is the same as anywhere else (checked in development).

## Performance

On an AMD Ryzen laptop CPU with 4 encoder threads, x264 `veryfast`, CRF 20:

| Settings | Speed |
|---|---|
| Screen blend, dim | ~2.3× real time |
| Screen blend, dim, blur 3 | ~1.5× real time |

FFmpeg runs at low CPU priority (`nice 10` / below-normal on Windows) and with a fixed thread
count, so the machine stays responsive and cooler. GPU encoders (NVENC, Quick Sync, AMF) take most
of the encoding work off the CPU.

## Cards and preview

Cards are drawn once per render as full-frame transparent PNGs at 2× size and scaled down, which
gives smooth ornaments. Arabic text is shaped by libraqm (through Pillow) and set in Amiri or Aref
Ruqaa. The live preview (`preview.compose`) builds the same frame with Pillow from single frames
that FFmpeg extracts, in about 0.3 s, so changes show without rendering.
