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

    def test_surah_picker_fills_titles(self):
        from qve.gui.window import MainWindow

        win = MainWindow()
        win.on_surah_picked(55)  # item 0 is "Choose surah…", so item n is surah n
        self.assertEqual(win.meta_edits["surah_ar"].text(), "سورة الرحمن")
        self.assertEqual(win.meta_edits["surah_number"].text(), "55")
        win.close()


if __name__ == "__main__":
    unittest.main()
