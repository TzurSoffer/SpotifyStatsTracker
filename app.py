import os
import json
import threading
from pathlib import Path
import time

from flask import Flask, render_template, redirect, request, url_for, jsonify, send_from_directory

from Database.database import Database

class SpotifyDashboardApp:
    def __init__(self):
        self.app = Flask(__name__)
        self.baseDir = Path(__file__).resolve().parent
        self.username = "Tzur"
        self.cookiesFile = self.baseDir / "cookies.json"
        self.database = Database(user=self.username)

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
        tracks = self.database.loadHistory()
        if limit is not None:
            size = len(tracks)
            return tracks[max(size - limit, 0) : size][::-1]
        return tracks[::-1]

    def startListenerIfNeeded(self):
        if self.database.listener is None:
            self.database.startListener(self.cookiesFile)
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
                data = json.loads(self.cookiesFile.read_text(encoding="utf-8"))
                if type(data) != dict or not data:
                    print("Invalid cookies file format.")
                    return False
                self.startListenerIfNeeded()
                if self.database.isListenerLoggedIn():
                    return True
            except Exception as e:
                print(e)
        return False

    def registerRoutes(self):
        @self.app.route('/img/<username>/tracks/<filename>')
        def serveTrackImage(username, filename):
            imageDir = os.path.join(self.baseDir, "Database", "img", username, "tracks")
            return send_from_directory(imageDir, filename)

        @self.app.route("/", methods=["GET"])
        def dashboard():
            if not self.ensureLoggedIn():
                # FIX: updated 'login' endpoint target
                return redirect(url_for("login", next=request.path))
            tracks = self.getLatestHistory(50)
            totalDurationMs = sum(track.get("duration", 0) for track in tracks)
            durationHours = totalDurationMs // 3_600_000
            durationMinutes = (totalDurationMs % 3_600_000) // 60_000
            totalDuration = (
                f"{durationHours}h {durationMinutes}m"
                if durationHours
                else f"{durationMinutes}m"
            )

            uniqueArtists = len({track.get("artist") for track in tracks if track.get("artist")})
            return render_template(
                "tracks.html",
                tracks=tracks,
                total=len(tracks),
                uniqueArtists=uniqueArtists,
                totalDuration=totalDuration,
                username=self.username
            )

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

                with open(self.cookiesFile, "w", encoding="utf-8") as f:
                    json.dump({"email": email, "cookies": cookies}, f, indent=2)

                # FIX: updated 'dashboard' endpoint target
                return redirect(url_for("dashboard"))

        @self.app.route("/import-progress", methods=["GET"])
        def importProgress():
            return jsonify(self.database.readProgress())

        @self.app.route("/top-songs", methods=["GET"])
        def topSongsPage():
            if not self.ensureLoggedIn():
                return redirect(url_for("login", next=request.path))

            rawTopSongs = self.database.getTopSongs()
            tracks = []
            for item in (rawTopSongs or [])[:50]:
                song = item.get("song", {})
                card = {}
                card["imageId"] = song.get("imageId") or song.get("album", {}).get("imageId") or ''
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

            totalPlays = sum(i.get("plays", 0) for i in (rawTopSongs or []))
            totalMs = sum(i.get("totalTimeListened", 0) for i in (rawTopSongs or []))

            return render_template("top_songs.html", tracks=tracks, username=self.username, totalPlays=totalPlays, totalTime=self.formatMs(totalMs))

        @self.app.route("/top-artists", methods=["GET"])
        def topArtistsPage():
            if not self.ensureLoggedIn():
                return redirect(url_for("login", next=request.path))

            rawTopArtists = self.database.getTopArtists()
            history = self.getLatestHistory(None)
            tracks = []
            for item in (rawTopArtists or [])[:50]:
                artistName = item.get("artist", "")
                rep = None
                for t in history:
                    artists = t.get("artists") or []
                    if artistName in artists or artistName == t.get("artist") or artistName == t.get("artistName"):
                        rep = t
                        break

                card = {}
                if rep:
                    card["imageId"] = rep.get("imageId")
                    card["album"] = rep.get("album") or {"name": rep.get("albumName") if rep.get("albumName") else ""}
                    card["url"] = rep.get("url")
                else:
                    card["imageId"] = ''
                    card["album"] = {"name": ""}
                    card["url"] = ""

                card["name"] = artistName
                card["artistsText"] = artistName
                card["durationText"] = self.formatMs(item.get("totalTimeListened", 0))
                card["plays"] = item.get("plays", 0)
                card["time"] = self.formatMs(item.get("totalTimeListened", 0))
                card["uniqueSongs"] = item.get("uniqueSongCount", 0)
                tracks.append(card)

            totalPlays = sum(i.get("plays", 0) for i in (rawTopArtists or []))
            totalUnique = sum(i.get("uniqueSongCount", 0) for i in (rawTopArtists or []))
            totalMs = sum(i.get("totalTimeListened", 0) for i in (rawTopArtists or []))

            return render_template("top_artists.html", tracks=tracks, username=self.username, totalPlays=totalPlays, totalUnique=totalUnique, totalTime=self.formatMs(totalMs))

    def run(self):
        self.app.run(host="0.0.0.0", debug=True, port=5000, threaded=False, use_reloader=False)

if __name__ == "__main__":
    dashboardApp = SpotifyDashboardApp()
    dashboardApp.run()