# Architecture

```text
Read-only media roots
        |
      Scanner
        |
  Library Service
   /      |      \
Manga   Images   Video
Repos   Repo     Repo
   \      |      /
      SQLite
        |
Desktop pages and viewers
```

Only Core owns SQLite and source registration. Desktop pages call repositories and services. Playback consumes a `VideoItem`; it does not scan or mutate the library. A future Phase 2 LAN module may consume the same repository interfaces without importing Desktop UI.

## Original-file invariant

Scanner operations are limited to directory enumeration and metadata reads. Thumbnail generation and viewers open originals read-only. No application API exposes delete, move, rename or overwrite. Missing records are marked unavailable and retained.

## Local-only invariant

Application runtime code does not import HTTP clients, sockets, web frameworks, analytics or update clients. CI may download development dependencies; the packaged application has no normal-use network feature.
