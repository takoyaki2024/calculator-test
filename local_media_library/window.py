from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from .database import Database
from .image_viewer import ImageViewer
from .manga_reader import MangaReader
from .pages import LibraryPage, SettingsPage
from .paths import AppPaths
from .repositories import ImageRepository, MangaRepository, VideoRepository
from .service import LibraryService
from .sorts import default_registry
from .theme import APP_STYLE
from .thumbnails import ThumbnailCache
from .video_player import VideoPlayer


class WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class ScanWorker(QRunnable):
    def __init__(self, service: LibraryService, thumbnails=None):
        super().__init__()
        self.service = service
        self.thumbnails = thumbnails
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            if self.thumbnails:
                self.thumbnails.prune()
            self.signals.finished.emit(self.service.scan_all())
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self, paths: AppPaths):
        super().__init__()
        paths.ensure()
        self.paths = paths
        self.database = Database(paths.database)
        self.service = LibraryService(self.database)
        self.mangas = MangaRepository(self.database)
        self.images = ImageRepository(self.database)
        self.videos = VideoRepository(self.database)
        self.thumbnails = ThumbnailCache(paths.thumbnails)
        self.pool = QThreadPool(self)
        self.scanning = False
        self.setWindowTitle("Local Media Library")
        self.resize(1200, 800)
        self.setMinimumSize(860, 580)
        self.setStyleSheet(APP_STYLE)
        shell = QWidget()
        outer = QHBoxLayout(shell)
        outer.setContentsMargins(0, 0, 0, 0)
        sidebar = QFrame(objectName="sidebar")
        sidebar.setFixedWidth(200)
        nav = QVBoxLayout(sidebar)
        brand = QLabel("LOCAL MEDIA\nLIBRARY", objectName="brand")
        nav.addWidget(brand)
        self.nav_buttons = []
        outer.addWidget(sidebar)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        self.setCentralWidget(shell)

        manga_sorts = default_registry()
        image_sorts = default_registry()
        video_sorts = default_registry()
        self.manga_page = LibraryPage("漫画", self.mangas.list, manga_sorts, self.thumbnails, "漫画")
        self.image_page = LibraryPage("画像", self.images.list, image_sorts, self.thumbnails, "画像")
        self.video_page = LibraryPage("動画", self.videos.list, video_sorts, self.thumbnails, "動画")
        self.settings_page = SettingsPage(paths.data)
        self.manga_reader = MangaReader(self.mangas)
        self.image_viewer = ImageViewer()
        self.video_player = VideoPlayer(self.videos)
        for page in (self.manga_page, self.image_page, self.video_page, self.settings_page,
                     self.manga_reader, self.image_viewer, self.video_player):
            self.stack.addWidget(page)
        for label, page in (("漫画", self.manga_page), ("画像", self.image_page),
                            ("動画", self.video_page), ("設定", self.settings_page)):
            button = QPushButton(label, checkable=True, objectName="nav")
            button.clicked.connect(lambda _checked=False, target=page: self.show_page(target))
            nav.addWidget(button)
            self.nav_buttons.append((button, page))
        nav.addStretch()

        self.manga_page.item_opened.connect(self.open_manga)
        self.image_page.item_opened.connect(self.open_image)
        self.video_page.item_opened.connect(self.open_video)
        self.manga_reader.back_requested.connect(lambda: self.show_page(self.manga_page))
        self.image_viewer.back_requested.connect(lambda: self.show_page(self.image_page))
        self.video_player.back_requested.connect(lambda: self.show_page(self.video_page))
        self.settings_page.add_requested.connect(self.add_source)
        self.settings_page.scan_requested.connect(self.scan_all)
        self.dirty_pages = {self.manga_page, self.image_page, self.video_page}
        QTimer.singleShot(0, self._startup)

    def _startup(self):
        self.show_page(self.manga_page)
        self.settings_page.set_sources(self.service.sources())
        if self.service.sources():
            self.scan_all()

    def show_page(self, page: QWidget) -> None:
        if self.stack.currentWidget() is self.video_player and page is not self.video_player:
            self.video_player.stop()
        self.stack.setCurrentWidget(page)
        if page in self.dirty_pages:
            page.refresh()
            self.dirty_pages.discard(page)
        for button, target in self.nav_buttons:
            button.setChecked(target is page)

    def refresh_all(self) -> None:
        self.dirty_pages.update((self.manga_page, self.image_page, self.video_page))
        current = self.stack.currentWidget()
        if current in self.dirty_pages:
            current.refresh()
            self.dirty_pages.discard(current)
        self.settings_page.set_sources(self.service.sources())

    def add_source(self, path: str, mode: str) -> None:
        try:
            self.service.add_source(path, mode)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "フォルダを追加できません", str(exc))
            return
        self.refresh_all()
        self.scan_all()

    def scan_all(self) -> None:
        if self.scanning:
            return
        self.scanning = True
        self.statusBar().showMessage("スキャン中…")
        worker = ScanWorker(self.service, self.thumbnails)
        worker.signals.finished.connect(self._scan_finished)
        worker.signals.failed.connect(self._scan_failed)
        self.pool.start(worker)

    def _scan_finished(self, results) -> None:
        self.scanning = False
        self.refresh_all()
        totals = [sum(row[index] for row in results.values()) for index in range(4)] if results else [0, 0, 0, 0]
        self.statusBar().showMessage(
            f"漫画 {totals[0]} / 画像 {totals[1]} / 動画 {totals[2]} / 読み取りエラー {totals[3]}", 15000
        )

    def _scan_failed(self, message: str) -> None:
        self.scanning = False
        self.statusBar().showMessage("スキャンに失敗しました")
        QMessageBox.warning(self, "スキャンエラー", message)

    def open_manga(self, item_key) -> None:
        item = self.manga_page.by_id.get(item_key)
        if item:
            self.manga_reader.open_work(item)
            self.show_page(self.manga_reader)

    def open_image(self, item_key) -> None:
        item = self.image_page.by_id.get(item_key)
        if item:
            self.image_viewer.open_item(item)
            self.show_page(self.image_viewer)

    def open_video(self, item_key) -> None:
        item = self.video_page.by_id.get(item_key)
        if item:
            self.video_player.open_item(item)
            self.show_page(self.video_player)

    def closeEvent(self, event) -> None:
        self.video_player.stop()
        for page in (self.manga_page, self.image_page, self.video_page):
            page.generation += 1
            page.thumbnail_pool.clear()
            if page.video_thumbnails:
                page.video_thumbnails.reset()
        self.pool.waitForDone(15000)
        super().closeEvent(event)
