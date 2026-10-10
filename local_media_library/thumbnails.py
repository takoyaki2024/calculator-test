from __future__ import annotations

import hashlib
import os
from pathlib import Path

from PySide6.QtCore import QIODevice, QSaveFile, QSize, Qt
from PySide6.QtGui import QColor, QImage, QImageReader, QPainter, QPixmap


class ThumbnailCache:
    def __init__(self, directory: Path, max_bytes: int = 512 * 1024 * 1024):
        self.directory = directory
        self.max_bytes = max_bytes
        self.needs_prune = False
        directory.mkdir(parents=True, exist_ok=True)

    def _key(self, source: Path, size: int, mtime_ns: int) -> Path:
        value = f"{source.resolve()}\0{size}\0{mtime_ns}".encode("utf-8", "surrogatepass")
        return self.directory / f"{hashlib.sha256(value).hexdigest()}.jpg"

    def cached(self, source: Path, size: int, mtime_ns: int) -> QPixmap | None:
        path = self._key(source, size, mtime_ns)
        if not path.is_file():
            return None
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return None
        # Cache maintenance must not turn a concurrently deleted file into an
        # empty JPEG or discard an otherwise usable in-memory thumbnail.
        try:
            os.utime(path, None)
        except OSError:
            pass
        return pixmap

    def store(self, source: Path, size: int, mtime_ns: int, image: QImage,
              target: QSize = QSize(220, 300)) -> QPixmap:
        canvas = QImage(target, QImage.Format.Format_RGB32)
        canvas.fill(QColor("#111827"))
        scaled = image.scaled(target, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        painter = QPainter(canvas)
        painter.drawImage((target.width() - scaled.width()) // 2, (target.height() - scaled.height()) // 2, scaled)
        painter.end()
        output = QSaveFile(str(self._key(source, size, mtime_ns)))
        if not output.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(output.errorString())
        if not canvas.save(output, "JPG", 84):
            output.cancelWriting()
            raise OSError("サムネイルを保存できません")
        if not output.commit():
            raise OSError(output.errorString())
        self.needs_prune = True
        return QPixmap.fromImage(canvas)

    def image(self, source: Path, size: int, mtime_ns: int, target: QSize = QSize(220, 300)) -> QPixmap:
        cached_pixmap = self.cached(source, size, mtime_ns)
        if cached_pixmap is not None:
            return cached_pixmap
        image = self.decode(source, target)
        if image.isNull():
            return self.placeholder("未対応", target)
        return self.store(source, size, mtime_ns, image, target)

    @staticmethod
    def decode(source: Path, target: QSize = QSize(220, 300)) -> QImage:
        """Worker-safe decoding: no QPixmap or source writes."""
        reader = QImageReader(str(source))
        reader.setAutoTransform(True)
        original = reader.size()
        if original.isValid():
            original.scale(target, Qt.AspectRatioMode.KeepAspectRatio)
            reader.setScaledSize(original)
        return reader.read()

    @staticmethod
    def placeholder(label: str, target: QSize = QSize(220, 300)) -> QPixmap:
        image = QImage(target, QImage.Format.Format_RGB32)
        image.fill(QColor("#182235"))
        painter = QPainter(image)
        painter.setPen(QColor("#9fb0c7"))
        painter.drawText(image.rect(), Qt.AlignmentFlag.AlignCenter, label)
        painter.end()
        return QPixmap.fromImage(image)

    def prune(self) -> int:
        self.needs_prune = False
        files = []
        total = 0
        for path in self.directory.glob("*.jpg"):
            try:
                stat = path.stat()
            except OSError:
                continue
            total += stat.st_size
            files.append((stat.st_atime_ns, stat.st_size, path))
        removed = 0
        for _, length, path in sorted(files):
            if total <= self.max_bytes:
                break
            try:
                path.unlink()
                total -= length
                removed += 1
            except OSError:
                pass
        return removed
