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
    def __init__(self, user: str = "Tzur", baseDir: Path = None):
        self.user = user
        self.listener = None
        self.baseDir = baseDir or Path(__file__).resolve().parent

        self.imgDir = self.baseDir / "img" / self.user / "tracks"
        self.downloadedImagesPath = self.imgDir / "metadata.json"
        self.historyPath = self.baseDir / "history.json"
        self.progressPath = self.baseDir / "progress.json"

        self.downloadedImages = self._loadDownloadedImagesCache()
        self.resetProgress()

    def _loadDownloadedImagesCache(self) -> list:
        if self.downloadedImagesPath.exists():
            try:
                return json.loads(self.downloadedImagesPath.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        return []

    def _ensureJsonFile(self, path: Path, default):
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(json.dumps(default, indent=4), encoding="utf-8")
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            path.write_text(json.dumps(default, indent=4), encoding="utf-8")
            return default

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

    def loadHistory(self) -> list:
        return self._ensureJsonFile(self.historyPath, [])

    def saveHistory(self, history: list):
        self.historyPath.parent.mkdir(parents=True, exist_ok=True)
        self.historyPath.write_text(json.dumps(history, indent=4), encoding="utf-8")

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

    def addToHistoryFromData(self, meta: dict):
        self.saveImg(meta["imageUrl"], meta["imageId"])
        history = self.loadHistory()
        history.append(meta)
        self.saveHistory(history)

    def addToHistoryFromTrackData(self, timestamp, track, timePlayed):
        self.addToHistoryFromData(Client.formatTrack(timestamp, track, timePlayed))

    def importSpotifyHistory(self, exportedHistory):
        history = self.loadHistory()
        importer = Importer()
        total = len(exportedHistory) if isinstance(exportedHistory, list) else 0
        self.writeProgress("running", 0, total, "Starting import")
        
        index = 0
        try:
            for index, meta in enumerate(importer.importHistory(exportedHistory), start=1):
                self.saveImg(meta["imageUrl"], meta["imageId"])
                history.append(meta)
                self.writeProgress("running", index, total, f"Imported {index} of {total}")
            self.saveHistory(history)
            self.writeProgress("complete", total, total, "Import complete")
        except Exception as e:
            self.writeProgress("failed", index, total, f"Import failed: {e}", error=True)
            raise

    def filterTracksByInterval(self, tracks: list, startDate: datetime.datetime = None, endDate: datetime.datetime = None) -> list:
        if startDate is None and endDate is None:
            return tracks

        filtered = []
        for track in tracks:
            playedAt = track.get("playedAt")
            date = datetime.datetime.fromtimestamp(int(playedAt))

            if startDate and date < startDate:
                continue
            if endDate and date > endDate:
                break
                
            filtered.append(track)
        return filtered

    def getTopSongs(self, startDate: datetime.datetime = None, endDate: datetime.datetime = None) -> list:
        """Return songs sorted by play count with full song metadata and listen totals."""
        tracks = self.filterTracksByInterval(self.loadHistory(), startDate, endDate)
        songs = {}

        for track in tracks:
            key = track["id"]
            timePlayed = track["timePlayed"]
            if key not in songs:
                songs[key] = {
                    "plays": 0,
                    "totalTimeListened": 0,
                    "song": {},
                }
                songs[key]["song"].update(track)
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

        return sorted(
            normalized,
            key=lambda item: (-item["plays"], -item["totalTimeListened"], item["song"].get("name", ""))
        )

    def getTopArtists(self, startDate: datetime.datetime = None, endDate: datetime.datetime = None) -> list:
        """Return artists sorted by total plays with aggregated data and listen totals."""
        tracks = self.filterTracksByInterval(self.loadHistory(), startDate, endDate)
        artistsStats = {}

        for track in tracks:
            artists = track.get("artists", [])
            timePlayed = track.get("timePlayed", 0)
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
                artistsStats[artistName]["uniqueSongs"].add(track.get("id"))

        normalized = []
        for v in artistsStats.values():
            normalized.append({
                "plays": v["plays"],
                "totalTimeListened": v["totalTimeListened"],
                "artist": v["artist"],
                "uniqueSongCount": len(v["uniqueSongs"]),
            })

        return sorted(
            normalized,
            key=lambda item: (-item["plays"], -item["totalTimeListened"], item["artist"])
        )
        
    def _addToDatabaseFromListener(self, data):
        if not data:
            return
        for item in data:
            track = item.get("track")
            timestamp = item.get("played_at")
            msPlayed = item.get("ms_played", 0)
            if track and timestamp:
                self.addToHistoryFromTrackData(timestamp, track, msPlayed)

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

