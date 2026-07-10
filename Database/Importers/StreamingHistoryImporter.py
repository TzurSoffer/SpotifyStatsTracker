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
    # 500 allows for frequent progress bar updates in the UI and batches API pre-fetches
    # to avoid rate limits/network blocking without long delays.
    CHUNK_SIZE = 500

    def __init__(self, user="Tzur"):
        self.sp = SpotipyFree.Spotify()

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

    def importHistory(self, parsedHistory, known, exportType, progressCallback=None):
        if len(parsedHistory) == 0:
            return []
        if exportType == "spotifyAcountExport":
            return self.importAcountHistory(parsedHistory, known=known, progressCallback=progressCallback)
        if exportType == "spotifyExtendedExport":
                return self.importExtendedHistory(parsedHistory, known=known, progressCallback=progressCallback)
        if exportType == "musicoletPremium":
            return self.importMusicoletCSVExport(parsedHistory, known=known, progressCallback=progressCallback)
        return []

    def buildKnownIndex(self, knownTrack):
        index = {}
        for item in knownTrack:
            index[item["id"]] = item
            if len(item["artists"]) == 0:
                continue
            index[item["name"]+item["artists"][0]["name"]] = item
        return index

    def _parseHistory(self, dataFunction, history):
        parsedItems = []
        for item in history:
            try:
                name, artist, startTimestamp, timePlayed, trackUri = dataFunction(item)
                parsedItems.append((name, artist, startTimestamp, timePlayed, trackUri))
            except Exception:
                continue
        return parsedItems

    def _identifyMissingTracks(self, chunk, known):
        missingTracks = {}
        for name, artist, startTimestamp, timePlayed, trackUri in chunk:
            idKey = name + artist if name and artist else None
            if trackUri and trackUri in known:
                continue
            if idKey and idKey in known:
                continue
            
            if trackUri:
                missingTracks[trackUri] = (name, artist, trackUri)
            elif idKey:
                missingTracks[idKey] = (name, artist, None)
        return missingTracks

    def _prefetchMissingTracks(self, missingTracks, chunkStart, totalItems, known, progressCallback):
        totalMissing = len(missingTracks)
        fetchedCount = 0
        
        def fetchOne(key, info):
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
            return key, meta

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetchOne, k, val): k for k, val in missingTracks.items()}
            for future in concurrent.futures.as_completed(futures):
                fetchedCount += 1
                if progressCallback:
                    progressCallback(
                        "running", 
                        chunkStart, 
                        totalItems, 
                        f"Pre-fetching batch metadata ({fetchedCount}/{totalMissing})..."
                    )
                
                try:
                    key, meta = future.result()
                    if meta:
                        formatted = Client.formatTrack(meta)
                        known[formatted["id"]] = formatted
                        if key != formatted["id"]:
                            known[key] = formatted
                        if len(formatted["artists"]) > 0:
                            nameArtistKey = formatted["name"] + formatted["artists"][0]["name"]
                            known[nameArtistKey] = formatted
                except Exception as e:
                    print(f"Error saving pre-fetched track: {parseError(e)}")

    def _processPlay(self, item, known):
        name, artist, startTimestamp, timePlayed, trackUri = item
        try:
            idKey = name + artist if name and artist else None
            
            if trackUri and trackUri in known:
                matchedId = trackUri
            elif idKey and idKey in known:
                matchedId = idKey
            else:
                matchedId = None

            if matchedId:
                meta = Client.embedPlayInfo(known[matchedId].copy(), startTimestamp, timePlayed)
            else:
                if not name or not artist:
                    return None
                
                if trackUri:
                    try:
                        meta = self.sp.track(trackUri)
                    except Exception:
                        meta = self._searchForSong(name=name, artist=artist)
                else:
                    meta = self._searchForSong(name=name, artist=artist)
                    
                meta = Client.formatTrack(meta, startTimestamp, msPlayed=timePlayed)
                
                newCopy = meta.copy()
                known[meta["id"]] = newCopy
                if idKey:
                    known[idKey] = newCopy

            return meta
        except Exception as e:
            print(f"Error processing item: {parseError(e)}")
            return None
        
    def _import(self, dataFunction, history, known=[], progressCallback=None):
        known = self.buildKnownIndex(known)
        
        parsedItems = self._parseHistory(dataFunction, history)
        totalItems = len(parsedItems)
        if totalItems == 0:
            return
            
        for chunkStart in range(0, totalItems, self.CHUNK_SIZE):
            chunk = parsedItems[chunkStart : chunkStart + self.CHUNK_SIZE]
            
            missingTracks = self._identifyMissingTracks(chunk, known)
            
            # Fetch missing tracks in this chunk concurrently
            if missingTracks:
                self._prefetchMissingTracks(
                    missingTracks, 
                    chunkStart, 
                    totalItems, 
                    known, 
                    progressCallback
                )
            
            # Yield items from the current chunk (fully in-memory now)
            for item in chunk:
                meta = self._processPlay(item, known)
                if meta:
                    yield meta

    def importAcountHistory(self, history, known=[], progressCallback=None):
        def dataFunction(item):
            endTimestamp = timeToInt(item["endTime"])
            timePlayed = item["msPlayed"]

            startTimestamp = endTimestamp-timePlayed//1000
            name=item["trackName"]
            artist=item["artistName"]
            return name, artist, startTimestamp, timePlayed, None
        
        yield from self._import(dataFunction, history, known, progressCallback)

    def importExtendedHistory(self, history, known=[], progressCallback=None):
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
        
        yield from self._import(dataFunction, history, known, progressCallback)

    def importMusicoletCSVExport(self, rows, known=[], progressCallback=None):
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
                    playCount = int(song[PLAYCOUNT])
                    
                    for _ in range(playCount):
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

        yield from self._import(dataFunction, expand(rows), known, progressCallback)