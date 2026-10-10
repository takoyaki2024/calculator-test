from __future__ import annotations

from collections.abc import Callable
from weakref import ref

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

from .models import ImageItem, MangaWork, SourceFolder, VideoItem, VideoWork
from .sorts import SortRegistry
from .thumbnails import ThumbnailCache
from .video_thumbnails import VideoThumbnailer
from .work_thumbnails import WorkThumbnailer


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
                 kind: str, auto_video_thumbnails: bool = True, load_page: Callable | None = None,
                 thumbnailer_factory=VideoThumbnailer):
        super().__init__()
        self.load_items = load_items
        self.load_page = load_page
        self.total = 0
        self.sorts = sorts
        self.thumbnails = thumbnails
        self.kind = kind
        self.auto_video_thumbnails = auto_video_thumbnails
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
        self.video_thumbnails = thumbnailer_factory(thumbnails, self) if kind == "動画" else None
        self.video_completed = set()
        self.video_visible = set()
        self.video_requested = set()
        self.image_requested = set()
        self.search_pending = False
        self.video_timer = QTimer(self, singleShot=True, interval=350)
        self.video_timer.timeout.connect(self._visible_video_thumbnails)
        layout = QVBoxLayout(self)
        heading = self.heading = QLabel(title)
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
        self.list.itemActivated.connect(self._activate)
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

    def _activate(self, item):
        self.item_opened.emit(item.data(Qt.ItemDataRole.UserRole))

    def refresh(self, *, preserve=False) -> None:
        self.search_pending = False
        self.search_timer.stop()
        scroll = self.list.verticalScrollBar().value() if preserve else 0
        current = self.list.currentItem()
        selected = current.data(Qt.ItemDataRole.UserRole) if preserve and current else None
        if not preserve:
            self.offset = 0
        self._load_current()
        if selected in self.entries:
            self.list.setCurrentItem(self.entries[selected])
        self.list.doItemsLayout()
        self.list.verticalScrollBar().setValue(scroll)

    def _load_current(self):
        query, sort = self.search.text().strip(), self.sort.currentData() or "newest"
        if self.load_page:
            result = self.load_page(query, offset=self.offset, limit=self.page_size, sorts=self.sorts, sort=sort)
            self.total = result.total
            if self.offset >= self.total and self.offset:
                self.offset = max(0, ((self.total - 1) // self.page_size) * self.page_size)
                result = self.load_page(query, offset=self.offset, limit=self.page_size, sorts=self.sorts, sort=sort)
            self.items = result.items
        else:
            self.items = self.sorts.apply(self.load_items(query), sort)
            self.total = len(self.items)
        self._populate()

    def _page(self, direction):
        self.offset = max(0, self.offset + direction * self.page_size)
        if self.load_page:
            self._load_current()
        else:
            self._populate()

    def _populate(self):
        self.generation += 1
        self.thumbnail_pool.clear()
        self.image_requested.clear()
        if self.video_thumbnails:
            self.video_thumbnails.reset()
            self.video_completed.clear()
            self.video_visible.clear()
            self.video_requested.clear()
        items = self.items if self.load_page else self.items[self.offset:self.offset + self.page_size]
        def identity(item):
            prefix = ("video-work" if isinstance(item, VideoWork) else "manga" if isinstance(item, MangaWork)
                      else "image" if isinstance(item, ImageItem) else "video")
            return prefix, item.id

        self.by_id = {identity(item): item for item in items}
        self.list.clear()
        self.entries.clear()
        self.thumbnail_sources.clear()
        for item in items:
            entry = QListWidgetItem(f"{item.title}\n{item.file_count}本" if isinstance(item, VideoWork) else item.title)
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
            elif isinstance(item, VideoWork):
                pixmap = self.thumbnails.placeholder("フォルダ")
            else:
                pixmap = self.thumbnails.placeholder(self.kind)
            entry.setIcon(QIcon(pixmap))
            entry.setToolTip(str(item.path) if hasattr(item, "path") else item.title)
            self.list.addItem(entry)
            self.entries[item_key] = entry
        self.empty.setVisible(not items)
        total = self.total
        self.count_label.setText(f"{self.offset + 1 if total else 0}–{self.offset + len(items)} / {total}件")
        self.previous_button.setEnabled(self.offset > 0)
        self.next_button.setEnabled(self.offset + self.page_size < total)
        self._schedule_video_thumbnails()

    def _schedule_video_thumbnails(self, *_):
        if self.isVisible():
            self.video_timer.start()

    def _visible_video_thumbnails(self):
        if not self.isVisible():
            return
        viewport = self.list.viewport().rect()
        keys = {key for key, entry in self.entries.items()
                if not self.list.visualItemRect(entry).isEmpty()
                and self.list.visualItemRect(entry).intersects(viewport)}
        if not self.video_thumbnails:
            for key in self.entries:
                if key not in keys or key in self.image_requested or key not in self.thumbnail_sources:
                    continue
                self.image_requested.add(key)
                path, size, mtime = self.thumbnail_sources[key]
                try:
                    cached = self.thumbnails.cached(path, size, mtime)
                except OSError:
                    cached = None
                if cached is not None:
                    self.entries[key].setIcon(QIcon(cached))
                else:
                    worker = ThumbnailWorker(key, self.generation, path)
                    worker.signals.finished.connect(self._image_thumbnail)
                    self.thumbnail_pool.start(worker)
            return
        if not self.auto_video_thumbnails:
            for key in keys:
                item = self.by_id[key]
                if isinstance(item, VideoWork):
                    item = item.cover
                if not isinstance(item, VideoItem):
                    continue
                try:
                    cached = self.thumbnails.cached(item.path, item.size, item.mtime_ns)
                except OSError:
                    cached = None
                if cached is not None:
                    self.entries[key].setIcon(QIcon(cached))
            return
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
        if self.search_pending:
            self.refresh()
        self._schedule_video_thumbnails()

    def hideEvent(self, event):
        self.search_pending = self.search_pending or self.search_timer.isActive()
        self.search_timer.stop()
        self.video_timer.stop()
        self.generation += 1
        self.thumbnail_pool.clear()
        self.image_requested.clear()
        if self.video_thumbnails:
            self.video_thumbnails.reset()
            self.video_visible.clear()
            self.video_requested.clear()
        super().hideEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_video_thumbnails()

    def _image_thumbnail(self, key, generation, image):
        if generation != self.generation or not self.isVisible() or key not in self.entries or image is None or image.isNull():
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


class VideoLibraryPage(LibraryPage):
    """Visible works generate one cover each; work contents never auto-decode."""

    def __init__(self, repository, sorts, thumbnails):
        self.repository = repository
        self.current_work = None
        self.work_sort = "newest"
        self.work_view = None
        # Avoid retaining this QWidget through its stored loader during Qt shutdown.
        page_ref = ref(self)
        super().__init__("動画 — 作品フォルダ", lambda query: page_ref()._load(query), sorts, thumbnails, "動画",
                         auto_video_thumbnails=False, load_page=lambda query, **kwargs: page_ref()._load_page(query, **kwargs),
                         thumbnailer_factory=WorkThumbnailer)
        navigation = QHBoxLayout()
        self.back_button = QPushButton("作品一覧に戻る")
        self.back_button.clicked.connect(self.show_works)
        self.generate_button = QPushButton("選択した作品の表紙を再試行")
        self.generate_button.clicked.connect(self.generate_selected)
        self.thumbnail_status = QLabel(self._cover_help())
        self.video_thumbnails.cancelled.connect(self._generation_cancelled)
        self.thumbnail_status.setWordWrap(True)
        navigation.addWidget(self.back_button)
        navigation.addWidget(self.generate_button)
        navigation.addWidget(self.thumbnail_status, 1)
        self.layout().insertLayout(1, navigation)
        self.back_button.hide()

    def _generation_cancelled(self):
        self.generate_button.setEnabled(True)
        self.thumbnail_status.setText(self._cover_help())

    def _cover_help(self):
        return ("作品ごとに表紙1枚。表示中の作品から順番に生成します" if self.current_work is None else
                "動画を選択して再生できます。個別サムネイルは自動生成しません")

    def _visible_video_thumbnails(self):
        super()._visible_video_thumbnails()
        if not self.isVisible() or self.current_work is not None:
            return
        viewport = self.list.viewport().rect()
        works = {key: self.by_id[key] for key, entry in self.entries.items()
                 if isinstance(self.by_id[key], VideoWork) and self.by_id[key].cover is not None
                 and not self.list.visualItemRect(entry).isEmpty()
                 and self.list.visualItemRect(entry).intersects(viewport)}
        self.video_thumbnails.keep_visible(work.cover for work in works.values())
        self.video_requested.intersection_update(works)
        for key, work in works.items():
            if key in self.video_requested or key in self.video_completed:
                continue
            self.video_requested.add(key)
            self.video_thumbnails.request(work.cover,
                lambda pixmap, key=key, generation=self.generation: self._work_cover(key, generation, pixmap))

    def _work_cover(self, key, generation, pixmap):
        if generation != self.generation:
            return
        self._video_thumbnail(key, generation, pixmap)
        if pixmap is None and key in self.entries:
            self.entries[key].setToolTip("表紙を生成できませんでした。作品を選択して再試行できます。\n" + self.video_thumbnails.last_error)

    def _load(self, query):
        if self.current_work is None:
            return self.repository.works(query)
        return self.repository.in_work(*self.current_work.id, query)

    def _load_page(self, query, **kwargs):
        if self.current_work is None:
            return self.repository.works_page(query, **kwargs)
        return self.repository.page(query, work=self.current_work.id, **kwargs)

    def _activate(self, entry):
        key = entry.data(Qt.ItemDataRole.UserRole)
        item = self.by_id.get(key)
        if isinstance(item, VideoWork):
            self.work_sort = self.sort.currentData()
            self.work_view = (self.search.text(), self.offset, self.list.verticalScrollBar().value(), key)
            self.current_work = item
            self.heading.setText(f"動画 — {item.title}")
            self.back_button.show()
            self.generate_button.hide()
            self._clear_search()
            natural_index = self.sort.findData("natural")
            if natural_index >= 0:
                self.sort.blockSignals(True)
                self.sort.setCurrentIndex(natural_index)
                self.sort.blockSignals(False)
            self.refresh()
        elif isinstance(item, VideoItem):
            self.item_opened.emit(key)

    def _clear_search(self):
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)

    def show_works(self):
        self.current_work = None
        self.generate_button.setEnabled(True)
        self.thumbnail_status.setText(self._cover_help())
        self.heading.setText("動画 — 作品フォルダ")
        self.back_button.hide()
        self.generate_button.show()
        self._clear_search()
        self.sort.blockSignals(True)
        self.sort.setCurrentIndex(max(0, self.sort.findData(self.work_sort)))
        self.sort.blockSignals(False)
        if self.work_view:
            query, offset, scroll, selected = self.work_view
            self.search.blockSignals(True)
            self.search.setText(query)
            self.search.blockSignals(False)
            self.search_timer.stop()
            self.offset = offset
            self._load_current()
            if selected in self.entries:
                self.list.setCurrentItem(self.entries[selected])
            self.list.doItemsLayout()
            self.list.verticalScrollBar().setValue(scroll)
        else:
            self.refresh()

    def refresh(self, *, preserve=False):
        super().refresh(preserve=preserve)
        self.generate_button.setEnabled(True)
        self.thumbnail_status.setText(self._cover_help())

    def _page(self, direction):
        super()._page(direction)
        self.generate_button.setEnabled(True)
        self.thumbnail_status.setText(self._cover_help())

    def generate_selected(self):
        entry = self.list.currentItem()
        key = entry.data(Qt.ItemDataRole.UserRole) if entry else None
        item = self.by_id.get(key)
        if isinstance(item, VideoWork):
            item = item.cover
        if not isinstance(item, VideoItem):
            self.thumbnail_status.setText("表紙を再試行する作品を選択してください")
            return
        self.video_thumbnails.reset()
        self.generate_button.setEnabled(False)
        self.video_requested.clear()
        self.thumbnail_status.setText("代表動画から表紙1枚を生成中…（15秒で生成処理を終了します）")
        generation = self.generation
        def finished(pixmap):
            if generation != self.generation:
                return
            self._video_thumbnail(key, generation, pixmap)
            self.generate_button.setEnabled(True)
            self.thumbnail_status.setText("生成完了" if pixmap is not None else
                                          "生成できませんでした：" + (self.video_thumbnails.last_error or "映像を取得できません"))
        self.video_thumbnails.request(item, finished, retry=True)

    def showEvent(self, event):
        self.generate_button.setEnabled(True)
        self.thumbnail_status.setText(self._cover_help())
        super().showEvent(event)


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
