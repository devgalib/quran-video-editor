"""Command line: python -m qve <command> ..."""

import argparse
import os
import sys
import time

from . import cards, ffmpeg, library
from .config import load_jobs


def cmd_render(a):
    jobs = load_jobs(a.project)
    if a.only:
        jobs = [jobs[i - 1] for i in a.only]
    failed = 0
    for n, job in enumerate(jobs, 1):
        if a.keep_temp:
            job["render"]["keep_temp"] = True
        if os.path.exists(job["output"]) and not a.overwrite:
            print(f"[{n}/{len(jobs)}] skip, exists: {job['output']}")
            continue
        print(f"[{n}/{len(jobs)}]", end=" ", flush=True)
        try:
            from .render import Job
            Job(job, a.seconds).run(lambda msg, end="\n": print(msg, end=end, flush=True))
        except Exception as exc:  # keep going with the rest of a batch
            failed += 1
            print(f"FAILED: {exc}", file=sys.stderr, flush=True)
    return 1 if failed else 0


def cmd_cards(a):
    """Write every card of the project as PNG, to check the design before rendering."""
    from .cards.draw import check_arabic_support
    check_arabic_support()
    job = load_jobs(a.project)[0]
    os.makedirs(a.out, exist_ok=True)
    for i, card in enumerate(job["cards"], 1):
        fields = {**job["meta"], **card.get("fields", {})}
        path = os.path.join(a.out, f"card_{i}_{card['template']}.png")
        cards.render(card["template"], fields, card.get("options", {}),
                     job["video"]["width"], job["video"]["height"], path)
        print(path)


def cmd_templates(_a):
    for name, fn in cards.TEMPLATES.items():
        print(f"{name:16} {(fn.__doc__ or '').strip()}")


def cmd_scan(a):
    t = time.time()
    paths = library.find_videos(a.folder)
    clips = library.clip_infos(paths, workers=a.workers)
    total = sum(c["duration"] for c in clips)
    print(f"{len(clips)} usable clips of {len(paths)} files, {total / 60:.1f} min in total "
          f"({time.time() - t:.1f}s; cached for next time)")


def cmd_encoders(_a):
    hw = ffmpeg.list_hw_encoders()
    print("libx264 (CPU) always available")
    print("hardware: " + (", ".join(hw) if hw else "none usable on this machine"))


def cmd_gui(_a):
    from .gui import main as gui_main
    return gui_main()


def cmd_mcp(_a):
    from .mcp_server import main as mcp_main
    mcp_main()


def main(argv=None):
    p = argparse.ArgumentParser(prog="qve", description="Quran video editor")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="render a project or batch file")
    r.add_argument("project")
    r.add_argument("--seconds", type=float, help="render only the first N seconds (quick preview)")
    r.add_argument("--only", type=int, nargs="+", metavar="N", help="render only these job numbers")
    r.add_argument("--overwrite", action="store_true", help="re-render outputs that already exist")
    r.add_argument("--keep-temp", action="store_true", help="keep chunk files and logs")
    r.set_defaults(fn=cmd_render)

    c = sub.add_parser("cards", help="export the project's cards as PNG")
    c.add_argument("project")
    c.add_argument("--out", default="card-preview")
    c.set_defaults(fn=cmd_cards)

    sub.add_parser("templates", help="list card templates").set_defaults(fn=cmd_templates)

    s = sub.add_parser("scan", help="probe a clip folder and cache durations")
    s.add_argument("folder")
    s.add_argument("--workers", type=int, default=4)
    s.set_defaults(fn=cmd_scan)

    sub.add_parser("encoders", help="list usable hardware encoders").set_defaults(fn=cmd_encoders)
    sub.add_parser("gui", help="open the desktop app").set_defaults(fn=cmd_gui)
    sub.add_parser("mcp", help="run the MCP server on stdio").set_defaults(fn=cmd_mcp)

    a = p.parse_args(argv)
    return a.fn(a) or 0
