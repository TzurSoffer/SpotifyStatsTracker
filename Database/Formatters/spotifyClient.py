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

        for artist in (albumRaw.get("artists") or []):
            artists.append(
                {
                    "name": artist.get("name", ""),
                    "url": artist.get("external_urls", {}).get("spotify", "N/A"),
                }
            )

        artistsText = ", ".join(a.get("name", "") for a in artists)

        return artists, artistsText

    @staticmethod
    def _formatAlbum(albumRaw):
        images = albumRaw.get("images") or []
        firstImage = images[0] if images else {}

        return {
            "name": albumRaw.get("name", "Unknown album"),
            "url": albumRaw.get("external_urls", {}).get("spotify", "#"),
            "id": albumRaw.get("id", 0),
            "imageUrl": firstImage.get("url", ""),
            "totalTracks": albumRaw.get("total_tracks", 0),
            "releaseDateText": albumRaw.get("release_date", "NA"),
        }

    @staticmethod
    def formatTrack(timestamp, track, msPlayed):
        try:
            playedAt = datetime.datetime.fromtimestamp(float(timestamp))
        except ValueError:
            playedAt = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except:
            playedAt = datetime.datetime.fromtimestamp(0)

        track = track or {}
        album = track.get("album") or {}

        images = album.get("images") or []
        firstImage = images[0] if images else {}

        duration = track.get("duration_ms") or 0

        artists, artistsText = Client._formatArtists(album)

        return {
            "name": track.get("name", "Unknown Track"),
            "releaseDateText": album.get("release_date", "NA"),
            "id": track.get("id", 0),
            "url": track.get("external_urls", {}).get("spotify", "#"),
            "playedAt": timestamp,
            "playedAtText": playedAt.strftime("%Y-%m-%d %H:%M"),
            "timePlayed": msPlayed,
            "artists": artists,
            "artistsText": artistsText,
            "album": Client._formatAlbum(album),
            "imageUrl": firstImage.get("url", ""),
            "imageId": album.get("id", 0),
            "duration": duration,
            "durationText": Client._formatDuration(duration),
            "explicit": bool(track.get("explicit", False)),
            "isrc": track.get("external_ids", {}).get("isrc", ""),
            "discNumber": track.get("disc_number", 0),
            "trackNumber": track.get("track_number", 0),
        }