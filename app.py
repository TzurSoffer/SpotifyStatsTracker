import os
import json
import threading
from pathlib import Path
import time

from flask import Flask, render_template, redirect, request, url_for, jsonify, send_from_directory

from Database.database import Database
from Database.Migrators.migrate import migrateIfNeeded
from SpotipyFree import saveSession, parseCookieString

class SpotifyDashboardApp:
    def __init__(self):
        migrateIfNeeded()
        self.app = Flask(__name__)
        self.baseDir = Path(__file__).resolve().parent
        self.username = "Tzur"
        self.cookiesFile = self.baseDir / "secrets" / "cookies.json"
        self.database = Database(user=self.username)
        self.database.resetProgress()

        # Register routes
        self.registerRoutes()

        # Initialize background listener if cookies exist
        if self.cookiesFile.exists():
            self.startListenerIfNeeded()

    def formatMs(self, ms: int) -> str:
        if not ms:
            return "0s"
        seconds = ms // 1000
        minutes, sec = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}h {minutes}m"
        if minutes:
            return f"{minutes}m {sec}s"
        return f"{sec}s"

    def getLatestHistory(self, limit=None):
        return self.database.getEntriesFromNew(limit)

    def paginate(self, items, page, pageSize=50):
        page = max(1, page)
        total = len(items)
        start = (page - 1) * pageSize
        end = start + pageSize
        return items[start:end], total, page, max(1, (total + pageSize - 1) // pageSize), start

    def startListenerIfNeeded(self):
        if self.database.listener is None:
            self.database.startListener(str(self.cookiesFile))
            print("Started listener thread.")
            time.sleep(2)  # Give listener time to initialize

    def runImportBackground(self, historyData):
        try:
            self.database.importSpotifyHistory(historyData)
        except Exception:
            pass

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
        @self.app.route('/img/<username>/tracks/<filename>')
        def serveTrackImage(username, filename):
            imageDir = os.path.join(self.baseDir, "Database", "Users", username, "img", "tracks")
            return send_from_directory(imageDir, filename)

        @self.app.route("/import-history", methods=["POST"])
        def importHistory():
            if self.database.readProgress().get("status") == "running":
                return redirect(url_for("importPage"))

            upload = request.files.get("history_file")
            if upload is None or upload.filename == "":
                return redirect(url_for("importPage"))

            try:
                historyData = json.load(upload)
            except json.JSONDecodeError:
                return redirect(url_for("importPage"))

            thread = threading.Thread(target=self.runImportBackground, args=(historyData,), daemon=True)
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

        @self.app.route("/", methods=["GET"])
        def dashboard():
            if not self.ensureLoggedIn():
                return redirect(url_for("login", next=request.path))
            page = int(request.args.get("page", 1) or 1)
            pageSize = 50
            total = self.database.getEntriesCount()
            startIndex = (page - 1) * pageSize
            tracks = self.database.getEntriesFromNew(count=pageSize, startIndex=startIndex)
            totalPages = max(1, (total + pageSize - 1) // pageSize)

            totalDurationMs = sum(track.get("timePlayed", 0) for track in self.getLatestHistory(None))
            durationHours = totalDurationMs // 3_600_000
            durationMinutes = (totalDurationMs % 3_600_000) // 60_000
            totalDuration = (
                f"{durationHours}h {durationMinutes}m"
                if durationHours
                else f"{durationMinutes}m"
            )

            uniqueArtists = len({track.get("artist") for track in self.getLatestHistory(None) if track.get("artist")})
            prevUrl = url_for("dashboard", page=page - 1) if page > 1 else None
            nextUrl = url_for("dashboard", page=page + 1) if page < totalPages else None

            return render_template(
                "tracks.html",
                tracks=tracks,
                total=total,
                uniqueArtists=uniqueArtists,
                totalDuration=totalDuration,
                username=self.username,
                page=page,
                totalPages=totalPages,
                prevUrl=prevUrl,
                nextUrl=nextUrl,
                startIndex=startIndex,
            )

        @self.app.route("/top-songs", methods=["GET"])
        def topSongsPage():
            if not self.ensureLoggedIn():
                return redirect(url_for("login", next=request.path))

            page = int(request.args.get("page", 1) or 1)
            rawTopSongs = self.database.getTopSongs() or []
            pageItems, total, page, totalPages, startIndex = self.paginate(rawTopSongs, page)

            tracks = []
            for item in pageItems:
                song = item.get("song", {})
                card = {}
                card["id"] = song.get("id", "")
                card["name"] = song.get("name") or song.get("title") or ""
                card["artistsText"] = song.get("artistsText") or (", ".join(song.get("artists", [])) if song.get("artists") else song.get("artist") or "")
                card["album"] = song.get("album") or {"name": ""}
                card["playedAtText"] = song.get("playedAtText") or ""
                dur = song.get("duration") or song.get("durationMs") or 0
                card["durationText"] = self.formatMs(dur)
                card["trackNumber"] = song.get("trackNumber") or song.get("track_number") or 0
                card["discNumber"] = song.get("discNumber") or song.get("disc_number") or 0
                card["explicit"] = song.get("explicit", False)
                card["isrc"] = song.get("isrc")
                card["url"] = song.get("url") or song.get("external_urls", {}).get("spotify") or ""
                card["plays"] = item.get("plays", 0)
                card["time"] = self.formatMs(item.get("totalTimeListened", 0))
                tracks.append(card)

            totalPlays = sum(i.get("plays", 0) for i in rawTopSongs)
            totalMs = sum(i.get("totalTimeListened", 0) for i in rawTopSongs)
            prevUrl = url_for("topSongsPage", page=page - 1) if page > 1 else None
            nextUrl = url_for("topSongsPage", page=page + 1) if page < totalPages else None

            return render_template(
                "top_songs.html",
                tracks=tracks,
                username=self.username,
                totalPlays=totalPlays,
                totalTime=self.formatMs(totalMs),
                page=page,
                totalPages=totalPages,
                prevUrl=prevUrl,
                nextUrl=nextUrl,
                startIndex=startIndex,
            )

        @self.app.route("/top-artists", methods=["GET"])
        def topArtistsPage():
            if not self.ensureLoggedIn():
                return redirect(url_for("login", next=request.path))

            page = int(request.args.get("page", 1) or 1)
            rawTopArtists = self.database.getTopArtists() or []
            pageItems, total, page, totalPages, startIndex = self.paginate(rawTopArtists, page)
            history = self.getLatestHistory(None)
            tracks = []
            for item in pageItems:
                artistName = item.get("artist", "")
                rep = None
                for t in history:
                    artists = t.get("artists") or []
                    if artistName in artists or artistName == t.get("artist") or artistName == t.get("artistName"):
                        rep = t
                        break

                card = {}
                if rep:
                    card["id"] = rep.get("id", "")
                    card["album"] = rep.get("album") or {"name": rep.get("albumName") if rep.get("albumName") else ""}
                    card["url"] = rep.get("url")
                else:
                    card["id"] = ""
                    card["album"] = {"name": ""}
                    card["url"] = ""

                card["name"] = artistName
                card["artistsText"] = artistName
                card["durationText"] = self.formatMs(item.get("totalTimeListened", 0))
                card["plays"] = item.get("plays", 0)
                card["time"] = self.formatMs(item.get("totalTimeListened", 0))
                card["uniqueSongs"] = item.get("uniqueSongCount", 0)
                tracks.append(card)

            totalPlays = sum(i.get("plays", 0) for i in rawTopArtists)
            totalUnique = sum(i.get("uniqueSongCount", 0) for i in rawTopArtists)
            totalMs = sum(i.get("totalTimeListened", 0) for i in rawTopArtists)
            prevUrl = url_for("topArtistsPage", page=page - 1) if page > 1 else None
            nextUrl = url_for("topArtistsPage", page=page + 1) if page < totalPages else None

            return render_template(
                "top_artists.html",
                tracks=tracks,
                username=self.username,
                totalPlays=totalPlays,
                totalUnique=totalUnique,
                totalTime=self.formatMs(totalMs),
                page=page,
                totalPages=totalPages,
                prevUrl=prevUrl,
                nextUrl=nextUrl,
                startIndex=startIndex,
            )

    def run(self):
        self.app.run(host="0.0.0.0", debug=True, port=5000, threaded=False, use_reloader=False)

if __name__ == "__main__":
    dashboardApp = SpotifyDashboardApp()
    dashboardApp.run()