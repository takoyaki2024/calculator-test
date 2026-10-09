from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from .models import MangaPage, MangaWork
from .repositories import MangaRepository


class MangaReader(QWidget):
    back_requested = Signal()

    def __init__(self, repository: MangaRepository):
        super().__init__()
        self.repository = repository
        self.work: MangaWork | None = None
        self.pages: tuple[MangaPage, ...] = ()
        self.index = 0
        self.zoom = 1.0
        self.fit = True
        self.cached_page = None
        self.original_pixmap = QPixmap()
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        for label, callback in (("← 一覧", self.back_requested.emit), ("前", self.previous), ("次", self.next),
                                ("−", self.zoom_out), ("＋", self.zoom_in), ("幅に合わせる", self.fit_width)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            controls.addWidget(button)
        self.status = QLabel()
        controls.addWidget(self.status, 1, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(controls)
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setWidget(self.label)
        layout.addWidget(self.scroll, 1)

    def open_work(self, work: MangaWork) -> None:
        self.cached_page = None
        self.work = work
        self.pages = self.repository.pages(work.id)
        self.index = min(work.last_page, max(0, len(self.pages) - 1))
        self.fit = True
        self._render()

    def _render(self) -> None:
        if not self.pages:
            self.label.setText("ページが見つかりません")
            return
        page = self.pages[self.index]
        if self.cached_page != page.path:
            reader = QImageReader(str(page.path))
            reader.setAutoTransform(True)
            image = reader.read()
            if image.isNull():
                self.label.setText(f"この画像を開けません\n{reader.errorString()}")
                return
            self.original_pixmap = QPixmap.fromImage(image)
            self.cached_page = page.path
        pixmap = self.original_pixmap
        if self.fit:
            width = max(200, self.scroll.viewport().width() - 24)
            pixmap = pixmap.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
        else:
            pixmap = pixmap.scaled(pixmap.size() * self.zoom, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
        self.label.setPixmap(pixmap)
        self.label.resize(pixmap.size())
        self.status.setText(f"{self.work.title}  {self.index + 1} / {len(self.pages)}")

    def previous(self) -> None:
        if self.index > 0:
            self.index -= 1
            self._save()
            self._render()

    def next(self) -> None:
        if self.index + 1 < len(self.pages):
            self.index += 1
            self._save()
            self._render()

    def _save(self) -> None:
        if self.work:
            self.repository.save_position(self.work.id, self.index)

    def zoom_in(self) -> None:
        self.fit = False
        self.zoom = min(4.0, self.zoom * 1.2)
        self._render()

    def zoom_out(self) -> None:
        self.fit = False
        self.zoom = max(0.2, self.zoom / 1.2)
        self._render()

    def fit_width(self) -> None:
        self.fit = True
        self._render()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.fit and self.pages:
            self._render()
