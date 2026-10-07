from __future__ import annotations

from collections import deque
from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QMediaPlayer, QVideoSink

from .models import VideoItem
from .thumbnails import ThumbnailCache


class VideoThumbnailer(QObject):
    """Sequentially decodes one frame; never writes to the media source."""

    def __init__(self, cache: ThumbnailCache, parent=None):
        super().__init__(parent)
        self.cache = cache
        self.player = QMediaPlayer(self)
        self.sink = QVideoSink(self)
        self.player.setVideoOutput(self.sink)
        self.player.mediaStatusChanged.connect(self._status)
        self.player.errorOccurred.connect(lambda *_: self._finish(None))
        self.sink.videoFrameChanged.connect(self._frame)
        self.queue = deque()
        self.current = None

    def request(self, item: VideoItem, callback: Callable[[QPixmap | None], None]) -> None:
        cached = self.cache.cached(item.path, item.size, item.mtime_ns)
        if cached is not None:
            callback(cached)
            return
        self.queue.append((item, callback))
        if self.current is None:
            self._next()

    def reset(self) -> None:
        self.queue.clear()
        self.current = None
        self.player.stop()
        self.player.setSource(QUrl())

    def _next(self) -> None:
        if not self.queue:
            self.current = None
            return
        self.current = self.queue.popleft()
        item, _callback = self.current
        if not item.path.is_file() or item.path.is_symlink():
            self._finish(None)
            return
        self.player.setSource(QUrl.fromLocalFile(str(item.path)))

    def _status(self, status) -> None:
        if self.current is None:
            return
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            duration = self.player.duration()
            self.player.setPosition(min(3000, max(0, duration // 10)))
            self.player.play()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self._finish(None)

    def _frame(self, frame) -> None:
        if self.current is None or not frame.isValid():
            return
        item, _callback = self.current
        image = frame.toImage()
        if not image.isNull():
            self._finish(self.cache.store(item.path, item.size, item.mtime_ns, image))

    def _finish(self, pixmap) -> None:
        if self.current is None:
            return
        _item, callback = self.current
        self.current = None
        self.player.stop()
        self.player.setSource(QUrl())
        callback(pixmap)
        QTimer.singleShot(0, self._next)
