"""Placing background clips on the timeline and splitting it into render chunks.

All timeline positions are whole frames, so chunks join back together exactly.
Clip i starts `trans` frames before clip i-1 ends; the overlap is the transition.
"""

import random
from dataclasses import dataclass


@dataclass
class ClipUse:
    path: str
    src_in: float        # seconds into the source clip
    start: int           # timeline frame
    length: int          # frames
    transition: str      # xfade type into this clip ("" for the first)

    @property
    def end(self):
        return self.start + self.length


@dataclass
class ChunkItem:
    path: str
    src_in: float
    length: int          # frames used from src_in on
    offset: int          # frame (chunk-relative) where the transition into this item starts
    transition: str


@dataclass
class Chunk:
    index: int
    start: int
    end: int
    items: list

    @property
    def length(self):
        return self.end - self.start


def _clip_order(clips, rng):
    """Endless shuffled stream of clips; no clip repeats until all were used, never twice in a row."""
    last = None
    while True:
        batch = clips[:]
        rng.shuffle(batch)
        if last is not None and len(batch) > 1 and batch[0]["path"] == last["path"]:
            batch.append(batch.pop(0))
        yield from batch
        last = batch[-1]


def plan_backgrounds(clips, total, fps, trans, opts, transition_types, order="random"):
    """Cover `total` frames with clips. Returns [ClipUse]."""
    rng = random.Random(opts.get("seed"))
    min_len = max(int(opts["min_clip_seconds"] * fps), 2 * trans + fps)
    max_len = max(int(opts["max_clip_seconds"] * fps), min_len)
    usable = [c for c in clips if int((c["duration"] - 0.25) * fps) >= min_len]
    if not usable:
        raise ValueError(f"no background clip is at least {min_len / fps:.1f}s long")

    uses = []
    start = 0
    tail = trans + fps  # never leave a last piece shorter than this
    for n, clip in enumerate(_clip_order(usable, rng)):
        avail = int((clip["duration"] - 0.25) * fps)
        length = min(avail, max_len)
        if start + length >= total:
            length = total - start
        elif total - (start + length - trans) < tail:
            # the next clip would only flash briefly: stretch this one, or shorten it
            if start + avail >= total:
                length = total - start
            else:
                length = max(min_len, total - start - tail + trans)
                if total - (start + length - trans) < trans + 2:
                    length = total - start  # renderer freezes the last frame if the clip runs out
        src_in = 0.0
        if opts.get("random_start") and avail > length:
            src_in = rng.uniform(0, (avail - length) / fps)
        if order == "cycle":
            kind = transition_types[(n - 1) % len(transition_types)]
        else:
            kind = rng.choice(transition_types)
        uses.append(ClipUse(clip["path"], round(src_in, 3), start, length, kind if uses else ""))
        if start + length >= total:
            return uses
        start += length - trans


def plan_chunks(uses, total, fps, trans, clips_per_chunk):
    """Cut the timeline in the middle of a clip's solo part every `clips_per_chunk` clips."""
    cuts = [0]
    for i in range(clips_per_chunk, len(uses), clips_per_chunk):
        use = uses[i]
        solo_start = use.start + trans
        solo_end = use.end - (trans if i < len(uses) - 1 else 0)
        if solo_end - solo_start >= 2:
            cuts.append((solo_start + solo_end) // 2)
    cuts.append(total)

    chunks = []
    for index, (a, b) in enumerate(zip(cuts, cuts[1:])):
        items = []
        for use in uses:
            lo, hi = max(use.start, a), min(use.end, b)
            if lo >= hi:
                continue
            items.append(ChunkItem(
                path=use.path,
                src_in=round(use.src_in + (lo - use.start) / fps, 3),
                length=hi - lo,
                offset=use.start - a if items else 0,
                transition=use.transition if items else "",
            ))
        chunks.append(Chunk(index, a, b, items))
    return chunks
