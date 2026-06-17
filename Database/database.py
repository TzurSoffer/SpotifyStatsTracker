import datetime
import threading
import json
from pathlib import Path
from io import BytesIO

import requests
from PIL import Image

try:
    from Database.Formatters.spotifyClient import Client
    from Database.Importers.StreamingHistoryImporter import Importer
    from Database.Listeners.spotifyListener import Listener
    from Database.utils import parseError, convertToDatetime
except ModuleNotFoundError:
    from Formatters.spotifyClient import Client
    from Importers.StreamingHistoryImporter import Importer
    from Listeners.spotifyListener import Listener
    from utils import parseError, convertToDatetime

class Database:
    def __init__(self, user: str = "Tzur"):
        self.user = user
        self.listener = None
        self.baseDir = Path(__file__).resolve().parent

        self.imgDir_tracks = self.baseDir / "Users" / self.user / "img" / "tracks"
        self.imgDir_artists = self.baseDir / "Users" / self.user / "img" / "artists"
        self.entriesPath = self.baseDir / "Users" / self.user / "entries.json"
        self.tracksPath = self.baseDir / "Users" / self.user / "tracks.json"
        self.progressPath = self.baseDir / "Users" / self.user / "progress.json"

        self.fileLock = threading.RLock()

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
                self.appendTrackData(timestamp, track, msPlayed)

    def _loadEntries(self) -> list:
        """ Load ONLY id and info about time played from the JSON file. """
        return self._loadJsonFile(self.entriesPath, [])

    def _saveEntries(self, entries: list):
        """ Save ONLY id and info about time played to the JSON file. """
        self._save(self.entriesPath, entries)
    
    def _saveTracks(self, tracks: dict):
        """ Save full track metadata to the JSON file. """
        self._save(self.tracksPath, tracks)

    def _loadTracks(self) -> list:
        """ Load full track metadata from the JSON file. """
        return self._loadJsonFile(self.tracksPath, {})
    
    def _addTrack(self, tracks, track):
        tracks.update({track["id"]: track})
        return tracks

    def _saveNewTrackFromId(self, id, tracks=None):
        if tracks == None:
            tracks = self._loadTracks()
        track = Client.formatTrack(self.listener.track(id))
        tracks = self._addTrack(tracks, track)
        self._saveTracks(tracks)

    def _splitEntryAndTrack(self, metadata: dict) -> tuple[list, dict]:
        entry = {
            "id": metadata["id"],
            "playedAt": metadata["playedAt"],
            "timePlayed": metadata["timePlayed"],
        }
        metadata.pop("playedAt")
        metadata.pop("timePlayed")
        return entry, metadata

    def _paginateEntry(self, entry: dict, tracks: dict = None) -> dict:
        if tracks == None:
            tracks = self._loadTracks()

        if entry["id"] not in tracks:
            print(f"Missing track metadata for {entry["id"]}, downloading it")
            try:
                self._saveNewTrackFromId(entry["id"], tracks)
            except:
                print("Failed to download track")
                return None

        meta = tracks[entry["id"]]
        meta["playedAt"] = entry["playedAt"]
        meta["timePlayed"] = entry["timePlayed"]
        return meta

    def _paginateEntries(self, entries: list) -> list:
        ret = []
        tracks = self._loadTracks()
        for entry in entries:
            metadata = self._paginateEntry(entry, tracks)
            if metadata != None:
                ret.append(metadata)
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

    def getHistory(self) -> int:
        history = self._loadEntries()
        return self._paginateEntries(history)

    def getEntriesCount(self) -> int:
        """Return total number of entries in the database."""
        return len(self._loadEntries())
    
    def getEntriesFromNew(self, count: int | None = None, startIndex: int = 0) -> list:
        """ Return the latest `count` entries from history, sorted from newest to oldest. If count is None, return all entries. """
        entries = self._loadEntries()
        startPos = len(entries) - startIndex   #< Everything is reversed
        
        if count is not None:
            endPos = startPos - count
            endPos = None if endPos <= 0 else endPos
            slicedEntries = entries[startPos - 1 : endPos : -1]   #< slice and reverse
        else:
            slicedEntries = entries[startPos - 1 : : -1]           #< slice and reverse
            
        return self._paginateEntries(slicedEntries)

    def getEntriesFromOld(self, count: int | None = None, startIndex: int = 0) -> list:
            """ Return the oldest `count` entries from history, sorted from oldest to newest. If count is None, return all entries. """
            entries = self._loadEntries()

            if count is not None:
                endIndex = startIndex + count
                slicedEntries = entries[startIndex:endIndex]
            else:
                slicedEntries = entries[startIndex:]
                
            return self._paginateEntries(slicedEntries)

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

    def _saveImg(self, path: Path, url: str, imgId: str):
        metadataPath = path / "metadata.json"
        path.mkdir(parents=True, exist_ok=True)
        ids = self._loadJsonFile(metadataPath, [])
        if imgId in ids:
            print(f"Image for {imgId} already downloaded.")
            return
        try:
            response = requests.get(url)
            response.raise_for_status()
            img = Image.open(BytesIO(response.content))
            ext = img.format.lower() if img.format else "jpeg"
            
            img.save(path / f"{imgId}.{ext}")
            ids.append(imgId)

            metadataPath.write_text(
                json.dumps(ids, indent=4), encoding="utf-8"
            )
        except requests.exceptions.RequestException as e:
            print(f"Error fetching image from {url}: {parseError(e)}")
        except Exception as e:
            print(f"Error saving image: {parseError(e)}")

    def saveTrackImg(self, url: str, imgId: str):
        self._saveImg(self.imgDir_tracks, url, imgId)

    def saveArtistImg(self, url: str, imgId: str):
        self._saveImg(self.imgDir_artists, url, imgId)

    def appendMetadata(self, meta: dict) -> None:
        self.saveTrackImg(meta["imageUrl"], meta["imageId"])
        for artist in meta["artists"]:
            self.saveArtistImg(artist["imageUrl"], artist["imageId"])
        entry, track = self._splitEntryAndTrack(meta)
        self.appendEntries(entry)
        self.updateTracks(track)

    def appendTrackData(self, timestamp, track, timePlayed):
        self.appendMetadata(Client.formatTrack(track, timestamp, timePlayed))

    def resortDatabase(self):
        """ In case entries got out of order, this will sort them by playedAt timestamp. """
        entries = self._loadEntries()
        entries.sort(
            key=lambda x: convertToDatetime(x["playedAt"]).timestamp()
        )
        print("Resorted Database")

        self._saveEntries(entries)

    def importHistory(self, exportedHistory):
        entries = self._loadEntries()
        tracks = self._loadTracks()
        importer = Importer()
        total = importer.getLengthOfImport(exportedHistory)
        self.writeProgress("running", 0, total, "Starting import")

        index = 0
        try:
            for index, meta in enumerate(importer.importHistory(exportedHistory, self._loadTracks().values()), start=1):  #< We only want the tracks, the importer doesn't care about the keys
                e, t = self._splitEntryAndTrack(meta)
                entries.append(e)
                tracks = self._addTrack(tracks, t)
                self.writeProgress("running", index, total, f"Imported {index} of {total}")
            self._saveEntries(entries)
            self._saveTracks(tracks)
            self.resortDatabase()     #< Entries are not added in order, so sort them by timestamp
            self.writeProgress("complete", total, total, "Import complete")
        except Exception as e:
            self.writeProgress("failed", index, total, f"Import failed: {parseError(e)}", error=True)
            raise

    def filterEntriesByInterval(self, entries: list, startDate: datetime.datetime = None, endDate: datetime.datetime = None) -> list:
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
        entries = self.filterEntriesByInterval(self._loadEntries(), startDate, endDate)
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
                songs[key]["firstListenedAt"] = playedAt       #< database is sorted, so first find must be first time lisened

            songs[key]["plays"] += 1
            songs[key]["totalTimeListened"] += timePlayed
        return list(songs.values())

    def getArtistsStats(self, startDate: datetime.datetime = None, endDate: datetime.datetime = None) -> list:
        """Return artists sorted by total plays with aggregated data and listen totals."""
        tracks = self._loadTracks()
        entries = self.filterEntriesByInterval(self._loadEntries(), startDate, endDate)
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

    def _getTopStats(self, items, compareKeys, startDate: datetime.datetime = None, endDate: datetime.datetime = None, by: str = "plays") -> list:
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
        return self._getTopStats(songs, compKeys, startDate, endDate, by)
        

    def getTopArtists(self, startDate: datetime.datetime = None, endDate: datetime.datetime = None, by: str = "plays") -> list:
        artists = self.getArtistsStats(startDate, endDate)
        compKeys = (by, "totalTimeListened", "name")
        return self._getTopStats(artists, compKeys, startDate, endDate, by)

    def startListener(self, cookiesFile):
        self.listener = Listener(cookiesFile)
        self.listener.startListener_thread(callback=self._addToDatabaseFromListener)
    
    def isListenerLoggedIn(self):
        if self.listener == None:
            return False
        return self.listener.isLoggedIn()


if __name__ == "__main__":
    import SpotipyFree

    manager = Database(user="Tzur")
    manager.startListener("cookies.json")
    import pysole
    pysole.probe()

    # sp = SpotipyFree.Spotify()
    # sp.login()

    # importFile = Path("importMe.json")
    # if importFile.exists():
    #     with importFile.open("r", encoding="utf-8") as f:
    #         historyPayload = json.load(f)
    #     manager.importSpotifyHistory(historyPayload)

