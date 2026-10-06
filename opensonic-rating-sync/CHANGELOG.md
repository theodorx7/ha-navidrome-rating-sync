<!-- https://developers.home-assistant.io/docs/apps/presentation#keeping-a-changelog -->

<h2 align="left">1.1.0 - 2026-10-06</h2>

<div align="left">
  <a href="https://github.com/theodorx7/ha-navidrome-rating-sync#donate"><img src="https://img.shields.io/static/v1?label=DONATE&message=USDT%20&labelColor=555&color=26A17B&style=for-the-badge" alt="DONATE USDT"></a> &thinsp; <a href="https://donate.stream/donate_6a8404d5ea133"><img src="https://img.shields.io/badge/DONAT.stream-fc0?style=for-the-badge&logo=heart&logoColor=white" alt="DONAT.stream"></a>
</div>

### Added
- New option **Delete low-rated tracks** (off by default): a track rated 1 star on the server or 0.5/1 star in its file tags is permanently deleted from disk.

## 1.0.1 - 2026-09-30

### Fixed
- 0.5-star ratings in FLAC/OGG/Opus/APE/WavPack files were incorrectly read as 5 stars.
- False "update" log entries for likes (in the file or on the server) no longer appear during Dry-Runs in one-way sync modes.
- Failed attempts to update a rating/like on the server are no longer recorded as successful: each field is tracked separately and retried on the next sync if an error occurs (previously, a server connection failure could silently roll back the rating).
- An empty server port with the HTTP protocol no longer results in an error.
- On the first run, if a track has no rating (0) on one side but has a rating (e.g., 4 stars) on the other, the existing rating is now automatically applied instead of triggering repeated "unresolved" warnings.
- Server connection errors now display the actual reason for the failure (e.g., incorrect password or network issues).
- Atomic saving now works correctly.

### Changed
- Internal optimizations: faster database handling and code refactoring.
- Other minor adjustments.

### Added
- Atomic saving: temporary files left over from interrupted writes are now cleared from the disk.

## 1.0.0 - 2026-09-05

- Initial release
