import csv
import json
import datetime
import SpotipyFree

try:
    from Database.Formatters.spotifyClient import Client
    from Database.utils import timeToInt, parseError
except ModuleNotFoundError:
    from Formatters.spotifyClient import Client
    from utils import timeToInt, parseError


class Importer:
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

    def importHistory(self, history, known=[]):
        history, type = self._convertToList(history)
        if len(history) == 0:
            return []
        if type == "spotifyAcountExport":
            return self.importAcountHistory(history, known=known)
        if type == "spotifyExtendedExport":
                return self.importExtendedHistory(history, known=known)
        if type == "musicoletPremium":
            return self.importMusicoletCSVExport(history, known=known)
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
                    meta = Client.embedPlayInfo(known[id], startTimestamp, timePlayed)

                else:
                    meta = self._searchForSong(name=name, artist=artist)
                    meta = Client.formatTrack(meta, startTimestamp, msPlayed=timePlayed)  #< Update with correct played at info:
                    known[id] = meta

                yield meta
            except Exception as e:
                print(f"Error processing item: {parseError(e)}")
                continue

    def importAcountHistory(self, history, known=[]):
        def dataFunction(item):
            endTimestamp = timeToInt(item["endTime"])
            timePlayed = item["msPlayed"]

            startTimestamp = endTimestamp-timePlayed//1000
            name=item["trackName"]
            artist=item["artistName"]
            return name, artist, startTimestamp, timePlayed
        
        yield from self._import(dataFunction, history, known)

    def importExtendedHistory(self, history, known=[]):
        def dataFunction(item):
            ts = item["ts"]
            startTimestamp = timeToInt(ts)
            timePlayed = item.get("ms_played", 0)

            name = item["master_metadata_track_name"]
            artist = item["master_metadata_album_artist_name"]
            return name, artist, startTimestamp, timePlayed
        
        yield from self._import(dataFunction, history, known)

    def importMusicoletCSVExport(self, rows, known=[]):
        def expand(rows):
            ### Data formatted in: FILE_PATH,TITLE,ARTIST,ALBUM,ALBUM_ARTIST,COMPOSER,GENRE,YEAR,DURATION_MS,PLAY_COUNT
            NAME = 1
            ARTISTS = 2
            DURATION_MS = 8
            PLAYCOUNT = 9

            currentTime = datetime.datetime.now()
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
            return item

        yield from self._import(dataFunction, expand(rows), known)