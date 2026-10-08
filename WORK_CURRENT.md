# Current work

This is the continuation entrypoint for the Local Media Library project. Read this file, then `docs/stage-0-audit.md`, `docs/architecture.md`, and `docs/test-matrix.md` before changing code.

## Product boundary — LOCKED

- Windows Phase 1 is a completely local Library + Viewer for already-saved manga, images and videos.
- It has no downloader, browser extension, receiver, updater, cloud/API/login, telemetry, advertising, analytics, automatic crash upload, LAN server or iPhone UI.
- Runtime must not transmit filenames, paths, history, thumbnails, metadata or media.
- Originals are read-only: no delete, move, rename or overwrite operation.
- Source registration has two categories: Manga, and mixed Image/Video. Scanner classifies the latter into separate Image and Video libraries. Manga, Image and Video have separate pages, models, repositories and type-specific viewers. Desktop UI uses Core APIs, never SQL.
- LAN/iPhone is a later Phase 2 and must not block or enter Phase 1.

## Current checkpoint

- Base repository: `takoyaki2024/calculator-test`
- Base commit: `c85ac82d8d675771864ab1c9aa7a2e46717f565a`
- Working branch: `feature/local-media-library`
- Stage 0 audit: complete and recorded.
- Stage 1 Core/SQLite/scanner/classification/minimum library: implemented; automated tests pass.
- Stage 2 manga reader/image viewer/video player: implemented; automated synthetic-media tests pass.
- Stage 3 search/sort/thumbnail cache/UX: implemented; automated tests pass.
- Stage 4 automated validation: PASS for separate Manga/Image/Video pages at source commit `b7746c1043ff5fc00ed6292a8abb92d812cb266c`.
- CI run `37736627021`: SUCCESS on Python 3.11 and 3.12.
- Windows package run `37736627019`: SUCCESS. Tests, one-folder EXE, waited startup smoke, waited packaged video decode/control probe, and artifact upload passed.
- Packaged probe: 11 decoded video frames, 36 decoded audio buffers, pause/seek/resume/fullscreen state PASS. Visible display and audible speaker output remain explicitly unverified.
- Windows artifact ID `11531737732`; 59,086,549 bytes; artifact SHA-256 `c8fa169cbefa6e34597cabb904738557d3f89064d86942d73fffa6e65e2fd5d5`.
- Real Windows/user-media/outbound-connection gate: pending and must not be claimed by automation.

## Verified automated behavior

- Idempotent scans; two source categories (Manga and mixed Image/Video); three separate media libraries and records; Japanese and nested long paths.
- Natural page ordering; explicit source modes; temporary and unsupported files ignored; symlinks excluded.
- Missing roots/items become unavailable without deleting database history.
- Incomplete enumeration does not mark unseen records missing.
- SQLite application identity, transactional scan storage, schema migration and retained reader/player position.
- Scanning does not mutate source bytes.
- Image/manga thumbnails decode at reduced size, regenerate from originals and use a bounded disposable cache.
- Video thumbnails decode one frame through Qt Multimedia.
- Synthetic MP4 H.264/AAC probe requires decoded video frames and audio buffers, pause, seek, saved-position reopen and fullscreen state.
- Runtime source has no downloader/network/analytics imports. This static check is not the final Windows network observation.

## Stop/gate

Continue autonomously through CI and packaged Windows automation. Stop only when the next result depends on the user's real Windows display/audio, actual saved-folder structure/codecs, or outbound-connection observation. Do not merge to `main` without explicit approval. Do not publish user data or paths.

Automated work is now at that stop gate. The next action is one real Windows run using representative saved folders: inspect manga grouping/page order, image/video thumbnails, visible image/video, audible audio, playback controls, restart/resume, rescan, and no unexpected outbound connections. Do not mark Phase 1 complete or merge to `main` before this passes.
