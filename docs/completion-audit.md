# Release-candidate audit — 2026-10-09

This is a functional/reliability audit of the performance repairs, not a claim
that the real Windows Phase 1 completion gate passed.

## Reproduced before repair

1. Refreshing a hidden image page still queued image decoders.
2. Emitting a delayed frame from a cancelled video's sink after starting the
   next request assigned that old frame to the current request.
3. Removing the cache directory made saving fail silently while returning a
   successful thumbnail.
4. Reopening the same manga library record after advancing a page restarted at
   its stale position, not the database's latest saved position.

These cases were added as failing tests first. They now pass. Late-frame testing
injects a synthetic delayed Qt event; it demonstrates missing attribution in
code, not an observation that the user's actual codec emitted that event.

## Repairs and additional checks

- Image/manga thumbnail requests now also use viewport gating. Hidden pages
  clear pending jobs and invalidate running results; image and video decoding
  do not remain queued together after navigation.
- Search debounce is suspended while hidden and the pending query is applied
  on return, rather than rebuilding a hidden library.
- Each video decode uses its own player/sink and generation token. Late frames,
  errors and status callbacks from disposed requests cannot affect a new one.
- Cache JPEG writes use QSaveFile's atomic commit. A failed write is handled as
  failure, and cache access-time maintenance cannot recreate deleted files.
- Cache pruning is independent of scanning and runs in the background after
  writes, at most once a minute. The size limit is enforced on maintenance,
  not synchronously at every write; temporary overshoot is possible. A cache
  cleanup failure cannot stop the library scan.
- Managed data is excluded from source enumeration even when its parent is
  selected. Registering the managed-data directory itself is rejected.
- Reader and Player query the latest saved position through their repositories
  when reopening. Zoom resets on opening another work/image. Stopping playback
  also exits fullscreen.
- Broken-video failure proceeds to the next valid clip. Original classification,
  natural sorting, missing retention, transactions and source-byte invariance
  continue to be covered by the full suite. No network service was added.

## Evidence and unresolved gates

Local/offscreen: 33 passed, 1 Windows-packaged-only test skipped. The suite includes
real PNG/MP4 fixture decoding and synthetic fault/event injection. Tests cover
visible-only requests, scroll changes, hide/resume, stale events, cache failure,
cache pruning, managed-directory exclusion, resume state and corrupted-video
continuation. Static runtime boundary tests pass.

The previous package does not certify these changes. A fresh Windows CI/package,
startup smoke and decoded-frame/audio/control probe are required for this source.

Only the user's real Windows environment and saved media can certify sustained
CPU/GPU/disk load, actual first-frame quality, actual codec support, physical
display/audio and outbound-connection observation. Full metadata queries and
first-open viewer decoding remain synchronous; extremely large collections or
images may need further work after real measurements. No guarantee of zero
future defects or Phase 1 completion is made from automated tests.
