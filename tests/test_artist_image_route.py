import unittest
from unittest.mock import patch, MagicMock
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

_original_modules = {}
for m in ["Database.database", "Database.Migrators.migrate", "Database.utils", "SpotipyFree"]:
    if m in sys.modules:
        _original_modules[m] = sys.modules[m]

sys.modules["Database.database"] = MagicMock()
sys.modules["Database.Migrators.migrate"] = MagicMock()
sys.modules["Database.utils"] = MagicMock()
sys.modules["SpotipyFree"] = MagicMock()


def tearDownModule():
    for m in ["Database.database", "Database.Migrators.migrate", "Database.utils", "SpotipyFree"]:
        if m in _original_modules:
            sys.modules[m] = _original_modules[m]
        elif m in sys.modules:
            del sys.modules[m]


from app import SpotifyDashboardApp


class TestServeArtistImageRoute(unittest.TestCase):
    @patch('app.SpotifyDashboardApp.startVersionCheck_thread')
    @patch('app.SpotifyDashboardApp.checkLogin_thread')
    @patch('app.migrateIfNeeded')
    @patch('app.Path.exists')
    def _makeApp(self, mock_exists, mock_migrate, mock_check, mock_version):
        mock_exists.return_value = False
        return SpotifyDashboardApp()

    @patch('app.send_from_directory')
    @patch('app.os.path.exists')
    def test_delegates_lazy_fetch_to_the_cached_user_database(self, mock_path_exists, mock_send):
        """The route must not reimplement the scrape itself; it should delegate to the
        already-instantiated Database for that user so the fetch is deduplicated
        instead of duplicating the download logic inline."""
        mock_path_exists.return_value = False
        mock_send.return_value = "OK"

        dash = self._makeApp()
        fakeDb = MagicMock()
        dash.user_databases["alice"] = fakeDb

        client = dash.app.test_client()
        resp = client.get('/img/alice/artists/artist123.jpeg')

        self.assertEqual(resp.status_code, 200)
        fakeDb.lazyFetchArtistImage.assert_called_once()
        calledArtistId, calledPath = fakeDb.lazyFetchArtistImage.call_args[0]
        self.assertEqual(calledArtistId, "artist123")
        self.assertTrue(str(calledPath).endswith(os.path.join("alice", "img", "artists", "artist123.jpeg")))

    @patch('app.send_from_directory')
    @patch('app.os.path.exists')
    def test_skips_lazy_fetch_when_file_already_present(self, mock_path_exists, mock_send):
        mock_path_exists.return_value = True
        mock_send.return_value = "OK"

        dash = self._makeApp()
        fakeDb = MagicMock()
        dash.user_databases["alice"] = fakeDb

        client = dash.app.test_client()
        resp = client.get('/img/alice/artists/artist123.jpeg')

        self.assertEqual(resp.status_code, 200)
        fakeDb.lazyFetchArtistImage.assert_not_called()

    @patch('app.send_from_directory')
    @patch('app.os.path.exists')
    def test_serves_existing_file_without_error_when_no_database_cached_yet(self, mock_path_exists, mock_send):
        """If no Database has been instantiated for this username (e.g. server just
        restarted), the route must not crash - it just skips the lazy fetch."""
        mock_path_exists.return_value = False
        mock_send.return_value = "OK"

        dash = self._makeApp()

        client = dash.app.test_client()
        resp = client.get('/img/unknown_user/artists/artist123.jpeg')

        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
