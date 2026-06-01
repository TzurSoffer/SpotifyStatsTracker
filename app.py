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


def getLatestHistory(limit=None):
    tracks = loadHistory()
    if limit is not None:
        size = len(tracks)
        tracks = tracks[max(size - limit, 0) : size]
    return tracks


@app.route("/")
def dashboard():
    tracks = getLatestHistory(50)
    # tracks.sort(key=lambda t: t["playedAt"], reverse=True)    #< assume tracks are already in order of play

    totalDurationMs = sum(track["duration"] for track in tracks)
    durationHours = totalDurationMs // 3_600_000
    durationMinutes = (totalDurationMs % 3_600_000) // 60_000
    totalDuration = (
        f"{durationHours}h {durationMinutes}m"
        if durationHours
        else f"{durationMinutes}m"
    )

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
