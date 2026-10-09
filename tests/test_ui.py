from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QImage

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
    window.show_page(window.image_page)
    window.show_page(window.video_page)
    assert len(window.manga_page.by_id) == 1
    assert len(window.image_page.by_id) == 1
    assert len(window.video_page.by_id) == 1
    manga_key = next(iter(window.manga_page.by_id))
    window.open_manga(manga_key)
    assert not window.manga_reader.label.pixmap().isNull()
    image_key = next(iter(window.image_page.by_id))
    window.open_image(image_key)
    assert not window.image_viewer.pixmap.isNull()
    opened = []
    window.video_player.open_item = opened.append
    video_key = next(iter(window.video_page.by_id))
    window.open_video(video_key)
    assert opened[0].title == "映像"
    assert window.stack.currentWidget() is window.video_player
    window.close()
