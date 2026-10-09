# Performance repair — 2026-10-09

## Confirmed implementation problems

Startup constructed all three lists before showing the window. Image thumbnail
decoding ran synchronously on the UI thread. Each search keystroke fetched and
rebuilt the entire list. Hidden video pages queued every video. Video callbacks
searched the list linearly. Manga zoom and resize re-decoded the original. Every
scan temporarily marked all records missing and rewrote unchanged records.

## Changes

- First paint precedes initial library loading. Hidden pages load on navigation.
- Cards and thumbnail requests are bounded to 100 per page. Page navigation
  reuses the metadata result, preserving search and SortRegistry semantics.
- Image/cover decoding uses two workers; QPixmap and widget updates stay on the
  UI thread. Results from old page generations are discarded.
- Search waits for 250 ms of inactivity. Video callback lookup is constant-time.
- Manga zoom/resize reuse the decoded current page; opening a work invalidates it.
- Startup scan remains enabled. Enumeration still checks all configured files;
  this is not a watcher or an incremental directory traversal. Unchanged image
  and video rows bypass upserts. Unchanged manga upserts do not change rows.
- Only genuinely unseen records become unavailable after complete enumeration.
  Partial scans retain unseen records. Originals and classification are unchanged.
- Cache pruning runs alongside the background scan, not before first paint.

## Evidence and limits

Linux/offscreen regression: 23 passed, 1 Windows-only test skipped. A synthetic
10,001-work library built only 100 cards in 0.037 seconds. This excludes real
media decoding, database loading and Windows packaging, and is not a prediction
of user-machine startup time. A deliberately held image decoder did not block
refresh. A second unchanged 10,000-image storage pass changed only the source scan
timestamp, not media rows. Existing missing/partial/idempotence tests still pass.

Not yet certified: Windows package for this commit, actual saved-media performance,
outbound connections, high-resolution first-open latency and native codec behavior.
Repository queries still load all metadata; very large libraries may require Core
query pagination after measurement. Viewer first-open decoding is still synchronous.
Do not claim Phase 1 complete from these automated results.
