"""Background work for the window: previews, folder scans, renders. Nothing here touches widgets."""

import traceback

from PySide6.QtCore import QObject, QRunnable, QThread, Signal
from PySide6.QtGui import QImage

from .. import ffmpeg, library, preview


def pil_to_qimage(im):
    data = im.tobytes("raw", "RGB")
    return QImage(data, im.width, im.height, 3 * im.width, QImage.Format.Format_RGB888).copy()


class _Signals(QObject):
    result = Signal(object, object)   # (tag, value)
    failed = Signal(object, str)


class Task(QRunnable):
    """Run fn(*args) on the thread pool; emit result(tag, value) or failed(tag, message)."""

    def __init__(self, tag, fn, *args):
        super().__init__()
        self.tag, self.fn, self.args = tag, fn, args
        self.signals = _Signals()

    def run(self):
        try:
            value = self.fn(*self.args)
        except Exception as exc:
            self.signals.failed.emit(self.tag, f"{exc}")
            return
        self.signals.result.emit(self.tag, value)


def make_preview(job, t, bg_clip, quran_duration, size):
    return pil_to_qimage(preview.compose(job, t, bg_clip, quran_duration, size))


def scan_folder(folder):
    """Probe every clip (results are cached for the renderer). Returns (paths, total_seconds)."""
    clips = library.clip_infos(library.find_videos(folder))
    return [c["path"] for c in clips], sum(c["duration"] for c in clips)


def probe_video(path):
    return ffmpeg.probe(path)


def hw_encoders():
    return ffmpeg.list_hw_encoders()


class RenderThread(QThread):
    progress = Signal(float, float, float)   # fraction, speed, eta seconds
    line = Signal(str)
    done = Signal(bool, str)                 # ok, output path or error message

    def __init__(self, job, limit_seconds=None):
        super().__init__()
        self.job, self.limit = job, limit_seconds
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        from ..render import Job

        def report(msg, end="\n"):
            if end == "\n":
                self.line.emit(msg.strip())

        try:
            Job(self.job, self.limit).run(report, self.progress.emit, lambda: self._stop)
        except ffmpeg.Cancelled:
            self.done.emit(False, "Cancelled. Starting again continues from the last finished part.")
        except Exception as exc:
            self.line.emit(traceback.format_exc())
            self.done.emit(False, str(exc))
        else:
            self.done.emit(True, self.job["output"])
