from hashlib import sha256
from pathlib import Path
from shutil import copyfile
import sys

from PySide6.QtCore import QProcess
from PySide6.QtGui import QImage

from local_media_library.database import Database
from local_media_library.models import VideoItem
from local_media_library.pages import VideoLibraryPage
from local_media_library.repositories import VideoRepository
from local_media_library.service import LibraryService
from local_media_library.sorts import video_registry
from local_media_library.thumbnails import ThumbnailCache
from local_media_library.work_thumbnails import WorkThumbnailer
from tests.test_ui import wait_until


def item_for(path):
    stat = path.stat()
    return VideoItem(1, 1, path.name, path, path.stem, True, stat.st_size, stat.st_mtime_ns)


def test_two_works_get_distinct_real_frames_one_each_and_reuse_after_restart(tmp_path, qapp):
    root = tmp_path / '保存済み'
    for work, fixture in [('作品赤', 'work-red.mp4'), ('作品青', 'work-blue.mp4')]:
        folder = root / work
        folder.mkdir(parents=True)
        copyfile(Path('tests/fixtures') / fixture, folder / '1.mp4')
        for i in range(2, 22):
            (folder / f'{i}.mp4').write_bytes(b'synthetic unsupported video')
    before = {p: sha256(p.read_bytes()).hexdigest() for p in root.rglob('*.mp4')}
    db = Database(tmp_path / 'state.sqlite3')
    service = LibraryService(db)
    source = service.add_source(root, 'gallery')
    service.scan_source(source.id)
    repo = VideoRepository(db)
    cache = ThumbnailCache(tmp_path / 'cache')
    page = VideoLibraryPage(repo, video_registry(), cache)
    page.resize(1000, 700)
    page.refresh()
    page.show()
    qapp.processEvents()
    page.video_timer.stop()
    page._visible_video_thumbnails()
    assert len(page.video_thumbnails.queue) == 2  # 42 videos, two representative requests
    assert wait_until(lambda: len(page.video_completed) == 2, timeout_ms=15000)
    assert len(list(cache.directory.glob('*.jpg'))) == 2
    colors = {}
    for work in repo.works():
        cover = work.cover
        image = QImage(str(cache._key(cover.path, cover.size, cover.mtime_ns)))
        assert not image.isNull()
        colors[work.title] = image.pixelColor(image.width() // 2, image.height() // 2)
    assert colors['作品赤'].red() > 200 and colors['作品赤'].blue() < 30
    assert colors['作品青'].blue() > 200 and colors['作品青'].red() < 30
    page.close()
    restarted = WorkThumbnailer(ThumbnailCache(cache.directory))
    received = []
    for work in repo.works():
        restarted.request(work.cover, received.append)
    assert len(received) == 2 and all(p is not None for p in received)
    assert restarted.process is None and not restarted.queue
    assert {p: sha256(p.read_bytes()).hexdigest() for p in before} == before
    restarted.reset()


def test_failure_survives_restart_but_changed_source_can_retry(tmp_path, qapp):
    path = tmp_path / '壊れた.mp4'
    path.write_bytes(b'synthetic bad video')
    item = item_for(path)
    cache = ThumbnailCache(tmp_path / 'cache')
    generator = WorkThumbnailer(cache)
    received = []
    generator.request(item, received.append)
    assert wait_until(lambda: bool(received), timeout_ms=15000)
    assert received == [None]
    assert cache.directory.joinpath('video-failures.json').is_file()
    generator.reset()
    restored = WorkThumbnailer(cache)
    restored.request(item, received.append)
    assert received == [None, None] and not restored.queue
    path.write_bytes(b'synthetic modified bad video')
    restored.request(item_for(path), received.append)
    assert len(restored.queue) == 1
    restored.reset()
    restored.request(item, received.append, retry=True)
    assert len(restored.queue) == 1
    restored.reset()


def test_deadline_kills_only_owned_child_and_persists_failure(tmp_path, qapp):
    path = tmp_path / 'synthetic.mp4'
    path.write_bytes(b'synthetic')
    generator = WorkThumbnailer(ThumbnailCache(tmp_path / 'cache'))
    received = []
    generator.current = (item_for(path), received.append)
    process = generator.process = QProcess(generator)
    process.start(sys.executable, ['-c', 'import time; time.sleep(60)'])
    assert process.waitForStarted(1000)
    assert process.state() == QProcess.ProcessState.Running
    generator._expired()
    assert received == [None]
    assert process.state() == QProcess.ProcessState.NotRunning
    assert generator.process is None and generator.current is None
    assert '15秒以内' in generator.last_error
    generator.reset()


def test_hidden_or_inner_work_does_not_generate_all_video_files(tmp_path, qapp):
    root = tmp_path / 'media'
    root.mkdir()
    copyfile('tests/fixtures/work-red.mp4', root / '1.mp4')
    db = Database(tmp_path / 'state.sqlite3')
    service = LibraryService(db)
    source = service.add_source(root, 'gallery')
    service.scan_source(source.id)
    page = VideoLibraryPage(VideoRepository(db), video_registry(), ThumbnailCache(tmp_path / 'cache'))
    page.refresh()
    page._visible_video_thumbnails()
    assert not page.video_thumbnails.queue
    page._activate(page.list.item(0))
    page.show()
    qapp.processEvents()
    page._visible_video_thumbnails()
    assert not page.video_thumbnails.queue and page.video_thumbnails.process is None
    page.show_works()
    page._visible_video_thumbnails()
    assert len(page.video_thumbnails.queue) == 1
    page.hide()
    assert not page.video_thumbnails.queue and page.video_thumbnails.process is None
    page.close()
