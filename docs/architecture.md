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

The VideoRepository derives work-folder summaries from existing video references,
keyed by source identity and relative directory, and exposes files directly in a
work. The Desktop Video page navigates folders then videos; Image stays separate.
Opening either video view reads existing cache but never requests video decoding.
Single-file thumbnail generation is an explicit user operation, independently of
Desktop Playback. No schema migration or original-file reorganization is needed.

Scanner operations are limited to directory enumeration and metadata reads. Thumbnail generation and viewers open originals read-only. No application API exposes delete, move, rename or overwrite. Missing records are marked unavailable and retained.

## Local-only invariant

Application runtime code does not import HTTP clients, sockets, web frameworks, analytics or update clients. CI may download development dependencies; the packaged application has no normal-use network feature.
