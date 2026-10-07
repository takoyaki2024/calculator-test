# Phase 1 test matrix

| Requirement | Automated evidence | Real Windows gate |
|---|---|---|
| Repeat scan / no duplicates | repository identity tests | rescan actual folder |
| Manga/image/video classification | scanner and service tests | inspect actual saved layout |
| Japanese / long paths | scanner tests | packaged app on actual NTFS paths |
| Missing / external drive | unavailable-retention tests | disconnect/reconnect if applicable |
| Unsupported / broken / partial files | candidate/error-isolation tests | inspect representative damaged/in-progress data |
| Natural Sort | exact order test | inspect real manga pages |
| Thumbnail regeneration | cache deletion/regeneration test | inspect cover/image/video thumbnails |
| SQLite interruption | transaction rollback and schema tests | close/relaunch during normal use |
| Original unchanged | before/after SHA-256 test | compare representative source metadata |
| Manga Reader | offscreen real image open/navigation | visible reading/zoom |
| Image Viewer | offscreen real image open | visible fit/zoom |
| Video Player | H.264/AAC frames/audio buffers/control probe | visible picture, audible sound, actual codecs |
| Sort / search | registry and UI tests | actual library behavior |
| Offline / no outbound traffic | source boundary audit | monitor packaged app during normal use |

Automation prevents regressions but cannot certify physical display/audio, unseen folder semantics or OS-level network behavior.
