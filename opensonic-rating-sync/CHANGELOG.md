<!-- https://developers.home-assistant.io/docs/apps/presentation#keeping-a-changelog -->

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
