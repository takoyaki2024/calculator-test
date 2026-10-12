import hashlib
from pathlib import Path

import pytest

from local_media_library.database import APPLICATION_ID, Database
from local_media_library.repositories import ImageRepository, MangaRepository, VideoRepository
from local_media_library.service import LibraryService
from local_media_library.scanner import ScanResult


def put(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@pytest.fixture
def library(tmp_path):
    database = Database(tmp_path / "state" / "library.sqlite3")
    return LibraryService(database), MangaRepository(database), ImageRepository(database), VideoRepository(database)


def test_repeat_scan_is_idempotent_and_preserves_source_bytes(tmp_path, library):
    service, mangas, images, videos = library
    root = tmp_path / "media"
    put(root / "book" / "1.jpg", b"one")
    put(root / "book" / "2.jpg", b"two")
    put(root / "photo.png", b"photo")
    put(root / "movie.mp4", b"video")
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    source = service.add_source(root, "auto")
    assert service.scan_source(source.id)[:3] == (1, 1, 1)
    ids = ([x.id for x in mangas.list()], [x.id for x in images.list()], [x.id for x in videos.list()])
    assert service.scan_source(source.id)[:3] == (1, 1, 1)
    assert ids == ([x.id for x in mangas.list()], [x.id for x in images.list()], [x.id for x in videos.list()])
    after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    assert before == after


def test_missing_root_marks_unavailable_without_deleting_record(tmp_path, library):
    service, _mangas, images, _videos = library
    root = tmp_path / "drive"
    put(root / "写真.jpg", b"x")
    source = service.add_source(root, "image")
    service.scan_source(source.id)
    item_id = images.list()[0].id
    root.rename(tmp_path / "drive-disconnected")
    assert service.scan_source(source.id) == (0, 0, 0, 1)
    assert not images.list()
    assert images.list(include_missing=True)[0].id == item_id


def test_partial_enumeration_preserves_unseen_records(tmp_path, library):
    service, _mangas, images, _videos = library
    root = tmp_path / "photos"
    put(root / "a.jpg", b"a")
    source = service.add_source(root, "image")
    service.scan_source(source.id)
    existing = images.list()[0].id

    class PartialScanner:
        def scan(self, _root, _mode):
            return ScanResult((), (), (), ("subdirectory: access denied",))

    service.scanner = PartialScanner()
    assert service.scan_source(source.id) == (0, 0, 0, 1)
    assert images.list()[0].id == existing


def test_progress_survives_rescan(tmp_path, library):
    service, mangas, _images, videos = library
    root = tmp_path / "videos"
    put(root / "sample.mp4", b"x")
    source = service.add_source(root, "video")
    service.scan_source(source.id)
    item = videos.list()[0]
    videos.save_position(item.id, 12345)
    service.scan_source(source.id)
    assert videos.list()[0].position_ms == 12345

    manga_root = tmp_path / "mangas"
    put(manga_root / "book" / "1.jpg", b"one")
    put(manga_root / "book" / "2.jpg", b"two")
    manga_source = service.add_source(manga_root, "manga")
    service.scan_source(manga_source.id)
    work = mangas.list()[0]
    mangas.save_position(work.id, 1)
    service.scan_source(manga_source.id)
    assert mangas.list()[0].last_page == 1


def test_failed_store_rolls_back_complete_scan(tmp_path, library, monkeypatch):
    service, _mangas, images, _videos = library
    root = tmp_path / "images"
    put(root / "a.jpg", b"a")
    source = service.add_source(root, "image")
    service.scan_source(source.id)
    original = images.list()[0]
    put(root / "b.jpg", b"b")
    database = service.database
    original_transaction = database.transaction

    class FailingContext:
        def __enter__(self):
            self.inner = original_transaction()
            self.connection = self.inner.__enter__()
            return self.connection

        def __exit__(self, exc_type, exc, tb):
            if exc_type is None:
                failure = RuntimeError("power loss")
                self.inner.__exit__(RuntimeError, failure, None)
                raise failure
            return self.inner.__exit__(exc_type, exc, tb)

    monkeypatch.setattr(database, "transaction", lambda: FailingContext())
    with pytest.raises(RuntimeError):
        service.scan_source(source.id)
    assert [item.id for item in images.list()] == [original.id]


def test_foreign_database_rejected(tmp_path):
    path = tmp_path / "foreign.sqlite3"
    import sqlite3
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA application_id=123")
    with pytest.raises(RuntimeError, match="別のアプリ"):
        Database(path)


def test_database_identity(tmp_path):
    database = Database(tmp_path / "library.sqlite3")
    with database.connect() as connection:
        assert connection.execute("PRAGMA application_id").fetchone()[0] == APPLICATION_ID


def test_schema_one_is_migrated_transactionally(tmp_path):
    import sqlite3
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
        connection.execute("PRAGMA user_version=1")
        connection.execute(
            "CREATE TABLE manga_works(id INTEGER PRIMARY KEY, source_id INTEGER, relative_dir TEXT, "
            "title TEXT, page_count INTEGER, mtime_ns INTEGER, available INTEGER, favorite INTEGER)"
        )
    database = Database(path)
    with database.connect() as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(manga_works)")}
        assert "last_page" in columns
