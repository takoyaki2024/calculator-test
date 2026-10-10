# Architecture

```text
Read-only roots: Manga | Mixed Image/Video
                |              |
               Scanner + Library Service
                         |
       Manga Repo | Image Repo | Video Repo
                         |
                      SQLite
                         |
       Manga page | Image page | Video page | Settings
                         |
              Reader | Viewer | Player
```

Only Core owns SQLite and source registration. Desktop pages call repositories and services. A mixed image/video source is classified by Scanner, then exposed through separate Image and Video repositories and pages. Playback consumes a `VideoItem`; it does not scan or mutate the library. A future Phase 2 LAN module may consume the same repository interfaces without importing Desktop UI.

## Original-file invariant

Video work-folder summaries and representative video references are persisted by Core
scan storage, keyed by source identity and relative directory. Schema 3 migrates earlier
management metadata transactionally. Core paged queries perform registered SQL sorting,
literal Unicode search and counting; Desktop instantiates only the current 100 records.
The Video page navigates works then videos; Image stays separate. Visible work covers
generate one representative frame each through a sequential owned child process and
reuse the persistent cache. The Desktop enforces a 15-second child deadline; failed
fingerprints are retained locally with explicit retry. Work contents never auto-generate
all video thumbnails. Desktop Playback is independent of cover extraction.
See `large-library-audit.md` for the validated scope and remaining scaling limits.

Scanner operations are limited to directory enumeration and metadata reads. Thumbnail generation and viewers open originals read-only. No application API exposes delete, move, rename or overwrite. Missing records are marked unavailable and retained.

## Local-only invariant

Application runtime code does not import HTTP clients, sockets, web frameworks, analytics or update clients. CI may download development dependencies; the packaged application has no normal-use network feature.
