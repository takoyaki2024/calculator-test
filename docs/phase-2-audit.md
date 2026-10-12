# Phase 2 — iPhone local viewing, 2026-10-12

## Authorization and confirmed baseline

The user now authorizes Phase 2 after asking for iPhone viewing with high security
and accepting the proposed home-Wi-Fi-only, HTTPS, PC-approved-device design.
This explicitly supersedes the earlier prohibition on implementing LAN/iPhone;
all other original read-only/no-cloud/no-downloader boundaries remain unchanged.
The current Windows source has no listener. Core has paged separate repositories,
schema 3, persisted video works and local thumbnail caches. No actual iPhone or
user media is available in this workspace. Desktop automation cannot certify Safari.

## Selected small scope

- Optional, OFF at every startup. Bind one selected local RFC1918 IPv4 address,
  never wildcard, public address or IPv6. No discovery/UPnP/router configuration.
- HTTPS TLS 1.2+ only for library, media and pairing; local certificates. A separate
  explicitly enabled temporary bootstrap listener may serve ONLY the public CA
  certificate, never keys, pairing code, titles or media. User must compare its
  SHA-256 fingerprint on PC before trusting it on iPhone. It closes independently.
- New short-lived pairing code, hard attempt limit, PC approval after comparing
  a challenge shown on both screens. High-entropy HttpOnly/Secure/SameSite cookies,
  in-memory sessions, bounded expiry, revoke all on OFF/exit; no cloud account.
- Fixed Host, same-origin write requests, strict CSP/self-only assets, no CORS,
  no remote scripts/fonts, no server access logs containing paths/history.
- Read-only catalog APIs use Core; requests refer to numeric database IDs, never
  supplied filesystem paths. Source containment and symlink/reparse checks, deny
  managed data. Streaming has bounded concurrency, deadlines and chunked reads.
- Existing cached covers only; no new background video extraction/transcoding.
  Safari-incompatible codecs display an error; no promise all existing videos play.
- Separate mobile module/UI, no HTTP/SQL logic in Desktop viewers. Cryptography
  supplies local certificate generation (Apache-2.0 OR BSD-3-Clause), no service.
  RSA-2048/SHA256, leaf SAN IP, serverAuth, validity below Apple's 825-day limit.
  Generated CA signing private key is discarded; private leaf material stays local
  in restricted management storage and is never included in a package or Git.

## Risks and release gates

LAN address restrictions alone do not establish client identity, encryption or
protection against a compromised local device; HTTPS plus approval is mandatory.
TLS cannot hide packet sizes/timing from a network observer. No claim of zero risk.
Initial iPhone certificate installation/trust is a required human OS action.
Trust-bootstrap fingerprint comparison must use the PC screen, not the same HTTP
channel. Windows firewall Private-profile allowance may require an OS prompt;
the application must not open Public-profile/wildcard access automatically.

Before delivery: real verified TLS loopback requests using synthetic media,
unauthorized/revoked/expired/session/cross-origin/path traversal/range/concurrency
checks, Desktop regressions, Windows packaging and packaged mobile probe.
Actual Windows+iPhone Wi-Fi connectivity, verified certificate trust, visible
reading/playback/audio/seek and outbound observation remain a real-device gate.
Do not claim this completed solely from Python tests. Deliver changed application
files only, preserving data; validate old-build hashes before replacing files.

## Stage 1–2 evidence

Local full suite before additional adversarial tests: 55 passed, one Windows-only
skip, clean exit. Ten focused mobile tests use verified TLS sockets and synthetic
original media; no fake HTTP. Loopback packaged-entrypoint probe PASS for TLS trust,
unauthorized denial, approval, asset inclusion, byte ranges, revoke and unchanged
originals. Slow TLS handshake concurrency and clean socket shutdown also checked.
Windows package and actual iPhone certificate bootstrap remain pending.

Startup loads no mobile module until its settings page is opened, then starts no
listener until ON. A separate scrollable settings page preserves the existing
Desktop layout. Scanner/schema/desktop viewers were not rewritten. No database
migration or new video decoding/transcoding worker was added. Session/cookie and
certificate keys are excluded from Git/package; shared/network drive references
are not published. Certificate signing root key is discarded after generation.
