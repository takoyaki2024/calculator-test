from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

from .models import ImageItem, MangaWork, SourceFolder, VideoItem
from .sorts import SortRegistry
from .thumbnails import ThumbnailCache
from .video_thumbnails import VideoThumbnailer


class LibraryPage(QWidget):
    item_opened = Signal(object)

    def __init__(self, title: str, load_items: Callable, sorts: SortRegistry, thumbnails: ThumbnailCache,
                 kind: str):
        super().__init__()
        self.load_items = load_items
        self.sorts = sorts
        self.thumbnails = thumbnails
        self.kind = kind
        self.by_id = {}
        self.generation = 0
        self.video_thumbnails = VideoThumbnailer(thumbnails, self) if kind == "動画" else None
        layout = QVBoxLayout(self)
        heading = QLabel(title)
        heading.setObjectName("heading")
        layout.addWidget(heading)
        controls = QHBoxLayout()
        self.search = QLineEdit(placeholderText="タイトルを検索")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        controls.addWidget(self.search, 1)
        self.sort = QComboBox()
        for option in sorts.options():
            self.sort.addItem(option.label, option.key)
        self.sort.currentIndexChanged.connect(self.refresh)
        controls.addWidget(self.sort)
        refresh = QPushButton("更新")
        refresh.clicked.connect(self.refresh)
        controls.addWidget(refresh)
        layout.addLayout(controls)
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setIconSize(QSize(176, 240))
        self.list.setGridSize(QSize(210, 290))
        self.list.setWordWrap(True)
        self.list.itemActivated.connect(lambda item: self.item_opened.emit(item.data(Qt.ItemDataRole.UserRole)))
        layout.addWidget(self.list, 1)
        self.empty = QLabel("フォルダを設定すると、ここに表示されます")
        self.empty.setObjectName("muted")
        layout.addWidget(self.empty)

    def refresh(self) -> None:
        self.generation += 1
        generation = self.generation
        if self.video_thumbnails:
            self.video_thumbnails.reset()
        items = self.load_items(self.search.text().strip())
        items = self.sorts.apply(items, self.sort.currentData() or "newest")
        def identity(item):
            prefix = "manga" if isinstance(item, MangaWork) else "image" if isinstance(item, ImageItem) else "video"
            return prefix, item.id

        self.by_id = {identity(item): item for item in items}
        self.list.clear()
        for item in items:
            entry = QListWidgetItem(item.title)
            item_key = identity(item)
            entry.setData(Qt.ItemDataRole.UserRole, item_key)
            entry.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            if isinstance(item, MangaWork) and item.cover_path:
                try:
                    stat = item.cover_path.stat()
                    pixmap = self.thumbnails.image(item.cover_path, stat.st_size, stat.st_mtime_ns)
                except OSError:
                    pixmap = self.thumbnails.placeholder("漫画")
            elif isinstance(item, ImageItem):
                pixmap = self.thumbnails.image(item.path, item.size, item.mtime_ns)
            elif isinstance(item, VideoItem):
                pixmap = self.thumbnails.placeholder("▶\n動画")
            else:
                pixmap = self.thumbnails.placeholder(self.kind)
            entry.setIcon(QIcon(pixmap))
            entry.setToolTip(str(item.path) if hasattr(item, "path") else item.title)
            self.list.addItem(entry)
            if isinstance(item, VideoItem) and self.video_thumbnails:
                self.video_thumbnails.request(
                    item, lambda value, item_key=item_key, token=generation: self._video_thumbnail(item_key, token, value)
                )
        self.empty.setVisible(not items)

    def _video_thumbnail(self, item_key, generation: int, pixmap) -> None:
        if generation != self.generation or pixmap is None:
            return
        for index in range(self.list.count()):
            entry = self.list.item(index)
            if entry.data(Qt.ItemDataRole.UserRole) == item_key:
                entry.setIcon(QIcon(pixmap))
                break


class SettingsPage(QWidget):
    add_requested = Signal(str, str)
    scan_requested = Signal()

    def __init__(self, data_path):
        super().__init__()
        layout = QVBoxLayout(self)
        heading = QLabel("設定")
        heading.setObjectName("heading")
        layout.addWidget(heading)
        help_text = QLabel("保存済みメディアのフォルダを登録します。原本の移動・削除・改名は行いません。")
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        row = QHBoxLayout()
        add_manga = QPushButton("漫画フォルダを追加")
        add_manga.clicked.connect(lambda: self._choose("manga"))
        row.addWidget(add_manga)
        add_gallery = QPushButton("画像・動画フォルダを追加")
        add_gallery.clicked.connect(lambda: self._choose("gallery"))
        row.addWidget(add_gallery)
        scan = QPushButton("すべて再スキャン")
        scan.clicked.connect(self.scan_requested.emit)
        row.addWidget(scan)
        row.addStretch()
        layout.addLayout(row)
        self.sources = QListWidget()
        layout.addWidget(self.sources, 1)
        location = QLabel(f"管理データ: {data_path}\nサムネイルは削除しても再生成できます。")
        location.setObjectName("muted")
        location.setWordWrap(True)
        layout.addWidget(location)

    def _choose(self, mode: str) -> None:
        path = QFileDialog.getExistingDirectory(self, "保存済みメディアのフォルダ")
        if path:
            self.add_requested.emit(path, mode)

    def set_sources(self, sources: tuple[SourceFolder, ...]) -> None:
        self.sources.clear()
        labels = {"auto": "旧自動", "manga": "漫画", "gallery": "画像・動画", "image": "画像", "video": "動画"}
        for source in sources:
            state = "利用可能" if source.available else "未接続"
            self.sources.addItem(f"[{labels[source.mode]}] {source.path}  —  {state}")
