import datetime


class Client:
    @staticmethod
    def _formatDuration(ms: int) -> str:
        seconds = max(0, ms // 1000)
        minutes = seconds // 60
        remaining = seconds % 60
        return f"{minutes}:{remaining:02d}"

    @staticmethod
    def _formatArtists(albumRaw):
        artists = []
        for artist in (
            albumRaw.get("artists", []) or []
        ):  # < list of artists names and links to spotify
            artists.append(
                {
                    "name": artist.get("name", ""),
                    "url": artist.get("external_urls", {"spotify": "N/A"})["spotify"],
                }
            )
        artistsText = ", ".join(a["name"] for a in artists)
        return artists, artistsText

    @staticmethod
    def _formatAlbum(albumRaw):
        return {
            "name": albumRaw.get("name", "Unknown album"),
            "url": albumRaw.get("external_urls", {}).get("spotify", "#"),
            "id": albumRaw.get("id", 0),
            "imageUrl": albumRaw.get("images", [{}])[0].get("url", ""),
            "totalTracks": albumRaw.get("total_tracks", 0),
            "releaseDateText": albumRaw.get("release_date", "NA"),
        }

    @staticmethod
    def formatTrack(timestamp, track, msPlayed):
        try:
            playedAt = datetime.datetime.fromtimestamp(float(timestamp))
        except Exception:
            playedAt = datetime.datetime.fromtimestamp(0)
        duration = track["duration_ms"] or 0
        album = track.get("album", {}) or {}
        artists, artistsText = Client._formatArtists(album)

        return {
            "name": track["name"],
            "releaseDateText": album.get("release_date", "NA"),
            "id": track["id"],
            "url": track["external_urls"]["spotify"],
            "playedAt": timestamp,
            "playedAtText": playedAt.strftime("%Y-%m-%d %H:%M"),
            "timePlayed": msPlayed,
            "artists": artists,
            "artistsText": artistsText,
            "album": Client._formatAlbum(album),
            "imageUrl": album["images"][0]["url"],
            "imageId": album["id"],
            "duration": duration,
            "durationText": Client._formatDuration(duration),
            "explicit": bool(track.get("explicit", False)),
            "isrc": track["external_ids"]["isrc"],
            "discNumber": track["disc_number"],
            "trackNumber": track["track_number"],
        }
