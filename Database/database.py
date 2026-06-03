import datetime
import json
from pathlib import Path
from io import BytesIO

import requests
from PIL import Image

try:
    from Database.Formatters.spotifyClient import Client
    from Database.Importers.StreamingHistoryImporter import Importer
    from Database.Listeners.spotifyListener import Listener
except ModuleNotFoundError:
    from Formatters.spotifyClient import Client
    from Importers.StreamingHistoryImporter import Importer
    from Listeners.spotifyListener import Listener

class Database:
    def __init__(self, user: str = "Tzur"):
        self.user = user
        self.listener = None
        self.baseDir = Path(__file__).resolve().parent

        self.imgDir = self.baseDir / "Users" / self.user / "img" / "tracks"
        self.downloadedImagesPath = self.imgDir / "metadata.json"
        self.entriesPath = self.baseDir / "Users" / self.user / "entries.json"
        self.tracksPath = self.baseDir / "Users" / self.user / "tracks.json"
        self.progressPath = self.baseDir / "Users" / self.user / "progress.json"

        self.downloadedImages = self._loadDownloadedImagesCache()
        self.resetProgress()

    def _addToDatabaseFromListener(self, data) -> None:
        if not data:
            return
        for item in data:
            track = item.get("track")
            timestamp = item.get("played_at")
            msPlayed = item.get("ms_played", 0)
            if track and timestamp:
                self.appendTrackData(timestamp, track, msPlayed)

    def _loadDownloadedImagesCache(self) -> list:
        if self.downloadedImagesPath.exists():
            try:
                return json.loads(self.downloadedImagesPath.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        return []

    def _ensureJsonFile(self, path: Path, default) -> list:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(json.dumps(default, indent=4), encoding="utf-8")
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            path.write_text(json.dumps(default, indent=4), encoding="utf-8")
            return default

    def _save(self, file, data):
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(data, indent=4), encoding="utf-8")

    def _loadEntries(self) -> list:
        """ Load ONLY id and info about time played from the JSON file. """
        return self._ensureJsonFile(self.entriesPath, [])

    def _saveEntries(self, entries: list):
        """ Save ONLY id and info about time played to the JSON file. """
        self._save(self.entriesPath, entries)
    
    def _saveTracks(self, tracks: dict):
        """ Save full track metadata to the JSON file. """
        self._save(self.tracksPath, tracks)

    def _loadTracks(self) -> list:
        """ Load full track metadata from the JSON file. """
        return self._ensureJsonFile(self.tracksPath, {})
    
    def _splitEntriesAndTracks(self, metadata: list) -> tuple[list, dict]:
        entries = []
        tracks = {}
        if type(metadata) == dict:
            metadata = [metadata]
        for item in metadata:
            entry = {
                "id": item["id"],
                "playedAt": item["playedAt"],
                "playedAtText": item["playedAtText"],
                "timePlayed": item["timePlayed"]
            }
            entries.append(entry)
            item.pop("playedAt")
            item.pop("playedAtText")
            item.pop("timePlayed")
            tracks[item["id"]] = item
        return entries, tracks

    def _paginateEntry(self, entry: dict, tracks: dict = None) -> dict:
        if tracks is None:
            tracks = self._loadTracks()
        meta = tracks[entry["id"]]
        meta["playedAt"] = entry["playedAt"]
        meta["playedAtText"] = entry["playedAtText"]
        meta["timePlayed"] = entry["timePlayed"]
        return meta

    def _paginateEntries(self, entries: list) -> list:
        ret = []
        tracks = self._loadTracks()
        for entry in entries:
            ret.append(self._paginateEntry(entry, tracks))
        return ret

    def appendEntries(self, newEntries: list):
        if not newEntries:
            return
        entries = self._loadEntries()
        entries.extend(newEntries)
        self._saveEntries(entries)
    
    def updateTracks(self, tracks: dict):
        if not tracks:
            return
        existingTracks = self._loadTracks()
        existingTracks.update(tracks)          #< Add new track if missing, or update existing track metadata if already exists
        self._saveTracks(existingTracks)

    def getHistory(self) -> int:
        history = self._loadEntries()
        return self._paginateEntries(history)
    
    def getEntriesFromNew(self, count: int) -> list:
        """ Return the latest `count` entries from history, sorted from newest to oldest. If count is None, return all entries. """
        tracks = self._loadEntries()
        if count is not None:
            return self._paginateEntries(tracks[:count][::-1])
        return self._paginateEntries(tracks[::-1])

    def getEntriesFromOld(self, count: int) -> list:
        """ Return the oldest `count` entries from history, sorted from oldest to newest. If count is None, return all entries. """
        tracks = self._loadEntries()
        if count is not None:
            return self._paginateEntries(tracks[-count:])
        return self._paginateEntries(tracks)

    def getEntriesFromIndex(self, index: int, count: int = None, oldest_first: bool = False) -> list:
        tracks = self._loadEntries()
        index = min(index, len(tracks) - 1)
        if count is not None:
            if oldest_first:
                return self._paginateEntries(tracks[index:index + count])
            else:
                return self._paginateEntries(tracks[index - count:index]) if index >= count else self._paginateEntries(tracks[:index])
        return [self._paginateEntries([tracks[index]])]

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

    def saveImg(self, url: str, imgId: str):
        self.imgDir.mkdir(parents=True, exist_ok=True)
        if imgId in self.downloadedImages:
            print(f"Image for {imgId} already downloaded.")
            return
        try:
            response = requests.get(url)
            response.raise_for_status()
            img = Image.open(BytesIO(response.content))
            ext = img.format.lower() if img.format else "jpg"
            
            img.save(self.imgDir / f"{imgId}.{ext}")
            self.downloadedImages.append(imgId)
            
            self.downloadedImagesPath.parent.mkdir(parents=True, exist_ok=True)
            self.downloadedImagesPath.write_text(
                json.dumps(self.downloadedImages, indent=4), encoding="utf-8"
            )
        except requests.exceptions.RequestException as e:
            print(f"Error fetching image from {url}: {e}")
        except Exception as e:
            print(f"Error saving image: {e}")

    def appendMetadata(self, meta: dict) -> None:
        self.saveImg(meta["imageUrl"], meta["imageId"])
        entry, track = self._splitEntriesAndTracks(meta)
        self.appendEntries(entry)
        self.updateTracks(track)

    def appendTrackData(self, timestamp, track, timePlayed):
        self.appendMetadata(Client.formatTrack(timestamp, track, timePlayed))

    def importSpotifyHistory(self, exportedHistory):
        entries = self._loadEntries()
        tracks = self._loadTracks()
        importer = Importer()
        total = len(exportedHistory)
        self.writeProgress("running", 0, total, "Starting import")

        index = 0
        try:
            for index, meta in enumerate(importer.importHistory(exportedHistory), start=1):
                e, t = self._splitEntriesAndTracks(meta)
                entries.append(e)
                tracks.extend(t)
                self.writeProgress("running", index, total, f"Imported {index} of {total}")
            self._saveEntries(entries)
            self._saveTracks(tracks)
            self.writeProgress("complete", total, total, "Import complete")
        except Exception as e:
            self.writeProgress("failed", index, total, f"Import failed: {e}", error=True)
            raise

    def filterEntriesByInterval(self, entries: list, startDate: datetime.datetime = None, endDate: datetime.datetime = None) -> list:
        if startDate is None and endDate is None:
            return entries

        filtered = []
        for track in entries:
            playedAt = track["playedAt"]
            date = datetime.datetime.fromtimestamp(int(playedAt))

            if startDate and date < startDate:
                continue
            if endDate and date > endDate:
                break
                
            filtered.append(track)
        return filtered

    def getTopSongs(self, startDate: datetime.datetime = None, endDate: datetime.datetime = None, by: str = "plays") -> list:
        return sorted(
            self.getSongsStats(startDate, endDate),
            key=lambda item: (-item[by], -item["totalTimeListened"], item["song"].get("name", ""))
        )

    def getSongsStats(self, startDate: datetime.datetime = None, endDate: datetime.datetime = None) -> list:
        """Return songs sorted by play count with full song metadata and listen totals."""
        entries = self.filterEntriesByInterval(self._loadEntries(), startDate, endDate)
        songs = {}

        for entry in entries:
            key = entry["id"]
            timePlayed = entry["timePlayed"]
            if key not in songs:
                songs[key] = {
                    "plays": 0,
                    "totalTimeListened": 0,
                    "song": None,
                }
                songs[key]["song"] = self._paginateEntry(entry)  #< Get full song metadata for this entry
            songs[key]["plays"] += 1
            songs[key]["totalTimeListened"] += timePlayed

        normalized = []
        for v in songs.values():
            song = v["song"].copy()
            normalized.append({
                "plays": v["plays"],
                "totalTimeListened": v["totalTimeListened"],
                "song": song,
            })
        return normalized

    def getTopArtists(self, startDate: datetime.datetime = None, endDate: datetime.datetime = None, by: str = "plays") -> list:
        return sorted(
            self.getArtistsStats(startDate, endDate),
            key=lambda item: (-item[by], -item["totalTimeListened"], item["artist"])
        )

    def getArtistsStats(self, startDate: datetime.datetime = None, endDate: datetime.datetime = None) -> list:
        """Return artists sorted by total plays with aggregated data and listen totals."""
        entries = self.filterEntriesByInterval(self._loadEntries(), startDate, endDate)
        artistsStats = {}

        for entry in entries:
            artists = entry.get("artists", [])
            timePlayed = entry["timePlayed"]
            for artist in artists:
                artistName = artist["name"]
                if artistName not in artistsStats:
                    artistsStats[artistName] = {
                        "plays": 0,
                        "totalTimeListened": 0,
                        "artist": artistName,
                        "uniqueSongs": set(),
                    }

                artistsStats[artistName]["plays"] += 1
                artistsStats[artistName]["totalTimeListened"] += timePlayed
                artistsStats[artistName]["uniqueSongs"].add(entry.get("id"))

        normalized = []
        for v in artistsStats.values():
            normalized.append({
                "plays": v["plays"],
                "totalTimeListened": v["totalTimeListened"],
                "artist": v["artist"],
                "uniqueSongCount": len(v["uniqueSongs"]),
            })
        
        return normalized

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

