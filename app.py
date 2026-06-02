import os
import json
import threading
from pathlib import Path
import time

from flask import Flask, render_template, redirect, request, url_for, jsonify, send_from_directory

from Database.database import Database

app = Flask(__name__)
baseDir = Path(__file__).resolve().parent
USERNAME = "Tzur"
COOKIES_FILE = baseDir / "cookies.json"

database = Database(user=USERNAME)

@app.route('/img/<username>/tracks/<filename>')
def serve_track_image(username, filename):
    imageDir = os.path.join(baseDir, "Database", "img", username, "tracks")
    return send_from_directory(imageDir, filename)

def get_latest_history(limit=None):
    tracks = database.loadHistory()
    if limit is not None:
        size = len(tracks)
        return tracks[max(size - limit, 0) : size][::-1]   #< Reverse the list to get the latest items first
    return tracks[::-1]      #< doing it like this instead of reversing the whole list to save memory and cpu if the history is large

def format_ms(ms: int) -> str:
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

def startListenerIfNeeded():
    if database.listener == None:
        database.startListener(COOKIES_FILE)
        print("Started listener thread.")
        time.sleep(2)  # give listener time to initialize

def run_import_background(history_data):
    try:
        database.importSpotifyHistory(history_data)
    except Exception:
        pass

def ensure_logged_in(redirect_to=None):
    if COOKIES_FILE.exists():
        try:
            data = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
            if type(data) != dict or not data:
                print("Invalid cookies file format.")
                return False
            startListenerIfNeeded()
            if database.isListenerLoggedIn():
                return True
        except Exception as e:
            print(e)
    return False


@app.route("/", methods=["GET"])
def dashboard():
    if not ensure_logged_in():
        return redirect(url_for("login", next=request.path))
    tracks = get_latest_history(50)
    total_duration_ms = sum(track.get("duration", 0) for track in tracks)
    duration_hours = total_duration_ms // 3_600_000
    duration_minutes = (total_duration_ms % 3_600_000) // 60_000
    total_duration = (
        f"{duration_hours}h {duration_minutes}m"
        if duration_hours
        else f"{duration_minutes}m"
    )

    unique_artists = len({track.get("artist") for track in tracks if track.get("artist")})
    return render_template(
        "tracks.html",
        tracks=tracks,
        total=len(tracks),
        uniqueArtists=unique_artists,
        totalDuration=total_duration,
        username=USERNAME
    )


@app.route("/import-history", methods=["POST"])
def import_history():
    if database.readProgress().get("status") == "running":
        return redirect(url_for("import_page"))

    upload = request.files.get("history_file")
    if upload is None or upload.filename == "":
        return redirect(url_for("import_page"))

    try:
        history_data = json.load(upload)
    except json.JSONDecodeError:
        return redirect(url_for("import_page"))

    thread = threading.Thread(target=run_import_background, args=(history_data,), daemon=True)
    thread.start()
    return redirect(url_for("import_page"))


@app.route("/import", methods=["GET"])
def import_page():
    return render_template("import.html", importProgress=database.readProgress())

@app.route("/login", methods=["GET", "POST"])
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
            return render_template("login.html", step=2, email=email,
                                   error="Cookies required.")

        with open(COOKIES_FILE, "w", encoding="utf-8") as f:
            json.dump({"email": email, "cookies": cookies}, f, indent=2)

        return redirect(url_for("dashboard"))

@app.route("/import-progress", methods=["GET"])
def import_progress():
    return jsonify(database.readProgress())


@app.route("/top-songs", methods=["GET"])
def top_songs_page():
    if not ensure_logged_in():
        return redirect(url_for("login", next=request.path))

    raw_top_songs = database.getTopSongs()
    tracks = []
    for item in (raw_top_songs or [])[:50]:
        song = item.get("song", {})
        card = {}
        card["imageId"] = song.get("imageId") or song.get("album", {}).get("imageId") or ''
        card["name"] = song.get("name") or song.get("title") or ""
        card["artistsText"] = song.get("artistsText") or (", ".join(song.get("artists", [])) if song.get("artists") else song.get("artist") or "")
        card["album"] = song.get("album") or {"name": ""}
        card["playedAtText"] = song.get("playedAtText") or ""
        dur = song.get("duration") or song.get("durationMs") or 0
        card["durationText"] = format_ms(dur)
        card["trackNumber"] = song.get("trackNumber") or song.get("track_number") or 0
        card["discNumber"] = song.get("discNumber") or song.get("disc_number") or 0
        card["explicit"] = song.get("explicit", False)
        card["isrc"] = song.get("isrc")
        card["url"] = song.get("url") or song.get("external_urls", {}).get("spotify") or ""
        card["plays"] = item.get("plays", 0)
        card["time"] = format_ms(item.get("totalTimeListened", 0))
        tracks.append(card)

    total_plays = sum(i.get("plays", 0) for i in (raw_top_songs or []))
    total_ms = sum(i.get("totalTimeListened", 0) for i in (raw_top_songs or []))

    return render_template("top_songs.html", tracks=tracks, username=USERNAME, totalPlays=total_plays, totalTime=format_ms(total_ms))


@app.route("/top-artists", methods=["GET"])
def top_artists_page():
    if not ensure_logged_in():
        return redirect(url_for("login", next=request.path))

    raw_top_artists = database.getTopArtists()
    # build representative track-like cards for each artist
    history = get_latest_history(None)
    tracks = []
    for item in (raw_top_artists or [])[:50]:
        artist_name = item.get("artist", "")
        # find a representative track with this artist
        rep = None
        for t in history:
            artists = t.get("artists") or []
            # artists may be list of names or ids
            if artist_name in artists or artist_name == t.get("artist") or artist_name == t.get("artistName"):
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

        card["name"] = artist_name
        card["artistsText"] = artist_name
        card["durationText"] = format_ms(item.get("totalTimeListened", 0))
        card["plays"] = item.get("plays", 0)
        card["time"] = format_ms(item.get("totalTimeListened", 0))
        card["uniqueSongs"] = item.get("uniqueSongCount", 0)
        tracks.append(card)

    total_plays = sum(i.get("plays", 0) for i in (raw_top_artists or []))
    total_unique = sum(i.get("uniqueSongCount", 0) for i in (raw_top_artists or []))
    total_ms = sum(i.get("totalTimeListened", 0) for i in (raw_top_artists or []))

    return render_template("top_artists.html", tracks=tracks, username=USERNAME, totalPlays=total_plays, totalUnique=total_unique, totalTime=format_ms(total_ms))

if COOKIES_FILE.exists():
    startListenerIfNeeded()

if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=False, use_reloader=False)
