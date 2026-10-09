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
        self.token = 0
        self._create_decoder()
        self.queue = deque()
        self.current = None
        self.timeout = QTimer(self, singleShot=True, interval=10000)
        self.timeout.timeout.connect(lambda: self._finish(None))
        self.next_timer = QTimer(self, singleShot=True, interval=500)
        self.next_timer.timeout.connect(self._next)

    def _create_decoder(self):
        if hasattr(self, "player"):
            self.player.stop()
            self.player.setSource(QUrl())
            self.player.deleteLater()
            self.sink.deleteLater()
        self.player = QMediaPlayer(self)
        self.sink = QVideoSink(self)
        self.player.setVideoOutput(self.sink)
        token = self.token
        self.player.mediaStatusChanged.connect(lambda status: self._status(status, token))
        self.player.errorOccurred.connect(lambda *_: self._finish(None, token))
        self.sink.videoFrameChanged.connect(lambda frame: self._frame(frame, token))

    def request(self, item: VideoItem, callback: Callable[[QPixmap | None], None]) -> None:
        try:
            cached = self.cache.cached(item.path, item.size, item.mtime_ns)
        except OSError:
            cached = None
        if cached is not None:
            callback(cached)
            return
        self.queue.append((item, callback))
        if self.current is None and not self.next_timer.isActive():
            self.next_timer.start()

    def reset(self) -> None:
        self.token += 1
        self.timeout.stop()
        self.next_timer.stop()
        self.queue.clear()
        self.current = None
        self.player.stop()
        self.player.setSource(QUrl())

    def _next(self) -> None:
        if self.current is not None:
            return
        if not self.queue:
            self.current = None
            return
        self.current = self.queue.popleft()
        item, _callback = self.current
        if not item.path.is_file() or item.path.is_symlink():
            self._finish(None)
            return
        self.timeout.start()
        self.token += 1
        self._create_decoder()
        self.player.setSource(QUrl.fromLocalFile(str(item.path)))

    def _status(self, status, token=None) -> None:
        if self.current is None or (token is not None and token != self.token):
            return
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            # First frame avoids seeking/decode work across a long GOP.
            self.player.play()
        elif status in (QMediaPlayer.MediaStatus.InvalidMedia, QMediaPlayer.MediaStatus.EndOfMedia):
            self._finish(None)

    def _frame(self, frame, token=None) -> None:
        if self.current is None or (token is not None and token != self.token) or not frame.isValid():
            return
        item, _callback = self.current
        image = frame.toImage()
        if not image.isNull():
            try:
                pixmap = self.cache.store(item.path, item.size, item.mtime_ns, image)
            except OSError:
                pixmap = None
            self._finish(pixmap)

    def _finish(self, pixmap, token=None) -> None:
        if self.current is None or (token is not None and token != self.token):
            return
        self.timeout.stop()
        _item, callback = self.current
        self.current = None
        self.token += 1
        self.player.stop()
        self.player.setSource(QUrl())
        callback(pixmap)
        self.next_timer.start()
