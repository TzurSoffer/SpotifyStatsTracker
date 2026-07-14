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
from Database.utils import msToString, convertToDatetime, formatDuration, dateToString, versionTuple, now, parseDateString
from SpotipyFree import saveSession, parseCookieString

class SpotifyDashboardApp:
    def __init__(self):
        migrateIfNeeded()
        self.app = Flask(__name__)
        self.baseDir = Path(__file__).resolve().parent
        self.isLoggedIn = False
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
        self.startVersionCheck_thread()
        self.checkLogin_thread()

        self.registerRoutes()

    def startListenerIfNeeded(self):
        if self.database.listener is None:
            self.database.startListener(str(self.cookiesFile))
            print("Started listener thread.")
            time.sleep(2)  # Give listener time to initialize
    
    def checkLogin_thread(self):
        self._ensureLogin()
        thread = threading.Thread(target=self._checkLoginLoop, daemon=True)
        thread.start()
    
    def _ensureLogin(self):
        if self.cookiesFile.exists():
            try:
                json.loads(self.cookiesFile.read_text(encoding="utf-8"))
                self.startListenerIfNeeded()
                if self.database.isListenerLoggedIn():
                    self.isLoggedIn = True
            except Exception as e:
                print(e)
                self.isLoggedIn = False
        else:
            self.isLoggedIn = False
    
    def _checkLoginLoop(self):
        while True:
            self._ensureLogin()
            time.sleep(60 * 5)  # Check every 5 minutes

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

        song["contextName"] = None
        if "playedFrom" in song:
            song["contextName"] = self.database.playlistName(song["playedFrom"])

        artists = song.get("artists") or []
        if not isinstance(artists, list):
            artists = []
        artistsText = ", ".join(a.get("name", "") for a in artists if isinstance(a, dict))

        album = song.get("album") or {}
        if not isinstance(album, dict):
            album = {"name": str(album)}
        song["album"] = album

        releaseDate = album.get("releaseDate")
        releaseDateText = dateToString(releaseDate) if releaseDate else ""
        song["releaseDateText"] = releaseDateText
        song["artistsText"] = artistsText
        song["durationText"] = formatDuration(song.get("duration", 0))
        album["releaseDateText"] = releaseDateText
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

    def _embedActivityPeriodTextElements(self, activityPeriods, every: int = 24) -> list[dict]:
        embedded = []
        for periodStart, periodEnd, totalTimeMs, playCount in activityPeriods:
            startDate = convertToDatetime(periodStart)
            endDate = convertToDatetime(periodEnd)
            if every <= 1:
                dateText = startDate.strftime("%H:%M")
                tooltipDate = f"{startDate.strftime('%A, %b %d, %Y %H:%M')} - {endDate.strftime('%H:%M')}"
            elif every < 24 * 7:
                dateText = startDate.strftime("%b %d")
                tooltipDate = f"{startDate.strftime('%A, %b %d, %Y')} - {endDate.strftime('%A, %b %d, %Y')}"
            elif every < 24 * 30:
                dateText = startDate.strftime("Week of %b %d")
                tooltipDate = f"{startDate.strftime('%A, %b %d, %Y')} - {endDate.strftime('%A, %b %d, %Y')}"
            elif every < 24 * 365:
                dateText = startDate.strftime("%b %Y")
                tooltipDate = f"{startDate.strftime('%B %Y')} - {endDate.strftime('%B %Y')}"
            else:
                dateText = startDate.strftime("%Y")
                tooltipDate = f"{startDate.strftime('%B %Y')} - {endDate.strftime('%B %Y')}"

            embedded.append({
                "date": dateToString(startDate),
                "dateText": dateText,
                "tooltipDate": tooltipDate,
                "playCount": playCount,
                "totalTimeMs": totalTimeMs,
                "totalTimeText": msToString(totalTimeMs),
            })
        return embedded

    def _getActivityBarGrouping(self, interval: str, startDate, endDate) -> tuple[int, str]:
        if interval == "day":
            return 1, "Hourly activity"
        if interval == "week":
            return 24, "Daily activity"
        if interval == "month":
            return 24 * 7, "Weekly activity"
        if interval == "year":
            return 24 * 30, "Monthly activity"
        if interval in ("5years", "all time"):
            return 24 * 365, "Yearly activity"

        if startDate and endDate:
            spanDays = max(1, int((endDate - startDate).total_seconds() // 86400))
            if spanDays <= 1:
                return 1, "Hourly activity"
            if spanDays <= 7:
                return 24, "Daily activity"
            if spanDays <= 31:
                return 24 * 7, "Weekly activity"
            if spanDays <= 365:
                return 24 * 30, "Monthly activity"

        return 24, "Daily activity"

    def _buildPageUrl(self, endpoint, page, **queryArgs):
        cleanArgs = {key: value for key, value in queryArgs.items() if value not in (None, "")}
        cleanArgs["page"] = page
        return url_for(endpoint, **cleanArgs)

    def _getNeighboringUrls(self, name, page, totalPages, **queryArgs):
        prevUrl = self._buildPageUrl(name, page - 1, **queryArgs) if page > 1 else None
        nextUrl = self._buildPageUrl(name, page + 1, **queryArgs) if page < totalPages else None
        return prevUrl, nextUrl

    def _normalizeSearchQuery(self, query: str | None) -> str:
        return (query or "").strip().lower()

    def _getSearchableText(self, item: dict) -> str:
        parts = [
            item.get("name", ""),
            item.get("artistsText", ""),
            item.get("artist", ""),
            item.get("contextName", ""),
            item.get("album", {}).get("name", "") if type(item.get("album")) == dict else "",
        ]

        artists = item.get("artists", [])
        for artist in artists:
            if type(artist) == dict:
                parts.append(artist.get("name", ""))
            else:
                parts.append(str(artist))

        playedFrom = item.get("playedFrom")
        if playedFrom:
            try:
                parts.append(self.database.playlistName(playedFrom))
            except:
                pass

        return " ".join(str(part) for part in parts if part)

    def _filterBySearch(self, items, query):
        normalizedQuery = self._normalizeSearchQuery(query)
        if not normalizedQuery:
            return items

        filtered = []
        for item in items:
            searchableText = self._getSearchableText(item).lower()
            if normalizedQuery in searchableText:
                filtered.append(item)
        return filtered

    def _getTotal(self, arr, key):
        return sum(i.get(key, 0) for i in arr)

    def _embedIndices(self, items):
        for index, item in enumerate(items, start=1):
            item["absoluteIndex"] = index
        return items

    def _getChangeText(self, currentValue, previousValue):
        if previousValue is None or previousValue == 0:
            if currentValue == 0:
                return None, ""
            return f"New this period", "change-positive"

        change = ((currentValue - previousValue) / previousValue) * 100
        formatted = f"{abs(round(change, 1))}% {'more' if change > 0 else 'less'} than the previous period"
        cssClass = "change-positive" if change > 0 else "change-negative"
        return formatted, cssClass

    def _getSpotifyEmbedUrl(self, entityType: str, entityData) -> str | None:
        if not entityData:
            return None

        if entityType == "playlist":
            if isinstance(entityData, str) and entityData.startswith("http"):
                return entityData.replace("https://open.spotify.com/playlist/", "https://open.spotify.com/embed/playlist/")
            if isinstance(entityData, str) and entityData.startswith("playlist:"):
                playlistId = entityData.split(":", 1)[-1]
                return f"https://open.spotify.com/embed/playlist/{playlistId}"
            return None

        if isinstance(entityData, str) and entityData.startswith("http"):
            identifier = entityData.rstrip("/").split("/")[-1]
            return f"https://open.spotify.com/embed/{entityType}/{identifier}"

        if isinstance(entityData, str):
            return f"https://open.spotify.com/embed/{entityType}/{entityData}"

        return None

    def _buildSongDetailContext(self, songId: str):
        tracks = self.database._loadTracks() or {}
        track = tracks.get(songId)
        if not track:
            return None

        entries = [entry for entry in (self.database._loadEntries() or []) if entry.get("id") == songId]
        historyItems = []
        for entry in entries:
            historyItem = dict(track)
            historyItem["playedAt"] = entry.get("playedAt")
            historyItem["timePlayed"] = entry.get("timePlayed", 0)
            historyItem["playedFrom"] = entry.get("playedFrom")
            historyItems.append(self._embedSongTextElements(historyItem))

        historyItems.sort(key=lambda item: item.get("playedAt", 0), reverse=True)

        totalTimeMs = sum(item.get("timePlayed", 0) for item in historyItems)
        plays = len(historyItems)
        firstPlayedAt = min((item.get("playedAt", 0) for item in historyItems), default=0)
        lastPlayedAt = max((item.get("playedAt", 0) for item in historyItems), default=0)

        entity = self._embedSongTextElements(dict(track))
        entity["spotifyEmbedUrl"] = self._getSpotifyEmbedUrl("track", track.get("url"))
        entity["playCount"] = plays
        entity["totalTimeMs"] = totalTimeMs
        entity["firstListenedText"] = convertToDatetime(firstPlayedAt).strftime("%b %d, %Y") if firstPlayedAt else "Never"
        entity["lastListenedText"] = convertToDatetime(lastPlayedAt).strftime("%b %d, %Y") if lastPlayedAt else "Never"

        return {
            "entityType": "song",
            "entity": entity,
            "stats": {
                "plays": plays,
                "totalTimeMs": totalTimeMs,
                "totalTimeText": msToString(totalTimeMs),
                "firstListenedText": entity["firstListenedText"],
                "lastListenedText": entity["lastListenedText"],
            },
            "historyItems": historyItems[:8],
            "relatedTracks": historyItems[:8],
            "pageTitle": f"{entity['name']} | Spotify Tracker",
        }

    def _buildArtistDetailContext(self, artistId: str):
        tracks = self.database._loadTracks() or {}
        entries = self.database._loadEntries() or []
        matchingEntries = []
        relatedTracks = []
        artistEntity = None

        for entry in entries:
            track = tracks.get(entry.get("id"))
            if not track:
                continue
            artist = next((item for item in track.get("artists", []) if str(item.get("id", "")) == str(artistId)), None)
            if not artist:
                continue
            if artistEntity is None:
                artistEntity = dict(artist)
                artistEntity["imageId"] = artist.get("imageId") or track.get("imageId")

            historyItem = dict(track)
            historyItem["playedAt"] = entry.get("playedAt")
            historyItem["timePlayed"] = entry.get("timePlayed", 0)
            historyItem["playedFrom"] = entry.get("playedFrom")
            historyItem["artistEntity"] = artist
            embeddedHistoryItem = self._embedSongTextElements(historyItem)
            matchingEntries.append(embeddedHistoryItem)

            if not any(str(item.get("id", "")) == str(track.get("id")) for item in relatedTracks):
                relatedTracks.append(embeddedHistoryItem)

        if not artistEntity:
            return None

        matchingEntries.sort(key=lambda item: item.get("playedAt", 0), reverse=True)
        relatedTracks.sort(key=lambda item: item.get("playedAt", 0), reverse=True)
        totalTimeMs = sum(item.get("timePlayed", 0) for item in matchingEntries)
        plays = len(matchingEntries)
        firstPlayedAt = min((item.get("playedAt", 0) for item in matchingEntries), default=0)
        lastPlayedAt = max((item.get("playedAt", 0) for item in matchingEntries), default=0)

        artistEntity["spotifyEmbedUrl"] = self._getSpotifyEmbedUrl("artist", artistEntity.get("url"))
        artistEntity["playCount"] = plays
        artistEntity["totalTimeMs"] = totalTimeMs
        artistEntity["firstListenedText"] = convertToDatetime(firstPlayedAt).strftime("%b %d, %Y") if firstPlayedAt else "Never"
        artistEntity["lastListenedText"] = convertToDatetime(lastPlayedAt).strftime("%b %d, %Y") if lastPlayedAt else "Never"

        return {
            "entityType": "artist",
            "entity": artistEntity,
            "stats": {
                "plays": plays,
                "totalTimeMs": totalTimeMs,
                "totalTimeText": msToString(totalTimeMs),
                "uniqueSongs": len({item.get("id") for item in matchingEntries}),
                "firstListenedText": artistEntity["firstListenedText"],
                "lastListenedText": artistEntity["lastListenedText"],
            },
            "historyItems": matchingEntries[:8],
            "relatedTracks": relatedTracks[:8],
            "pageTitle": f"{artistEntity['name']} | Spotify Tracker",
        }

    def _buildPlaylistDetailContext(self, playlistId: str):
        entries = [entry for entry in (self.database._loadEntries() or []) if entry.get("playedFrom") == playlistId]
        if not entries:
            return None

        tracks = self.database._loadTracks() or {}
        relatedTracks = []
        for entry in entries:
            track = tracks.get(entry.get("id"))
            if not track:
                continue
            historyItem = dict(track)
            historyItem["playedAt"] = entry.get("playedAt")
            historyItem["timePlayed"] = entry.get("timePlayed", 0)
            historyItem["playedFrom"] = entry.get("playedFrom")
            relatedTracks.append(self._embedSongTextElements(historyItem))

        relatedTracks.sort(key=lambda item: item.get("playedAt", 0), reverse=True)
        totalTimeMs = sum(item.get("timePlayed", 0) for item in relatedTracks)
        plays = len(relatedTracks)
        firstPlayedAt = min((item.get("playedAt", 0) for item in relatedTracks), default=0)
        lastPlayedAt = max((item.get("playedAt", 0) for item in relatedTracks), default=0)

        entityName = self.database.playlistName(playlistId) or playlistId.split(":", 1)[-1]
        entity = {
            "name": entityName,
            "id": playlistId,
            "url": f"https://open.spotify.com/playlist/{playlistId.split(':', 1)[-1]}",
            "spotifyEmbedUrl": self._getSpotifyEmbedUrl("playlist", playlistId),
            "imageId": relatedTracks[0].get("imageId") if relatedTracks else None,
            "playCount": plays,
            "totalTimeMs": totalTimeMs,
            "firstListenedText": convertToDatetime(firstPlayedAt).strftime("%b %d, %Y") if firstPlayedAt else "Never",
            "lastListenedText": convertToDatetime(lastPlayedAt).strftime("%b %d, %Y") if lastPlayedAt else "Never",
        }

        return {
            "entityType": "playlist",
            "entity": entity,
            "stats": {
                "plays": plays,
                "totalTimeMs": totalTimeMs,
                "totalTimeText": msToString(totalTimeMs),
                "uniqueSongs": len({item.get("id") for item in relatedTracks}),
                "firstListenedText": entity["firstListenedText"],
                "lastListenedText": entity["lastListenedText"],
            },
            "relatedTracks": relatedTracks[:8],
            "pageTitle": f"{entityName} | Spotify Tracker",
        }

    def getPage(self, items, page, pageSize=50):
        """ Gets items in page as well as other data including total pages and start index """
        page = max(1, page)
        total = len(items)
        totalPages = max(1, (total + pageSize - 1) // pageSize)
        start = (page - 1) * pageSize
        end = start + pageSize
        return (items[start:end], totalPages, start)

    def _getDateRange(self, interval: str = None, customStart: str = None, customEnd: str = None, default="day"):
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
            if interval == "":
                interval = default
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
                    startDate = None
                    endDate = None

            return startDate, endDate

    def _getIntervalLabel(self, interval: str = None, customStart: str = None, customEnd: str = None):
        labels = {
            "all time": "All Time",
            "day": "Last Day",
            "week": "Last Week",
            "month": "Last Month",
            "year": "Last Year",
            "5years": "Last 5 Years",
        }

        if interval == "custom" and customStart and customEnd:
            return f"Custom range: {customStart} to {customEnd}"

        return labels.get(interval or "day", "Last Day")

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

                saveSession(parseCookieString(cookies), email, self.cookiesFile)
                self.isLoggedIn = True
                self.startListenerIfNeeded()

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
            if not self.isLoggedIn:
                return redirect(url_for("login", next=request.path))

            customStart = request.args.get("startDate", "")
            customEnd = request.args.get("endDate", "")
            interval = request.args.get("interval", "day")
            if interval == "custom" and not (customStart and customEnd):
                interval = "all time"

            intervalLabel = self._getIntervalLabel(interval, customStart, customEnd)
            startDate, endDate = self._getDateRange(interval, customStart, customEnd, default="day")
            stats = self.database.getOverallStats(startDate, endDate)

            chartEndDate = endDate or now()
            heatmapSeries = self._embedActivityPeriodTextElements(
                self.database.getIntervalHeatmap(None, None, every=24),
                every=24,
            )

            barEvery, barSeriesLabel = self._getActivityBarGrouping(interval, startDate, endDate)
            barStartDate = startDate
            barEndDate = min(chartEndDate, now()) if chartEndDate else now()
            barSeries = self._embedActivityPeriodTextElements(
                self.database.getIntervalHeatmap(barStartDate, barEndDate, every=barEvery),
                every=barEvery,
            )

            heatmapYears = self.database.getAvailableYears() or [chartEndDate.year]
            selectedHeatmapYear = chartEndDate.year
            if selectedHeatmapYear not in heatmapYears:
                selectedHeatmapYear = heatmapYears[-1]

            totalDurationText = msToString(stats["totalDurationMs"])

            currentTopSong = self._embedTopSongTextElements(stats["currentTopSongs"][0], sortBy="plays", totalPlays=stats["totalSongsPlayed"], totalMs=stats["totalDurationMs"]) if stats["currentTopSongs"] else None
            currentTopArtist = self._embedArtistTextElement(stats["currentTopArtists"][0], sortBy="totalTimeListened", totalPlays=stats["totalSongsPlayed"], totalMs=stats["totalDurationMs"]) if stats["currentTopArtists"] else None

            totalSongsChangeText, totalSongsChangeClass = self._getChangeText(stats["totalSongsPlayed"], stats["previousSongsPlayed"])
            totalListenChangeText, totalListenChangeClass = self._getChangeText(stats["totalDurationMs"], stats["previousDurationMs"])

            return render_template(
                "overview.html",
                tracks=[],
                totalSongsPlayed=stats["totalSongsPlayed"],
                totalListenTime=totalDurationText,
                totalSongsChangeText=totalSongsChangeText,
                totalSongsChangeClass=totalSongsChangeClass,
                totalListenChangeText=totalListenChangeText,
                totalListenChangeClass=totalListenChangeClass,
                currentTopSong=currentTopSong,
                currentTopArtist=currentTopArtist,
                intervalLabel=intervalLabel,
                heatmapSeries=heatmapSeries,
                heatmapYears=heatmapYears,
                selectedHeatmapYear=selectedHeatmapYear,
                barSeries=barSeries,
                barSeriesLabel=barSeriesLabel,
                username=self.username,
                page=1,
                totalPages=1,
                prevUrl=None,
                nextUrl=None,
                startIndex=0,
                section="dashboard",
                interval=interval,
                customStart=customStart,
                customEnd=customEnd,
                activeTab="overview",
            )

        @self.app.route("/history", methods=["GET"])
        def historyPage():
            if not self.isLoggedIn:
                return redirect(url_for("login", next=request.path))

            page = int(request.args.get("page", 1) or 1)
            searchQuery = request.args.get("q", "")
            customStart = request.args.get("startDate", "")
            customEnd = request.args.get("endDate", "")
            interval = request.args.get("interval", "day")
            if interval == "custom" and not (customStart and customEnd):
                interval = "all time"

            self._getDateRange(interval, customStart, customEnd, default="day")
            tracks = self.database.getEntriesFromNew()
            if searchQuery:
                self._embedIndices(tracks)
            tracks = self._filterBySearch(tracks, searchQuery)
            tracks, totalPages, startIndex = self.getPage(tracks, page)
            tracks = self._embedSongsTextElements(tracks)

            prevUrl, nextUrl = self._getNeighboringUrls(
                "historyPage",
                page,
                totalPages,
                q=searchQuery,
                interval=interval,
                startDate=customStart,
                endDate=customEnd,
            )

            return render_template(
                "history.html",
                tracks=tracks,
                totalSongsPlayed=None,
                totalListenTime=None,
                totalSongsChangeText=None,
                totalSongsChangeClass=None,
                totalListenChangeText=None,
                totalListenChangeClass=None,
                currentTopSong=None,
                currentTopArtist=None,
                intervalLabel=None,
                heatmapSeries=None,
                heatmapYears=None,
                selectedHeatmapYear=None,
                barSeries=None,
                barSeriesLabel=None,
                username=self.username,
                page=page,
                totalPages=totalPages,
                prevUrl=prevUrl,
                nextUrl=nextUrl,
                startIndex=startIndex,
                section="history",
                interval=interval,
                customStart=customStart,
                customEnd=customEnd,
                activeTab="history",
            )

        @self.app.route("/charts", methods=["GET"])
        def chartsPage():
            return redirect(url_for("dashboard", **request.args))

        @self.app.route("/top-songs", methods=["GET"])
        def topSongsPage():
            if not self.isLoggedIn:
                return redirect(url_for("login", next=request.path))

            page = int(request.args.get("page", 1) or 1)
            searchQuery = request.args.get("q", "")
            sortBy = request.args.get("sortBy", "totalTimeListened")
            interval = request.args.get("interval", "")
            customStart = request.args.get("startDate", "")
            customEnd = request.args.get("endDate", "")
            
            startDate, endDate = self._getDateRange(interval, customStart, customEnd, default="all time")
            rawTopSongs = self.database.getTopSongs(startDate=startDate, endDate=endDate, by=sortBy)
            if searchQuery:
                self._embedIndices(rawTopSongs)
            tracks = self._filterBySearch(rawTopSongs, searchQuery)
            tracks, totalPages, startIndex = self.getPage(tracks, page)
            totalPlays = self._getTotal(rawTopSongs, "plays")
            totalMs = self._getTotal(rawTopSongs, "totalTimeListened")
            prevUrl, nextUrl = self._getNeighboringUrls(
                "topSongsPage",
                page,
                totalPages,
                q=searchQuery,
                sortBy=sortBy,
                interval=interval,
                startDate=customStart,
                endDate=customEnd,
            )

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
            if not self.isLoggedIn:
                return redirect(url_for("login", next=request.path))

            page = int(request.args.get("page", 1) or 1)
            searchQuery = request.args.get("q", "")
            sortBy = request.args.get("sortBy", "totalTimeListened")
            interval = request.args.get("interval", "")
            customStart = request.args.get("startDate", "")
            customEnd = request.args.get("endDate", "")
            
            startDate, endDate = self._getDateRange(interval, customStart, customEnd, default="all time")
            rawTopArtists = self.database.getTopArtists(startDate=startDate, endDate=endDate, by=sortBy) or []
            if searchQuery:
                self._embedIndices(rawTopArtists)
            tracks = self._filterBySearch(rawTopArtists, searchQuery)
            artists, totalPages, startIndex = self.getPage(tracks, page)
            totalPlays = self._getTotal(rawTopArtists, "plays")
            totalUnique = self._getTotal(rawTopArtists, "uniqueSongCount")
            totalMs = self._getTotal(rawTopArtists, "totalTimeListened")

            artists = self._embedArtistsTextElements(artists, sortBy=sortBy, totalPlays=totalPlays, totalMs=totalMs)
            prevUrl, nextUrl = self._getNeighboringUrls(
                "topArtistsPage",
                page,
                totalPages,
                q=searchQuery,
                sortBy=sortBy,
                interval=interval,
                startDate=customStart,
                endDate=customEnd,
            )

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

        @self.app.route("/song/<song_id>", methods=["GET"], endpoint="songDetailPage")
        def songDetailPage(song_id):
            if not self.isLoggedIn:
                return redirect(url_for("login", next=request.path))

            context = self._buildSongDetailContext(song_id)
            if not context:
                return redirect(url_for("dashboard"))

            return render_template("entity_detail.html", username=self.username, **context)

        @self.app.route("/artist/<artist_id>", methods=["GET"], endpoint="artistDetailPage")
        def artistDetailPage(artist_id):
            if not self.isLoggedIn:
                return redirect(url_for("login", next=request.path))

            context = self._buildArtistDetailContext(artist_id)
            if not context:
                return redirect(url_for("dashboard"))

            return render_template("entity_detail.html", username=self.username, **context)

        @self.app.route("/playlist/<path:playlist_id>", methods=["GET"], endpoint="playlistDetailPage")
        def playlistDetailPage(playlist_id):
            if not self.isLoggedIn:
                return redirect(url_for("login", next=request.path))

            context = self._buildPlaylistDetailContext(playlist_id)
            if not context:
                return redirect(url_for("dashboard"))

            return render_template("entity_detail.html", username=self.username, **context)

    def run(self):
        self.app.run(host="0.0.0.0", debug=True, port=5000, use_reloader=False)#, threaded=False)

if __name__ == "__main__":
    ## $env:IMPORT_KEYWORD="Weekly"
    ## $env:TZ="America/Los_Angeles"

    dashboardApp = SpotifyDashboardApp()
    dashboardApp.run()