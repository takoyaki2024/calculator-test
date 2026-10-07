from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from .models import ImageItem


class ImageViewer(QWidget):
    back_requested = Signal()

    def __init__(self):
        super().__init__()
        self.item: ImageItem | None = None
        self.pixmap = QPixmap()
        self.fit = True
        self.zoom = 1.0
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        for label, callback in (("← 一覧", self.back_requested.emit), ("−", self.zoom_out),
                                ("＋", self.zoom_in), ("画面に合わせる", self.fit_view)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        self.title = QLabel()
        row.addWidget(self.title, 1, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(row)
        self.label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.scroll = QScrollArea(widgetResizable=True)
        self.scroll.setWidget(self.label)
        layout.addWidget(self.scroll, 1)

    def open_item(self, item: ImageItem) -> None:
        self.item = item
        reader = QImageReader(str(item.path))
        reader.setAutoTransform(True)
        image = reader.read()
        self.pixmap = QPixmap.fromImage(image)
        self.title.setText(item.title)
        if self.pixmap.isNull():
            self.label.setText(f"この画像を開けません\n{reader.errorString()}")
            return
        self.fit = True
        self._render()

    def _render(self) -> None:
        if self.pixmap.isNull():
            return
        target = self.pixmap
        if self.fit:
            target = target.scaled(self.scroll.viewport().size(), Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
        else:
            target = target.scaled(target.size() * self.zoom, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
        self.label.setPixmap(target)
        self.label.resize(target.size())

    def zoom_in(self) -> None:
        self.fit = False
        self.zoom = min(4.0, self.zoom * 1.2)
        self._render()

    def zoom_out(self) -> None:
        self.fit = False
        self.zoom = max(0.2, self.zoom / 1.2)
        self._render()

    def fit_view(self) -> None:
        self.fit = True
        self._render()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.fit:
            self._render()
