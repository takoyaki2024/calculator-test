from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

from .models import ImageItem, MangaWork, SourceFolder, VideoItem
from .sorts import SortRegistry
from .thumbnails import ThumbnailCache
from .video_thumbnails import VideoThumbnailer


class ThumbnailSignals(QObject):
    finished = Signal(object, object, object)


class ThumbnailWorker(QRunnable):
    def __init__(self, key, generation, path):
        super().__init__()
        self.key, self.generation, self.path = key, generation, path
        self.signals = ThumbnailSignals()

    def run(self):
        try:
            value = ThumbnailCache.decode(self.path)
        except Exception:
            value = None
        self.signals.finished.emit(self.key, self.generation, value)


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
        self.offset = 0
        self.page_size = 100
        self.entries = {}
        self.thumbnail_sources = {}
        self.thumbnail_pool = QThreadPool(self)
        self.thumbnail_pool.setMaxThreadCount(2)
        self.search_timer = QTimer(self, singleShot=True, interval=250)
        self.search_timer.timeout.connect(self.refresh)
        self.video_thumbnails = VideoThumbnailer(thumbnails, self) if kind == "動画" else None
        self.video_completed = set()
        self.video_visible = set()
        self.video_timer = QTimer(self, singleShot=True, interval=350)
        self.video_timer.timeout.connect(self._visible_video_thumbnails)
        layout = QVBoxLayout(self)
        heading = QLabel(title)
        heading.setObjectName("heading")
        layout.addWidget(heading)
        controls = QHBoxLayout()
        self.search = QLineEdit(placeholderText="タイトルを検索")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda: self.search_timer.start())
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
        self.list.verticalScrollBar().valueChanged.connect(self._schedule_video_thumbnails)
        self.list.horizontalScrollBar().valueChanged.connect(self._schedule_video_thumbnails)
        paging = QHBoxLayout()
        self.previous_button = QPushButton("前の100件")
        self.next_button = QPushButton("次の100件")
        self.count_label = QLabel()
        self.previous_button.clicked.connect(lambda: self._page(-1))
        self.next_button.clicked.connect(lambda: self._page(1))
        paging.addWidget(self.previous_button)
        paging.addWidget(self.count_label, 1)
        paging.addWidget(self.next_button)
        layout.addLayout(paging)
        self.empty = QLabel("フォルダを設定すると、ここに表示されます")
        self.empty.setObjectName("muted")
        layout.addWidget(self.empty)

    def refresh(self) -> None:
        self.search_timer.stop()
        self.offset = 0
        self.items = self.sorts.apply(self.load_items(self.search.text().strip()), self.sort.currentData() or "newest")
        self._populate()

    def _page(self, direction):
        self.offset = max(0, self.offset + direction * self.page_size)
        self._populate()

    def _populate(self):
        self.generation += 1
        generation = self.generation
        self.thumbnail_pool.clear()
        if self.video_thumbnails:
            self.video_thumbnails.reset()
            self.video_completed.clear()
            self.video_visible.clear()
        items = self.items[self.offset:self.offset + self.page_size]
        def identity(item):
            prefix = "manga" if isinstance(item, MangaWork) else "image" if isinstance(item, ImageItem) else "video"
            return prefix, item.id

        self.by_id = {identity(item): item for item in items}
        self.list.clear()
        self.entries.clear()
        self.thumbnail_sources.clear()
        for item in items:
            entry = QListWidgetItem(item.title)
            item_key = identity(item)
            entry.setData(Qt.ItemDataRole.UserRole, item_key)
            entry.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            if isinstance(item, MangaWork) and item.cover_path:
                try:
                    stat = item.cover_path.stat()
                    self.thumbnail_sources[item_key] = (item.cover_path, stat.st_size, stat.st_mtime_ns)
                    pixmap = self.thumbnails.placeholder("漫画")
                except OSError:
                    pixmap = self.thumbnails.placeholder("漫画")
            elif isinstance(item, ImageItem):
                self.thumbnail_sources[item_key] = (item.path, item.size, item.mtime_ns)
                pixmap = self.thumbnails.placeholder("画像")
            elif isinstance(item, VideoItem):
                pixmap = self.thumbnails.placeholder("▶\n動画")
            else:
                pixmap = self.thumbnails.placeholder(self.kind)
            entry.setIcon(QIcon(pixmap))
            entry.setToolTip(str(item.path) if hasattr(item, "path") else item.title)
            self.list.addItem(entry)
            self.entries[item_key] = entry
            if item_key in self.thumbnail_sources:
                path, size, mtime = self.thumbnail_sources[item_key]
                try:
                    cached = self.thumbnails.cached(path, size, mtime)
                except OSError:
                    cached = None
                if cached is not None:
                    entry.setIcon(QIcon(cached))
                else:
                    worker = ThumbnailWorker(item_key, generation, path)
                    worker.signals.finished.connect(self._image_thumbnail)
                    self.thumbnail_pool.start(worker)
        self.empty.setVisible(not items)
        total = len(self.items)
        self.count_label.setText(f"{self.offset + 1 if total else 0}–{self.offset + len(items)} / {total}件")
        self.previous_button.setEnabled(self.offset > 0)
        self.next_button.setEnabled(self.offset + self.page_size < total)
        self._schedule_video_thumbnails()

    def _schedule_video_thumbnails(self, *_):
        if self.video_thumbnails and self.isVisible():
            self.video_timer.start()

    def _visible_video_thumbnails(self):
        if not self.video_thumbnails or not self.isVisible():
            return
        viewport = self.list.viewport().rect()
        keys = {key for key, entry in self.entries.items()
                if not self.list.visualItemRect(entry).isEmpty()
                and self.list.visualItemRect(entry).intersects(viewport)}
        if keys == self.video_visible:
            return
        self.video_visible = keys
        self.video_thumbnails.reset()
        for key in self.entries:  # preserve display order
            if key in keys and key not in self.video_completed:
                self.video_thumbnails.request(
                    self.by_id[key],
                    lambda value, key=key, token=self.generation: self._video_thumbnail(key, token, value))

    def showEvent(self, event):
        super().showEvent(event)
        self._schedule_video_thumbnails()

    def hideEvent(self, event):
        if self.video_thumbnails:
            self.video_timer.stop()
            self.video_thumbnails.reset()
            self.video_visible.clear()
        super().hideEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_video_thumbnails()

    def _image_thumbnail(self, key, generation, image):
        if generation != self.generation or key not in self.entries or image is None or image.isNull():
            return
        try:
            path, size, mtime = self.thumbnail_sources[key]
            pixmap = self.thumbnails.store(path, size, mtime, image)
            self.entries[key].setIcon(QIcon(pixmap))
        except OSError:
            pass

    def _video_thumbnail(self, item_key, generation: int, pixmap) -> None:
        if generation != self.generation:
            return
        self.video_completed.add(item_key)
        if pixmap is None:
            return
        entry = self.entries.get(item_key)
        if entry is not None:
            entry.setIcon(QIcon(pixmap))


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
