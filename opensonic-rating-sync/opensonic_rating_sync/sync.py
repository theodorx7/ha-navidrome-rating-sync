import os
import logging
import math
import time
import datetime
from .database import get_track_state, upsert_track_state, get_meta, set_meta, reset_cache, delete_track_state
from . import ratings
import libopensonic

logger = logging.getLogger(__name__)

class SyncAgent:
    def __init__(self, config):
        self.config = config
        self.sync_mode = config['sync_mode']
        self.deleted_count = 0
        self._library_root = None
        
        host = config['server_host'].strip().lower()
        if host.startswith('https://'):
            host = host[8:]
        elif host.startswith('http://'):
            host = host[7:]
        host = host.split('/')[0]
        if host.count(':') > 1:
            host = f"[{host.split(']')[0].lstrip('[')}]"
        else:
            host = host.split(':')[0]
        base_url = f"{config['server_protocol']}://{host}"
        
        self.conn = libopensonic.Connection(
            base_url,
            username=config.get('user'),
            password=config.get('password'),
            port=config.get('server_port'),
            app_name="Rating Sync Agent"
        )
        try:
            ok = self.conn.ping()
            if not ok:
                raise ConnectionError()
            logger.info(f"Connected to server: {base_url}:{config['server_port']}")
        except Exception as e:
            self.conn.cleanup()
            logger.error(f"Failed to connect to server: {base_url}:{config['server_port']}: {e}")
            raise ConnectionError(f"Server connection failed: {base_url}:{config['server_port']}") from e

    def _track_label(self, song, file_path=None):
        """Formats a string as: Artist - Title | Filename"""
        artist = getattr(song, "artist", None) or ""
        title = getattr(song, "title", None) or "<untitled>"
        artist_title = f"{artist} - {title}" if artist else title
        name = os.path.basename(file_path) if file_path else getattr(song, "path", None) or "<path missing>"
        return f"{artist_title} | {name}"

    def run_sync(self):
        start_time = time.time()
        logger.info(f"Sync started in mode: {self.sync_mode}")

        # Detect option changes: reset file cache when a frozen field is enabled
        prev_ratings = get_meta('sync_ratings')
        prev_likes = get_meta('sync_likes')
        ratings_on = prev_ratings == 'false' and self.config['sync_ratings']
        likes_on = prev_likes == 'false' and self.config['sync_likes']
        if ratings_on or likes_on:
            logger.info("Sync option enabled — resetting cache for full re-read...")
            reset_cache(ratings_on, likes_on)
        set_meta('sync_ratings', str(self.config['sync_ratings']).lower())
        set_meta('sync_likes', str(self.config['sync_likes']).lower())

        server_songs = self._fetch_all_server_songs()
        logger.info(f"Found tracks on server: {len(server_songs)}")

        self._library_root = None
        if self.config['delete_low_rated'] and server_songs:
            try:
                self._library_root = os.path.commonpath(
                    [os.path.dirname(s.path) for s in server_songs if getattr(s, 'path', None)])
            except ValueError:
                logger.debug("Deletion log disabled: server returned inconsistent paths.")

        disk_updates = 0
        server_updates = 0
        processed_count = 0
        total_tracks = len(server_songs)

        if total_tracks > 0:
            logger.info(f"Sync is running. Scanning and processing {total_tracks} tracks...")
        
        for song in server_songs:
            processed_count += 1
            if processed_count % 1000 == 0 and processed_count != total_tracks:
                logger.info(f"Progress: {processed_count} / {total_tracks} tracks scanned...")

            try:
                u_file, u_server = self._process_song(song)
                if u_file: disk_updates += 1
                if u_server: server_updates += 1
            except RuntimeError:
                self.conn.cleanup()
                raise
            except Exception as e:
                logger.error(f"Error processing track: {self._track_label(song)}: {e}", exc_info=True)

        elapsed_time = time.time() - start_time
        formatted_time = time.strftime('%H:%M:%S', time.gmtime(elapsed_time))

        logger.info("-" * 41)
        if self.config['dry_run']:
            logger.info(f"      [DRY-RUN] Planned updates on DISK: {disk_updates}")
            logger.info(f"      [DRY-RUN] Planned updates on SERVER: {server_updates}")
            if self.config['delete_low_rated']:
                logger.info(f"      [DRY-RUN] Planned deletions: {self.deleted_count}")
        else:
            logger.info(f"      Files updated on DISK: {disk_updates}")
            logger.info(f"      Tracks updated on SERVER: {server_updates}")
            if self.config['delete_low_rated']:
                logger.info(f"      Files deleted: {self.deleted_count}")
        logger.info(f"      Execution time: {formatted_time}")

        self.conn.cleanup()

    def _fetch_all_server_songs(self):
        songs = []
        try:
            mf_id = int(self.config['music_folder_id']) if self.config['music_folder_id'] else None
            offset = 0
            count_per_request = 500
            while True:
                result = self.conn.search3(query="", song_count=count_per_request, song_offset=offset,
                                           artist_count=0, album_count=0, music_folder_id=mf_id)
                fetched_songs = result.song or []
                songs.extend(fetched_songs)
                if len(fetched_songs) < count_per_request: break
                offset += count_per_request
        except Exception as e:
            self.conn.cleanup()
            logger.error(f"Error fetching tracks (search3): {e}", exc_info=True)
            raise ConnectionError(f"Failed to fetch tracks from server: {e}") from e
        return songs

    def _get_action_str(self, w_star, w_rate, star_val, src_rate, tgt_rate):
        if w_star:
            return "❤️" if star_val == 1 else "❤️ ➜ 🤍"
        if w_rate:
            src_str = "⭐" * src_rate if src_rate > 0 else ""
            if tgt_rate > 0:
                tgt_str = "⭐" * tgt_rate
                return f"{src_str} ➜ {tgt_str}" if src_str else tgt_str
            return f"{src_str} ➜ ❌" if src_str else "❌"
        return "skip"

    def _resolve_lww(self, srv_val, f_val, db_srv_val, db_f_val, srv_mtime, f_mtime):
        """Last-Write-Wins architecture. Returns 'server', 'file', or 'unresolved'."""
        srv_changed = (srv_val != db_srv_val)
        f_changed = (f_val != db_f_val)

        if srv_changed and not f_changed: return 'server', srv_mtime
        if not srv_changed and f_changed: return 'file', f_mtime

        if f_mtime == 0 and srv_mtime == 0:
            if f_val != 0 and srv_val != 0: return 'unresolved', 0
            if srv_val != 0: return 'server', srv_mtime
            if f_val != 0: return 'file', f_mtime

        if f_mtime > srv_mtime: return 'file', f_mtime
        if srv_mtime > f_mtime: return 'server', srv_mtime
        return 'server' if self.config['conflict_resolution'] == 'server_wins' else 'file', max(srv_mtime, f_mtime)

    def _resolve_rating_conflict(self, song_id, song, file_path, f_rating_internal, srv_rating, db_state, is_new_file, now_time):
        prefix = "[DRY-RUN] " if self.config['dry_run'] else ""
        f_rating_5_scale = f_rating_internal / 2.0
        # The server holds whole stars only: compare its value with the file's rating rounded UP.
        f_rating_os = math.ceil(f_rating_5_scale)
        if f_rating_os == srv_rating:
            t_rate_os = srv_rating
            t_rate_internal = f_rating_internal
            w_file_rate, w_srv_rate = False, False
            final_f_rate_mtime = db_state['file_rating_mtime']
            final_s_rate_mtime = db_state['server_rating_mtime']
        else:
            db_srv_rating = db_state['server_rating']
            db_f_rating = db_state['file_rating']
            
            srv_changed = (srv_rating != db_srv_rating)
            f_changed = (f_rating_internal != db_f_rating)
            
            new_f_rate_mtime = now_time if (f_changed and not is_new_file) else db_state['file_rating_mtime']
            new_s_rate_mtime = now_time if (srv_changed and not is_new_file) else db_state['server_rating_mtime']
            
            winner, win_mtime = self._resolve_lww(srv_rating, f_rating_internal, db_srv_rating, db_f_rating, new_s_rate_mtime, new_f_rate_mtime)

            # One-way synchronization on mutual change (not the first run):
            # The master side always wins, preserving the source priority (does not act as a strict mirror).
            if not is_new_file:
                if self.sync_mode == 'file-to-server' and f_changed:
                    winner, win_mtime = 'file', new_f_rate_mtime
                elif self.sync_mode == 'server-to-file' and srv_changed:
                    winner, win_mtime = 'server', new_s_rate_mtime

            # One-way synchronization on first launch (empty database) or during a "stuck" unresolved conflict.
            if is_new_file or winner == 'unresolved':
                if self.sync_mode == 'file-to-server':
                    winner, win_mtime = 'file', now_time
                elif self.sync_mode == 'server-to-file':
                    winner, win_mtime = 'server', now_time
            
            if winner == 'server':
                t_rate_os = srv_rating
                t_rate_internal = srv_rating * 2
                w_file_rate, w_srv_rate = True, False
                if self.sync_mode == 'file-to-server':
                    final_f_rate_mtime, final_s_rate_mtime = db_state['file_rating_mtime'], win_mtime
                else:
                    final_f_rate_mtime, final_s_rate_mtime = win_mtime, win_mtime
            elif winner == 'file':
                t_rate_os = f_rating_os
                t_rate_internal = f_rating_internal
                w_file_rate, w_srv_rate = False, True
                if self.sync_mode == 'server-to-file':
                    final_f_rate_mtime, final_s_rate_mtime = win_mtime, db_state['server_rating_mtime']
                else:
                    final_f_rate_mtime, final_s_rate_mtime = win_mtime, win_mtime
            elif winner == 'unresolved':
                t_rate_os = srv_rating
                t_rate_internal = f_rating_internal
                w_file_rate, w_srv_rate = False, False
                final_f_rate_mtime = 0
                final_s_rate_mtime = 0

                # A frozen field stays silent; the warning resumes as soon as the field is enabled.
                if self.config['sync_ratings']:
                    header_str = f"{prefix}ID {song_id} — "
                    logger.warning(f"{header_str}{self._track_label(song, file_path)}")

                    indent = " " * len(header_str)
                    logger.warning(f"{indent}⚠️ Rating conflict: Server={srv_rating}★ | File={f_rating_5_scale:g}★ ")

                    logger.warning("Solution: manually change the rating in one of the locations and restart the sync, or temporarily use one-way mode to force overwrite the rating on one of the sides.")
        
        if not self.config['sync_ratings']:
            w_file_rate, w_srv_rate = False, False
            t_rate_os = srv_rating
            t_rate_internal = f_rating_internal
            final_f_rate_mtime = db_state['file_rating_mtime']
            final_s_rate_mtime = db_state['server_rating_mtime']

        return t_rate_os, t_rate_internal, w_file_rate, w_srv_rate, final_f_rate_mtime, final_s_rate_mtime

    def _resolve_like_conflict(self, f_starred, srv_starred, srv_star_mtime_val, db_state, is_new_file, now_time):
        db_srv_star = db_state['server_starred']
        db_f_star = db_state['file_starred']
        
        srv_star_changed = (srv_starred != db_srv_star)
        f_star_changed = (f_starred != db_f_star)
        
        new_f_star_mtime = now_time if f_star_changed else db_state['file_starred_mtime']
        new_s_star_mtime = srv_star_mtime_val if srv_star_changed else db_state['server_starred_mtime']
        
        if srv_starred == f_starred:
            star_winner = 'none'
        elif srv_star_changed and f_star_changed:
            star_winner, win_star_mtime = ('server' if self.config['conflict_resolution'] == 'server_wins' else 'file'), now_time
        else:
            star_winner, win_star_mtime = self._resolve_lww(srv_starred, f_starred, db_srv_star, db_f_star, new_s_star_mtime, new_f_star_mtime)
        
        # One-way sync: the source side wins, but only when the values actually differ.
        if srv_starred != f_starred:
            if not is_new_file:
                if self.sync_mode == 'file-to-server' and f_star_changed:
                    star_winner, win_star_mtime = 'file', new_f_star_mtime
                elif self.sync_mode == 'server-to-file' and srv_star_changed:
                    star_winner, win_star_mtime = 'server', new_s_star_mtime
            # First launch (empty database): the source state is imposed on the target.
            elif self.sync_mode == 'file-to-server':
                star_winner, win_star_mtime = 'file', now_time
            elif self.sync_mode == 'server-to-file':
                star_winner, win_star_mtime = 'server', now_time

        if star_winner == 'server':
            t_star = srv_starred
            w_file_star, w_srv_star = True, False
            if self.sync_mode == 'file-to-server':
                final_f_star_mtime, final_s_star_mtime = db_state['file_starred_mtime'], win_star_mtime
            else:
                final_f_star_mtime, final_s_star_mtime = win_star_mtime, win_star_mtime
        elif star_winner == 'file':
            t_star = f_starred
            w_file_star, w_srv_star = False, True
            if self.sync_mode == 'server-to-file':
                final_f_star_mtime, final_s_star_mtime = win_star_mtime, db_state['server_starred_mtime']
            else:
                final_f_star_mtime, final_s_star_mtime = win_star_mtime, win_star_mtime
        else:
            t_star = srv_starred
            w_file_star, w_srv_star = False, False
            final_f_star_mtime, final_s_star_mtime = new_f_star_mtime, new_s_star_mtime

        if not self.config['sync_likes']:
            w_file_star, w_srv_star = False, False
            t_star = srv_starred
            final_f_star_mtime = db_state['file_starred_mtime']
            final_s_star_mtime = db_state['server_starred_mtime']
            
        return t_star, w_file_star, w_srv_star, final_f_star_mtime, final_s_star_mtime

    def _save_to_db(self, db_state, t_star, t_rate_internal, t_rate_os, 
                    w_file_star, w_file_rate, w_srv_star, w_srv_rate, 
                    actual_f_rate_write, actual_f_star_write, actual_srv_rate_write, actual_srv_star_write, 
                    f_starred, f_rating_internal, srv_starred, srv_rating,
                    final_f_rate_mtime, final_s_rate_mtime, final_f_star_mtime, final_s_star_mtime,
                    current_mtime, song_id, file_path):
        
        sync_ratings = self.config['sync_ratings']
        sync_likes = self.config['sync_likes']
        is_new_file = (db_state['file_mtime_ns'] == 0)
        
        actual_f_rate_mtime = db_state['file_rating_mtime'] if (w_file_rate and not actual_f_rate_write) else final_f_rate_mtime
        actual_s_rate_mtime = db_state['server_rating_mtime'] if (w_srv_rate and not actual_srv_rate_write) else final_s_rate_mtime
        actual_f_star_mtime = db_state['file_starred_mtime'] if (w_file_star and not actual_f_star_write) else final_f_star_mtime
        actual_s_star_mtime = db_state['server_starred_mtime'] if (w_srv_star and not actual_srv_star_write) else final_s_star_mtime

        final_f_star = (t_star if (w_file_star and actual_f_star_write) else f_starred) if sync_likes else (0 if is_new_file else db_state['file_starred'])
        final_f_rate = (t_rate_internal if (w_file_rate and actual_f_rate_write) else f_rating_internal) if sync_ratings else (0 if is_new_file else db_state['file_rating'])
        final_s_star = (t_star if actual_srv_star_write else srv_starred) if sync_likes else (0 if is_new_file else db_state['server_starred'])
        final_s_rate = (t_rate_os if actual_srv_rate_write else srv_rating) if sync_ratings else (0 if is_new_file else db_state['server_rating'])

        upsert_track_state(
            song_id=song_id, file_path=file_path, mtime_ns=current_mtime,
            f_starred=final_f_star, f_rating=final_f_rate,
            s_starred=final_s_star, s_rating=final_s_rate,
            f_rate_mtime=actual_f_rate_mtime if sync_ratings else db_state['file_rating_mtime'], 
            s_rate_mtime=actual_s_rate_mtime if sync_ratings else db_state['server_rating_mtime'],
            f_star_mtime=actual_f_star_mtime if sync_likes else db_state['file_starred_mtime'], 
            s_star_mtime=actual_s_star_mtime if sync_likes else db_state['server_starred_mtime']
        )
    
    def _delete_low_rated(self, song, song_id, file_path, reason):
        db_exists = get_track_state(song_id) is not None
        file_exists = os.path.exists(file_path)
        if not db_exists and not file_exists:
            return False, False  # already deleted on a previous cycle; the server has not rescanned yet

        prefix = "[DRY-RUN] " if self.config['dry_run'] else ""
        header_str = f"{prefix}ID {song_id} — "
        indent = " " * len(header_str)
        logger.info(f"{header_str}{self._track_label(song, file_path)}")
        target = "File" if file_exists else "DB state (file already missing)"
        logger.info(f"{indent}❌ Delete {target} — {reason}")

        if self.config['dry_run']:
            self.deleted_count += 1
            return False, False

        # DB row goes first: if the file removal fails, the next cycle re-detects the low rating and retries
        delete_track_state(song_id)
        if file_exists:
            try:
                os.remove(file_path)
            except OSError as e:
                logger.error(f"{indent}Failed to delete file: {file_path}: {e}")
                return False, False
            self._append_deletion_log(file_path)
        self.deleted_count += 1
        return False, False

    def _append_deletion_log(self, file_path):
        if not self._library_root:
            return
        try:
            log_path = os.path.join(self._library_root, "deleted_by_rating_sync.log")
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(f"{datetime.datetime.now():%d.%m.%Y}: {file_path}\n")
        except OSError as e:
            logger.error(f"Failed to write deletion log: {e}")

    def _process_song(self, song):
        song_id = song.id
        # Read the 'starred' status directly from the search3 response (like the rating), without a separate list
        srv_starred = 1 if song.starred else 0
        # The server provides the exact timestamp when the track was STARRED (ISO 8601). Parse it.
        # If unstarred (srv_starred == 0), the API doesn't provide an unstar date, so we use time.time().
        if srv_starred == 1:
            try:
                srv_star_dt = datetime.datetime.fromisoformat(str(song.starred).replace('Z', '+00:00'))
                srv_star_mtime_val = srv_star_dt.timestamp()
            except Exception:
                srv_star_mtime_val = time.time()
        else:
            srv_star_mtime_val = time.time()

        srv_rating = int(song.user_rating or 0)
    
        song_path = song.path
        if not song_path:
            logger.error(f"Track {song_id} | {self._track_label(song)} has no attribute 'path'. Skip.")
            return False, False
    
        raw_path = song_path
        if os.path.isabs(raw_path):
            file_path = raw_path
        else:
            logger.error("Received relative path from server. Enable absolute paths on the server for client 'Rating Sync Agent [Python]'.")
            logger.error("If you are using Navidrome: in the menu, open the 'Players' section ---> Find and open the client settings named 'Rating Sync Agent [Python]' ---> Enable the 'Report Real Path' option ---> Click SAVE")
            raise RuntimeError("Server returns relative paths instead of absolute.")

        # Optional deletion of low-rated tracks (independent of the sync mode): 1★ on the server.
        if self.config['delete_low_rated'] and srv_rating == 1:
            return self._delete_low_rated(song, song_id, file_path, "Low rating: 1★ (server)")

        if not ratings.is_supported_file(file_path):
            return False, False

        # A single os.stat call instead of os.path.exists + os.stat for I/O optimization.
        try:
            current_mtime = os.stat(file_path).st_mtime_ns
        except FileNotFoundError:
            logger.error(f"File not found on disk: {file_path} (Track on server: {self._track_label(song)})")
            return False, False

        db_state = get_track_state(song_id) or {
            'file_mtime_ns': 0, 'file_starred': 0, 'file_rating': 0,
            'server_starred': 0, 'server_rating': 0,
            'file_rating_mtime': 0, 'server_rating_mtime': 0,
            'file_starred_mtime': 0, 'server_starred_mtime': 0
        }
        is_new_file = (db_state['file_mtime_ns'] == 0)

        if current_mtime != db_state['file_mtime_ns'] or is_new_file:
            f_rating_internal, f_starred = ratings.get_all_ratings_from_file(
                file_path, 
                self.config['sync_ratings'], 
                self.config['sync_likes']
            )
            logger.debug(f"READ FROM FILE: {os.path.basename(file_path)} -> rating={f_rating_internal}, starred={f_starred}")
        else:
            f_starred = db_state['file_starred']
            f_rating_internal = db_state['file_rating']

        # Normalize None to 0 (if there are no tags at all, mutagen might return None)
        f_rating_internal = f_rating_internal if f_rating_internal is not None else 0
        f_starred = f_starred if f_starred is not None else 0

        # Optional deletion of low-rated tracks: 0.5★/1★ in the file tags (requires sync_ratings
        # to be on, otherwise the file value is frozen/stale and must not drive a deletion).
        if self.config['delete_low_rated'] and self.config['sync_ratings'] and f_rating_internal in (1, 2):
            return self._delete_low_rated(song, song_id, file_path, f"Low rating: {f_rating_internal / 2:g}★ (file)")

        # --- LWW (LAST-WRITE-WINS) LOGIC ---
        now_time = time.time()
        prefix = "[DRY-RUN] " if self.config['dry_run'] else ""
        
        # 1. RATING
        t_rate_os, t_rate_internal, w_file_rate, w_srv_rate, final_f_rate_mtime, final_s_rate_mtime = \
            self._resolve_rating_conflict(song_id, song, file_path, f_rating_internal, srv_rating, db_state, is_new_file, now_time)
        
        # 2. LIKE STATUS
        t_star, w_file_star, w_srv_star, final_f_star_mtime, final_s_star_mtime = \
            self._resolve_like_conflict(f_starred, srv_starred, srv_star_mtime_val, db_state, is_new_file, now_time)
            
        write_file = (w_file_star or w_file_rate) and self.sync_mode in ['two-way', 'server-to-file']
        write_server = (w_srv_star or w_srv_rate) and self.sync_mode in ['two-way', 'file-to-server']
        
        # --- "NO CHANGES" BLOCK (respecting mode constraints) ---
        if not write_file and not write_server:
            if not self.config['dry_run']:

                blocked_by_mode = (w_file_star or w_file_rate or w_srv_star or w_srv_rate)
                if blocked_by_mode:
                    # Save CURRENT values and CURRENT timestamps (new ones)
                    final_f_star = f_starred
                    final_s_star = srv_starred
                    final_f_rate = f_rating_internal
                    final_s_rate = srv_rating
                else:
                    final_f_star = t_star
                    final_s_star = t_star
                    final_f_rate = t_rate_internal
                    final_s_rate = t_rate_os

                if not self.config['sync_ratings']:
                    final_f_rate = 0 if is_new_file else db_state['file_rating']
                    final_s_rate = 0 if is_new_file else db_state['server_rating']
                if not self.config['sync_likes']:
                    final_f_star = 0 if is_new_file else db_state['file_starred']
                    final_s_star = 0 if is_new_file else db_state['server_starred']

                if is_new_file or not (
                        file_path == db_state['file_path']
                        and current_mtime == db_state['file_mtime_ns']
                        and final_f_star == db_state['file_starred']
                        and final_f_rate == db_state['file_rating']
                        and final_s_star == db_state['server_starred']
                        and final_s_rate == db_state['server_rating']
                        and final_f_rate_mtime == db_state['file_rating_mtime']
                        and final_s_rate_mtime == db_state['server_rating_mtime']
                        and final_f_star_mtime == db_state['file_starred_mtime']
                        and final_s_star_mtime == db_state['server_starred_mtime']):
                    upsert_track_state(
                    song_id=song_id, file_path=file_path, mtime_ns=current_mtime,
                    f_starred=final_f_star, f_rating=final_f_rate,
                    s_starred=final_s_star, s_rating=final_s_rate,
                    f_rate_mtime=final_f_rate_mtime, s_rate_mtime=final_s_rate_mtime,
                    f_star_mtime=final_f_star_mtime, s_star_mtime=final_s_star_mtime
                )
            
            return False, False

        f_stars_5 = math.ceil(f_rating_internal / 2) if f_rating_internal else 0
        
        header_str = f"{prefix}ID {song_id} — "
        logger.info(f"{header_str}{self._track_label(song, file_path)}")
        
        indent = " " * len(header_str)
        
        if (write_file and w_file_rate) or (write_server and w_srv_rate):
            rate_file_str = self._get_action_str(False, write_file and w_file_rate, 0, f_stars_5, t_rate_os)
            rate_srv_str = self._get_action_str(False, write_server and w_srv_rate, 0, srv_rating, t_rate_os)
            logger.info(f"{indent}update: FILE={rate_file_str} | SERVER={rate_srv_str}")
            
        if (write_file and w_file_star) or (write_server and w_srv_star):
            like_file_str = self._get_action_str(write_file and w_file_star, False, t_star, 0, 0)
            like_srv_str = self._get_action_str(write_server and w_srv_star, False, t_star, 0, 0)
            logger.info(f"{indent}update: FILE={like_file_str} | SERVER={like_srv_str}")
        logger.info("")
        
        if self.config['dry_run']:
            return write_file, write_server

        # Production mode (apply changes)
        actual_f_rate_write = False
        actual_f_star_write = False
        actual_srv_rate_write = False
        actual_srv_star_write = False
        try:
            if write_file:
                # If the rating changed (even to 0), pass it as is. Pass None only if the rating didn't change (w_file_rate = False).
                r_val = t_rate_internal if w_file_rate else None
                # If the starred status changed, pass it as bool. Pass None only if the starred status didn't change (w_file_star = False).
                s_val = bool(t_star) if w_file_star else None
                
                # Get a tuple of write statuses (rating, starred) from ratings.py
                r_status, s_status = ratings.set_tags_to_file(file_path, rating=r_val, starred=s_val, atomic_save=self.config['atomic_save'])
                
                # Update separate flags only upon successful write of the specific field
                if r_status: actual_f_rate_write = True
                if s_status: actual_f_star_write = True
                    
                # If at least one field was successfully written, record the new file modification time
                if actual_f_rate_write or actual_f_star_write:
                    current_mtime = os.stat(file_path).st_mtime_ns

            if write_server:
                if w_srv_star:
                    if t_star == 1 and srv_starred == 0:
                        self.conn.star([song_id])
                        actual_srv_star_write = True
                    elif t_star == 0 and srv_starred == 1:
                        self.conn.unstar([song_id])
                        actual_srv_star_write = True
                if w_srv_rate:
                    if t_rate_os != srv_rating:
                        self.conn.set_rating(song_id, t_rate_os)
                        actual_srv_rate_write = True
        except Exception as e:
            logger.error(f"Write error for track {song_id} | {self._track_label(song, file_path)}: {e}", exc_info=True)

        self._save_to_db(
            db_state, t_star, t_rate_internal, t_rate_os, 
            w_file_star, w_file_rate, w_srv_star, w_srv_rate, 
            actual_f_rate_write, actual_f_star_write, actual_srv_rate_write, actual_srv_star_write, 
            f_starred, f_rating_internal, srv_starred, srv_rating,
            final_f_rate_mtime, final_s_rate_mtime, final_f_star_mtime, final_s_star_mtime,
            current_mtime, song_id, file_path
        )
        
        return (actual_f_rate_write or actual_f_star_write), (actual_srv_rate_write or actual_srv_star_write)
