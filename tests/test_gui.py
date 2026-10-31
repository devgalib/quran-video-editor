"""The desktop window builds and turns its widgets into a valid job (headless; skipped without PySide6)."""

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QSettings

    HAVE_QT = True
except ImportError:
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class WindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from qve.gui import create_app

        cls.tmp = tempfile.TemporaryDirectory()
        QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, cls.tmp.name)
        cls.app = create_app(["qve-test"])

    def test_collect_apply_roundtrip(self):
        from qve.config import DEFAULTS, deep_merge
        from qve.gui.window import MainWindow

        win = MainWindow()
        job = deep_merge(DEFAULTS, {
            "meta": {"surah_en": "Surah Al-Mulk", "surah_number": 67, "reciter": "R"},
            "intro_seconds": 8,
            "transitions": {"types": ["dissolve", "circleopen"]},
            "cards": [{"template": "bismillah", "start": 0, "duration": 5, "fields": {"translation": ""}}],
        })
        win.apply(job)
        out = win.collect()
        self.assertEqual(out["meta"]["surah_number"], 67)
        self.assertEqual(out["intro_seconds"], 8)
        self.assertEqual(out["transitions"]["types"], ["dissolve", "circleopen"])
        self.assertEqual(out["cards"][0]["template"], "bismillah")
        self.assertFalse(win.c_translation.isChecked())
        win.close()

    def test_changing_intro_updates_timeline(self):
        from qve.gui.window import MainWindow

        win = MainWindow()
        win.quran_info = {"duration": 20.0, "width": 1920, "height": 1080, "fps": 25.0, "has_audio": True}
        win.intro.setValue(10)  # used to recurse until RecursionError
        self.assertEqual(win.time_slider.maximum(), 299)
        self.assertTrue(win.time_label.text().endswith("0:30"))
        win.close()

    def test_leaving_the_video_box_keeps_the_preview_time(self):
        from qve.gui.window import MainWindow

        win = MainWindow()
        win.quran_edit.setText("/some/video.mp4")
        win.on_quran_changed()
        win.quran_info = {"duration": 20.0, "width": 1920, "height": 1080, "fps": 25.0, "has_audio": True}
        win._update_timeline()
        win.time_slider.setValue(55)
        win.on_quran_changed()  # focus left the box without a change
        self.assertIsNotNone(win.quran_info)
        self.assertEqual(win.time_slider.value(), 55)
        win.close()

    def test_surah_picker_fills_titles(self):
        from qve.gui.window import MainWindow

        win = MainWindow()
        win.on_surah_picked(55)  # item 0 is "Choose surah…", so item n is surah n
        self.assertEqual(win.meta_edits["surah_ar"].text(), "سورة الرحمن")
        self.assertEqual(win.meta_edits["surah_number"].text(), "55")
        win.close()


if __name__ == "__main__":
    unittest.main()
