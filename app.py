from flask import Flask, render_template, redirect, url_for
from pathlib import Path
import json
import datetime

app = Flask(__name__)
baseDir = Path(__file__).resolve().parent
historyPath = baseDir / "Database" / "history.json"


def loadHistory(start=None, end=None) -> list:
    if not historyPath.exists():
        return []

    try:
        with historyPath.open("r", encoding="utf-8") as f:
            tracks = json.load(f)
            if start is not None and end is not None:
                tracks = tracks[start:end]
            return tracks
    except json.JSONDecodeError:
        return []
    except Exception:
        return []

def formatDuration(ms: int) -> str:
    seconds = max(0, ms // 1000)
    minutes = seconds // 60
    remaining = seconds % 60
    return f"{minutes}:{remaining:02d}"


def enrichTrack(track: dict) -> dict:
    album = track.get("album", {}) or {}
    artists = album.get("artists", []) or []
    artistNames = ", ".join(a.get("name", "") for a in artists if isinstance(a, dict))

    timestamp = track.get("timestamp")
    try:
        playedAt = datetime.datetime.fromtimestamp(float(timestamp))
    except Exception:
        playedAt = datetime.datetime.fromtimestamp(0)

    return {
        "name": track.get("name", "Unknown"),
        "url": track.get("external_urls", {}).get("spotify", "#"),
        "imageUrl": track.get("image_url", ""),
        "albumName": album.get("name", "Unknown album"),
        "artist": artistNames or "Unknown artist",
        "durationMs": int(track.get("duration_ms", 0) or 0),
        "duration": formatDuration(int(track.get("duration_ms", 0) or 0)),
        "playedAt": playedAt,
        "playedAtText": playedAt.strftime("%Y-%m-%d %H:%M"),
        "explicit": bool(track.get("explicit", False)),
        "popularity": track.get("popularity", 0),
        "trackNumber": track.get("track_number", 0),
        "discNumber": track.get("disc_number", 0),
        "isrc": track.get("external_ids", {}).get("isrc", ""),
    }


@app.route("/")
def dashboard():
    tracks = [enrichTrack(track) for track in loadHistory()]
    tracks.sort(key=lambda t: t["playedAt"], reverse=True)

    totalDurationMs = sum(track["durationMs"] for track in tracks)
    durationHours = totalDurationMs // 3_600_000
    durationMinutes = (totalDurationMs % 3_600_000) // 60_000
    totalDuration = f"{durationHours}h {durationMinutes}m" if durationHours else f"{durationMinutes}m"

    uniqueArtists = len({track["artist"] for track in tracks if track["artist"]})

    return render_template(
        "tracks.html",
        tracks=tracks,
        total=len(tracks),
        uniqueArtists=uniqueArtists,
        totalDuration=totalDuration,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)