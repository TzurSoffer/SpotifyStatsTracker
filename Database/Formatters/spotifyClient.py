from Database.utils import convertToDatetime, timeToInt, msToString

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
    def embedPlayInfo(track, timestamp, timePlayed):
        playedAtTimestamp = timeToInt(timestamp)
        playedAt = convertToDatetime(playedAtTimestamp)
        
        track["playedAt"] = playedAtTimestamp
        track["playedAtText"] = playedAt.strftime("%Y-%m-%d %H:%M")
        track["timePlayed"] = timePlayed
        track["timePlayedText"] = msToString(timePlayed)
        return track
    
    @staticmethod
    def formatTrack(timestamp, track, msPlayed):
        track = track or {}
        album = track.get("album") or {}

        images = album.get("images") or []
        firstImage = images[0] if images else {}

        duration = track.get("duration_ms") or 0

        artists, artistsText = Client._formatArtists(album)

        track = {
            "name": track.get("name", "Unknown Track"),
            "releaseDateText": album["release_date"],
            "id": track["id"],
            "url": track["external_urls"]["spotify"],
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
        return Client.embedPlayInfo(track, timestamp, msPlayed)