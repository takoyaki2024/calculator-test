# Local Media Library

A local-first Windows media library for already-saved manga and video files.

## Scope

- Detect and index existing manga/video files without downloading, moving, or deleting originals.
- Read manga and play video on Windows.
- Open the library on an iPhone by scanning a QR code.
- iPhone access is LAN-only and requires short-lived QR pairing.
- Unauthenticated devices receive no library metadata, filenames, or thumbnails.
- The existing downloader/browser-extension projects remain separate.

## Architecture

- Library Core
- Manga Reader
- Video Player
- Windows UI
- LAN Viewer / API
- iPhone Web UI

## Security baseline

- LAN viewer is off by default and starts only when the user enables iPhone viewing.
- Pairing QR uses a cryptographically random, short-lived one-time token.
- A successful pairing receives a separate device credential.
- Internet exposure, UPnP, router port forwarding, and cloud relay are out of scope.
- The existing MangaReader localhost receiver is not reused or exposed.
- Mobile access is read-only; it cannot delete or move original files.
- No credentials, tokens, personal library paths, or user media are committed to this repository.

## Development rule

Audit and test before implementation. Keep modules isolated so manga, video, LAN access, and UI can be changed independently.
