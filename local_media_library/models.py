from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceFolder:
    id: int
    path: Path
    mode: str
    available: bool


@dataclass(frozen=True)
class MangaWork:
    id: int
    source_id: int
    relative_dir: str
    title: str
    page_count: int
    cover_path: Path | None
    available: bool
    mtime_ns: int
    favorite: bool = False
    last_page: int = 0


@dataclass(frozen=True)
class MangaPage:
    id: int
    work_id: int
    relative_path: str
    path: Path
    page_index: int
    available: bool


@dataclass(frozen=True)
class ImageItem:
    id: int
    source_id: int
    relative_path: str
    path: Path
    title: str
    available: bool
    size: int
    mtime_ns: int
    favorite: bool = False


@dataclass(frozen=True)
class VideoItem:
    id: int
    source_id: int
    relative_path: str
    path: Path
    title: str
    available: bool
    size: int
    mtime_ns: int
    position_ms: int = 0
    favorite: bool = False
