import sqlite3
from contextlib import closing
from time import perf_counter

from PySide6.QtCore import Qt

from local_media_library.database import Database, SCHEMA, APPLICATION_ID
from local_media_library.repositories import ImageRepository, VideoRepository
from local_media_library.scanner import Candidate, ScanResult
from local_media_library.service import LibraryService
from local_media_library.pages import LibraryPage, VideoLibraryPage
from local_media_library.sorts import default_registry, SortOption
from local_media_library.natural import natural_key
from local_media_library.thumbnails import ThumbnailCache
from local_media_library.paths import AppPaths
from local_media_library.window import MainWindow


def test_100k_library_queries_only_materialize_current_page(tmp_path, qapp):
    db = Database(tmp_path / 'state.sqlite3')
    service = LibraryService(db)
    source = service.add_source(tmp_path / '.', 'gallery')
    service._store(source.id, ScanResult((), tuple(Candidate(f'画像-{i}.jpg', 1, i) for i in range(100000)),
                                        tuple(Candidate(f'作品-{i // 20}/{i % 20}.mp4', 1, i) for i in range(100000)), ()))
    images = ImageRepository(db)
    start = perf_counter()
    result = images.page()
    print(f'100k images first page: {perf_counter() - start:.4f}s')
    assert result.total == 100000 and len(result.items) == 100
    assert [i.mtime_ns for i in result.items] == list(range(99999, 99899, -1))
    assert len(images.page(offset=99900).items) == 100
    assert len(images.page('画像-99999').items) == 1
    repo = VideoRepository(db)
    start = perf_counter()
    works = repo.works_page()
    print(f'100k videos / 5k works first page: {perf_counter() - start:.4f}s')
    assert works.total == 5000 and len(works.items) == 100
    assert all(w.file_count == 20 and w.cover is not None for w in works.items)
    # The production UI must never call the compatibility full-list method.
    page = LibraryPage('画像', lambda _: (_ for _ in ()).throw(AssertionError('full list used')),
                       default_registry(), ThumbnailCache(tmp_path / 'cache'), '画像', load_page=images.page)
    page.refresh()
    assert len(page.items) == 100 and page.total == 100000
    page._page(1)
    assert page.offset == 100 and len(page.items) == 100
    assert page.items[0].mtime_ns == 99899
    page.close()
    with closing(db.connect()) as c:
        plan = c.execute('EXPLAIN QUERY PLAN SELECT i.id FROM images i WHERE i.available=1 '
                         'ORDER BY i.mtime_ns DESC,i.title COLLATE CASEFOLD DESC,i.id DESC LIMIT 100').fetchall()
        assert any('image_newest' in r[3] for r in plan)
        assert not any('TEMP B-TREE' in r[3] for r in plan)


def test_unicode_literal_search_and_stable_sort_pages(tmp_path):
    db = Database(tmp_path / 'state.sqlite3')
    service = LibraryService(db)
    source = service.add_source(tmp_path, 'gallery')
    names = ['日本語_%', 'Straße', 'STRASSE', '2', '10', '1']
    service._store(source.id, ScanResult((), tuple(Candidate(n + '.jpg', 1, 1) for n in names), (), ()))
    repo = ImageRepository(db)
    assert repo.page('_%').total == 1
    assert repo.page('strasse').total == 2
    sorts = default_registry()
    sorts.register(SortOption('natural', 'ファイル名順', lambda i: natural_key(i.title),
                              sql_order='{alias}.title COLLATE NATURAL_ORDER,{alias}.id'))
    result = repo.page(sorts=sorts, sort='natural')
    assert [i.title for i in result.items][:3] == ['1', '2', '10']
    first = repo.page(limit=2, sort='title').items
    second = repo.page(offset=2, limit=2, sort='title').items
    assert not ({i.id for i in first} & {i.id for i in second})
    assert first == repo.page(limit=2, sort='title').items


def test_version_two_migrates_work_summaries_and_keeps_progress(tmp_path):
    path = tmp_path / 'old.sqlite3'
    with sqlite3.connect(path) as c:
        c.executescript(SCHEMA.replace(" relative_dir TEXT NOT NULL DEFAULT '.',\n", ''))
        c.execute(f'PRAGMA application_id={APPLICATION_ID}')
        c.execute('PRAGMA user_version=2')
        c.execute("INSERT INTO sources(id,path,mode,available) VALUES(1,'/synthetic/root','gallery',1)")
        c.execute("INSERT INTO videos(id,source_id,relative_path,title,size,mtime_ns,position_ms,favorite) "
                  "VALUES(42,1,'作品_%/1.mp4','1',100,123,5000,1)")
    db = Database(path)
    repo = VideoRepository(db)
    work = repo.works_page().items[0]
    assert work.relative_dir == '作品_%' and work.file_count == 1
    assert repo.page(work=work.id).items[0].position_ms == 5000
    assert repo.page(work=work.id).items[0].favorite
    assert Database(path).path == path  # repeat startup is idempotent
    assert len(repo.works()) == 1


def test_video_return_restores_search_page_selection_and_scroll(tmp_path, qapp):
    db = Database(tmp_path / 'state.sqlite3')
    service = LibraryService(db)
    source = service.add_source(tmp_path, 'gallery')
    service._store(source.id, ScanResult((), (), tuple(Candidate(f'作品-{i}/1.mp4', 1, i) for i in range(250)), ()))
    page = VideoLibraryPage(VideoRepository(db), default_registry(), ThumbnailCache(tmp_path / 'cache'))
    page.resize(650, 650)
    page.search.setText('作品')
    page.refresh()
    page.show()
    qapp.processEvents()
    page._page(1)
    page.list.setCurrentRow(15)
    page.list.verticalScrollBar().setValue(300)
    key = page.list.currentItem().data(Qt.ItemDataRole.UserRole)
    scroll = page.list.verticalScrollBar().value()
    page._activate(page.list.currentItem())
    assert page.list.count() == 1
    page.show_works()
    assert page.search.text() == '作品' and page.offset == 100
    assert page.list.currentItem().data(Qt.ItemDataRole.UserRole) == key
    assert page.list.verticalScrollBar().value() == scroll
    page.close()


def test_unchanged_scan_does_not_rebuild_works_or_clear_library(tmp_path, qapp, monkeypatch):
    root = tmp_path / 'media'
    root.mkdir()
    (root / '1.mp4').write_bytes(b'synthetic')
    window = MainWindow(AppPaths(tmp_path / 'app'))
    source = window.service.add_source(root, 'gallery')
    window.service.scan_source(source.id)
    revision = window.service.revision
    rebuilds = []
    monkeypatch.setattr(window.database, 'refresh_video_works', lambda *args: rebuilds.append(1))
    result = window.service.scan_source(source.id)
    assert not rebuilds and window.service.revision == revision
    refreshes = []
    monkeypatch.setattr(window, 'refresh_all', lambda: refreshes.append(1))
    window.scan_revision = revision
    window.scanning = True
    window._scan_finished({source.id: result})
    assert not refreshes
    window.close()


def test_startup_defers_cache_maintenance_until_scan_finishes(tmp_path, qapp, monkeypatch):
    window = MainWindow(AppPaths(tmp_path / 'app'))
    jobs = []
    monkeypatch.setattr(window.pool, 'start', jobs.append)
    window._startup()
    assert not jobs
    window.scanning = True
    window.prune_cache(force=True)
    assert not jobs and window.startup_cache_check
    window.scanning = False
    window.prune_cache()
    assert len(jobs) == 1 and not window.startup_cache_check
    window.close()
