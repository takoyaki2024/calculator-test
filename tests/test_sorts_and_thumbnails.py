from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage

from local_media_library.sorts import default_registry
from local_media_library.thumbnails import ThumbnailCache


@dataclass
class Item:
    title: str
    mtime_ns: int


def test_sort_registry_is_extensible():
    registry = default_registry()
    values = [Item("B", 2), Item("A", 1)]
    assert [x.title for x in registry.apply(values, "newest")] == ["B", "A"]
    assert [x.title for x in registry.apply(values, "oldest")] == ["A", "B"]
    assert [x.title for x in registry.apply(values, "title")] == ["A", "B"]


def test_thumbnail_cache_regenerates_without_changing_original(tmp_path, qapp):
    source = tmp_path / "原本.png"
    image = QImage(1200, 900, QImage.Format.Format_RGB32)
    image.fill("red")
    assert image.save(str(source))
    before = source.read_bytes()
    stat = source.stat()
    cache = ThumbnailCache(tmp_path / "cache", max_bytes=10_000_000)
    first = cache.image(source, stat.st_size, stat.st_mtime_ns, QSize(120, 120))
    cached = list((tmp_path / "cache").glob("*.jpg"))
    assert not first.isNull() and len(cached) == 1
    cached[0].unlink()
    second = cache.image(source, stat.st_size, stat.st_mtime_ns, QSize(120, 120))
    assert not second.isNull() and len(list((tmp_path / "cache").glob("*.jpg"))) == 1
    assert source.read_bytes() == before
