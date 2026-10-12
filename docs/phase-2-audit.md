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

## Final automated/package delivery evidence

- Local: 57 passed, 1 Windows-only skip for app/mobile source; offline delta
  roundtrip additionally passes (3 Windows updater cases skipped on Linux).
- Runtime commit `eefe12f3e53729a8002536e59f92abf1f295bac0`, tree
  `135ccc8c49dc3fe92052e93a073a2ace85a04a3e`: CI `38215681242` SUCCESS,
  Windows package `38215681248` SUCCESS. Startup, H.264/AAC (11 video frames,
  35 audio buffers), work-cover worker and verified-TLS mobile probes all pass.
  Artifact `11732297438`, outer SHA256
  `77dc4a731465f76dc7d1065f9189d33ef5f70d91a113e256233e18cff6f910a2`.
  Packaged mobile probe proves authorization/ranges/revoke/unchanged originals.
- Offline update commit `c58a0bc88b02a1dd660e00f3d17df88247b19ac0`
  failed Windows `38216370655` at the apply test: Windows PowerShell child could
  not load `Get-FileHash` in the runner environment. Library/network/media probes
  had already passed at the runtime commit. No failed update was delivered.
  Small fix replaces only that hash cmdlet with .NET SHA256; rejection tests now
  require their specific rejection reason, so unrelated failures cannot count as PASS.
- Final update source `4592a9f703e58c275ae91d8a773e51cf10e7d614`, CI
  `38216644609` SUCCESS; Windows `38216644558`, job `114702831386` SUCCESS.
  Actual Windows PowerShell tests cover apply, retained data, application-file
  backups, repeat apply, wrong-old-version rejection and corrupt-payload rejection.
  Full app startup/playback/cover/HTTPS probes also passed again. Runtime module
  code/assets are unchanged from the earlier runtime artifact used for this delta.
- Delta is 20 changed application files, 6,535,530 bytes. SHA256
  `09670b78f7aee3cbd2c38dcc8262913d09f15abaa365928437f505062098db48`.
  Built from the authoritative previously delivered 60,646,752-byte cover build
  and the validated new runtime. No data/keys/media are included. Applying its
  payload offline reconstructs every new application-file hash exactly.
- The delta is a separate `LocalMediaLibrary-iPhone-Update.zip`; the previous full
  release remains the supported base. Future updates must identify supported
  base application hashes. Distribution-file identity is kept privately, not in Git.
- Browser end-to-end rendering remains unverified: local Chromium acquisition
  returned truncated archives; the QtWebEngine fallback lacks libXtst in this
  execution environment. Neither failure was treated as a mobile UI PASS.
  Actual iPhone certificate fingerprint inspection/bootstrap, verified Safari
  connection, visibility, audio/seek and normal-use outbound observation still
  require the real Windows+iPhone. Do not mark Phase 2 complete or merge main.

## Follow-up audit — 2026-10-12, requested before final delivery

Reproduced against delivered runtime: a pending request can expire and be replaced
between Desktop polling and a user's approval click; the old UI approves the new
request because approval has no displayed-request identity. Test shows replacement
session changes to approved. Fix must bind approval to the exact opaque ticket
shown by the GUI, with atomic comparison in Authorization.

Reproduced interrupted/mixed certificate bundles: corrupt private key causes a
permanent SSL start error; swapping public CA leaves cached leaf/CA inconsistent.
Cache validation checks neither signing chain nor key/leaf match. Fix must validate
both before reuse and safely regenerate management certificates on inconsistency.

Actual-browser interaction was not previously verified. Add a Windows Edge browser
integration gate (existing system browser, fresh temporary profile) to exercise the
served assets, pairing, manga page changes, images, work navigation, video decode,
search and sort. This is distinct from Safari trust/bootstrap and physical audio.
Dedicated Codex Security workflow cannot run here: its shared prologue/core references
and scan tools are unavailable. No formal Codex Security report/PASS is claimed.
