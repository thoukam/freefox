**English** · [Français](CHANGELOG.fr.md)

# Changelog

All notable changes to FreeFox are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.2] - 2026-11-09

First release published on PyPI: `pip install freefox`.

### Fixed
- Package metadata: replaced an invalid PyPI classifier that blocked the upload of 0.2.1.
  The CI now validates `pyproject.toml` on every pull request.

## [0.2.1] - 2026-11-09

Not published on PyPI because of an invalid classifier; use 0.2.2. The Docker image
`ghcr.io/thoukam/freefox:0.2.1` is available.

### Added
- Published on PyPI, with the `freefox-dashboard` and `freefox-status` commands.
- `--version` on all commands (thanks [@X6M-Work](https://github.com/X6M-Work), #16).
- Documentation in English and French, with an architecture guide.

### Fixed
- An upload worker no longer stops silently when the BLAKE3 computation or the backend setup fails.

### Changed
- The systemd unit is now generic (`/etc/freefox/config.yaml`, `/var/lib/freefox`).

## [0.2.0] - 2026-08-15

### Added
- **AWS S3 and MinIO-compatible backend** (`storage.backend: s3`, extra `pip install freefox[s3]`):
  - durable multipart uploads, with `UploadId` and parts persisted in SQLite and resumed after restart,
  - automatic part sizing within the 10 000-part limit,
  - BLAKE3 and size stored in object metadata, deduplication and conflict detection,
  - standard AWS credential chain only (secrets in YAML are rejected), private CA bundle support,
  - redaction of signatures and keys in error messages.
- Per-transfer destination snapshots: queued work keeps its original backend settings.
- New `conflict` queue state: different content at the same remote path is never overwritten.
- Provider-neutral backend error hierarchy and lazy backend registry.
- `scripts/s3_smoke.py` for live S3 and MinIO checks.

## [0.1.0] - 2026-06-08

### Added
- Watcher for ROS 2 bags (`.mcap`, `.db3`) with stability detection and ignore patterns.
- Persistent SQLite upload queue with retries and exponential backoff.
- Google Drive backend: OAuth2 or service account, Shared Drives, resumable sessions persisted
  across restarts, robust folder creation, quota error handling.
- rsync backend for local disks, NAS and SSH destinations, with BLAKE3 sidecar files.
- BLAKE3 integrity fingerprints and hash-based deduplication.
- Local web dashboard: progress, duration, MiB/s and Mbps throughput, ETA, retries, incidents.
- Dedicated retry delays for transient network errors, and failed transfers requeued on start.
- systemd unit and `install.sh`.
- Docker image (`linux/amd64`, `linux/arm64`) published to GHCR, with Docker Compose files.
- GitHub Pages project site.

[Unreleased]: https://github.com/thoukam/freefox/compare/v0.2.2...HEAD
[0.2.2]: https://github.com/thoukam/freefox/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/thoukam/freefox/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/thoukam/freefox/releases/tag/v0.2.0
[0.1.0]: https://github.com/thoukam/freefox/commits/v0.2.0
