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

Windows source `f23ff415351f2813d002e01db630dfc1f93b4b6f` passed CI run
37920396468 and Windows package run 37920396498. Packaged startup and H.264/AAC
decode/control probe passed (11 video frames, 34 audio buffers). Artifact:
11611811371. This does not verify actual visible/audible output or user media.

Not yet certified: actual saved-media performance, outbound connections,
high-resolution first-open latency and actual saved-video codec behavior.
Repository queries still load all metadata; very large libraries may require Core
query pagination after measurement. Viewer first-open decoding is still synchronous.
Do not claim Phase 1 complete from these automated results.

## Video-generation follow-up

User reports initial video thumbnail generation is still heavy. Confirmed code
queued every video in a 100-card page and did not cancel generation when hidden.
This revision requests only cards intersecting the visible viewport after 350 ms
of settled scrolling. Leaving the page cancels the decoder and queue; playback
also cancels before opening the video. Image pages never create video decoders.
Cached cards reuse their thumbnails. The decoder uses the first frame rather
than seeking to three seconds, yields 500 ms between clips, and abandons a clip
after ten seconds. A first frame may be black; no extra preview search is done.

Tests verify hidden pages do not request decoding, only visible cards are
requested before/after scrolling, hide/reset cancellation, cache reuse without
reopening the video, and real fixture frame decoding. These structural checks
do not measure CPU/GPU load for the user's actual codecs. No source-folder
classification change: mixed saved roots still feed separate image/video pages.

Follow-up evidence: 25 local tests passed, 1 Windows-only test skipped. CI
37922156852 and Windows package 37922156936 succeeded for source
5fbde08dfb23c2e6da822c53d2c3d7e46f6c2a49. Startup smoke and video decode/control
probe passed (11 video frames, 35 audio buffers). Artifact 11611594442. Physical
display/audio, real-codec thumbnail cost and user-machine responsiveness remain
unverified. The archive contains no user media or database.
