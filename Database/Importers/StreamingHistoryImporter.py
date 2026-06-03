import SpotipyFree
import datetime

try:
    from Database.Formatters.spotifyClient import Client
    from Database.utils import convertToDatetime
except ModuleNotFoundError:
    from Formatters.spotifyClient import Client
    from utils import convertToDatetime


class Importer:
    def __init__(self):
        self.sp = SpotipyFree.Spotify()

    def _searchForSong(self, name, artist):
        query = f"track:{name} artist:{artist}"
        return self.sp.search(query, type="track", limit=1)["tracks"]["items"][0]

    def importHistory(self, history):
        if len(history) == 0:
            return []
        if "msPlayed" in history[0]:   #< Acount export
            return self.importAcountHistory(history)
        elif "ts" in history[0]:       #< Extended history export
            return self.importExtendedHistory(history)
        return []

    def importAcountHistory(self, history):
        known = {}
        for item in history:
            try:
                endTimestamp = datetime.datetime.strptime(item["endTime"], "%Y-%m-%d %H:%M")
                endTimestamp = int(endTimestamp.timestamp())
                msPlayed = item["msPlayed"]

                startTimestamp = endTimestamp-msPlayed//1000
                name=item["trackName"]
                artist=item["artistName"]
                id = name+artist
                if id in known:
                    meta = known[id]
                else:
                    track = self._searchForSong(name=name, artist=artist)
                    meta = Client.formatTrack(startTimestamp, track, msPlayed=msPlayed)
                    known[id] = meta

                yield meta
            except Exception as e:
                print(f"Error processing item: {e}")
                continue

    def importExtendedHistory(self, history):
        known = {}
        for item in history:
            try:
                if not item.get("master_metadata_track_name"):
                    continue

                ts = item["ts"]
                dt = convertToDatetime(ts)
                endTimestamp = int(dt.timestamp())
                msPlayed = item.get("ms_played", 0)
                startTimestamp = endTimestamp - (msPlayed // 1000)

                trackName = item["master_metadata_track_name"]
                artistName = item["master_metadata_album_artist_name"]

                id = trackName+artistName
                if id in known:
                    meta = known[id]
                else:
                    track = self._searchForSong(name=trackName, artist=artistName)
                    meta = Client.formatTrack(startTimestamp, track, msPlayed=msPlayed)
                    known[id] = meta

                yield meta
            except Exception as e:
                print(f"Error processing item: {e}")
                continue