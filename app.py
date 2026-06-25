import os
import json
import threading
import requests
from pathlib import Path
import time
from datetime import timedelta

from flask import Flask, render_template, redirect, request, url_for, jsonify, send_from_directory

from Database.database import Database
from Database.Migrators.migrate import migrateIfNeeded
from Database.utils import msToString, convertToDatetime, formatDuration, dateToString, versionTuple, now, startOfDay, parseDateString
from SpotipyFree import saveSession, parseCookieString

class SpotifyDashboardApp:
    def __init__(self):
        migrateIfNeeded()
        self.app = Flask(__name__)
        self.baseDir = Path(__file__).resolve().parent
        self.username = "Tzur"
        self.cookiesFile = self.baseDir / "secrets" / "cookies.json"
        self.database = Database(user=self.username)
        self.database.startAutoImporter()
        self.database.resetProgress()
        try:
            self.currentVersion = (self.baseDir / "Database" / "VERSION").read_text(encoding="utf-8").strip()  #< only needs to be checked once because app cant update without restart
        except Exception:
            self.currentVersion = "0.0.0"
        self.latestVersion = None
        self._version_lock = threading.Lock()

        self.registerRoutes()

        # Initialize background listener if cookies exist
        if self.cookiesFile.exists():
            self.startListenerIfNeeded()

        self.startVersionCheck_thread()

    def startListenerIfNeeded(self):
        if self.database.listener is None:
            self.database.startListener(str(self.cookiesFile))
            print("Started listener thread.")
            time.sleep(2)  # Give listener time to initialize

    def startVersionCheck_thread(self):
        thread = threading.Thread(target=self._versionCheckLoop, daemon=True)
        thread.start()

    def _versionCheckLoop(self):
        # Check version from GitHub at startup and then every hour.
        url = "https://raw.githubusercontent.com/TzurSoffer/SpotifyStatsTracker/main/Database/VERSION"
        while True:
            try:
                resp = requests.get(url, timeout=6)
                if resp.status_code == 200:
                    remoteVersion = resp.text.strip()
                    # store remoteVersion if it's newer than current
                    try:
                        with self._version_lock:
                            if versionTuple(remoteVersion) > versionTuple(self.currentVersion):
                                self.latestVersion = remoteVersion
                            else:
                                self.latestVersion = None
                    except:
                        pass
            except Exception:
                pass

            time.sleep(60 * 60)

    def _getPercentPlayedText(self, item, sortBy, totalPlays, totalMs):
        if sortBy == "plays":
            percent = round((item.get("plays", 0) / totalPlays * 100), 1) if totalPlays else 0
            return f"{percent}% of all plays"
        elif sortBy == "totalTimeListened":
            percent =  round((item.get("totalTimeListened", 0) / totalMs * 100), 1) if totalMs else 0
            return f"{percent}% of all time played"
        else:
            return ""

    def _embedSongTextElements(self, song) -> dict:
        if "playedAt" in song:   #< some tracks just dont have it (top tracks)
            playedAt = convertToDatetime(song["playedAt"])
            song["playedAtText"] = playedAt.strftime("%Y-%m-%d %H:%M")
            song["timePlayedText"] = msToString(song["timePlayed"])

        artistsText = ", ".join(a.get("name", "") for a in song["artists"])
        releaseDateText = dateToString(song["album"]["releaseDate"])
        song["releaseDateText"] = releaseDateText
        song["artistsText"] = artistsText
        song["durationText"] = formatDuration(song["duration"])
        song["album"]["releaseDateText"] = releaseDateText
        return song

    def _embedTopSongTextElements(self, song, sortBy=None, totalPlays=0, totalMs=0) -> dict:
        song["totalTimeListenedText"] = msToString(song.get("totalTimeListened", 0))
        song["firstListenedText"] = convertToDatetime(song.get("firstListenedAt", 0)).strftime("%b %d, %Y")
        song["sortPercentText"] = self._getPercentPlayedText(song, sortBy, totalPlays, totalMs)
        return song

    def _embedArtistTextElement(self, artist, sortBy=None, totalPlays=0, totalMs=0) -> dict:
        artist["totalTimeListenedText"] = msToString(artist.get("totalTimeListened", 0))
        artist["firstListenedText"] = convertToDatetime(artist.get("firstListenedAt", 0)).strftime("%b %d, %Y")
        artist["sortPercentText"] = self._getPercentPlayedText(artist, sortBy, totalPlays, totalMs)
        return artist

    def _embedSongsTextElements(self, songs) -> list[dict]:
        return [self._embedSongTextElements(song) for song in songs]

    def _embedTopSongsTextElements(self, songs, sortBy=None, totalPlays=0, totalMs=0) -> list[dict]:
        return [self._embedTopSongTextElements(song, sortBy, totalPlays, totalMs) for song in songs]

    def _embedArtistsTextElements(self, songs, sortBy=None, totalPlays=0, totalMs=0) -> list[dict]:
        return [self._embedArtistTextElement(song, sortBy, totalPlays, totalMs) for song in songs]

    def _getNeighboringUrls(self, name, page, totalPages):
        prevUrl = url_for(name, page=page - 1) if page > 1 else None
        nextUrl = url_for(name, page=page + 1) if page < totalPages else None
        return prevUrl, nextUrl
    
    def _getTotal(self, arr, key):
        return sum(i.get(key, 0) for i in arr)

    def _getListeningTotals(self, entries, startDate, endDate):
        totalSongsPlayed = 0
        totalListenMs = 0

        if startDate is None or endDate is None:
            return totalSongsPlayed, totalListenMs

        for entry in entries:
            playedAt = entry.get("playedAt")
            if playedAt is None:
                continue

            playedAtDate = convertToDatetime(playedAt)

            # Half-open interval: [startDate, endDate)
            if playedAtDate < startDate or playedAtDate >= endDate:
                continue

            totalSongsPlayed += 1
            totalListenMs += entry.get("timePlayed", 0)

        return totalSongsPlayed, totalListenMs

    def _getChangeText(self, currentValue, previousValue):
        if previousValue is None or previousValue == 0:
            if currentValue == 0:
                return None, ""
            return f"New this period", "change-positive"

        change = ((currentValue - previousValue) / previousValue) * 100
        formatted = f"{abs(round(change, 1))}% {'better' if change > 0 else 'worse'} than the previous period"
        cssClass = "change-positive" if change > 0 else "change-negative"
        return formatted, cssClass

    def getLatestHistory(self, limit=None):
        return self.database.getEntriesFromNew(limit)

    def getPage(self, items, page, pageSize=50):
        """ Gets items in page as well as other data including total pages and start index """
        page = max(1, page)
        total = len(items)
        totalPages = max(1, (total + pageSize - 1) // pageSize)
        start = (page - 1) * pageSize
        end = start + pageSize
        return (items[start:end], totalPages, start)

    def _getDateRange(self, interval: str = None, customStart: str = None, customEnd: str = None):
            """Get start and end dates based on interval or custom dates.

            Returns a half-open local interval [startDate, endDate).
            """
            nowLocal = now()
            startDate = None

            futureBuffer = timedelta(days=1) 

            endDate = nowLocal + futureBuffer   #< bypass any timezone issues

            if customStart and customEnd:
                try:
                    startLocal = parseDateString(customStart)
                    endLocal = parseDateString(customEnd)
                    if startLocal is None or endLocal is None:
                        raise ValueError("Invalid custom date")

                    startDate = startLocal
                    endDate = endLocal + timedelta(days=1)
                except ValueError:
                    pass

            if not startDate:
                if interval == "day":
                    startDate = nowLocal - timedelta(days=1)

                elif interval == "week":
                    startDate = nowLocal - timedelta(weeks=1)

                elif interval == "month":
                    startDate = nowLocal - timedelta(days=30)

                elif interval == "year":
                    startDate = nowLocal - timedelta(days=365)

                elif interval == "5years":
                    startDate = nowLocal - timedelta(days=365*5)
                else:
                    return None, None    # Default: all

            return startDate, endDate

    def _getPreviousDateRange(self, startDate, endDate):
        if not startDate or not endDate:
            return None, None

        duration = endDate - startDate
        previousEnd = startDate
        previousStart = startDate - duration
        return previousStart, previousEnd

    def _getIntervalLabel(self, interval: str = None, customStart: str = None, customEnd: str = None):
        labels = {
            "day": "Last Day",
            "week": "Last Week",
            "month": "Last Month",
            "year": "Last Year",
            "5years": "Last 5 Years",
        }

        if interval == "custom" and customStart and customEnd:
            return f"Custom range: {customStart} to {customEnd}"

        return labels.get(interval or "day", "Last Day")

    def ensureLoggedIn(self):
        if self.cookiesFile.exists():
            try:
                json.loads(self.cookiesFile.read_text(encoding="utf-8"))
                self.startListenerIfNeeded()
                if self.database.isListenerLoggedIn():
                    return True
            except Exception as e:
                print(e)
        return False

    def registerRoutes(self):
        def _is_version_newer(remote: str, local: str) -> bool:
            try:
                return versionTuple(remote) > versionTuple(local)
            except Exception:
                return False

        @self.app.route('/img/<username>/tracks/<filename>')
        def serveTrackImage(username, filename):
            imageDir = os.path.join(self.baseDir, "Database", "Users", username, "img", "tracks")
            return send_from_directory(imageDir, filename)

        @self.app.route('/img/<username>/artists/<filename>')
        def serveArtistImage(username, filename):
            imageDir = os.path.join(self.baseDir, "Database", "Users", username, "img", "artists")
            return send_from_directory(imageDir, filename)

        @self.app.route("/import-history", methods=["POST"])
        def importHistory():
            if self.database.readProgress().get("status") == "running":
                return redirect(url_for("importPage"))

            upload = request.files.get("history_file")
            if upload is None or upload.filename == "":
                return redirect(url_for("importPage"))

            thread = threading.Thread(target=self.database.importHistory, args=(upload.read().decode("utf-8"),), daemon=True)
            thread.start()
            time.sleep(1)  # Give thread time to start and update progress
            return redirect(url_for("importPage"))

        @self.app.route("/import", methods=["GET"])
        def importPage():
            return render_template("import.html", importProgress=self.database.readProgress())

        @self.app.route("/login", methods=["GET", "POST"])
        def login():
            step = request.form.get("step", "1")

            if step == "1":
                if request.method == "GET":
                    return render_template("login.html", step=1)

                email = request.form.get("email", "").strip()
                if not email:
                    return render_template("login.html", step=1, error="Email required.")

                return render_template("login.html", step=2, email=email)

            if step == "2":
                email = request.form.get("email", "")
                cookies = request.form.get("cookies", "")

                if not cookies:
                    return render_template("login.html", step=2, email=email, error="Cookies required.")

                # with open(self.cookiesFile, "w", encoding="utf-8") as f:
                #     json.dump({"email": email, "cookies": cookies}, f, indent=2)
                saveSession(parseCookieString(cookies), email, self.cookiesFile)

                # FIX: updated 'dashboard' endpoint target
                return redirect(url_for("dashboard"))

        @self.app.route("/import-progress", methods=["GET"])
        def importProgress():
            return jsonify(self.database.readProgress())

        @self.app.route("/version_status", methods=["GET"])
        def version_status():
            # Return the current and latest versions (latest is null if not newer)
            with self._version_lock:
                latest = self.latestVersion
            if latest and _is_version_newer(latest, self.currentVersion):
                return jsonify({"current": self.currentVersion, "latest": latest})
            else:
                return jsonify({"current": self.currentVersion, "latest": None})

        @self.app.route("/", methods=["GET"])
        def dashboard():
            if not self.ensureLoggedIn():
                return redirect(url_for("login", next=request.path))

            page = int(request.args.get("page", 1) or 1)
            customStart = request.args.get("startDate", "")
            customEnd = request.args.get("endDate", "")
            interval = request.args.get("interval", "day") or "day"
            if interval == "custom" and not (customStart and customEnd):
                interval = "day"

            intervalLabel = self._getIntervalLabel(interval, customStart, customEnd)
            currentStart, currentEnd = self._getDateRange(interval, customStart, customEnd)
            if currentStart is None or currentEnd is None:
                interval = "day"
                intervalLabel = self._getIntervalLabel(interval)
                currentStart, currentEnd = self._getDateRange(interval)

            previousStart, previousEnd = self._getPreviousDateRange(currentStart, currentEnd)

            pageSize = 50
            total = self.database.getEntriesCount()
            startIndex = (page - 1) * pageSize
            tracks = self.database.getEntriesFromNew(count=pageSize, startIndex=startIndex)
            tracks = self._embedSongsTextElements(tracks)
            historyEntries = self.getLatestHistory() or []

            totalSongsPlayed, totalDurationMs = self._getListeningTotals(historyEntries, currentStart, currentEnd)
            previousSongsPlayed, previousDurationMs = self._getListeningTotals(historyEntries, previousStart, previousEnd)

            totalPages = max(1, (total + pageSize - 1) // pageSize)

            currentTopSongs = self.database.getTopSongs(startDate=currentStart, endDate=currentEnd, by="plays") or []
            currentTopArtists = self.database.getTopArtists(startDate=currentStart, endDate=currentEnd, by="totalTimeListened") or []

            totalDurationText = msToString(totalDurationMs)
            uniqueArtists = len(currentTopArtists)

            currentTopSong = self._embedTopSongTextElements(currentTopSongs[0], sortBy="plays", totalPlays=totalSongsPlayed, totalMs=totalDurationMs) if currentTopSongs else None
            currentTopArtist = self._embedArtistTextElement(currentTopArtists[0], sortBy="totalTimeListened", totalPlays=totalSongsPlayed, totalMs=totalDurationMs) if currentTopArtists else None

            totalSongsChangeText, totalSongsChangeClass = self._getChangeText(
                totalSongsPlayed,
                previousSongsPlayed,
            )

            totalListenChangeText, totalListenChangeClass = self._getChangeText(
                totalDurationMs,
                previousDurationMs,
            )

            def _dashboardUrl(targetPage):
                params = {"page": targetPage, "interval": interval}
                if interval == "custom" and customStart and customEnd:
                    params["startDate"] = customStart
                    params["endDate"] = customEnd
                return url_for("dashboard", **params)

            prevUrl = _dashboardUrl(page - 1) if page > 1 else None
            nextUrl = _dashboardUrl(page + 1) if page < totalPages else None

            return render_template(
                "tracks.html",
                tracks=tracks,
                total=total,
                uniqueArtists=uniqueArtists,
                totalDuration=totalDurationText,
                totalSongsPlayed=totalSongsPlayed,
                totalListenTime=totalDurationText,
                totalSongsChangeText=totalSongsChangeText,
                totalSongsChangeClass=totalSongsChangeClass,
                totalListenChangeText=totalListenChangeText,
                totalListenChangeClass=totalListenChangeClass,
                currentTopSong=currentTopSong,
                currentTopArtist=currentTopArtist,
                username=self.username,
                page=page,
                totalPages=totalPages,
                prevUrl=prevUrl,
                nextUrl=nextUrl,
                startIndex=startIndex,
                section="dashboard",
                interval=interval,
                customStart=customStart,
                customEnd=customEnd,
                intervalLabel=intervalLabel,
            )

        @self.app.route("/top-songs", methods=["GET"])
        def topSongsPage():
            if not self.ensureLoggedIn():
                return redirect(url_for("login", next=request.path))

            page = int(request.args.get("page", 1) or 1)
            sortBy = request.args.get("sortBy", "totalTimeListened")
            interval = request.args.get("interval", "")
            customStart = request.args.get("startDate", "")
            customEnd = request.args.get("endDate", "")
            
            startDate, endDate = self._getDateRange(interval, customStart, customEnd)
            rawTopSongs = self.database.getTopSongs(startDate=startDate, endDate=endDate, by=sortBy) or []
            tracks, totalPages, startIndex = self.getPage(rawTopSongs, page)
            totalPlays = self._getTotal(rawTopSongs, "plays")
            totalMs = self._getTotal(rawTopSongs, "totalTimeListened")
            prevUrl, nextUrl = self._getNeighboringUrls("topSongsPage", page, totalPages)

            tracks = self._embedSongsTextElements(tracks)
            tracks = self._embedTopSongsTextElements(tracks, sortBy=sortBy, totalPlays=totalPlays, totalMs=totalMs)

            return render_template(
                "top_songs.html",
                tracks=tracks,
                username=self.username,
                totalPlays=totalPlays,
                totalTime=msToString(totalMs),
                page=page,
                totalPages=totalPages,
                prevUrl=prevUrl,
                nextUrl=nextUrl,
                startIndex=startIndex,
                section="top_songs",
                sortBy=sortBy,
                interval=interval,
                customStart=customStart,
                customEnd=customEnd,
            )

        @self.app.route("/top-artists", methods=["GET"])
        def topArtistsPage():
            if not self.ensureLoggedIn():
                return redirect(url_for("login", next=request.path))

            page = int(request.args.get("page", 1) or 1)
            sortBy = request.args.get("sortBy", "totalTimeListened")
            interval = request.args.get("interval", "")
            customStart = request.args.get("startDate", "")
            customEnd = request.args.get("endDate", "")
            
            startDate, endDate = self._getDateRange(interval, customStart, customEnd)
            rawTopArtists = self.database.getTopArtists(startDate=startDate, endDate=endDate, by=sortBy) or []
            artists, totalPages, startIndex = self.getPage(rawTopArtists, page)
            totalPlays = self._getTotal(rawTopArtists, "plays")
            totalUnique = self._getTotal(rawTopArtists, "uniqueSongCount")
            totalMs = self._getTotal(rawTopArtists, "totalTimeListened")

            artists = self._embedArtistsTextElements(artists, sortBy=sortBy, totalPlays=totalPlays, totalMs=totalMs)
            prevUrl, nextUrl = self._getNeighboringUrls("topArtistsPage", page, totalPages)

            return render_template(
                "top_artists.html",
                tracks=artists,
                username=self.username,
                totalPlays=totalPlays,
                totalUnique=totalUnique,
                totalTime=msToString(totalMs),
                page=page,
                totalPages=totalPages,
                prevUrl=prevUrl,
                nextUrl=nextUrl,
                startIndex=startIndex,
                section="top_artists",
                sortBy=sortBy,
                interval=interval,
                customStart=customStart,
                customEnd=customEnd,
            )

    def run(self):
        self.app.run(host="0.0.0.0", debug=True, port=5000)#, threaded=False, use_reloader=False)

if __name__ == "__main__":
    ## $env:IMPORT_KEYWORD="Weekly"
    ## $env:TZ="America/Los_Angeles"

    dashboardApp = SpotifyDashboardApp()
    dashboardApp.run()