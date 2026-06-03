import SpotipyFree
import datetime

try:
    from Database.Formatters.spotifyClient import Client
    from Database.utils import convertToDatetime
except ModuleNotFoundError:
    from Formatters.spotifyClient import Client
    from utils import convertToDatetime


class Importer:
    def __init__(self, user="Tzur"):
        self.sp = SpotipyFree.Spotify()

    def _searchForSong(self, name, artist):
        query = f"track:{name} artist:{artist}"
        return self.sp.search(query, type="track", limit=1)["tracks"]["items"][0]

    def importHistory(self, history, known=[]):
        if len(history) == 0:
            return []
        if "msPlayed" in history[0]:   #< Acount export
            return self.importAcountHistory(history, known=known)
        elif "ts" in history[0]:       #< Extended history export
            return self.importExtendedHistory(history, known=known)
        return []

    def buildKnownIndex(self, knownTrack):
        index = {}
        for item in knownTrack:
            if len(item["artists"]) == 0:
                continue
            index[item["name"]+item["artists"][0]["name"]] = item
        return index
        
    def _import(self, dataFunction, history, known=[]):
        known = self.buildKnownIndex(known)
        for item in history:
            try:
                name, artist, startTimestamp, timePlayed = dataFunction(item)

                id = name+artist
                if id in known:
                    meta = known[id]
                else:
                    meta = self._searchForSong(name=name, artist=artist)
                meta = Client.formatTrack(startTimestamp, meta, msPlayed=timePlayed)  #< Update with correct played at info
                if id not in known:
                    known[id] = meta

                yield meta
            except Exception as e:
                print(f"Error processing item: {e}")
                continue

    def importAcountHistory(self, history, known=[]):
        def dataFunction(item):
            endTimestamp = datetime.datetime.strptime(item["endTime"], "%Y-%m-%d %H:%M")
            endTimestamp = int(endTimestamp.timestamp())
            timePlayed = item["msPlayed"]

            startTimestamp = endTimestamp-timePlayed//1000
            name=item["trackName"]
            artist=item["artistName"]
            return name, artist, startTimestamp, timePlayed
        
        yield from self._import(dataFunction, history, known)

    def importExtendedHistory(self, history, known=[]):
        def dataFunction(item):
            ts = item["ts"]
            dt = convertToDatetime(ts)
            endTimestamp = int(dt.timestamp())
            timePlayed = item.get("ms_played", 0)
            startTimestamp = endTimestamp - (timePlayed // 1000)

            name = item["master_metadata_track_name"]
            artist = item["master_metadata_album_artist_name"]
            return name, artist, startTimestamp, timePlayed
        
        yield from self._import(dataFunction, history, known)
