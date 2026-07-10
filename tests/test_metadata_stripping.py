import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import threading
from pathlib import Path
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Database.database import Database
from Database.Formatters.spotifyClient import Client
from Database.Importers.StreamingHistoryImporter import Importer

FAKE_TRACK_METADATA = {
    "id": "track999",
    "name": "Metadata Only Song",
    "duration_ms": 180000,
    "external_urls": {"spotify": "https://open.spotify.com/track/track999"},
    "album": {
        "id": "album999",
        "name": "Album Name",
        "external_urls": {"spotify": "https://open.spotify.com/album/album999"},
        "images": [{"url": "https://example.com/img.jpg"}],
        "total_tracks": 12,
        "release_date": "2021-05-05",
        "artists": [{
            "name": "Artist Name",
            "id": "artist999",
            "external_urls": {"spotify": "https://open.spotify.com/artist/artist999"},
        }],
    },
}

class TestMetadataStripping(unittest.TestCase):
    def test_save_new_track_from_id_strips_play_fields(self):
        # Create a bare database instance
        db = Database.__new__(Database)
        db.listener = MagicMock()
        db.listener.track.return_value = FAKE_TRACK_METADATA
        db._saveTracks = MagicMock()
        
        tracks = {}
        db._saveNewTrackFromId("track999", tracks, deferSave=True)
        
        self.assertIn("track999", tracks)
        saved_track = tracks["track999"]
        
        # Verify play-specific fields are NOT present
        self.assertNotIn("playedAt", saved_track)
        self.assertNotIn("timePlayed", saved_track)
        self.assertNotIn("playedFrom", saved_track)

    def test_prefetch_missing_tracks_strips_play_fields(self):
        importer = Importer()
        importer.sp = MagicMock()
        importer.sp.track.return_value = FAKE_TRACK_METADATA
        
        missing_tracks = {
            "track999": ("Metadata Only Song", "Artist Name", "track999")
        }
        known = {}
        
        importer._prefetchMissingTracks(missing_tracks, 0, 1, known, progressCallback=None)
        
        self.assertIn("track999", known)
        cached_track = known["track999"]
        
        # Verify play-specific fields are NOT present in the cache
        self.assertNotIn("playedAt", cached_track)
        self.assertNotIn("timePlayed", cached_track)
        self.assertNotIn("playedFrom", cached_track)

class TestFormatTrackEmbedPlaybackInfo(unittest.TestCase):
    PLAYED_AT = 1620000000
    MS_PLAYED = 120000

    def test_format_track_without_playback_info_omits_play_fields(self):
        track = Client.formatTrack(FAKE_TRACK_METADATA, embedPlaybackInfo=False)

        self.assertNotIn("playedAt", track)
        self.assertNotIn("timePlayed", track)
        self.assertNotIn("playedFrom", track)
        self.assertEqual(track["id"], "track999")
        self.assertEqual(track["name"], "Metadata Only Song")

    def test_format_track_default_embeds_play_fields(self):
        track = Client.formatTrack(FAKE_TRACK_METADATA, self.PLAYED_AT, msPlayed=self.MS_PLAYED)

        self.assertEqual(track["playedAt"], self.PLAYED_AT)
        self.assertEqual(track["timePlayed"], self.MS_PLAYED)
        self.assertIn("playedFrom", track)

    def test_format_track_with_context_missing_uri_returns_none(self):
        contextWithoutUri = {"external_urls": {}}
        self.assertIsNone(Client.formatTrack(FAKE_TRACK_METADATA, self.PLAYED_AT, msPlayed=self.MS_PLAYED, context=contextWithoutUri))

    def test_format_track_with_playlist_context_sets_played_from(self):
        context = {"uri": "spotify:playlist:playlist999"}
        track = Client.formatTrack(FAKE_TRACK_METADATA, self.PLAYED_AT, msPlayed=self.MS_PLAYED, context=context)

        self.assertEqual(track["playedFrom"], "playlist:playlist999")

class TestProcessPlayCaching(unittest.TestCase):
    PLAYED_AT = 1620000000
    MS_PLAYED = 120000

    def test_process_play_caches_track_without_play_fields(self):
        importer = Importer()
        importer.sp = MagicMock()
        importer.sp.track.return_value = FAKE_TRACK_METADATA

        known = {}
        item = ("Metadata Only Song", "Artist Name", self.PLAYED_AT, self.MS_PLAYED, "track999")
        meta = importer._processPlay(item, known)

        # The yielded play carries the playback info
        self.assertEqual(meta["playedAt"], self.PLAYED_AT)
        self.assertEqual(meta["timePlayed"], self.MS_PLAYED)

        # The cached copies do not
        self.assertIn("track999", known)
        self.assertIn("Metadata Only SongArtist Name", known)
        for cached in (known["track999"], known["Metadata Only SongArtist Name"]):
            self.assertNotIn("playedAt", cached)
            self.assertNotIn("timePlayed", cached)
            self.assertNotIn("playedFrom", cached)

if __name__ == "__main__":
    unittest.main()
