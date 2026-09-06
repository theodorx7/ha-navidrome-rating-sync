![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg

<h2 align="left">Home Assistant App: Navidrome Rating Sync</h2>

<div align="right">
  <a href="https://github.com/theodorx7/ha-navidrome-rating-sync#donate"><img src="https://img.shields.io/static/v1?label=DONATE&message=USDT%20&labelColor=555&color=26A17B&style=for-the-badge" alt="DONATE USDT"></a> &thinsp; <a href="https://donate.stream/donate_6a8404d5ea133"><img src="https://img.shields.io/badge/DONATE.steam-fc0?style=for-the-badge&logo=heart&logoColor=white" alt="DONAT.stream"></a>
</div>

[English](https://github.com/theodorx7/ha-navidrome-rating-sync/blob/main/README.md) | [Russian](https://github.com/theodorx7/ha-navidrome-rating-sync/blob/main/README_RU.md)


An application for automatically synchronizing 1-5 star ratings and likes between audio files and a Navidrome server (Subsonic/OpenSonic API).

## Features
- Sync modes:
  - Two-way (merge)
  - One-way: Files → Navidrome / Navidrome → Files.
 
- Supported formats: FLAC, OGG, Opus, MP3, AIFF, WAV (ID3v2.4), APE, WavPack (APEv2), M4A (AAC/ALAC), WMA. Other formats are skipped without any log messages.

- Compatible with MusicBee likes (the `LOVE RATING` tag).

- Flexible scheduling: run on an interval, daily at a specific time, or manually via Home Assistant (dashboard button / automation).
 
- Dry Run mode: preview planned changes in the logs without physically writing to audio files or the server.

- Atomic writes (optional): Copy-Save-Replace mode protects audio files from corruption during simultaneous writes by multiple users/processes if your media library is on network storage (SMB/NFS). Atomic writes are disabled by default to prevent SSD wear.

- Power failure protection: changes are flushed directly to disk, bypassing the OS buffer, minimizing data loss during a sudden power outage.

- Independent processing of ratings and likes: you can choose to sync only likes or only ratings. If both are enabled, only the changed data is updated (e.g., changing a like won't rewrite the rating tag in the file).

- Fault tolerance: network errors or server unavailability will not cause the app to crash or restart—synchronization will simply resume on its next scheduled run.



### Main Use Cases 
- One-time rating migration:
Navidrome cannot import ratings from files into its database, nor does it write ratings from its database back into file tags. If you need to move ratings from one side to the other just once, use the one-way sync mode.

- Regular synchronization:
If you access your library remotely via Subsonic clients (e.g., Symfonium on your phone), ratings are only saved in the server's database. Meanwhile, at home, you might use a local desktop player (e.g., MusicBee) that reads and writes ratings directly to audio file tags. In this scenario, the app will sync the server and files to provide a seamless experience—no matter where you rated the track.



### How It Works
Audio file tags do not store the date a rating was applied or changed. Navidrome does track timestamps in its database, but the Subsonic API does not expose this data for ratings. The API can only retrieve the time a "like" was set, but data on when a "like" was removed is unavailable. Because of these limitations, the app maintains its own database, keeping a snapshot of the last known state of every track on both sides to resolve data conflicts as accurately as possible. The two-way sync loop works like this:

- Ratings on the server and in the files are compared against the snapshot in the add-on's database to determine which side has changed since the last sync. To optimize performance, file tags are not reread from the disk if the file modification time (mtime) matches the value stored in the add-on's database from the previous sync; instead, the rating is retrieved from the database (cache).

- If a rating changed on one side only, it is copied to the other.

- If ratings changed on both sides between sync cycles (a conflict), the priority source selected in the app settings (Server wins / File wins) takes precedence. Therefore, a more frequent sync interval leads to a more accurate detection of the changed side.

- The state snapshot is then updated in the add-on's database, becoming the new baseline.



## Requirements
- A Home Assistant installation with Supervisor (tested on HAOS).
- Both the [Navidrome](https://github.com/alexbelgium/hassio-addons/tree/master/navidrome) and Rating Sync add-ons must be installed on the same Home Assistant instance, and both must use the exact same paths to the audio files.
- The music library must be accessible from Home Assistant via one of the following methods:
    - HAOS internal drive (the /media folder).
    - An external drive mounted to HAOS — [guide](https://gist.github.com/microraptor/be170ea642abeb937fc030175ae89c0c)
    - Network attached storage (SMB) — [how to connect in Home Assistant](https://www.home-assistant.io/common-tasks/os/#network-storage)
- When a rating tag is modified in a file, its `mtime` (file modification date) must be updated.

The app has only been tested with Navidrome v0.63.2. In theory, synchronization should work with other Subsonic servers since it uses the standard API (py-opensonic for the server library, mutagen for file tags).



## Configuration and Running
- Provide the username/password of the user whose ratings should be synced. Navidrome stores ratings and likes per user.

- Select the sync mode, schedule, and enable Dry Run mode (highly recommended for the first run).

- Start the add-on. This will make the initial connection to Navidrome and create a virtual player called "Rating Sync Agent [Python]". Since Navidrome returns relative paths by default, the app won't be able to map server tracks to local files yet and will throw an error.

- Log into the Navidrome web interface using the same user you configured in the app. Go to Preferences → Players → Open the settings for the "Rating Sync Agent [Python]" client → Enable the "Report Real Path" option → Save.

- Restart the add-on and open the "Log" tab. Check if the planned changes are correct (test records in Dry Run mode will be prefixed with `[DRY-RUN]`).

- If everything looks good, disable Dry Run in the configuration and restart the add-on to begin syncing actual data.



## ⚠️ Local Player Setup and Tag Editing
The app only synchronizes ratings that are physically written to the audio file tags. Many audio players store ratings only in their internal databases by default—in which case, the app will have nothing to sync. Ensure your player supports writing ratings to file tags and that this feature is enabled.

Enabling rating/like tag writing (MusicBee example):
- Open tag settings: Preferences → Tags (1)
- Enable "store ratings in music file"
- For "save MP3 tags as", it is recommended to select ID3v2.4

### Tag Editors
If you modify ratings using a tag editor, make sure the option to preserve the original file modification date timestamp is disabled. If the file's modification date (mtime) does not change, the app will not detect and read the new rating.



## Triggering Sync from Home Assistant
You can trigger synchronization manually (via a dashboard button) or call it within automations. To do this, create a script in Home Assistant, switch to the YAML editing mode, and paste the following code:
```
sequence:
  - action: hassio.app_stdin
    metadata: {}
    data:
      app: YOUR_ADDON_SLUG_navidrome-rating-sync # enter the SLUG of the app installed on your system — switch to the visual editor to select it from the list of apps
      input: run
alias: 'Trigger rating and likes sync'
description: ''
icon: mdi:sync-circle
```



## ⚠️ Important Notes
- **Absolute paths:** Tracks on the server are matched with files strictly by their absolute path. If the "Report Real Path" option is not enabled in Navidrome, the sync will fail and log an error. 

- **Auto-start:** The synchronization process starts immediately upon booting the app. Do not start the add-on until you are sure all options are configured correctly.

- **First run in two-way mode with an empty database:** If a track's rating differs between the file and the server (and both are NON-zero), the conflict is not resolved automatically—the discrepancy is simply logged. You can resolve this by manually changing the rating on one side, or by temporarily running a one-way sync to overwrite data on the receiving side.

- **First run in one-way sync mode:** All ratings on the receiving side will be overwritten by the source ratings.

- **One-way sync is not a strict mirror:** New changes from the source are transferred to the receiver. However, if you manually change a rating on the receiving side later, it will not be forcibly overwritten by the old value from the source. It will only be overwritten if the rating is updated in the source again.

- **Only known tracks are processed:** Files that are not yet in the Navidrome database (not scanned by the server) are ignored by the app.

- **Moving or renaming files:** The app finds tracks based on the path provided by the server. If you move or rename files, rescan the library in Navidrome first (the existing rating data in the files and on the server will not be lost).


### Limitations
- **Single-user ratings and likes:** The app supports 1 user and 1 music library in Navidrome. Only one rating is stored in file tags.

- **Fractional stars:**
    - Navidrome only understands whole numbers, so when sending a rating to the server (e.g., 3.5 stars), the value is always rounded up to the nearest whole star (4).
    - In files, the fractional rating is preserved until it is overwritten by a new value from the server.
    - When comparing, a difference of 0.5 stars is tolerated. A discrepancy within half a star (e.g., 3.5 in the file and 4 on the server) is considered a match, and sync is skipped.



### Supported Tags
| Format | Rating | Like |
| :--- | :--- | :--- |
| MP3, AIFF, WAV | POPM (ID3v2.4) | TXXX:LOVE RATING |
| FLAC, OGG, Opus | RATING | LOVE RATING |
| APE, WavPack | RATING (APEv2) | LOVE RATING |
| M4A | RATE | LOVERATING |
| WMA | WM/SharedUserRating | musicbee/LOVE RATING |

If an MP3 file contains multiple POPM rating frames from different players (MusicBee, WMP, etc.), MusicBee frames take priority during reading, followed by no@email. 
When writing, all existing frames are updated so that all players can see the current rating.



### Removing/Clearing a Rating
- Rating (0 stars): 
  - FLAC/OGG/Opus/APE/WavPack/M4A/WMA: The rating tag is **deleted** from the file.
  - MP3/AIFF/WAV: POPM frames are not deleted but zeroed out, ensuring the play counter is untouched and accumulated statistics are preserved.

- Like: The `LOVE RATING` tag is not deleted—a value of "0" is written so that MusicBee correctly updates the data in its internal database.



### One-Way Sync Specifics
In one-way mode, data strictly flows in one direction—from source to receiver. Note the following behaviors:

- The receiving side does not become a strict mirror, and its modified ratings are not wiped.  
EXAMPLE: In "Navidrome → Files" mode, you change a rating in a file from 3 to 5. On the next run, the add-on will remember this change and will not revert the new rating to the old server (source) value. The track is considered conditionally synced. However, if you later change the rating on the server (the data source), the next sync will overwrite the file rating with the new server value, respecting the "Navidrome → Files" rule.

- Switching from one-way to two-way sync.  
EXAMPLE: In "Navidrome → Files" mode, you change a rating in a file from 3 to 5. The new rating is saved in the file, and the track is conditionally synced. If you switch to two-way mode, the newer "5" rating from the file will automatically be pushed to the server as the freshest data. The same logic applies to likes.

- Simultaneous changes on both sides: If you changed a rating in both the file and on the server since the last run, the next one-way sync will overwrite the receiving side with the rating from the source.



### Concurrency Protection
A run command received while a sync loop is already executing will be ignored. This prevents overlapping cycles and redundant track processing if a button is double-clicked or multiple Home Assistant automations trigger simultaneously.



### App Database
Track state snapshots are stored in the app's database. Restarting or updating the add-on does not affect the database.  
However, a database reset might be necessary if you drastically change the configuration (e.g., changing the user, library path, etc.).  
To delete the database, uninstall the add-on with the "Also remove add-on data" option checked, and reinstall it.



### Error Handling
| Situation | Behavior |
| :--- | :--- |
| Error processing a single track (permission denied, corrupted file) | The error is logged, and processing continues for the remaining files. |
| Failed disk write | The track's state in the add-on's database is not updated—a write attempt will be retried in the next sync loop. |
| Subsonic server is unavailable | The sync cycle is skipped, and a retry is performed on the next scheduled run (if configured). |


<a name="donate"></a>
## ❤️ Support the project
[![DONAT.stream](https://img.shields.io/badge/DONATE.steam-fc0?style=for-the-badge&logo=heart&logoColor=white)](https://donate.stream/donate_6a8404d5ea133)  

![USDT](https://img.shields.io/badge/USDT-26A17B?style=for-the-badge&logo=tether&logoColor=white)  
TRC-20 — TQrwpY2LWF96YBbBSZZawRqQ6j9K4PzPQo   
ETHEREUM — 0x963798c6219b4df6442192be1c89a8b852cc4830  
POLYGON — 0x8051a1cf7a3b41221d723f7eae77d59d14fb275b  
BEP-20 — 0x2a1581bcbd2dc64b9d0f494c636d1d5dacb898e6  
TON — EQBetln-nWakoK3LaTOn8l8oqnhNZgbVMHq_neSPPA6tS6nS  

