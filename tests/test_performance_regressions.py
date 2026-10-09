from contextlib import contextmanager
from threading import Event
from time import perf_counter

from PySide6.QtGui import QImage

from local_media_library.database import Database
from local_media_library.models import ImageItem, MangaWork
from local_media_library.pages import LibraryPage
from local_media_library.scanner import Candidate, ScanResult
from local_media_library.service import LibraryService
from local_media_library.sorts import default_registry
from local_media_library.thumbnails import ThumbnailCache
from tests.test_ui import wait_until


def test_large_library_is_bounded_and_search_is_debounced(tmp_path, qapp):
    items = tuple(MangaWork(i, 1, str(i), f"作品{i}", 1, None, True, i)
                  for i in range(10001))
    calls = []
    def load(query):
        calls.append(query)
        return items
    page = LibraryPage("漫画", load, default_registry(), ThumbnailCache(tmp_path), "漫画")
    start = perf_counter()
    page.refresh()
    print(f"10001 work refresh: {perf_counter() - start:.4f}s")
    assert page.list.count() == 100
    assert len(page.entries) == 100
    page._page(1)
    assert len(calls) == 1  # paging reuses loaded metadata
    assert page.offset == 100
    for text in ("作", "作品", "作品1"):
        page.search.setText(text)
    assert len(calls) == 1
    assert wait_until(lambda: len(calls) == 2)
    assert calls[-1] == "作品1"
    page.close()


def test_slow_decode_does_not_block_refresh(tmp_path, qapp, monkeypatch):
    started, release = Event(), Event()
    def slow_decode(path):
        started.set()
        release.wait(5)
        image = QImage(20, 20, QImage.Format.Format_RGB32)
        image.fill(0)
        return image
    monkeypatch.setattr(ThumbnailCache, "decode", staticmethod(slow_decode))
    item = ImageItem(1, 1, "synthetic.png", tmp_path / "synthetic.png", "image", True, 1, 1)
    cache = ThumbnailCache(tmp_path / "cache")
    page = LibraryPage("画像", lambda _: (item,), default_registry(), cache, "画像")
    try:
        page.refresh()  # returns even while decoder is held by an event
        assert started.wait(2)
        assert page.list.count() == 1
        release.set()
        assert wait_until(lambda: len(tuple(cache.directory.glob("*.jpg"))) == 1)
    finally:
        release.set()
        page.thumbnail_pool.waitForDone()
        page.close()


def test_unchanged_scan_does_not_rewrite_media_rows(tmp_path):
    db = Database(tmp_path / "library.sqlite3")
    service = LibraryService(db)
    source = service.add_source(tmp_path, "gallery")
    result = ScanResult((), tuple(Candidate(f"image-{i}.png", 1, 1) for i in range(10000)), (), ())
    service._store(source.id, result)
    original = db.transaction
    changes = []
    @contextmanager
    def transaction():
        with original() as conn:
            yield conn
            changes.append(conn.total_changes)
    db.transaction = transaction
    service._store(source.id, result)
    assert sum(changes) == 1  # source scan timestamp only
