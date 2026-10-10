from pathlib import Path

from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QVideoFrame

from local_media_library.models import ImageItem, VideoItem
from local_media_library.pages import LibraryPage
from local_media_library.sorts import default_registry
from local_media_library.thumbnails import ThumbnailCache
from local_media_library.video_thumbnails import VideoThumbnailer
from local_media_library.database import Database
from local_media_library.service import LibraryService
from local_media_library.repositories import MangaRepository, VideoRepository
from local_media_library.manga_reader import MangaReader
from local_media_library.video_player import VideoPlayer


def test_hidden_image_page_does_not_queue_decode(tmp_path, qapp, monkeypatch):
    item = ImageItem(1, 1, "a.png", tmp_path / "a.png", "a", True, 1, 1)
    page = LibraryPage("画像", lambda _: (item,), default_registry(), ThumbnailCache(tmp_path / "cache"), "画像")
    requests = []
    monkeypatch.setattr(page.thumbnail_pool, "start", requests.append)
    page.refresh()
    assert not requests
    page.close()


def test_late_frame_from_cancelled_video_is_not_assigned_to_next(tmp_path, qapp):
    source = Path("tests/fixtures/baseline.mp4").resolve()
    stat = source.stat()
    item = VideoItem(1, 1, source.name, source, "clip", True, stat.st_size, stat.st_mtime_ns)
    thumbnailer = VideoThumbnailer(ThumbnailCache(tmp_path / "cache"))
    received = []
    thumbnailer.request(item, received.append)
    thumbnailer._next()
    old_sink = thumbnailer.sink
    thumbnailer.reset()
    thumbnailer.request(item, received.append)
    thumbnailer._next()
    image = QImage(20, 20, QImage.Format.Format_RGB32)
    image.fill("red")
    old_sink.videoFrameChanged.emit(QVideoFrame(image))
    assert not received
    assert not tuple((tmp_path / "cache").glob("*.jpg"))
    thumbnailer.reset()


def test_failed_thumbnail_write_is_not_reported_as_cached(tmp_path, qapp):
    import pytest
    image = QImage(20, 20, QImage.Format.Format_RGB32)
    image.fill("red")
    cache = ThumbnailCache(tmp_path / "cache")
    cache.directory.rmdir()
    with pytest.raises(OSError):
        cache.store(tmp_path / "source.png", 1, 1, image)


def test_reader_and_player_use_latest_saved_position(tmp_path, qapp):
    db = Database(tmp_path / "state" / "library.sqlite3")
    service = LibraryService(db)
    root = tmp_path / "manga"
    root.mkdir()
    image = QImage(20, 20, QImage.Format.Format_RGB32)
    image.fill("red")
    for name in ("1.png", "2.png"):
        assert image.save(str(root / name))
    source = service.add_source(root, "manga")
    service.scan_source(source.id)
    manga_repo = MangaRepository(db)
    stale_work = manga_repo.list()[0]
    reader = MangaReader(manga_repo)
    reader.open_work(stale_work)
    reader.next()
    reader.open_work(stale_work)
    assert reader.index == 1

    source = service.add_source(Path("tests/fixtures").resolve(), "video")
    service.scan_source(source.id)
    video_repo = VideoRepository(db)
    stale_video = video_repo.list()[0]
    video_repo.save_position(stale_video.id, 2000)
    player = VideoPlayer(video_repo)
    player.open_item(stale_video)
    assert player.item.position_ms == 2000
    player.stop()
    player.close()
    reader.close()


def test_search_is_suspended_when_page_is_hidden(tmp_path, qapp):
    from tests.test_ui import wait_until
    calls = []
    def load(query):
        calls.append(query)
        return ()
    page = LibraryPage("画像", load, default_registry(), ThumbnailCache(tmp_path), "画像")
    page.refresh()
    page.show()
    qapp.processEvents()
    page.search.setText("検索")
    page.hide()
    assert not page.search_timer.isActive()
    wait_until(lambda: False, timeout_ms=350)
    assert calls == [""]
    page.show()
    qapp.processEvents()
    assert calls == ["", "検索"]
    page.close()


def test_management_directory_never_becomes_library_media(tmp_path):
    import pytest
    managed = tmp_path / "app" / "data"
    cache = managed / "thumbnails"
    cache.mkdir(parents=True)
    (cache / "cached.jpg").write_bytes(b"synthetic cache")
    (tmp_path / "original.jpg").write_bytes(b"synthetic source")
    db = Database(managed / "library.sqlite3")
    service = LibraryService(db, managed_directory=managed)
    source = service.add_source(tmp_path, "gallery")
    assert service.scan_source(source.id)[:3] == (0, 1, 0)
    with pytest.raises(ValueError):
        service.add_source(cache, "gallery")


def test_broken_video_does_not_block_next_thumbnail(tmp_path, qapp):
    from tests.test_ui import wait_until
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"synthetic invalid media")
    source = Path("tests/fixtures/baseline.mp4").resolve()
    stat = source.stat()
    items = (VideoItem(1, 1, broken.name, broken, "broken", True, broken.stat().st_size, 1),
             VideoItem(2, 1, source.name, source, "good", True, stat.st_size, stat.st_mtime_ns))
    thumbnailer = VideoThumbnailer(ThumbnailCache(tmp_path / "cache"))
    received = []
    for item in items:
        thumbnailer.request(item, received.append)
    assert wait_until(lambda: len(received) == 2)
    assert received[0] is None
    assert received[1] is not None and not received[1].isNull()
    thumbnailer.reset()


def test_cache_is_disposable_bounded_and_failure_does_not_block_scanning(tmp_path, qapp):
    from local_media_library.window import CachePruneWorker, ScanWorker
    image = QImage(20, 20, QImage.Format.Format_RGB32)
    image.fill("red")
    cache = ThumbnailCache(tmp_path / "cache", max_bytes=1)
    cache.store(tmp_path / "synthetic.png", 1, 1, image)
    assert cache.needs_prune
    assert cache.prune() == 1
    assert not cache.needs_prune
    assert not tuple(cache.directory.glob("*.jpg"))
    class FailedCache:
        def prune(self):
            raise OSError("synthetic read-only cache")
    failures = []
    worker = CachePruneWorker(FailedCache())
    worker.signals.failed.connect(failures.append)
    worker.run()
    assert len(failures) == 1
    db = Database(tmp_path / "state" / "library.sqlite3")
    service = LibraryService(db)
    source = tmp_path / "source"
    source.mkdir()
    assert image.save(str(source / "original.png"))
    service.add_source(source, "gallery")
    results = []
    scan = ScanWorker(service)
    scan.signals.finished.connect(results.append)
    scan.run()
    assert next(iter(results[0].values()))[:3] == (0, 1, 0)
