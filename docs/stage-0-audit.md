# Stage 0 audit — 2026-10-08

## Confirmed facts

- `main` at `c85ac82d8d675771864ab1c9aa7a2e46717f565a` contained only a README; no calculator implementation or user data remained.
- The old README described LAN/iPhone scope that conflicts with the Phase 1 LOCKED requirements. It is superseded by this audit.
- The repository is public. Therefore no real paths, filenames, media, credentials, database, cache, or user history may enter Git.
- The prior MangaReader project demonstrated that PySide6 widgets, Qt Multimedia, SQLite, PyInstaller and a portable adjacent `data/` directory are workable on Windows. Its downloader, receiver, updater, database and UI are not copied into this application.
- No real user media was available in the repository or execution workspace for Stage 0 inspection.

## Technology selection

- Python 3.11+ keeps the code small and testable.
- PySide6 supplies the Windows desktop UI, image decoding and local video playback. It is LGPLv3/commercial dual licensed; this project uses ordinary dynamic Qt libraries and does not modify Qt.
- Python's built-in SQLite driver supplies transactions and WAL persistence with no server.
- PyInstaller creates a standalone Windows folder. It is GPLv2 with an exception permitting distribution of bundled applications.
- No web framework, filesystem watcher, FFmpeg executable, cloud SDK, analytics SDK or network client is a runtime dependency.

## Architecture decision

The application is split into Core, three media modules and Desktop UI. UI modules never issue SQL. Manga, images and video have distinct records and repository APIs. Shared infrastructure is limited to source folders, scanning metadata, sort registration and cache location.

Source media is read-only. Initial scans enumerate and stat files. Decoding happens only in viewers or thumbnail generation. Cache and database live under `data/`, separate from media roots.

## Classification decision and uncertainty

Supported initial image candidates: JPEG, PNG, WebP, BMP and GIF. Supported initial video candidates: MP4, M4V, MKV, WebM, MOV and AVI. An extension is a discovery hint, not proof of decodability.

Folder mode can be explicit (`manga`, `image`, `video`) or `auto`. In auto mode, a directory containing at least two candidate images and no candidate video is a manga work. Mixed image/video directories remain separate image and video items. Temporary download suffixes are ignored. This is a conservative initial rule, not a claim about unseen user data. Real folder structure remains an explicit Windows gate.

## Risks and gates

- Actual codec playback depends on the Windows/Qt multimedia backend and must be proven with the user's real videos.
- Actual manga grouping depends on the user's saved folder structure and must be checked without modifying it.
- Windows packaging, visible rendering, audible output, long-path behavior and outbound connection observation require a packaged Windows run.
- Unit/offscreen tests are regression evidence only, not Phase 1 completion.

## Cost / complexity audit

There is no paid service or runtime cloud cost. The chosen stack avoids resident servers and duplicated media. Thumbnails consume bounded, disposable disk cache. Startup differential scanning is proportional to configured file count; continuous watchers and content hashes are deferred until measurements justify them.
