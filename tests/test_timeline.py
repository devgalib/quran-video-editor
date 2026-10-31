import unittest

from qve.timeline import plan_backgrounds, plan_chunks

FPS, TRANS = 30, 30
OPTS = {"seed": 1, "min_clip_seconds": 4, "max_clip_seconds": 20, "random_start": True}


def clips(*durations):
    return [{"path": f"c{i}.mp4", "duration": d} for i, d in enumerate(durations)]


class TimelineTest(unittest.TestCase):
    def check(self, library, total, per_chunk=3):
        uses = plan_backgrounds(library, total, FPS, TRANS, OPTS, ["fade", "dissolve"])
        self.assertEqual(uses[0].start, 0)
        self.assertEqual(uses[-1].end, total)
        for prev, cur in zip(uses, uses[1:]):
            self.assertEqual(cur.start, prev.end - TRANS)       # exact overlap = transition
            self.assertGreater(cur.length, TRANS)
            self.assertNotEqual(cur.path, prev.path)            # no clip twice in a row
        chunks = plan_chunks(uses, total, FPS, TRANS, per_chunk)
        self.assertEqual(chunks[0].start, 0)
        self.assertEqual(chunks[-1].end, total)
        for a, b in zip(chunks, chunks[1:]):
            self.assertEqual(a.end, b.start)
        for chunk in chunks:
            # the chained xfades must produce exactly the chunk's frame count
            length = chunk.items[0].length
            for item in chunk.items[1:]:
                self.assertEqual(item.offset, length - TRANS)
                length = item.offset + item.length
            self.assertEqual(length, chunk.length)
        return uses, chunks

    def test_long_video_many_clips(self):
        uses, chunks = self.check(clips(10, 12, 15, 20, 30, 8), 9 * 60 * FPS)
        self.assertGreater(len(chunks), 5)
        self.assertTrue(all(len(c.items) <= 4 for c in chunks))

    def test_short_video_single_clip(self):
        uses, chunks = self.check(clips(30), 10 * FPS)
        self.assertEqual(len(uses), 1)

    def test_awkward_lengths(self):
        for total_s in (21, 37.4, 59.9, 61, 123.3):
            self.check(clips(10, 11, 6.5), int(total_s * FPS))

    def test_too_short_library(self):
        with self.assertRaises(ValueError):
            plan_backgrounds(clips(1, 2), 300, FPS, TRANS, OPTS, ["fade"])


if __name__ == "__main__":
    unittest.main()
