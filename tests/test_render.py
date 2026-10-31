"""End-to-end tests with tiny synthetic videos made by FFmpeg (skipped when FFmpeg is missing)."""

import os
import shutil
import subprocess
import tempfile
import unittest

from PIL import features

from qve import ffmpeg
from qve.config import DEFAULTS, deep_merge, load_jobs, prepare_job

HAVE_FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")
HAVE_RAQM = features.check("raqm")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def make(path, source, seconds, audio=False):
    args = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", source]
    if audio:
        args += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100"]
    args += ["-t", str(seconds), "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    if audio:
        args += ["-c:a", "aac", "-shortest"]
    subprocess.run(args + [path], check=True)


@unittest.skipUnless(HAVE_FFMPEG, "FFmpeg not installed")
class RenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="qve-test-")
        cls.recitation = os.path.join(cls.tmp, "recitation.mp4")
        # white "text" moving over black, like a recitation video, with audio
        make(cls.recitation, "color=black:s=640x360:r=25,drawbox=x=200+t*20:y=150:w=180:h=40:color=white:t=fill",
             5, audio=True)
        cls.clips = os.path.join(cls.tmp, "clips")
        os.makedirs(cls.clips)
        make(os.path.join(cls.clips, "a.mp4"), "testsrc2=s=640x360:r=30", 3)
        make(os.path.join(cls.clips, "b.mp4"), "smptehdbars=s=320x240:r=24", 3)
        make(os.path.join(cls.clips, "c.mp4"), "testsrc2=s=360x640:r=60", 3)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def job(self, **extra):
        project = deep_merge({
            "quran_video": self.recitation,
            "output": os.path.join(self.tmp, "out", "{surah_en}.mp4"),
            "meta": {"surah_en": "Test Surah", "surah_ar": "سورة الرحمن", "reciter": "Reciter"},
            "intro_seconds": 1,
            "backgrounds": {"folder": self.clips, "max_clip_seconds": 2.5, "min_clip_seconds": 1.5,
                            "seed": 7, "blur": 2},
            "transitions": {"duration": 0.5, "types": ["fade", "dissolve", "circleopen"]},
            "video": {"width": 320, "height": 180, "preset": "ultrafast", "threads": 2},
            "render": {"clips_per_chunk": 2},
        }, extra)
        return prepare_job(deep_merge(DEFAULTS, project), self.tmp)

    def frames_and_audio(self, path):
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-count_frames", "-show_entries",
             "stream=codec_type,nb_read_frames,width,height", "-of", "csv=p=0", path],
            capture_output=True, text=True, check=True).stdout.split()
        return out

    def test_full_render(self):
        from qve.render import Job

        job = self.job()
        r = Job(job)
        r.run(report=lambda *a, **k: None)
        self.assertTrue(os.path.exists(job["output"]))
        self.assertEqual(r.total, 30 * 6)          # 1 s intro + 5 s recitation at 30 fps
        self.assertGreater(len(r.chunks), 1)       # chunking was exercised
        streams = self.frames_and_audio(job["output"])
        self.assertIn("video,320,180,180", streams)
        self.assertTrue(any(s.startswith("audio") for s in streams))
        self.assertFalse(os.path.exists(r.tmp))    # temp files cleaned up

    def test_chromakey_and_limit(self):
        from qve.render import Job

        job = self.job(quran_layer={"key": "chromakey"}, output=os.path.join(self.tmp, "out", "green.mp4"))
        Job(job, limit_seconds=2).run(report=lambda *a, **k: None)
        self.assertIn("video,320,180,60", self.frames_and_audio(job["output"]))

    @unittest.skipUnless(HAVE_RAQM, "Pillow without libraqm")
    def test_render_with_cards(self):
        from qve.render import Job

        job = self.job(cards=[{"template": "royal", "start": 0, "duration": 2},
                              {"template": "corner", "start": 2.5, "duration": 2, "animation": "fade"}],
                       output=os.path.join(self.tmp, "out", "cards.mp4"))
        Job(job, limit_seconds=3).run(report=lambda *a, **k: None)
        self.assertIn("video,320,180,90", self.frames_and_audio(job["output"]))

    def test_cancel(self):
        from qve.render import Job

        job = self.job(output=os.path.join(self.tmp, "out", "cancelled.mp4"))
        with self.assertRaises(ffmpeg.Cancelled):
            Job(job).run(report=lambda *a, **k: None, stop=lambda: True)
        self.assertFalse(os.path.exists(job["output"]))

    def test_preview(self):
        from qve import preview

        img = preview.compose(self.job(), 2.0, os.path.join(self.clips, "a.mp4"), 5.0, size=(320, 180))
        self.assertEqual(img.size, (320, 180))
        self.assertGreater(max(img.convert("L").getextrema()), 100)

    def test_missing_video_message(self):
        from qve.render import Job

        job = self.job(quran_video=os.path.join(self.tmp, "nope.mp4"))
        with self.assertRaisesRegex(FileNotFoundError, "recitation video not found"):
            Job(job)


@unittest.skipUnless(HAVE_RAQM, "Pillow without libraqm")
class CardTest(unittest.TestCase):
    def test_every_template_draws(self):
        from qve.cards import TEMPLATES, render_image

        meta = {"surah_ar": "سورة الملك", "surah_en": "Surah Al-Mulk", "surah_meaning": "The Sovereignty",
                "surah_number": 67, "reciter": "Reciter", "channel": "Channel"}
        for name in TEMPLATES:
            img = render_image(name, meta, {}, 480, 270)
            self.assertEqual(img.size, (480, 270), name)
            self.assertGreater(img.getchannel("A").getextrema()[1], 200, name)


class ConfigTest(unittest.TestCase):
    def test_example_batch(self):
        jobs = load_jobs(os.path.join(ROOT, "examples", "batch.json"))
        self.assertEqual(len(jobs), 2)
        self.assertTrue(jobs[0]["output"].endswith(os.path.join("output", "Surah Ar-Rahman - Reciter One.mp4")))
        self.assertEqual(jobs[1]["cards"][1]["template"], "bismillah")
        self.assertTrue(os.path.isabs(jobs[1]["quran_video"]))

    def test_unsafe_filename_characters(self):
        job = prepare_job(deep_merge(DEFAULTS, {"quran_video": "x.mp4", "output": "out/{surah_en}.mp4",
                                                "meta": {"surah_en": 'A: B? "C"'}}), "/base")
        self.assertEqual(os.path.basename(job["output"]), "A_ B_ _C_.mp4")


try:
    import mcp  # noqa: F401
    HAVE_MCP = True
except ImportError:
    HAVE_MCP = False


@unittest.skipUnless(HAVE_MCP, "mcp not installed")
class McpToolsTest(unittest.TestCase):
    def test_find_surah(self):
        from qve.mcp_server import find_surah

        self.assertEqual(find_surah("55")[0]["surah_ar"], "سورة الرحمن")
        self.assertEqual(find_surah("mulk")[0]["surah_number"], 67)
        self.assertEqual(len(find_surah("114")), 1)

    def test_templates(self):
        from qve.mcp_server import list_templates

        self.assertIn("royal", [t["name"] for t in list_templates()])


if __name__ == "__main__":
    unittest.main()
