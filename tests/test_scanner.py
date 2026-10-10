from pathlib import Path

from local_media_library.natural import natural_key
from local_media_library.scanner import Scanner


def touch(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_natural_sort():
    assert sorted(["10.jpg", "1.jpg", "2.jpg"], key=natural_key) == ["1.jpg", "2.jpg", "10.jpg"]


def test_auto_classifies_manga_images_and_video(tmp_path):
    touch(tmp_path / "漫画 日本語" / "1.jpg")
    touch(tmp_path / "漫画 日本語" / "2.jpg")
    touch(tmp_path / "漫画 日本語" / "10.jpg")
    touch(tmp_path / "混在" / "写真.png")
    touch(tmp_path / "混在" / "映像.mp4")
    touch(tmp_path / "単独.webp")
    touch(tmp_path / "無視.txt")
    touch(tmp_path / "途中.mp4.part")

    result = Scanner().scan(tmp_path, "auto")

    assert [manga.title for manga in result.mangas] == ["漫画 日本語"]
    assert [Path(page.relative_path).name for page in result.mangas[0].pages] == ["1.jpg", "2.jpg", "10.jpg"]
    assert {item.relative_path for item in result.images} == {"単独.webp", "混在/写真.png"}
    assert {item.relative_path for item in result.videos} == {"混在/映像.mp4"}


def test_explicit_modes_avoid_heuristic(tmp_path):
    touch(tmp_path / "album" / "1.jpg")
    touch(tmp_path / "album" / "2.jpg")
    touch(tmp_path / "album" / "clip.mp4")
    assert not Scanner().scan(tmp_path, "image").mangas
    assert len(Scanner().scan(tmp_path, "image").images) == 2
    assert len(Scanner().scan(tmp_path, "manga").mangas) == 1
    gallery = Scanner().scan(tmp_path, "gallery")
    assert not gallery.mangas
    assert len(gallery.images) == 2
    assert len(gallery.videos) == 1


def test_symlinks_are_not_followed(tmp_path):
    real = tmp_path / "real"
    touch(real / "a.jpg")
    touch(real / "b.jpg")
    link = tmp_path / "linked"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        return
    result = Scanner().scan(tmp_path, "auto")
    assert len(result.mangas) == 1


def test_long_nested_and_broken_candidate_do_not_abort(tmp_path):
    nested = tmp_path / ("長い" * 30) / ("名前" * 30)
    touch(nested / "壊れた画像.jpg", b"not-an-image")
    result = Scanner().scan(tmp_path, "auto")
    assert len(result.images) == 1


def test_scan_reads_metadata_without_opening_media(tmp_path, monkeypatch):
    touch(tmp_path / "photo.jpg", b"private bytes")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("scanner opened media content")

    monkeypatch.setattr(Path, "open", forbidden)
    result = Scanner().scan(tmp_path, "image")
    assert len(result.images) == 1
