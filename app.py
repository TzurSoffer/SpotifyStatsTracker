import os
import json
import secrets
import threading
import requests
from pathlib import Path
import time
from datetime import timedelta

from flask import Flask, render_template, redirect, request, url_for, jsonify, send_from_directory, session, g

from Database.database import Database
from Database.Migrators.migrate import migrateIfNeeded
from Database.utils import msToString, convertToDatetime, formatDuration, dateToString, versionTuple, now, startOfDay, parseDateString
from SpotipyFree import saveSession, parseCookieString

class SpotifyDashboardApp:
    def __init__(self):
        migrateIfNeeded()
        self.app = Flask(__name__)
        self.baseDir = Path(__file__).resolve().parent
        self.app.secret_key = self._get_or_create_secret_key()
        self.app.permanent_session_lifetime = timedelta(days=30)
        self.cookiesFile = self.baseDir / "secrets" / "cookies.json"
        
        self.user_databases = {}
        self._db_lock = threading.RLock()
        
        try:
            self.currentVersion = (self.baseDir / "Database" / "VERSION").read_text(encoding="utf-8").strip()  #< only needs to be checked once because app cant update without restart
        except Exception:
            self.currentVersion = "0.0.0"
        self.latestVersion = None
        self._version_lock = threading.Lock()
        self.startVersionCheck_thread()
        self.checkLogin_thread()

        self.registerRoutes()

    def _get_or_create_secret_key(self):
        """Resolve the Flask session-signing key. Prefers FLASK_SECRET_KEY, otherwise
        persists a random key under secrets/ so sessions can't be forged using the
        publicly-known default that used to ship in this repo."""
        envKey = os.environ.get("FLASK_SECRET_KEY")
        if envKey:
            return envKey

        keyFile = self.baseDir / "secrets" / "flask_secret_key.txt"
        if keyFile.exists():
            existingKey = keyFile.read_text(encoding="utf-8").strip()
            if existingKey:
                return existingKey

        newKey = secrets.token_hex(32)
        keyFile.parent.mkdir(parents=True, exist_ok=True)
        keyFile.write_text(newKey, encoding="utf-8")
        return newKey

    def get_username_for_email(self, email):
        map_file = self.baseDir / "secrets" / "users_map.json"
        if map_file.exists():
            try:
                users_map = json.loads(map_file.read_text(encoding="utf-8"))
                if email in users_map:
                    return users_map[email]
            except Exception:
                pass
        
        return None

    def _migrate_legacy_database_if_needed(self, username):
        import shutil
        users_dir = self.baseDir / "Database" / "Users"
        target_dir = users_dir / username
        
        # If target already contains data (entries.json exists and is not empty), no migration is needed
        target_entries = target_dir / "entries.json"
        if target_entries.exists() and target_entries.stat().st_size > 2:
            return
            
        # Possible legacy source directories:
        # 1. Database/Users/Tzur (from early multi-user version)
        # 2. Database/Tzur (legacy single-user version)
        # 3. Database (legacy single-user version directly in Database folder)
        legacy_sources = [
            users_dir / "Tzur",
            self.baseDir / "Database" / "Tzur",
            self.baseDir / "Database"
        ]
        
        for src in legacy_sources:
            if src.exists() and src.resolve() != target_dir.resolve() and src.resolve() != users_dir.resolve():
                src_entries = src / "entries.json"
                # Check if this source directory actually has database entries
                if src_entries.exists() and src_entries.stat().st_size > 2:
                    print(f"Migrating legacy database from {src} to {target_dir}...")
                    
                    # Create target directory
                    target_dir.mkdir(parents=True, exist_ok=True)
                    
                    try:
                        if src.resolve() == (self.baseDir / "Database").resolve():
                            # Only migrate individual database files to avoid recursive copying of Database/Users
                            db_files = ["entries.json", "tracks.json", "playlists.json", "progress.json"]
                            for file_name in db_files:
                                file_path = src / file_name
                                if file_path.exists():
                                    shutil.copy2(file_path, target_dir / file_name)
                                    file_path.unlink()
                            
                            # Copy image directories if they exist
                            for img_type in ["tracks", "artists"]:
                                img_src = src / "img" / img_type
                                if img_src.exists():
                                    img_dst = target_dir / "img" / img_type
                                    img_dst.mkdir(parents=True, exist_ok=True)
                                    for item in img_src.iterdir():
                                        if item.is_file():
                                            shutil.copy2(item, img_dst / item.name)
                            
                            # Clean up legacy img folders if they are empty
                            legacy_img = src / "img"
                            if legacy_img.exists():
                                try:
                                    shutil.rmtree(legacy_img)
                                except Exception:
                                    pass
                        else:
                            # Copy all contents recursively
                            def copy_recursive(src_path, dst_path):
                                dst_path.mkdir(parents=True, exist_ok=True)
                                for item in src_path.iterdir():
                                    target_item = dst_path / item.name
                                    if item.is_dir():
                                        copy_recursive(item, target_item)
                                    else:
                                        shutil.copy2(item, target_item)
                            copy_recursive(src, target_dir)
                            # Remove the old directory to keep files clean and avoid re-migration
                            shutil.rmtree(src)
                        print(f"Successfully migrated and cleaned up legacy folder: {src}")
                    except Exception as e:
                        print(f"Error migrating legacy database: {e}")
                    break

    def get_or_create_user(self, email):
        username = self.get_username_for_email(email)
        if not username:
            # Create a new username from email prefix
            prefix = email.split("@")[0]
            sanitized = "".join(c for c in prefix if c.isalnum() or c in ("-", "_")).strip()
            if not sanitized:
                sanitized = f"user_{int(time.time())}"
                
            # Ensure uniqueness under Database/Users/
            username = sanitized
            counter = 1
            users_dir = self.baseDir / "Database" / "Users"
            while (users_dir / username).exists() or username in self.user_databases:
                username = f"{sanitized}_{counter}"
                counter += 1
                
            # Save to mapping
            map_file = self.baseDir / "secrets" / "users_map.json"
            users_map = {}
            if map_file.exists():
                try:
                    users_map = json.loads(map_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            users_map[email] = username
            map_file.parent.mkdir(parents=True, exist_ok=True)
            map_file.write_text(json.dumps(users_map, indent=4), encoding="utf-8")
        
        # Ensure legacy folders are migrated to this user's active directory
        self._migrate_legacy_database_if_needed(username)
        
        # Ensure directories exist
        users_dir = self.baseDir / "Database" / "Users"
        (users_dir / username).mkdir(parents=True, exist_ok=True)
        
        return username

    def get_user_db(self, username, email):
        with self._db_lock:
            if username not in self.user_databases:
                db = Database(user=username, cookiesFile=str(self.cookiesFile), email=email)
                db.startAutoImporter()
                db.resetProgress()
                db.startListener(str(self.cookiesFile), email=email)
                self.user_databases[username] = db
            return self.user_databases[username]

    def is_user_logged_in(self, email):
        if not email:
            return False
        if not self.cookiesFile.exists():
            return False
        try:
            cookies_data = json.loads(self.cookiesFile.read_text(encoding="utf-8"))
            has_cookie = any(c.get("identifier") == email for c in cookies_data)
            if not has_cookie:
                return False
        except Exception:
            return False
            
        username = self.get_username_for_email(email)
        if username and username in self.user_databases:
            return self.user_databases[username].isListenerLoggedIn()
        return True

    def checkLogin_thread(self):
        self._ensureAllUsersLogin()
        thread = threading.Thread(target=self._checkLoginLoop, daemon=True)
        thread.start()
    
    def _ensureAllUsersLogin(self):
        if self.cookiesFile.exists():
            try:
                cookies_data = json.loads(self.cookiesFile.read_text(encoding="utf-8"))
                for entry in cookies_data:
                    email = entry.get("identifier")
                    if email:
                        username = self.get_or_create_user(email)
                        self.get_user_db(username, email)
            except Exception as e:
                print("Error initializing users:", e)
    
    def _checkLoginLoop(self):
        while True:
            self._ensureAllUsersLogin()
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
            db = g.get("db", None)
            if db:
                song["contextName"] = db.playlistName(song["playedFrom"])

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
                db = g.get("db", None)
                if db:
                    parts.append(db.playlistName(playedFrom))
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

        def get_current_user_or_redirect():
            email = session.get("email")
            if not email or not self.is_user_logged_in(email):
                return None, None, None
            
            # Ensure the username matches the correct email mapping to prevent session pollution from legacy user "Tzur"
            correct_username = self.get_username_for_email(email)
            if not correct_username:
                correct_username = self.get_or_create_user(email)
            
            if session.get("username") != correct_username:
                session["username"] = correct_username

            username = correct_username
            db = self.get_user_db(username, email)
            g.db = db
            return email, username, db

        def _authorized_image_username():
            """Returns the username the current session is allowed to view images for, or None."""
            email = session.get("email")
            if not email or not self.is_user_logged_in(email):
                return None
            return self.get_username_for_email(email)

        @self.app.route('/img/<username>/tracks/<filename>')
        def serveTrackImage(username, filename):
            if username != _authorized_image_username() or filename != os.path.basename(filename):
                return "", 404
            imageDir = os.path.join(self.baseDir, "Database", "Users", username, "img", "tracks")
            return send_from_directory(imageDir, filename)

        @self.app.route('/img/<username>/artists/<filename>')
        def serveArtistImage(username, filename):
            if username != _authorized_image_username() or filename != os.path.basename(filename):
                return "", 404
            imageDir = os.path.join(self.baseDir, "Database", "Users", username, "img", "artists")
            imagePath = os.path.join(imageDir, filename)

            if not os.path.exists(imagePath):
                artistId = filename.split('.')[0]
                db = self.user_databases.get(username)
                if db:
                    db.lazyFetchArtistImage(artistId, Path(imagePath))

            return send_from_directory(imageDir, filename)

        @self.app.route("/import-history", methods=["POST"])
        def importHistory():
            email, username, db = get_current_user_or_redirect()
            if not email:
                return redirect(url_for("login"))

            if db.readProgress().get("status") == "running":
                return redirect(url_for("importPage"))

            upload = request.files.get("history_file")
            if upload is None or upload.filename == "":
                return redirect(url_for("importPage"))

            thread = threading.Thread(target=db.importHistory, args=(upload.read().decode("utf-8"),), daemon=True)
            thread.start()
            time.sleep(1)  # Give thread time to start and update progress
            return redirect(url_for("importPage"))

        @self.app.route("/import", methods=["GET"])
        def importPage():
            email, username, db = get_current_user_or_redirect()
            if not email:
                return redirect(url_for("login"))
            return render_template("import.html", importProgress=db.readProgress())

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
                session.permanent = True
                username = self.get_or_create_user(email)
                self.get_user_db(username, email)
                session["email"] = email
                session["username"] = username

                return redirect(url_for("dashboard"))

        @self.app.route("/logout", methods=["GET"])
        def logout():
            session.clear()
            return redirect(url_for("login"))

        @self.app.route("/import-progress", methods=["GET"])
        def importProgress():
            email, username, db = get_current_user_or_redirect()
            if not email:
                return jsonify({"error": "unauthorized"}), 401
            return jsonify(db.readProgress())

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
            email, username, db = get_current_user_or_redirect()
            if not email:
                return redirect(url_for("login", next=request.path))

            page = int(request.args.get("page", 1) or 1)
            searchQuery = request.args.get("q", "")
            customStart = request.args.get("startDate", "")
            customEnd = request.args.get("endDate", "")
            interval = request.args.get("interval", "day")
            if interval == "custom" and not (customStart and customEnd):
                interval = "all time"

            tracks = db.getEntriesFromNew()
            if searchQuery:
                self._embedIndices(tracks)
            tracks = self._filterBySearch(tracks, searchQuery)
            tracks, totalPages, startIndex = self.getPage(tracks, page)
            tracks = self._embedSongsTextElements(tracks)

            intervalLabel = self._getIntervalLabel(interval, customStart, customEnd)
            startDate, endDate = self._getDateRange(interval, customStart, customEnd, default="day")
            stats = db.getOverallStats(startDate, endDate) 

            totalDurationText = msToString(stats["totalDurationMs"])

            currentTopSong = self._embedTopSongTextElements(stats["currentTopSongs"][0], sortBy="plays", totalPlays=stats["totalSongsPlayed"], totalMs=stats["totalDurationMs"]) if stats["currentTopSongs"] else None
            currentTopArtist = self._embedArtistTextElement(stats["currentTopArtists"][0], sortBy="totalTimeListened", totalPlays=stats["totalSongsPlayed"], totalMs=stats["totalDurationMs"]) if stats["currentTopArtists"] else None

            totalSongsChangeText, totalSongsChangeClass = self._getChangeText(stats["totalSongsPlayed"], stats["previousSongsPlayed"])
            totalListenChangeText, totalListenChangeClass = self._getChangeText(stats["totalDurationMs"], stats["previousDurationMs"])

            prevUrl, nextUrl = self._getNeighboringUrls(
                "dashboard",
                page,
                totalPages,
                q=searchQuery,
                interval=interval,
                startDate=customStart,
                endDate=customEnd,
            )

            return render_template(
                "tracks.html",
                tracks=tracks,
                totalSongsPlayed=stats["totalSongsPlayed"],
                totalListenTime=totalDurationText,
                totalSongsChangeText=totalSongsChangeText,
                totalSongsChangeClass=totalSongsChangeClass,
                totalListenChangeText=totalListenChangeText,
                totalListenChangeClass=totalListenChangeClass,
                currentTopSong=currentTopSong,
                currentTopArtist=currentTopArtist,
                intervalLabel=intervalLabel,
                username=username,
                page=page,
                totalPages=totalPages,
                prevUrl=prevUrl,
                nextUrl=nextUrl,
                startIndex=startIndex,
                section="dashboard",
                interval=interval,
                customStart=customStart,
                customEnd=customEnd,
            )

        @self.app.route("/top-songs", methods=["GET"])
        def topSongsPage():
            email, username, db = get_current_user_or_redirect()
            if not email:
                return redirect(url_for("login", next=request.path))

            page = int(request.args.get("page", 1) or 1)
            searchQuery = request.args.get("q", "")
            sortBy = request.args.get("sortBy", "totalTimeListened")
            interval = request.args.get("interval", "")
            customStart = request.args.get("startDate", "")
            customEnd = request.args.get("endDate", "")
            
            startDate, endDate = self._getDateRange(interval, customStart, customEnd, default="all time")
            rawTopSongs = db.getTopSongs(startDate=startDate, endDate=endDate, by=sortBy)
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
                username=username,
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
            email, username, db = get_current_user_or_redirect()
            if not email:
                return redirect(url_for("login", next=request.path))

            page = int(request.args.get("page", 1) or 1)
            searchQuery = request.args.get("q", "")
            sortBy = request.args.get("sortBy", "totalTimeListened")
            interval = request.args.get("interval", "")
            customStart = request.args.get("startDate", "")
            customEnd = request.args.get("endDate", "")
            
            startDate, endDate = self._getDateRange(interval, customStart, customEnd, default="all time")
            rawTopArtists = db.getTopArtists(startDate=startDate, endDate=endDate, by=sortBy) or []
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
                username=username,
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
        self.app.run(host="0.0.0.0", debug=True, port=5000, use_reloader=False)#, threaded=False)

if __name__ == "__main__":
    ## $env:IMPORT_KEYWORD="Weekly"
    ## $env:TZ="America/Los_Angeles"

    dashboardApp = SpotifyDashboardApp()
    dashboardApp.run()