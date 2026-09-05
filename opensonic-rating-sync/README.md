![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg

<h2 align="left">Home Assistant App: Navidrome Rating Sync</h2>

<div align="right">
  <a href="https://github.com/theodorx7/ha-subsonic-rating-sync#donate"><img src="https://img.shields.io/static/v1?label=DONATE&message=USDT%20&labelColor=555&color=26A17B&style=for-the-badge" alt="DONATE USDT"></a> &thinsp; <a href="https://donate.stream/donate_6a8404d5ea133"><img src="https://img.shields.io/badge/DONATE.steam-fc0?style=for-the-badge&logo=heart&logoColor=white" alt="DONAT.stream"></a>
</div>

[English](https://github.com/theodorx7/ha-subsonic-rating-sync/blob/main/README.md) | [Russian](https://github.com/theodorx7/ha-subsonic-rating-sync/blob/main/README_RU.md)

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


## SEE DOCUMENTATION TAB FOR MORE DETAILS



### ❤️ Support the project
[![DONAT.stream](https://img.shields.io/badge/DONATE.steam-fc0?style=for-the-badge&logo=heart&logoColor=white)](https://donate.stream/donate_6a8404d5ea133)  

![USDT](https://img.shields.io/badge/USDT-26A17B?style=for-the-badge&logo=tether&logoColor=white)  
TRC-20 — TQrwpY2LWF96YBbBSZZawRqQ6j9K4PzPQo   
ETHEREUM — 0x963798c6219b4df6442192be1c89a8b852cc4830  
POLYGON — 0x8051a1cf7a3b41221d723f7eae77d59d14fb275b  
BEP-20 — 0x2a1581bcbd2dc64b9d0f494c636d1d5dacb898e6  
TON — EQBetln-nWakoK3LaTOn8l8oqnhNZgbVMHq_neSPPA6tS6nS  

