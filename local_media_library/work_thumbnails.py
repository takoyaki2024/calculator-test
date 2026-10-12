"""Owned, sequential child-process extraction for representative video covers."""
from __future__ import annotations

import json
import sys
from collections import deque

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QSaveFile, QIODevice, QTimer, Signal


class WorkThumbnailer(QObject):
    cancelled = Signal()
    def __init__(self, cache, parent=None):
        super().__init__(parent)
        self.cache = cache
        self.queue = deque()
        self.current = None
        self.process = None
        self.last_error = ""
        self.failures_path = cache.directory / 'video-failures.json'
        try:
            failures = json.loads(self.failures_path.read_text(encoding='utf-8'))
            self.failures = failures if isinstance(failures, dict) else {}
        except (OSError, ValueError):
            self.failures = {}
        self.next_timer = QTimer(self, singleShot=True, interval=500)
        self.next_timer.timeout.connect(self._next)
        self.timeout = QTimer(self, singleShot=True, interval=15000)
        self.timeout.timeout.connect(self._expired)

    def _key(self, item):
        return self.cache._key(item.path, item.size, item.mtime_ns).stem

    def _cached(self, item):
        try:
            return self.cache.cached(item.path, item.size, item.mtime_ns)
        except OSError:
            return None

    def request(self, item, callback, *, retry=False):
        self.last_error = ''
        cached = self._cached(item)
        if cached is not None:
            callback(cached)
            return
        key = self._key(item)
        if retry:
            self.failures.pop(key, None)
            self._save_failures()
        elif key in self.failures:
            self.last_error = str(self.failures[key])
            callback(None)
            return
        self.queue.append((item, callback))
        if self.current is None and not self.next_timer.isActive():
            self.next_timer.start()

    def reset(self):
        had_requests = self.current is not None or bool(self.queue)
        self.timeout.stop()
        self.next_timer.stop()
        self.queue.clear()
        self.current = None
        self._dispose()
        if had_requests:
            self.cancelled.emit()

    def keep_visible(self, items):
        keys = {self._key(item) for item in items}
        self.queue = deque((item, callback) for item, callback in self.queue if self._key(item) in keys)
        if self.current is not None and self._key(self.current[0]) not in keys:
            self.timeout.stop()
            self.current = None
            self._dispose()
            self.cancelled.emit()
        if self.current is None and self.queue and not self.next_timer.isActive():
            self.next_timer.start()

    def _dispose(self):
        process, self.process = self.process, None
        if process is not None:
            # Only our own child is ever killed. Wait bounds overlap with the next child.
            if process.state() != QProcess.ProcessState.NotRunning:
                process.kill()
                process.waitForFinished(1000)
            process.deleteLater()

    def _next(self):
        if self.current is not None or not self.queue:
            return
        self.current = self.queue.popleft()
        item, _ = self.current
        cached = self._cached(item)
        if cached is not None:
            self._finish(cached)
            return
        if not item.path.is_file() or item.path.is_symlink():
            self._finish(None, '原本が見つからないか、シンボリックリンクです')
            return
        process = self.process = QProcess(self)
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert('QT_QPA_PLATFORM', 'offscreen')
        process.setProcessEnvironment(environment)
        process.finished.connect(lambda code, status, owner=process: self._completed(owner, code, status))
        process.errorOccurred.connect(lambda error, owner=process: self._process_error(owner, error))
        # Child logs contain no result protocol; discard bounded native decoder output.
        process.setStandardOutputFile(QProcess.nullDevice())
        process.setStandardErrorFile(QProcess.nullDevice())
        arguments = ([] if getattr(sys, 'frozen', False) else ['-m', 'local_media_library']) + [
            '--thumbnail-worker', str(item.path), '--thumbnail-cache', str(self.cache.directory),
            '--thumbnail-size', str(item.size), '--thumbnail-mtime', str(item.mtime_ns)]
        self.timeout.start()
        process.start(sys.executable, arguments)

    def _completed(self, owner, code, status):
        if owner is not self.process or self.current is None:
            return
        item, _ = self.current
        cached = self._cached(item) if code == 0 and status == QProcess.ExitStatus.NormalExit else None
        if cached is not None:
            self.cache.needs_prune = True
        self._finish(cached, '' if cached is not None else 'この動画から表紙を生成できませんでした')

    def _process_error(self, owner, error):
        if owner is self.process and error == QProcess.ProcessError.FailedToStart:
            self._finish(None, '表紙の生成処理を起動できませんでした')

    def _expired(self):
        if self.current is not None:
            self._finish(None, '15秒以内に表紙を生成できなかったため、生成処理を終了しました')

    def _finish(self, pixmap, reason=''):
        if self.current is None:
            return
        self.timeout.stop()
        item, callback = self.current
        self.current = None
        self._dispose()
        self.last_error = reason
        key = self._key(item)
        if pixmap is None:
            self.failures[key] = reason
            while len(self.failures) > 4096:
                self.failures.pop(next(iter(self.failures)))
        else:
            removed = self.failures.pop(key, None)
        if pixmap is None or removed is not None:
            self._save_failures()
        callback(pixmap)
        if self.current is None and self.queue:
            self.next_timer.start()

    def _save_failures(self):
        output = QSaveFile(str(self.failures_path))
        if output.open(QIODevice.OpenModeFlag.WriteOnly):
            output.write(json.dumps(self.failures, ensure_ascii=False).encode('utf-8'))
            output.commit()


