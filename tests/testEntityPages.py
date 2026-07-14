import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import SpotifyDashboardApp


class DummyDatabase:
    def __init__(self):
        self.entries = [
            {"id": "track-1", "playedAt": 1_700_000_000, "timePlayed": 180_000, "playedFrom": "playlist:abc123"},
            {"id": "track-1", "playedAt": 1_700_000_100, "timePlayed": 220_000, "playedFrom": "playlist:abc123"},
            {"id": "track-2", "playedAt": 1_700_000_200, "timePlayed": 90_000, "playedFrom": None},
        ]
        self.tracks = {
            "track-1": {
                "id": "track-1",
                "name": "Song One",
                "url": "https://open.spotify.com/track/track-1",
                "duration": 240_000,
                "artists": [{"id": "artist-1", "name": "Artist One"}],
                "album": {"name": "Album One", "id": "album-1"},
                "imageId": "album-1",
                "explicit": False,
                "isrc": "ABC123",
            },
            "track-2": {
                "id": "track-2",
                "name": "Song Two",
                "url": "https://open.spotify.com/track/track-2",
                "duration": 200_000,
                "artists": [{"id": "artist-2", "name": "Artist Two"}],
                "album": {"name": "Album Two", "id": "album-2"},
                "imageId": "album-2",
                "explicit": True,
                "isrc": "XYZ789",
            },
        }
        self.playlists = {"album": {}, "playlist": {"abc123": "Chill Picks"}}

    def _loadEntries(self):
        return self.entries

    def _loadTracks(self):
        return self.tracks

    def _loadPlaylists(self):
        return self.playlists

    def playlistName(self, playlistUri):
        if not playlistUri:
            return None
        type_key, playlist_id = playlistUri.split(":", 1)
        return self.playlists[type_key].get(playlist_id)


class EntityPageTests(unittest.TestCase):
    def test_song_detail_context_aggregates_stats(self):
        app = SpotifyDashboardApp.__new__(SpotifyDashboardApp)
        app.database = DummyDatabase()

        context = app._buildSongDetailContext("track-1")

        self.assertEqual(context["entity"]["name"], "Song One")
        self.assertEqual(context["stats"]["plays"], 2)
        self.assertEqual(context["stats"]["totalTimeMs"], 400_000)

    def test_artist_detail_context_lists_related_songs(self):
        app = SpotifyDashboardApp.__new__(SpotifyDashboardApp)
        app.database = DummyDatabase()

        context = app._buildArtistDetailContext("artist-1")

        self.assertEqual(context["entity"]["name"], "Artist One")
        self.assertEqual(context["stats"]["plays"], 2)
        self.assertEqual(len(context["relatedTracks"]), 1)

    def test_playlist_detail_context_uses_playlist_name(self):
        app = SpotifyDashboardApp.__new__(SpotifyDashboardApp)
        app.database = DummyDatabase()

        context = app._buildPlaylistDetailContext("playlist:abc123")

        self.assertEqual(context["entity"]["name"], "Chill Picks")
        self.assertEqual(context["stats"]["plays"], 2)


if __name__ == "__main__":
    unittest.main()
