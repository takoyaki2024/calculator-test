from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .natural import natural_key

IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"})
VIDEO_EXTENSIONS = frozenset({".mp4", ".m4v", ".mkv", ".webm", ".mov", ".avi"})
TEMPORARY_SUFFIXES = frozenset({".part", ".partial", ".tmp", ".crdownload", ".download"})
SOURCE_MODES = frozenset({"auto", "manga", "gallery", "image", "video"})


@dataclass(frozen=True)
class Candidate:
    relative_path: str
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class MangaCandidate:
    relative_dir: str
    title: str
    pages: tuple[Candidate, ...]
    mtime_ns: int


@dataclass(frozen=True)
class ScanResult:
    mangas: tuple[MangaCandidate, ...]
    images: tuple[Candidate, ...]
    videos: tuple[Candidate, ...]
    errors: tuple[str, ...]


class Scanner:
    def __init__(self, excluded_roots: tuple[Path, ...] = ()):
        self.excluded_roots = tuple(path.resolve() for path in excluded_roots)

    def _excluded(self, path: Path) -> bool:
        return any(path == root or root in path.parents for root in self.excluded_roots)

    def scan(self, root: Path, mode: str) -> ScanResult:
        if mode not in SOURCE_MODES:
            raise ValueError(f"unsupported source mode: {mode}")
        root = root.resolve(strict=True)
        if self._excluded(root):
            raise ValueError("管理データのフォルダはメディアとして登録できません")
        if not root.is_dir():
            raise NotADirectoryError(root)

        mangas: list[MangaCandidate] = []
        images: list[Candidate] = []
        videos: list[Candidate] = []
        errors: list[str] = []

        def walk_error(exc: OSError) -> None:
            errors.append(f"{exc.filename or root}: {exc.strerror or exc}")

        for current_text, dirs, names in os.walk(root, topdown=True, onerror=walk_error, followlinks=False):
            current = Path(current_text)
            dirs[:] = sorted(
                (name for name in dirs if not (current / name).is_symlink()
                 and not self._excluded(current / name)), key=natural_key
            )
            candidates: list[tuple[str, Candidate]] = []
            for name in sorted(names, key=natural_key):
                path = current / name
                suffix = path.suffix.casefold()
                if suffix in TEMPORARY_SUFFIXES or path.is_symlink():
                    continue
                kind = "image" if suffix in IMAGE_EXTENSIONS else "video" if suffix in VIDEO_EXTENSIONS else ""
                if not kind:
                    continue
                try:
                    stat = path.stat()
                    if not path.is_file():
                        continue
                    relative = path.relative_to(root).as_posix()
                    candidates.append((kind, Candidate(relative, stat.st_size, stat.st_mtime_ns)))
                except OSError as exc:
                    errors.append(f"{path}: {exc}")

            directory_images = [item for kind, item in candidates if kind == "image"]
            directory_videos = [item for kind, item in candidates if kind == "video"]
            make_manga = mode == "manga" or (
                mode == "auto" and len(directory_images) >= 2 and not directory_videos
            )
            if make_manga and directory_images:
                relative_dir = current.relative_to(root).as_posix()
                if relative_dir == ".":
                    relative_dir = ""
                ordered = tuple(sorted(directory_images, key=lambda item: natural_key(item.relative_path)))
                title = current.name if relative_dir else root.name
                mangas.append(MangaCandidate(relative_dir, title, ordered, max(p.mtime_ns for p in ordered)))
            elif mode != "video":
                images.extend(directory_images)
            if mode != "image" and mode != "manga":
                videos.extend(directory_videos)

        return ScanResult(
            tuple(sorted(mangas, key=lambda item: natural_key(item.relative_dir))),
            tuple(sorted(images, key=lambda item: natural_key(item.relative_path))),
            tuple(sorted(videos, key=lambda item: natural_key(item.relative_path))),
            tuple(errors),
        )
