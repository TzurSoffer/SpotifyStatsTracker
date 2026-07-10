import csv
import json
import datetime
import SpotipyFree
import concurrent.futures
import threading

try:
    from Database.Formatters.spotifyClient import Client
    from Database.utils import timeToInt, parseError, now
except ModuleNotFoundError:
    from Formatters.spotifyClient import Client
    from utils import timeToInt, parseError, now


class Importer:
    def __init__(self, user="Tzur", cookiesFile=None, email=None):
        self.sp = SpotipyFree.Spotify(cookiesFile=cookiesFile, email=email)

    def _searchForSong(self, name, artist):
        query = f"track:{name} artist:{artist}"
        track = self.sp.search(query, type="track", limit=1)["tracks"]["items"][0]
        # track = self.sp.track(track["external_urls"]["spotify"])
        return track

    def _convertToList(self, export):
        if export.lstrip().startswith("FILE_PATH,"):
            return export.splitlines()[1:], "musicoletPremium"
        try:
            export = json.loads(export)
            if "msPlayed" in export[0]:   #< Acount export
                return export, "spotifyAcountExport"
            if "ts" in export[0]:         #< Extended export
                return export, "spotifyExtendedExport"
        except:
            pass
        return [], "None"
    
    def getLengthOfImport(self, export):
        return len(self._convertToList(export)[0])

    def importHistory(self, parsedHistory, known, exportType, progress_callback=None):
        if len(parsedHistory) == 0:
            return []
        if exportType == "spotifyAcountExport":
            return self.importAcountHistory(parsedHistory, known=known, progress_callback=progress_callback)
        if exportType == "spotifyExtendedExport":
                return self.importExtendedHistory(parsedHistory, known=known, progress_callback=progress_callback)
        if exportType == "musicoletPremium":
            return self.importMusicoletCSVExport(parsedHistory, known=known, progress_callback=progress_callback)
        return []

    def buildKnownIndex(self, knownTrack):
        index = {}
        for item in knownTrack:
            index[item["id"]] = item
            if len(item["artists"]) == 0:
                continue
            index[item["name"]+item["artists"][0]["name"]] = item
        return index
        
    def _import(self, dataFunction, history, known=[], progress_callback=None):
        known = self.buildKnownIndex(known)
        
        # 1. Parse all items into memory first (fast)
        parsed_items = []
        for item in history:
            try:
                name, artist, startTimestamp, timePlayed, trackUri = dataFunction(item)
                parsed_items.append((name, artist, startTimestamp, timePlayed, trackUri))
            except Exception:
                continue
                
        total_items = len(parsed_items)
        if total_items == 0:
            return
            
        # Process history in chunks (batches) of 500 entries
        CHUNK_SIZE = 500
        
        for chunk_start in range(0, total_items, CHUNK_SIZE):
            chunk = parsed_items[chunk_start : chunk_start + CHUNK_SIZE]
            
            # Identify missing tracks in the current chunk
            missing_tracks = {}
            for name, artist, startTimestamp, timePlayed, trackUri in chunk:
                id_key = name+artist if name and artist else None
                if trackUri and trackUri in known:
                    continue
                if id_key and id_key in known:
                    continue
                
                if trackUri:
                    missing_tracks[trackUri] = (name, artist, trackUri)
                elif id_key:
                    missing_tracks[id_key] = (name, artist, None)
            
            # Fetch missing tracks in this chunk concurrently
            if missing_tracks:
                total_missing = len(missing_tracks)
                fetched_count = 0
                lock = threading.Lock()
                
                def fetch_one(key, info):
                    nonlocal fetched_count
                    name, artist, trackUri = info
                    meta = None
                    try:
                        if trackUri:
                            try:
                                meta = self.sp.track(trackUri)
                            except Exception:
                                meta = self._searchForSong(name=name, artist=artist)
                        else:
                            meta = self._searchForSong(name=name, artist=artist)
                    except Exception as e:
                        print(f"Error fetching {name} by {artist}: {parseError(e)}")
                        
                    with lock:
                        fetched_count += 1
                        if progress_callback:
                            progress_callback("running", chunk_start, total_items, f"Pre-fetching batch metadata ({fetched_count}/{total_missing})...")
                    return key, meta
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    futures = {executor.submit(fetch_one, k, val): k for k, val in missing_tracks.items()}
                    for future in concurrent.futures.as_completed(futures):
                        key = futures[future]
                        try:
                            key, meta = future.result()
                            if meta:
                                formatted = Client.formatTrack(meta)
                                known[formatted["id"]] = formatted
                                if key != formatted["id"]:
                                    known[key] = formatted
                                if len(formatted["artists"]) > 0:
                                    name_artist_key = formatted["name"] + formatted["artists"][0]["name"]
                                    known[name_artist_key] = formatted
                        except Exception as e:
                            print(f"Error saving pre-fetched track: {parseError(e)}")
            
            # Yield items from the current chunk (fully in-memory now)
            for name, artist, startTimestamp, timePlayed, trackUri in chunk:
                try:
                    id_key = name+artist if name and artist else None
                    
                    if trackUri and trackUri in known:
                        matched_id = trackUri
                    elif id_key and id_key in known:
                        matched_id = id_key
                    else:
                        matched_id = None

                    if matched_id:
                        meta = Client.embedPlayInfo(known[matched_id].copy(), startTimestamp, timePlayed)
                    else:
                        if not name or not artist:
                            continue
                        
                        if trackUri:
                            try:
                                meta = self.sp.track(trackUri)
                            except Exception:
                                meta = self._searchForSong(name=name, artist=artist)
                        else:
                            meta = self._searchForSong(name=name, artist=artist)
                            
                        meta = Client.formatTrack(meta, startTimestamp, msPlayed=timePlayed)
                        
                        new_copy = meta.copy()
                        known[meta["id"]] = new_copy
                        if id_key:
                            known[id_key] = new_copy

                    yield meta
                except Exception as e:
                    print(f"Error processing item: {parseError(e)}")
                    continue

    def importAcountHistory(self, history, known=[], progress_callback=None):
        def dataFunction(item):
            endTimestamp = timeToInt(item["endTime"])
            timePlayed = item["msPlayed"]

            startTimestamp = endTimestamp-timePlayed//1000
            name=item["trackName"]
            artist=item["artistName"]
            return name, artist, startTimestamp, timePlayed, None
        
        yield from self._import(dataFunction, history, known, progress_callback)

    def importExtendedHistory(self, history, known=[], progress_callback=None):
        def dataFunction(item):
            ts = item["ts"]
            endTimestamp = timeToInt(ts)
            timePlayed = item.get("ms_played", 0)
            startTimestamp = endTimestamp - timePlayed // 1000

            name = item["master_metadata_track_name"]
            artist = item["master_metadata_album_artist_name"]
            uri = item.get("spotify_track_uri")
            trackUri = uri.split(":")[-1] if uri else None
            return name, artist, startTimestamp, timePlayed, trackUri
        
        yield from self._import(dataFunction, history, known, progress_callback)

    def importMusicoletCSVExport(self, rows, known=[], progress_callback=None):
        def expand(rows):
            ### Data formatted in: FILE_PATH,TITLE,ARTIST,ALBUM,ALBUM_ARTIST,COMPOSER,GENRE,YEAR,DURATION_MS,PLAY_COUNT
            NAME = 1
            ARTISTS = 2
            DURATION_MS = 8
            PLAYCOUNT = 9

            currentTime = now()
            formatedData = []
            reader = csv.reader(rows)
            
            for song in reader:
                if not song:
                    continue
                    
                try:
                    name = song[NAME]
                    mainArtist = song[ARTISTS].split("/")[0]
                    timePlayed = int(song[DURATION_MS])
                    play_count = int(song[PLAYCOUNT])
                    
                    for _ in range(play_count):
                        startTimestamp = currentTime.strftime("%Y-%m-%d %H:%M:%S")
                        formatedData.append((
                            name,
                            mainArtist,
                            startTimestamp,
                            timePlayed
                        ))
                        currentTime += datetime.timedelta(milliseconds=timePlayed)
                        
                except (IndexError, ValueError) as e:
                    continue
                    
            return formatedData

        def dataFunction(item):
            name, mainArtist, startTimestamp, timePlayed = item
            return name, mainArtist, startTimestamp, timePlayed, None

        yield from self._import(dataFunction, expand(rows), known, progress_callback)