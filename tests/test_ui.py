from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QImage

from local_media_library.models import ImageItem, VideoItem
from local_media_library.paths import AppPaths
from local_media_library.window import MainWindow


def make_image(path: Path, color: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = QImage(80, 120, QImage.Format.Format_RGB32)
    image.fill(color)
    assert image.save(str(path))


def wait_until(predicate, timeout_ms=5000):
    loop = QEventLoop()
    timer = QTimer(interval=20)
    deadline = QTimer(singleShot=True, interval=timeout_ms)
    timer.timeout.connect(lambda: loop.quit() if predicate() else None)
    deadline.timeout.connect(loop.quit)
    timer.start()
    deadline.start()
    loop.exec()
    return predicate()


def test_window_scans_and_opens_manga_and_image(tmp_path, qapp):
    manga_root = tmp_path / "漫画ファイル"
    gallery_root = tmp_path / "画像動画ファイル"
    make_image(manga_root / "作品" / "1.png", "red")
    make_image(manga_root / "作品" / "2.png", "blue")
    make_image(gallery_root / "写真.png", "green")
    (gallery_root / "映像.mp4").write_bytes(b"test placeholder")
    window = MainWindow(AppPaths(tmp_path / "app"))
    window.service.add_source(manga_root, "manga")
    window.service.add_source(gallery_root, "gallery")
    window.scan_all()
    assert wait_until(lambda: not window.scanning)
    assert len(window.manga_page.by_id) == 1
    assert len(window.gallery_page.by_id) == 2
    assert set(window.gallery_page.by_id) == {("image", 1), ("video", 1)}
    manga_key = next(iter(window.manga_page.by_id))
    window.open_manga(manga_key)
    assert not window.manga_reader.label.pixmap().isNull()
    image_key = next(key for key, item in window.gallery_page.by_id.items() if isinstance(item, ImageItem))
    window.open_gallery_item(image_key)
    assert not window.image_viewer.pixmap.isNull()
    opened = []
    window.video_player.open_item = opened.append
    video_key = next(key for key, item in window.gallery_page.by_id.items() if isinstance(item, VideoItem))
    window.open_gallery_item(video_key)
    assert isinstance(opened[0], VideoItem)
    assert window.stack.currentWidget() is window.video_player
    window.close()
