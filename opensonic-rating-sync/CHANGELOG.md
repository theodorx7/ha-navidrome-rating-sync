<!-- https://developers.home-assistant.io/docs/apps/presentation#keeping-a-changelog -->

## 1.0.1 - 2026-09-26

### Fixed
- 0.5-star ratings in FLAC/OGG/Opus/APE/WavPack files were read as 5 stars.
- Ratings and likes were not written to audio files that had no tags yet.
- The daily start time is now handled safely: values like "4:5:00" are
  accepted and normalized automatically (previously a single-digit hour
  could stop the add-on).
- A zero or negative sync interval caused endless re-syncing
  (now limited to 1–168 hours).
- A blank server port with the http protocol now defaults to port 80
  (previously 443 was used and the connection failed).
- Connection errors now show the actual reason (e.g. wrong password
  or network problem).
- False "update" log entries for likes in one-way sync modes.

### Changed
- Internal improvements: faster database handling and code refactoring.

## 1.0.0 - 2026-09-05

- Initial release
