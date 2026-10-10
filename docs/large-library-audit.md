# Large library follow-up — 2026-10-10

## User scope and evidence

The user reports more than 10% CPU on the home page without interaction, slow startup,
poor browsing, and unsuccessful video thumbnails. This is a user observation, not a
CPU trace: the responsible native/backend process is unconfirmed. The user explicitly
excluded adding per-operation CPU diagnostics, and retained the 512 MiB cache limit.

Code audit identified all-record Python loading/search/sort for a 100-card view;
all-video Python grouping on every work-library refresh; cover subquery sorting without
a page-order index; simultaneous startup scan/cache enumeration; and unchanged scans
clearing the current view. These are confirmed structural problems independently of
which task consumes CPU on the actual Windows machine.

## Implemented first stage

- Core paged repository APIs fetch at most 100 models in production pages. SQLite
  performs search and registered ordering before LIMIT/OFFSET. Count/page use one read
  transaction. Unicode casefold and literal substring behavior are retained, including
  Japanese, sharp-s and percent/underscore characters. Stable IDs break sort ties.
- SortRegistry owns query ordering implementations; Desktop passes registry keys and
  pagination arguments only. Existing full-list APIs remain for compatibility; the
  production UI does not use them.
- Schema 3 adds video directory references and persisted work summaries/counts/cover
  references. Schema 1/2 migration, including summary backfill, is transactional.
  Existing original references, IDs, favorite and playback/reader state are retained.
- Scan storage rebuilds summaries only for changed video sources, in the same transaction.
  Missing sources keep records and hide unavailable works. Partial enumeration retains
  unseen records. Unchanged manga works/pages avoid redundant SQL statements.
- Unchanged scans update scan state without recreating libraries or thumbnail requests.
  Changed scans preserve current page, selection and scroll where possible.
- Startup shows the saved manga library first. Startup scan remains enabled as required.
  Cache maintenance waits for the periodic timer and never runs alongside a scan.
  Scan/cache work share one worker slot. Cache capacity remains 512 MiB.
- Video folder return restores search, root sorting, page offset, selection and scroll.
  Work cards reuse the representative video's existing cached thumbnail, without decode.

## Boundaries and remaining work

This stage does not claim the user's 10% CPU problem is resolved. Scanner still walks
all registered files and keeps per-source candidate/identity data; count and literal
substring search can inspect index rows; deep OFFSET traverses earlier index entries.
The change bounds model creation/UI cards, not every operation to constant cost.
Cache maintenance still enumerates cached JPEGs, but is deferred and separated from scan.
The initial schema migration performs one-time metadata backfill/index creation; large
existing databases may take time before first display. Older executables reject schema 3.

Video generation remains explicit one-file Qt Multimedia generation. This stage improves
library structure and cached work covers; it does not solve arbitrary native decoder stalls,
add background auto-generation, guarantee a CPU ceiling, or hard-kill blocked decoders.
A separate-process generator is a later focused change requiring its own validation.
No new network/server/dependency/original mutation operation was added.

## Validation

- New on-disk SQLite dataset: 100,000 images plus 100,000 videos in 5,000 works;
  current page contains 100 models, paging/search/counts and persisted covers are checked.
  EXPLAIN confirms indexed newest image ordering without temporary order sorting.
- Unicode/literal search, stable ties, natural order, schema-2 migration with favorites
  and player state, unchanged-scan no-rebuild/no-view-refresh, deferred cache maintenance,
  work return including scroll/search/page/selection.
- Existing scanner, partial/missing, source SHA invariant, SQLite rollback, reader/viewer,
  baseline real video decode/cache reuse/regeneration and original boundary regressions.
- Local suite: 43 passed, one packaged-Windows-only skip (7.72 seconds). This is not
  real Windows media/display/audio/CPU or outbound-connection validation.
- Windows package evidence for this source will be recorded after CI.
