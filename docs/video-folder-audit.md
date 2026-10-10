# Video folder and thumbnail audit — 2026-10-09

## Confirmed scope and source findings

- User confirmed: one saved folder represents one work and contains multiple files.
  Navigation is inside the app: Video -> work folder -> videos -> Desktop Player.
- iPhone, LAN and vertical mobile playback remain Phase 2; not implemented here.
- Existing scanner persists source identity and relative POSIX paths. Existing
  video rows/positions support grouping without migration, rescan or source writes.
- Prior page automatically requested visible video thumbnails. Qt Multimedia opens
  each original, plays to its first frame, converts to an image, then reduces it
  to a small cache image. Small output does not mean low-resolution decoding.
  Viewport changes reset pending work. Failure left a placeholder without a reason.
- User reports excessive CPU and absent thumbnails after tens of minutes.
  This is a report, not reproduced measurement. Actual media, backend, installed
  build and CPU traces are unavailable here. Codec/GPU/cache/viewport causes are
  not asserted as established.

## Minimal repair

- Core VideoRepository supplies folder summaries and their videos. Identity is
  (source_id, relative_dir). Same-name folders in different roots/parents remain
  independent. Root-level loose videos form a work titled after the source root.
  Nested folders containing videos form their own works; multi-level series
  structure is not inferred. Images and their page stay independent.
- Folder cards show name/count and a cheap placeholder; no video cover decoding.
- Inside a work: videos, search, natural filename order (1,2,10), extensible sorts
  and return button. Folder sort is restored on return.
- Production Video page displays existing cache only: automatic generation OFF.
  Select a video and explicitly generate just that file. No batch, scroll-triggered
  generation or silent retry. Read/decode, timeout or cache-write failures display
  a reason. Leaving the page or starting playback cancels thumbnail work.
- Existing first-frame decoder is retained. Ten-second timer requests cancellation;
  it is not a hard CPU/process limit when a native codec blocks the event loop.
  Single-file performance and hardware decoding are not claimed as proven.
- Originals/history/positions are preserved; cache format remains compatible.

## Validation and remaining gate

- Synthetic mixed Japanese folders: repeat scans, same-title distinct roots,
  wildcard characters, nested/root loose files, missing-root recovery and hashes.
- UI: folder activation versus playback, zero automatic decode requests in both
  views, one selected manual request, failure display and stale callback protection.
- Real baseline H.264/AAC fixture: manual generation, cache reuse without decode,
  regeneration after cache removal. Natural repository file order: 1,2,10.
- Local: 37 passed, one Windows-only skip, three repeated clean full-suite exits;
  application startup/exit smoke passed.
  A native exit failure occurred when the Qt test fixture left windows alive until
  interpreter shutdown. Explicit fixture cleanup while QApplication remains alive
  restores clean exit. Tests must pass through process exit, not just assertions.
- Source `a53477be610a28fcfc574897d237932b7b1e3342`: CI `37928546383`
  (Python 3.11/3.12) SUCCESS. Windows package `37928546435` SUCCESS: tests,
  one-folder build, packaged startup and baseline video decode/control probe.
  Artifact `11615531271`, outer ZIP SHA-256
  `c79e102e8f1a54c9b5195134fda15a46998d8a93b06291668bfd5c3fe382ba8b`.
  Actual user Windows CPU/media,
  display/audio and outbound-connection gate remain pending. Not Phase 1 complete.
