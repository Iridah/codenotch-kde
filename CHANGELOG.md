# Changelog

All notable changes to this project are documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/);
versioning is [SemVer](https://semver.org/).

## [Unreleased]

## [0.1.3] - 2026-09-07
### Security
- The OAuth bearer token is now only ever sent to `https://*.anthropic.com`.
  `fetch_usage` validates the configured `endpoint` (scheme + host allowlist)
  and uses an opener that refuses cross-host and non-HTTPS redirects, so a
  tampered `config.json` can no longer redirect the token off-site. Response
  body is capped at 2 MB.
- `hook.py` sanitises `session_id` (`[A-Za-z0-9._-]{1,128}`, no `.`/`..`) before
  using it as a filename and verifies the resolved path stays inside
  `~/.claude/codenotch/` — closes a path-traversal write/unlink via a crafted
  hook payload. State files are written `0600`, the state dir `0700`. The
  unused `message` field is no longer stored.
- `prerm` rejects a non-plausible `SUDO_USER` and drops privileges with
  `runuser` + `env` instead of `su -c` with an interpolated string.

### Added
- `SECURITY.md` (threat model, reporting, unofficial-endpoint note).
- `.github/dependabot.yml` to keep GitHub Actions pinned/updated.

### Changed
- systemd unit is sandboxed: `ProtectSystem=strict`, `ProtectHome=read-only`
  with explicit `ReadWritePaths`, `NoNewPrivileges`, `SystemCallFilter=@system-service`,
  restricted address families/namespaces, private cache dir, `UMask=0077`.
- `load_cfg` coerces every field to a sane type/range; a malformed config can
  no longer crash startup or move the window off-screen.
- Config file is written atomically at mode `0600`.

## [0.1.2] - 2026-09-07
### Added
- Auto-hide: the bar collapses to a `peek`-px accent sliver at the screen edge
  and reveals on hover, tucking away `hide_delay_ms` after the pointer leaves.
- Forced-visible while a Claude session is waiting on the user.
- One-time reveal on startup so the bar is discoverable.
- Right-click menu toggle for auto-hide; `autohide`, `peek`, `reveal_ms`,
  `hide_delay_ms` config keys.

### Changed
- Larger default size: `scale` default 1.0 -> 1.3, heavier main font.

## [0.1.1] - 2026-09-07
### Fixed
- `extract_meters` now prefers the API's explicit `limits[]` array and a
  whitelist of known buckets, ignoring internal codename buckets
  (`nimbus_quill`, `tangelo`, ...) that previously showed up as noise meters.
- Whole-number percentages are no longer rescaled (a `percent: 1` stayed 100%).

## [0.1.0] - 2026-09-07
### Added
- Initial release: PyQt6 always-on-top overlay for KDE Plasma on X11.
- Reads `~/.claude/.credentials.json` and polls
  `https://api.anthropic.com/api/oauth/usage`.
- 5-hour / weekly / opus meters with reset countdown.
- Session state dot (working / waiting / idle / none) fed by Claude Code hooks
  (`codenotch --install-hooks`) with a transcript-mtime fallback.
- `.deb` packaging, systemd `--user` service, desktop entry.

[Unreleased]: https://github.com/Iridah/codenotch-kde/compare/v0.1.3...HEAD
[0.1.3]: https://github.com/Iridah/codenotch-kde/releases/tag/v0.1.3
[0.1.2]: https://github.com/Iridah/codenotch-kde/releases/tag/v0.1.2
[0.1.1]: https://github.com/Iridah/codenotch-kde/releases/tag/v0.1.1
[0.1.0]: https://github.com/Iridah/codenotch-kde/releases/tag/v0.1.0
