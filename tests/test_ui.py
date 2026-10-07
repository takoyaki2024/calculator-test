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
    root = tmp_path / "media"
    make_image(root / "漫画" / "1.png", "red")
    make_image(root / "漫画" / "2.png", "blue")
    make_image(root / "写真.png", "green")
    window = MainWindow(AppPaths(tmp_path / "app"))
    source = window.service.add_source(root, "auto")
    window.scan_all()
    assert wait_until(lambda: not window.scanning)
    assert len(window.manga_page.by_id) == 1
    assert len(window.image_page.by_id) == 1
    manga_id = next(iter(window.manga_page.by_id))
    window.open_manga(manga_id)
    assert not window.manga_reader.label.pixmap().isNull()
    image_id = next(iter(window.image_page.by_id))
    window.open_image(image_id)
    assert not window.image_viewer.pixmap.isNull()
    window.close()
