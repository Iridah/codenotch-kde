# Changelog

All notable changes to this project are documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/);
versioning is [SemVer](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/iridah/codenotch-kde/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/iridah/codenotch-kde/releases/tag/v0.1.2
[0.1.1]: https://github.com/iridah/codenotch-kde/releases/tag/v0.1.1
[0.1.0]: https://github.com/iridah/codenotch-kde/releases/tag/v0.1.0
