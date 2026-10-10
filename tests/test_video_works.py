from hashlib import sha256
from pathlib import Path
from shutil import copyfile

from PySide6.QtCore import Qt

from local_media_library.database import Database
from local_media_library.repositories import ImageRepository, VideoRepository
from local_media_library.service import LibraryService
from local_media_library.pages import VideoLibraryPage
from local_media_library.sorts import default_registry
from local_media_library.thumbnails import ThumbnailCache
from tests.test_ui import wait_until


def make_library(tmp_path):
    root = tmp_path / "保存済み"
    root.mkdir()
    for relative in ("作品A/1.mp4", "作品A/2.mp4", "作品A/10.mp4", "作品A/画像.jpg",
                     "作品A/子フォルダ/別動画.mp4", "作品_%/1.mp4", "直置き.mp4"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic media")
    db = Database(tmp_path / "app" / "library.sqlite3")
    service = LibraryService(db)
    source = service.add_source(root, "gallery")
    service.scan_source(source.id)
    return root, service, source, db, VideoRepository(db)


def test_folder_identity_scans_missing_and_originals(tmp_path):
    root, service, source, db, repo = make_library(tmp_path)
    hashes = {p: sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    service.scan_source(source.id)
    works = {w.relative_dir: w for w in repo.works()}
    assert set(works) == {"作品A", "作品A/子フォルダ", "作品_%", "."}
    assert works["作品A"].file_count == 3
    assert [v.title for v in repo.in_work(*works["作品A"].id)] == ["1", "2", "10"]
    assert len(repo.in_work(*works["作品_%"].id)) == 1
    assert [v.title for v in repo.in_work(*works["."].id)] == ["直置き"]
    assert repo.works("作品a")[0].title == "作品A"
    assert [v.title for v in repo.in_work(*works["作品A"].id, "10")] == ["10"]
    assert len(ImageRepository(db).list()) == 1
    other = tmp_path / "別ドライブ" / "作品A"
    other.mkdir(parents=True)
    (other / "1.mp4").write_bytes(b"synthetic media")
    second = service.add_source(other.parent, "gallery")
    service.scan_source(second.id)
    assert len(repo.works("作品A")) == 2  # same title, independent source identity
    root.rename(tmp_path / "一時未接続")  # simulate missing root in a test fixture only
    service.scan_source(source.id)
    assert len(repo.works()) == 1
    moved = tmp_path / "一時未接続"
    moved.rename(root)
    service.scan_source(source.id)
    assert len(repo.works()) == 5
    assert {p: sha256(p.read_bytes()).hexdigest() for p in hashes} == hashes


def test_folder_navigation_generates_one_cover_per_visible_work_not_contents(tmp_path, qapp):
    _, _, _, _, repo = make_library(tmp_path)
    page = VideoLibraryPage(repo, default_registry(), ThumbnailCache(tmp_path / "cache"))
    requested = []
    page.video_thumbnails.request = lambda item, callback, **kwargs: requested.append((item, callback))
    page.refresh()
    page.show()
    qapp.processEvents()
    page.video_timer.stop()
    page._visible_video_thumbnails()
    covers = [page.by_id[key].cover.id for key, entry in page.entries.items()
              if page.list.visualItemRect(entry).intersects(page.list.viewport().rect())]
    assert {item.id for item, _ in requested} == set(covers)
    assert len(requested) == len(covers)
    requested.clear()
    entry = next(page.list.item(i) for i in range(page.list.count())
                 if page.by_id[page.list.item(i).data(Qt.ItemDataRole.UserRole)].relative_dir == "作品A")
    opened = []
    page.item_opened.connect(opened.append)
    page._activate(entry)
    assert not opened  # opening work is not playback
    assert page.list.count() == 3
    page._visible_video_thumbnails()
    assert not requested
    page.list.setCurrentRow(0)
    selected = page.by_id[page.list.item(0).data(Qt.ItemDataRole.UserRole)]
    page.generate_selected()
    assert len(requested) == 1 and requested[0][0].id == selected.id
    assert not page.generate_button.isEnabled()
    requested[0][1](None)
    assert "生成できません" in page.thumbnail_status.text()
    assert page.generate_button.isEnabled()
    page._activate(page.list.item(0))
    assert len(opened) == 1
    # stale callbacks cannot modify a new folder view
    page.show_works()
    requested[0][1](None)
    assert "作品ごとに表紙1枚" in page.thumbnail_status.text()
    assert page.current_work is None
    assert page.list.count() == 4
    page.close()


def test_manual_real_video_cache_reuse_and_regeneration(tmp_path, qapp, monkeypatch):
    root = tmp_path / "media" / "作品"
    root.mkdir(parents=True)
    copyfile(Path("tests/fixtures/baseline.mp4"), root / "1.mp4")
    db = Database(tmp_path / "app" / "library.sqlite3")
    service = LibraryService(db)
    source = service.add_source(root.parent, "gallery")
    service.scan_source(source.id)
    repo = VideoRepository(db)
    cache = ThumbnailCache(tmp_path / "cache")
    page = VideoLibraryPage(repo, default_registry(), cache)
    page.refresh()
    page.show()
    qapp.processEvents()
    page._activate(page.list.item(0))
    page.list.setCurrentRow(0)
    assert not list(cache.directory.glob("*.jpg"))
    page.generate_selected()
    assert wait_until(lambda: page.generate_button.isEnabled())
    assert page.thumbnail_status.text() == "生成完了"
    generated = list(cache.directory.glob("*.jpg"))
    assert len(generated) == 1
    decodes = []
    original = page.video_thumbnails._next
    monkeypatch.setattr(page.video_thumbnails, "_next", lambda: (decodes.append(1), original())[1])
    page.generate_selected()
    assert not decodes  # cache hit never opens a decoder
    generated[0].unlink()
    page.generate_selected()
    page.video_thumbnails.next_timer.stop()
    page.video_thumbnails._next()
    assert wait_until(lambda: page.generate_button.isEnabled())
    assert len(decodes) == 1
    assert page.thumbnail_status.text() == "生成完了"
    page.close()


def test_timeout_failure_and_natural_ui_sort(tmp_path, qapp):
    from local_media_library.paths import AppPaths
    from local_media_library.window import MainWindow
    root, _, _, _, _ = make_library(tmp_path)
    window = MainWindow(AppPaths(tmp_path / "portable"))
    source = window.service.add_source(root, "gallery")
    window.service.scan_source(source.id)
    window.show()
    qapp.processEvents()
    window.show_page(window.video_page)
    page = window.video_page
    entry = next(page.list.item(i) for i in range(page.list.count())
                 if page.by_id[page.list.item(i).data(Qt.ItemDataRole.UserRole)].relative_dir == "作品A")
    page._activate(entry)
    assert [page.list.item(i).text() for i in range(page.list.count())] == ["1", "2", "10"]
    page.list.setCurrentRow(0)
    page.generate_selected()
    # Hold the first-frame operation before native decoding, then trigger timeout.
    thumbnailer = page.video_thumbnails
    thumbnailer.next_timer.stop()
    thumbnailer.current = thumbnailer.queue.popleft()
    thumbnailer.timeout.timeout.emit()
    assert page.generate_button.isEnabled()
    assert "15秒以内" in page.thumbnail_status.text()
    assert thumbnailer.current is None and not thumbnailer.queue
    page.show_works()
    assert page.sort.currentData() == "newest"
    assert thumbnailer.process is None
    window.close()
