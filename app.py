from flask import Flask, render_template, redirect, url_for
from pathlib import Path
import json
import datetime

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
HISTORY_PATH = BASE_DIR / "Database" / "history.json"


def load_history():
    if not HISTORY_PATH.exists():
        return []

    try:
        with HISTORY_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []
    except Exception:
        return []


def format_duration(ms: int) -> str:
    seconds = max(0, ms // 1000)
    minutes = seconds // 60
    remaining = seconds % 60
    return f"{minutes}:{remaining:02d}"


def enrich_track(track: dict) -> dict:
    album = track.get("album", {}) or {}
    artists = album.get("artists", []) or []
    artist_names = ", ".join(a.get("name", "") for a in artists if isinstance(a, dict))

    timestamp = track.get("timestamp")
    try:
        played_at = datetime.datetime.fromtimestamp(float(timestamp))
    except Exception:
        played_at = datetime.datetime.fromtimestamp(0)

    return {
        "name": track.get("name", "Unknown"),
        "url": track.get("external_urls", {}).get("spotify", "#"),
        "image_url": track.get("image_url", ""),
        "album_name": album.get("name", "Unknown album"),
        "artist": artist_names or "Unknown artist",
        "duration_ms": int(track.get("duration_ms", 0) or 0),
        "duration": format_duration(int(track.get("duration_ms", 0) or 0)),
        "played_at": played_at,
        "played_at_text": played_at.strftime("%Y-%m-%d %H:%M"),
        "explicit": bool(track.get("explicit", False)),
        "popularity": track.get("popularity", 0),
        "track_number": track.get("track_number", 0),
        "disc_number": track.get("disc_number", 0),
        "isrc": track.get("external_ids", {}).get("isrc", ""),
    }


@app.route("/")
def dashboard():
    tracks = [enrich_track(track) for track in load_history()]
    tracks.sort(key=lambda t: t["played_at"], reverse=True)

    total_duration_ms = sum(track["duration_ms"] for track in tracks)
    duration_hours = total_duration_ms // 3_600_000
    duration_minutes = (total_duration_ms % 3_600_000) // 60_000
    total_duration = f"{duration_hours}h {duration_minutes}m" if duration_hours else f"{duration_minutes}m"

    unique_artists = len({track["artist"] for track in tracks if track["artist"]})

    return render_template(
        "tracks.html",
        tracks=tracks,
        total=len(tracks),
        unique_artists=unique_artists,
        total_duration=total_duration,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
