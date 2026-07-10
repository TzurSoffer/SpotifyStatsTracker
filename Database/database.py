from __future__ import annotations
import datetime
import copy
import os
import re
import threading
import json
from pathlib import Path
from io import BytesIO

import requests
from PIL import Image
import concurrent.futures

try:
    from Database.Formatters.spotifyClient import Client
    from Database.Importers.StreamingHistoryImporter import Importer
    from Database.Importers.AutoImporter import AutoImporter
    from Database.Listeners.spotifyListener import Listener
    from Database.utils import parseError, convertToDatetime
except ModuleNotFoundError:
    from Formatters.spotifyClient import Client
    from Importers.StreamingHistoryImporter import Importer
    from Importers.AutoImporter import AutoImporter
    from Listeners.spotifyListener import Listener
    from utils import parseError, convertToDatetime

class Database:
    def __init__(self, user: str, cookiesFile: str | None = None, email: str | None = None):
        if not user:
            raise ValueError("Database user must be specified and cannot be empty.")
        self.user = user
        self.cookiesFile = cookiesFile
        self.email = email
        self.listener = None
        self.baseDir = Path(__file__).resolve().parent

        self.imgDir_tracks = self.baseDir / "Users" / self.user / "img" / "tracks"
        self.imgDir_artists = self.baseDir / "Users" / self.user / "img" / "artists"
        self.entriesPath = self.baseDir / "Users" / self.user / "entries.json"
        self.tracksPath = self.baseDir / "Users" / self.user / "tracks.json"
        self.playlistsPath = self.baseDir / "Users" / self.user / "playlists.json"
        self.progressPath = self.baseDir / "Users" / self.user / "progress.json"
        self.autoImportFolderPath = self.baseDir / ".." / "autoImport" / self.user

        self.fileLock = threading.RLock()
        self.entriesCache = None
        self.tracksCache = None
        self.playlistsCache = None

        self._imageIdsLock = threading.RLock()
        self._downloadedTrackImages = None
        self._downloadedArtistImages = None
        self._artistImageLazyFetchAttempted = set()
        self._imageDownloadExecutor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

        filterKeyword = os.environ.get("IMPORT_KEYWORD", None)
        print(f"auto import filtering by {filterKeyword}")
        self.autoImporter = AutoImporter(folderPath=self.autoImportFolderPath,
                                         importCallback=self.importHistory,
                                         pollInterval=5,
                                         keyword=filterKeyword)

    def _loadJsonFile(self, path: Path, default):
        with self.fileLock:
            path.parent.mkdir(parents=True, exist_ok=True)

            if not path.exists():
                path.write_text(
                    json.dumps(default, indent=4),
                    encoding="utf-8"
                )
                return default

            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                print(f"Corrupted JSON in {path}: {e}")
                raise

    def _save(self, file, data):
        with self.fileLock:
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(json.dumps(data, indent=4), encoding="utf-8")

    def _addToDatabaseFromListener(self, data) -> None:
        if not data:
            return
        for item in data:
            track = item.get("track")
            timestamp = item.get("played_at")
            msPlayed = item.get("ms_played", 0)
            if track:
                self.appendTrackData(timestamp, track, msPlayed, context=item.get("context", None))

    def _loadEntries(self) -> list:
        """Load ONLY id and info about time played from the JSON file."""
        if self.entriesCache is None:
            self.entriesCache = self._loadJsonFile(self.entriesPath, [])
        return self.entriesCache

    def _saveEntries(self, entries: list):
        """Save ONLY id and info about time played to the JSON file."""
        self.entriesCache = entries
        self._save(self.entriesPath, entries)

    def _saveTracks(self, tracks: dict):
        """Save full track metadata to the JSON file."""
        self.tracksCache = tracks
        self._save(self.tracksPath, tracks)

    def _loadTracks(self) -> dict:
        """Load full track metadata from the JSON file."""
        if self.tracksCache is None:
            self.tracksCache = self._loadJsonFile(self.tracksPath, {})
        return self.tracksCache

    def _loadPlaylists(self) -> dict:
        """Load playlist id to name mappings from the JSON file."""
        if self.playlistsCache is None:
            self.playlistsCache = self._loadJsonFile(self.playlistsPath, {"album": {}, "playlist": {}})
        return self.playlistsCache

    def _savePlaylists(self, playlists: dict):
        """Save playlist id to name mappings to the JSON file."""
        self.playlistsCache = playlists
        self._save(self.playlistsPath, playlists)

    def playlistName(self, playlistUri: str | None) -> str | None:
        """Return the playlist name for a Spotify playlist URI or id, caching it on first lookup."""
        if not playlistUri:
            return None
        type, playlistId = playlistUri.split(":", 1)
        playlists = self._loadPlaylists()
        return playlists[type].get(playlistId, None)
    
    def _addTrack(self, tracks, track):
        tracks[track["id"]] = track
        return tracks

    def _saveNewTrackFromId(self, id, tracks=None, deferSave=False):
        if tracks == None:
            tracks = self._loadTracks()
        track = Client.formatTrack(self.listener.track(id))
        tracks = self._addTrack(tracks, track)
        if not deferSave:
            self._saveTracks(tracks)

    def _splitEntryAndTrack(self, metadata: dict) -> tuple[list, dict]:
        entry = {
            "id": metadata["id"],
            "playedAt": metadata["playedAt"],
            "timePlayed": metadata["timePlayed"],
            "playedFrom": metadata.get("playedFrom"),
        }
        metadata.pop("playedAt")
        metadata.pop("timePlayed")
        metadata.pop("playedFrom", None)
        return entry, metadata

    def _paginateEntry(self, entry: dict, tracks: dict = None, deferSave: bool = False) -> dict:
        if tracks is None:
            tracks = self._loadTracks()

        if entry["id"] not in tracks:
            print(f"Missing track metadata for {entry['id']}, downloading it")
            try:
                self._saveNewTrackFromId(entry["id"], tracks, deferSave=deferSave)
            except Exception:
                print("Failed to download track")
                return None

        meta = tracks[entry["id"]].copy()

        meta["playedAt"] = entry["playedAt"]
        meta["timePlayed"] = entry["timePlayed"]
        meta["playedFrom"] = entry.get("playedFrom", None)

        return meta

    def _paginateEntries(self, entries: list) -> list:
        ret = []
        tracks = self._loadTracks()
        initialLength = len(tracks)
        for entry in entries:
            metadata = self._paginateEntry(entry, tracks, deferSave=True)
            if metadata != None:
                ret.append(metadata)
                
        if len(tracks) > initialLength:
            self._saveTracks(tracks)
            
        return ret

    def appendEntries(self, newEntries: list):
        if not newEntries:
            return
        entries = self._loadEntries()
        entries.append(newEntries)
        self._saveEntries(entries)
    
    def updateTracks(self, track: dict):
        if not track:
            return
        existingTracks = self._loadTracks()
        self._addTrack(existingTracks, track)          #< Add new track if missing, or update existing track metadata if already exists
        self._saveTracks(existingTracks)

    def updatePlaylists(self, playlist):
        if playlist is None:
            return
        existingPlaylists = self._loadPlaylists()
        contextType, playlistId = playlist.split(":", 1)
        if playlistId not in existingPlaylists[contextType]:
            try:
                if contextType == "album":
                    existingPlaylists[contextType][playlistId] = self.listener.albumName(playlistId)
                else:
                    existingPlaylists[contextType][playlistId] = self.listener.playlistName(playlistId)
            except Exception as e:
                print(f"Error occurred while fetching playlist name for {playlistId} (probably due to playlist being private): {e}")
                existingPlaylists[contextType][playlistId] = None
            self._savePlaylists(existingPlaylists)

    def getHistory(self) -> int:
        history = self._loadEntries()
        return self._paginateEntries(history)

    def getEntriesCount(self) -> int:
        """Return total number of entries in the database."""
        return len(self._loadEntries())
    
    def getEntriesFromNew(self, count: int | None = None, startIndex: int = 0, fullPagination: bool = True) -> list:
        """ Return the latest `count` entries from history, sorted from newest to oldest. If count is None, return all entries. """
        entries = self._loadEntries()
        startPos = len(entries) - startIndex   #< Everything is reversed
        
        if count is not None:
            endPos = startPos - count
            endPos = None if endPos <= 0 else endPos
            slicedEntries = entries[startPos - 1 : endPos : -1]   #< slice and reverse
        else:
            slicedEntries = entries[startPos - 1 : : -1]          #< slice and reverse
        
        if fullPagination:
            return self._paginateEntries(slicedEntries)
        return slicedEntries

    def getEntriesFromOld(self, count: int | None = None, startIndex: int = 0, fullPagination: bool = True) -> list:
            """ Return the oldest `count` entries from history, sorted from oldest to newest. If count is None, return all entries. """
            entries = self._loadEntries()

            if count is not None:
                endIndex = startIndex + count
                slicedEntries = entries[startIndex:endIndex]
            else:
                slicedEntries = entries[startIndex:]
                
            if fullPagination:
                return self._paginateEntries(slicedEntries)
            return slicedEntries

    def writeProgress(self, status: str, current: int = 0, total: int = 0, message: str = "", error: bool = False):
        payload = {
            "status": status,
            "current": current,
            "total": total,
            "percentage": round((current / total * 100) if total else 0),
            "message": message,
            "error": error,
        }
        self.progressPath.parent.mkdir(parents=True, exist_ok=True)
        self.progressPath.write_text(json.dumps(payload, indent=4), encoding="utf-8")

    def readProgress(self) -> dict:
        defaultProgress = {
            "status": "idle",
            "current": 0,
            "total": 0,
            "percentage": 0,
            "message": "",
            "error": False,
        }
        if not self.progressPath.exists():
            return defaultProgress
        try:
            return json.loads(self.progressPath.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return defaultProgress
    
    def resetProgress(self):
        self.writeProgress("idle", 0, 0, "", False)

    def _downloadImageTask(self, path: Path, url: str, imgId: str, metadataPath: Path, cachedIdsSet: set):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            img = Image.open(BytesIO(response.content))
            ext = img.format.lower() if img.format else "jpeg"
            
            img.save(path / f"{imgId}.{ext}")
            
            with self._imageIdsLock:
                # Add to set and persist. Pre-adding handles immediate concurrent lookups, 
                # this ensures it's persisted successfully.
                cachedIdsSet.add(imgId)
                metadataPath.write_text(json.dumps(list(cachedIdsSet), indent=4), encoding="utf-8")
        except requests.exceptions.RequestException as e:
            print(f"Error fetching image from {url}: {parseError(e)}")
        except Exception as e:
            print(f"Error saving image: {parseError(e)}")

    def _saveImg(self, path: Path, url: str, imgId: str, isTrack: bool):
        metadataPath = path / "metadata.json"
        
        with self._imageIdsLock:
            if isTrack:
                if self._downloadedTrackImages is None:
                    path.mkdir(parents=True, exist_ok=True)
                    self._downloadedTrackImages = set(self._loadJsonFile(metadataPath, []))
                cachedSet = self._downloadedTrackImages
            else:
                if self._downloadedArtistImages is None:
                    path.mkdir(parents=True, exist_ok=True)
                    self._downloadedArtistImages = set(self._loadJsonFile(metadataPath, []))
                cachedSet = self._downloadedArtistImages

            if imgId in cachedSet:
                return
            
            # Pre-add to set to prevent duplicate concurrent download requests for the same image
            cachedSet.add(imgId)

        self._imageDownloadExecutor.submit(self._downloadImageTask, path, url, imgId, metadataPath, cachedSet)

    def saveTrackImg(self, url: str, imgId: str):
        self._saveImg(self.imgDir_tracks, url, imgId, isTrack=True)

    def saveArtistImg(self, url: str, imgId: str):
        self._saveImg(self.imgDir_artists, url, imgId, isTrack=False)

    def lazyFetchArtistImage(self, artistId: str, imagePath: Path) -> bool:
        """Best-effort synchronous fetch of an artist's image scraped from their public
        Spotify page, used as a fallback for artists we never received image metadata
        for from the API. Deduplicated per artist id (via the same lock used by the
        rest of the image pipeline) so repeated requests for a still-missing image
        don't keep re-hitting Spotify. Returns True if the image exists on disk after
        this call, whether freshly fetched or already cached.
        """
        if imagePath.exists():
            return True
        if not artistId:
            return False

        with self._imageIdsLock:
            if artistId in self._artistImageLazyFetchAttempted:
                return imagePath.exists()
            self._artistImageLazyFetchAttempted.add(artistId)

        try:
            res = requests.get(f"https://open.spotify.com/artist/{artistId}", timeout=5)
            match = re.search(r'<meta property="og:image" content="([^"]+)"', res.text)
            if not match:
                return False
            imgData = requests.get(match.group(1), timeout=5).content
            imagePath.parent.mkdir(parents=True, exist_ok=True)
            imagePath.write_bytes(imgData)
            return True
        except Exception as e:
            print(f"Failed to lazy load artist image for {artistId}: {parseError(e)}")
            return False

    def saveImagesFromTrack(self, track: dict):
        self.saveTrackImg(track["imageUrl"], track["imageId"])

    def appendMetadata(self, meta: dict) -> None:
        self.saveImagesFromTrack(meta)
        entry, track = self._splitEntryAndTrack(meta)
        self.appendEntries(entry)
        self.updateTracks(track)
        self.updatePlaylists(entry.get("playedFrom", None))

    def appendTrackData(self, timestamp, track, timePlayed, context=None):
        self.appendMetadata(Client.formatTrack(track, timestamp, timePlayed, context=context))

    def resortDatabase(self):
        """ In case entries got out of order, this will sort them by playedAt timestamp. """
        entries = self._loadEntries()
        entries.sort(
            key=lambda x: x.get("playedAt", 0) if isinstance(x.get("playedAt", 0), (int, float)) else convertToDatetime(x.get("playedAt", 0)).timestamp()
        )
        print("Resorted Database")

        self._saveEntries(entries)

    def importHistory(self, exportedHistory):
        entries = self._loadEntries()
        tracks = self._loadTracks()
        importer = Importer(cookiesFile=self.cookiesFile, email=self.email)
        
        parsedHistory, exportType = importer._convertToList(exportedHistory)
        if not parsedHistory:
            return
            
        total = len(parsedHistory)
        self.writeProgress("running", 0, total, "Starting import")

        def progress_callback(status, current, total_steps, message):
            self.writeProgress(status, current, total_steps, message)

        index = 0
        try:
            for index, meta in enumerate(importer.importHistory(parsedHistory, self._loadTracks().values(), exportType, progress_callback=progress_callback), start=1):  #< We only want the tracks, the importer doesn't care about the keys
                e, t = self._splitEntryAndTrack(meta)
                entries.append(e)
                tracks = self._addTrack(tracks, t)
                self.saveImagesFromTrack(t)
                
                if index % 10 == 0 or index == total:
                    self.writeProgress("running", index, total, f"Imported {index} of {total}")
            
            # Sort entries in-memory before saving, avoiding redundant read/writes
            entries.sort(
                key=lambda x: x.get("playedAt", 0) if isinstance(x.get("playedAt", 0), (int, float)) else convertToDatetime(x.get("playedAt", 0)).timestamp()
            )
            self._saveEntries(entries)
            self._saveTracks(tracks)
            self.writeProgress("complete", total, total, "Import complete")
        except Exception as e:
            self.writeProgress("failed", index, total, f"Import failed: {parseError(e)}", error=True)
            raise

    def filterByInterval(self, entries: list, startDate: datetime.datetime = None, endDate: datetime.datetime = None) -> list:
        if startDate is None and endDate is None:
            return entries

        filtered = []
        for track in entries:
            playedAt = track["playedAt"]
            date = convertToDatetime(playedAt)

            if startDate and date < startDate:
                continue
            if endDate and date > endDate:
                break
                
            filtered.append(track)
        return filtered

    def getSongsStats(self, startDate: datetime.datetime = None, endDate: datetime.datetime = None) -> list:
        """Return songs sorted by play count with full song metadata and listen totals."""
        tracks = self._loadTracks()
        entries = self.filterByInterval(self._loadEntries(), startDate, endDate)
        songs = {}

        for entry in entries:
            key = entry["id"]
            timePlayed = entry["timePlayed"]
            playedAt = entry.get("playedAt")
            
            if key not in songs:
                metadata = self._paginateEntry(entry, tracks)  #< Get full song metadata for this entry
                if metadata == None:
                    continue
                songs[key] = metadata
                songs[key]["plays"] = 0
                songs[key]["totalTimeListened"] = 0
                songs[key]["firstListenedAt"] = playedAt       #< database is sorted, so first find must be first time listened

            songs[key]["plays"] += 1
            songs[key]["totalTimeListened"] += timePlayed
        return list(songs.values())

    def getArtistsStats(self, startDate: datetime.datetime = None, endDate: datetime.datetime = None) -> list:
        """Return artists sorted by total plays with aggregated data and listen totals."""
        tracks = self._loadTracks()
        entries = self.filterByInterval(self._loadEntries(), startDate, endDate)
        artistsStats = {}

        for entry in entries:
            timePlayed = entry["timePlayed"]
            playedAt = entry.get("playedAt")
            metadata = self._paginateEntry(entry, tracks)
            if metadata == None:
                continue
            
            artists = metadata.get("artists", [])
            for artist in artists:
                artistName = artist["name"]
                if artistName not in artistsStats:
                    artistsStats[artistName] = artist
                    artistsStats[artistName]["plays"] = 0
                    artistsStats[artistName]["totalTimeListened"] = 0
                    artistsStats[artistName]["uniqueSongs"] = set()
                    artistsStats[artistName]["firstListenedAt"] = playedAt

                artistsStats[artistName]["plays"] += 1
                artistsStats[artistName]["totalTimeListened"] += timePlayed
                artistsStats[artistName]["uniqueSongs"].add(entry.get("id"))

        normalized = []
        for v in artistsStats.values():
            uniqueSongCount = len(v["uniqueSongs"])
            v["uniqueSongCount"] = uniqueSongCount
            v.pop("uniqueSongs")
            normalized.append(v)

        return normalized
    
    def _getListeningTotals(self, entries):
        totalSongsPlayed = 0
        totalDurationMs = 0
        for entry in entries:
            totalSongsPlayed += 1
            totalDurationMs += entry["timePlayed"]
        return totalSongsPlayed, totalDurationMs

    def _getTotal(self, arr, key):
        return sum(i.get(key, 0) for i in arr)

    def getOverallStats(self, startDate: datetime.datetime = None, endDate: datetime.datetime = None) -> list:
        """Return songs sorted by play count with full song metadata and listen totals."""
        previousEntries = []
        if startDate and endDate:
            duration = endDate - startDate
            previousStart = startDate - duration
            previousEnd = startDate
            previousEntries = self.filterByInterval(self._loadEntries(),
                                                    previousStart,
                                                    previousEnd)
        currentTopSongs = self.getTopSongs(startDate=startDate, endDate=endDate, by="plays")
        currentTopArtists = self.getTopArtists(startDate=startDate, endDate=endDate, by="totalTimeListened")
        
        # By using the already calculated currentTopSongs, we can save a lot of time by not having to iterate through the entire entries list again to calculate the totals.
        totalSongsPlayed = self._getTotal(currentTopSongs, "plays")
        totalDurationMs = self._getTotal(currentTopSongs, "totalTimeListened")
        previousSongsPlayed, previousDurationMs = self._getListeningTotals(previousEntries)
        
        return {"currentTopSongs": currentTopSongs,
                "currentTopArtists": currentTopArtists,
                "totalSongsPlayed": totalSongsPlayed,
                "totalDurationMs": totalDurationMs,
                "previousSongsPlayed": previousSongsPlayed,
                "previousDurationMs": previousDurationMs
                }

    def _sortTopStats(self, items, compareKeys, by: str = "plays") -> list:
        """
        Sorts songs within a date range. 
        'plays' and 'totalTimeListened' are sorted descending (highest first).
        'name' is sorted ascending (A to Z).
        """

        reverse=True
        if by == "name":
            reverse=False

        return sorted(
            items, 
            key=lambda item: tuple(item[key] for key in compareKeys),     #< the tuple acts as a tie breaker, if two elements 'by' are the same, it compares the 'totalTimeListened', then 'name'
            reverse=reverse
        )

    def getTopSongs(self, startDate: datetime.datetime = None, endDate: datetime.datetime = None, by: str = "plays") -> list:
        songs = self.getSongsStats(startDate, endDate)
        compKeys = (by, "totalTimeListened", "name")
        return self._sortTopStats(songs, compKeys, by)

    def getTopArtists(self, startDate: datetime.datetime = None, endDate: datetime.datetime = None, by: str = "plays") -> list:
        artists = self.getArtistsStats(startDate, endDate)
        compKeys = (by, "totalTimeListened", "name")
        return self._sortTopStats(artists, compKeys, by)

    def startListener(self, cookiesFile, email=None):
        if cookiesFile:
            self.cookiesFile = cookiesFile
        if email:
            self.email = email
        self.listener = Listener(self.cookiesFile, email=self.email)
        self.listener.startListener_thread(callback=self._addToDatabaseFromListener)

    def startAutoImporter(self):
        self.autoImporter.start()

    def isListenerLoggedIn(self):
        if self.listener == None:
            return False
        return self.listener.isLoggedIn()


if __name__ == "__main__":

    manager = Database(user="Tzur")
    manager.startListener("cookies.json")
    manager.startAutoImporter()
    import pysole
    pysole.probe()

    # import SpotipyFree
    # sp = SpotipyFree.Spotify()
    # sp.login()

    # importFile = Path("importMe.json")
    # if importFile.exists():
    #     with importFile.open("r", encoding="utf-8") as f:
    #         historyPayload = json.load(f)
    #     manager.importSpotifyHistory(historyPayload)

