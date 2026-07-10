import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import threading
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Other test modules replace Database.database with a MagicMock at import time and
# only restore it in their tearDownModule (which runs after their tests execute, not
# during collection). Since unittest discover imports every test file before running
# any tests, we might see that mock here first - force a real import regardless.
if isinstance(sys.modules.get("Database.database"), MagicMock):
    del sys.modules["Database.database"]

from Database.database import Database


def _bareDatabase():
    """A Database instance with only the state lazyFetchArtistImage needs, skipping
    the heavy __init__ (autoimporter/listener setup) that isn't relevant here."""
    db = Database.__new__(Database)
    db._imageIdsLock = threading.RLock()
    db._artistImageLazyFetchAttempted = set()
    return db


class TestLazyFetchArtistImage(unittest.TestCase):
    def test_returns_true_without_network_call_if_file_already_exists(self):
        db = _bareDatabase()
        with tempfile.TemporaryDirectory() as tmpdir:
            imagePath = Path(tmpdir) / "artist123.jpeg"
            imagePath.write_bytes(b"already-here")

            with patch("Database.database.requests.get") as mock_get:
                result = db.lazyFetchArtistImage("artist123", imagePath)

            self.assertTrue(result)
            mock_get.assert_not_called()

    def test_returns_false_when_artist_id_missing(self):
        db = _bareDatabase()
        with tempfile.TemporaryDirectory() as tmpdir:
            imagePath = Path(tmpdir) / "0.jpeg"
            with patch("Database.database.requests.get") as mock_get:
                result = db.lazyFetchArtistImage("", imagePath)

            self.assertFalse(result)
            mock_get.assert_not_called()

    def test_fetches_and_saves_image_on_first_call(self):
        db = _bareDatabase()
        with tempfile.TemporaryDirectory() as tmpdir:
            imagePath = Path(tmpdir) / "artist123.jpeg"

            pageResponse = MagicMock()
            pageResponse.text = '<meta property="og:image" content="https://example.com/pic.jpg">'
            imageResponse = MagicMock()
            imageResponse.content = b"fake-image-bytes"

            with patch("Database.database.requests.get", side_effect=[pageResponse, imageResponse]) as mock_get:
                result = db.lazyFetchArtistImage("artist123", imagePath)

            self.assertTrue(result)
            self.assertEqual(imagePath.read_bytes(), b"fake-image-bytes")
            self.assertEqual(mock_get.call_count, 2)

    def test_does_not_retry_after_a_failed_attempt_for_same_artist(self):
        """Negative caching: once we've tried (and failed to find an og:image) for an
        artist id, subsequent lookups for that id must not re-hit Spotify."""
        db = _bareDatabase()
        with tempfile.TemporaryDirectory() as tmpdir:
            imagePath = Path(tmpdir) / "missingArtist.jpeg"

            noImageResponse = MagicMock()
            noImageResponse.text = "<html>no og:image here</html>"

            with patch("Database.database.requests.get", return_value=noImageResponse) as mock_get:
                firstResult = db.lazyFetchArtistImage("missingArtist", imagePath)
                secondResult = db.lazyFetchArtistImage("missingArtist", imagePath)

            self.assertFalse(firstResult)
            self.assertFalse(secondResult)
            mock_get.assert_called_once()

    def test_network_exception_is_swallowed_and_returns_false(self):
        db = _bareDatabase()
        with tempfile.TemporaryDirectory() as tmpdir:
            imagePath = Path(tmpdir) / "artist999.jpeg"
            with patch("Database.database.requests.get", side_effect=Exception("boom")):
                result = db.lazyFetchArtistImage("artist999", imagePath)

            self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