def run_thumbnail_worker(source, directory, expected_size, expected_mtime):
    """Existing Qt decoder is isolated here; the parent enforces a hard deadline."""
    from PySide6.QtWidgets import QApplication
    from .models import VideoItem
    from .thumbnails import ThumbnailCache
    from .video_thumbnails import VideoThumbnailer
    # Lower only this child's scheduling priority; this is not a CPU ceiling.
    try:
        if sys.platform == 'win32':
            import ctypes
            kernel = ctypes.windll.kernel32
            kernel.GetCurrentProcess.restype = ctypes.c_void_p
            kernel.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x4000)
        else:
            import os
            os.nice(10)
    except (OSError, AttributeError):
        pass
    try:
        if source.is_symlink() or not source.is_file():
            return 2
        stat = source.stat()
        if (stat.st_size, stat.st_mtime_ns) != (expected_size, expected_mtime):
            return 2
    except OSError:
        return 2
    app = QApplication.instance() or QApplication([])
    cache = ThumbnailCache(directory)
    decoder = VideoThumbnailer(cache)
    item = VideoItem(0, 0, source.name, source, source.stem, True, expected_size, expected_mtime)
    # No MainWindow, no scan, no Player and no thumbnails for other files.
    QTimer.singleShot(0, lambda: decoder.request(item, lambda pixmap: app.exit(0 if pixmap is not None else 2)))
    result = app.exec()
    decoder.reset()
    return result


def run_work_cover_probe(fixtures, report):
    """Package gate: the frozen parent launches two frozen worker processes."""
    import hashlib
    import tempfile
    from pathlib import Path
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    from .models import VideoItem
    from .thumbnails import ThumbnailCache
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        cache = ThumbnailCache(Path(directory))
        generator = WorkThumbnailer(cache)
        items = []
        hashes = []
        for name in ('work-red.mp4', 'work-blue.mp4'):
            path = fixtures / name
            stat = path.stat()
            items.append(VideoItem(len(items), 0, name, path, name, True, stat.st_size, stat.st_mtime_ns))
            hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
        received = []
        def finished(pixmap):
            received.append(pixmap)
            if len(received) == 2:
                app.quit()
        for item in items:
            generator.request(item, finished)
        guard = QTimer(singleShot=True, interval=35000)
        guard.timeout.connect(app.quit)
        guard.start()
        app.exec()
        guard.stop()
        generated = len(received) == 2 and all(p is not None for p in received)
        cache_count = len(list(cache.directory.glob('*.jpg')))
        colors = []
        for item in items:
            image = QImage(str(cache._key(item.path, item.size, item.mtime_ns)))
            if not image.isNull():
                colors.append(image.pixelColor(image.width() // 2, image.height() // 2))
        distinct = (len(colors) == 2 and colors[0].red() > 200 and colors[0].blue() < 30
                    and colors[1].blue() > 200 and colors[1].red() < 30)
        repeated = []
        for item in items:
            generator.request(item, repeated.append)
        reuse = len(repeated) == 2 and all(p is not None for p in repeated) and not generator.queue and generator.process is None
        unchanged = hashes == [hashlib.sha256(i.path.read_bytes()).hexdigest() for i in items]
        generator.reset()
        passed = generated and cache_count == 2 and distinct and reuse and unchanged
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({'result': 'PASS' if passed else 'FAIL', 'works': 2, 'cache_files': cache_count,
                                     'distinct_frames': distinct, 'reuse_without_decoder': reuse,
                                     'originals_unchanged': unchanged}, indent=2), encoding='utf-8')
        return 0 if passed else 2
