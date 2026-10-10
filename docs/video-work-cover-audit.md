# One representative thumbnail per video work — 2026-10-11

## Audit before implementation

The user requests one generated thumbnail per work folder and reports identical work
thumbnails. Current code selects a separate representative video per folder using
source/directory identity; cache keys include absolute source path, size and mtime.
No cross-folder cache-key collision has been reproduced. What is reproducible is that
uncached work cards all display the same generic folder placeholder: the work view
reads existing cache only and never generates its own representative cover. The actual
user's visible cards have not been inspected, so identical decoded content is unconfirmed.

## Authorized change

Generate only the representative video's single frame for each visible work, sequentially;
never queue all videos inside a work. Persist and reuse each work's representative video
cache across navigation/restart. Leave image/manga categories separate and cache at 512 MiB.
Do not start video generation on the manga home page or during playback. Cancel requests
on navigation. Persist failed attempts by source fingerprint so startup does not retry
bad videos endlessly; provide explicit retry for a selected work.

Video native decoding must run in an owned child process. Parent timeout kills only that
process, so a native decoder hang cannot indefinitely occupy the desktop event loop.
Use existing Qt dependencies, with no executable downloader, runtime network, LAN module,
original writes or CPU instrumentation. Separate desktop playback remains unchanged.

## Validation plan

Distinct folder references/cache keys, visible-only work requests, exactly one video per
work, no automatic per-video generation, persisted reuse/failure behavior, child cancellation
and timeout, real fixture extraction/reuse, original bytes unchanged, existing regressions,
Windows package startup/playback and representative-cover child-process probe.

## Implementation and local evidence

- Work view requests only visible representative VideoItems; completed/queued identities
  are retained while visible. Offscreen queue entries are removed; leaving the page,
  opening a work or starting playback cancels the owned child and pending queue.
- No QMediaPlayer is created for production thumbnail extraction in the parent UI.
  One owned QProcess invokes the existing decoder in a headless worker, with a 500ms
  gap and lowered child scheduling priority. Parent hard deadline is 15 seconds;
  cancellation waits at most one second for child termination. This does not impose
  a percentage CPU ceiling or certify performance on actual user codecs.
- Cache fingerprints remain per absolute source path/size/mtime, so existing good cache
  is reused. Failure hashes/messages (no paths) are atomically saved in the cache's
  bounded 4,096-entry ledger. Explicit retry or changed file fingerprint allows retry.
  Very old failure entries can age out at that bound. Source files remain read-only.
- Two original synthetic color clips in two folders containing 42 video files: exactly
  two JPEGs, correct red/blue center pixels, persisted cache reuse with zero child starts,
  original SHA-256 unchanged. Folder reference duplication was not reproduced.
- Failure restart/retry, hidden/inner page no automatic extraction, killed sleeping child,
  visible-only requests, stale callback protection and existing scanner/Core/viewer gates.
- Local regression suite: 47 passed, one Windows-only skip, clean process exit (12.64s).
- Windows packaging adds a frozen-parent/frozen-worker probe for both distinct covers,
  cache reuse and unchanged originals, alongside the existing startup/playback gates.
  Windows results pending. Actual user media/display/outbound/CPU remain unverified.

## Packaged playback gate regression and minimal repair

The first Windows build passed source tests/startup, but the pre-existing playback probe
failed after seek, before resume. It incorrectly checked/reopened `repository.list()[0]`.
Adding the two new color fixtures made the list's newest entry a different video from
the requested baseline fixture. The same failure was reproduced locally (9 decoded
frames, pause/seek true, resume false). The probe now checks the selected item's ID and
reopens that selected item. Desktop Player behavior was not changed. The same baseline
probe with all three fixtures passes after the two-line correction. New Windows gate
verification is required; the failed build is not distributed.
