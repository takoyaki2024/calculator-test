from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer

from local_media_library.models import VideoItem
from local_media_library.thumbnails import ThumbnailCache
from local_media_library.video_thumbnails import VideoThumbnailer


def test_video_thumbnail_decodes_one_frame(tmp_path, qapp):
    source = Path("tests/fixtures/baseline.mp4").resolve()
    stat = source.stat()
    item = VideoItem(1, 1, source.name, source, "baseline", True, stat.st_size, stat.st_mtime_ns)
    cache = ThumbnailCache(tmp_path / "thumbs")
    thumbnailer = VideoThumbnailer(cache)
    received = []
    loop = QEventLoop()
    timeout = QTimer(singleShot=True, interval=10000)
    timeout.timeout.connect(loop.quit)
    thumbnailer.request(item, lambda pixmap: (received.append(pixmap), loop.quit()))
    timeout.start()
    loop.exec()
    assert received and received[0] is not None and not received[0].isNull()
    assert len(list((tmp_path / "thumbs").glob("*.jpg"))) == 1
    thumbnailer.request(item, received.append)
    assert len(received) == 2  # cached result without opening the video again
    assert thumbnailer.current is None
    assert thumbnailer.player.source().isEmpty()
    thumbnailer.reset()


def test_reset_cancels_pending_decoder(tmp_path, qapp):
    source = Path("tests/fixtures/baseline.mp4").resolve()
    stat = source.stat()
    item = VideoItem(1, 1, source.name, source, "baseline", True, stat.st_size, stat.st_mtime_ns)
    thumbnailer = VideoThumbnailer(ThumbnailCache(tmp_path))
    received = []
    thumbnailer.request(item, received.append)
    assert thumbnailer.next_timer.isActive()
    thumbnailer.reset()
    assert not thumbnailer.queue
    assert not thumbnailer.next_timer.isActive()
    assert not thumbnailer.timeout.isActive()
    assert thumbnailer.player.source().isEmpty()
    assert not received
