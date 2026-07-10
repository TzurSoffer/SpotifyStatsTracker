import unittest
from unittest.mock import patch, MagicMock, mock_open
import sys
import os
from pathlib import Path

# Ensure we can import app.py
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Backup original modules before we mock them
_original_modules = {}
for m in ["Database.database", "Database.Migrators.migrate", "Database.utils"]:
    if m in sys.modules:
        _original_modules[m] = sys.modules[m]

# Mock database imports to avoid side effects
sys.modules["Database.database"] = MagicMock()
sys.modules["Database.Migrators.migrate"] = MagicMock()
sys.modules["Database.utils"] = MagicMock()

def tearDownModule():
    # Restore original modules so we don't pollute other tests
    for m in ["Database.database", "Database.Migrators.migrate", "Database.utils"]:
        if m in _original_modules:
            sys.modules[m] = _original_modules[m]
        elif m in sys.modules:
            del sys.modules[m]

from app import SpotifyDashboardApp

class TestMultiUser(unittest.TestCase):
    @patch('app.SpotifyDashboardApp.startVersionCheck_thread')
    @patch('app.SpotifyDashboardApp.checkLogin_thread')
    @patch('app.migrateIfNeeded')
    @patch('app.Path.exists')
    @patch('app.Path.read_text')
    def test_get_username_for_email_timorzipa(self, mock_read_text, mock_exists, mock_migrate, mock_check, mock_version):
        # Mock secrets map not existing
        mock_exists.return_value = False
        app = SpotifyDashboardApp()
        username = app.get_username_for_email("timorzipa@gmail.com")
        self.assertIsNone(username)

    @patch('app.SpotifyDashboardApp.startVersionCheck_thread')
    @patch('app.SpotifyDashboardApp.checkLogin_thread')
    @patch('app.migrateIfNeeded')
    @patch('app.Path.exists')
    @patch('app.Path.read_text')
    def test_get_username_for_email_from_map(self, mock_read_text, mock_exists, mock_migrate, mock_check, mock_version):
        mock_exists.return_value = True
        mock_read_text.return_value = '{"test@example.com": "test_user"}'
        
        app = SpotifyDashboardApp()
        username = app.get_username_for_email("test@example.com")
        self.assertEqual(username, "test_user")

    @patch('app.SpotifyDashboardApp.startVersionCheck_thread')
    @patch('app.SpotifyDashboardApp.checkLogin_thread')
    @patch('app.migrateIfNeeded')
    @patch('app.Path.exists')
    @patch('app.Path.mkdir')
    @patch('app.Path.write_text')
    def test_get_or_create_user(self, mock_write_text, mock_mkdir, mock_exists, mock_migrate, mock_check, mock_version):
        # Everything does not exist
        mock_exists.return_value = False
        app = SpotifyDashboardApp()
        
        username = app.get_or_create_user("john.doe@test.com")
        self.assertEqual(username, "johndoe")

    @patch('app.SpotifyDashboardApp.startVersionCheck_thread')
    @patch('app.SpotifyDashboardApp.checkLogin_thread')
    @patch('app.migrateIfNeeded')
    @patch('app.Path.exists')
    def test_get_user_db_cache(self, mock_exists, mock_migrate, mock_check, mock_version):
        mock_exists.return_value = False
        app = SpotifyDashboardApp()
        
        db1 = app.get_user_db("Tzur", "timorzipa@gmail.com")
        db2 = app.get_user_db("Tzur", "timorzipa@gmail.com")
        
        self.assertIs(db1, db2) # Should be the exact same object from cache

    @patch('app.SpotifyDashboardApp.startVersionCheck_thread')
    @patch('app.SpotifyDashboardApp.checkLogin_thread')
    @patch('app.migrateIfNeeded')
    def test_migrate_legacy_database(self, mock_migrate, mock_check, mock_version):
        import tempfile
        import shutil
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            app = SpotifyDashboardApp()
            app.baseDir = tmp_path
            
            # Create a legacy directory with entries.json
            legacy_dir = tmp_path / "Database" / "Users" / "Tzur"
            legacy_dir.mkdir(parents=True, exist_ok=True)
            legacy_entries = legacy_dir / "entries.json"
            legacy_entries.write_text('[{"id": "track_1"}]', encoding="utf-8")
            
            # Run migration to target "timorzipa"
            app._migrate_legacy_database_if_needed("timorzipa")
            
            # Target directory should now exist and have the copied entries.json
            target_dir = tmp_path / "Database" / "Users" / "timorzipa"
            target_entries = target_dir / "entries.json"
            
            self.assertTrue(target_entries.exists())
            self.assertEqual(target_entries.read_text(encoding="utf-8"), '[{"id": "track_1"}]')
            
            # Legacy directory should be removed/cleaned up
            self.assertFalse(legacy_dir.exists())

    def test_get_or_create_secret_key_persists_random_value(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            dash = SpotifyDashboardApp.__new__(SpotifyDashboardApp)
            dash.baseDir = Path(tmpdir)

            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("FLASK_SECRET_KEY", None)
                key1 = dash._get_or_create_secret_key()
                key2 = dash._get_or_create_secret_key()

            self.assertEqual(key1, key2)
            self.assertNotEqual(key1, "spotify-stats-tracker-secret")
            self.assertGreaterEqual(len(key1), 32)

    def test_get_or_create_secret_key_prefers_env_var(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            dash = SpotifyDashboardApp.__new__(SpotifyDashboardApp)
            dash.baseDir = Path(tmpdir)

            with patch.dict(os.environ, {"FLASK_SECRET_KEY": "my-env-secret"}):
                key = dash._get_or_create_secret_key()

            self.assertEqual(key, "my-env-secret")


class TestImageRouteAuthorization(unittest.TestCase):
    @patch('app.SpotifyDashboardApp.startVersionCheck_thread')
    @patch('app.SpotifyDashboardApp.checkLogin_thread')
    @patch('app.migrateIfNeeded')
    @patch('app.Path.exists')
    def _makeApp(self, mock_exists, mock_migrate, mock_check, mock_version):
        mock_exists.return_value = False
        return SpotifyDashboardApp()

    def test_serve_track_image_denies_mismatched_user(self):
        dash = self._makeApp()
        client = dash.app.test_client()
        with patch.object(dash, 'is_user_logged_in', return_value=True), \
             patch.object(dash, 'get_username_for_email', return_value='alice'):
            with client.session_transaction() as sess:
                sess['email'] = 'alice@example.com'
            resp = client.get('/img/bob/tracks/1.jpeg')
        self.assertEqual(resp.status_code, 404)

    def test_serve_track_image_denies_unauthenticated(self):
        dash = self._makeApp()
        client = dash.app.test_client()
        with patch.object(dash, 'is_user_logged_in', return_value=False):
            resp = client.get('/img/alice/tracks/1.jpeg')
        self.assertEqual(resp.status_code, 404)

    @patch('app.send_from_directory')
    def test_serve_track_image_allows_matching_user(self, mock_send):
        mock_send.return_value = "OK"
        dash = self._makeApp()
        client = dash.app.test_client()
        with patch.object(dash, 'is_user_logged_in', return_value=True), \
             patch.object(dash, 'get_username_for_email', return_value='alice'):
            with client.session_transaction() as sess:
                sess['email'] = 'alice@example.com'
            resp = client.get('/img/alice/tracks/1.jpeg')
        self.assertEqual(resp.status_code, 200)
        mock_send.assert_called_once()

    def test_serve_artist_image_denies_mismatched_user(self):
        dash = self._makeApp()
        client = dash.app.test_client()
        with patch.object(dash, 'is_user_logged_in', return_value=True), \
             patch.object(dash, 'get_username_for_email', return_value='alice'):
            with client.session_transaction() as sess:
                sess['email'] = 'alice@example.com'
            resp = client.get('/img/bob/artists/1.jpeg')
        self.assertEqual(resp.status_code, 404)

    def test_serve_image_rejects_path_traversal_filename(self):
        dash = self._makeApp()
        client = dash.app.test_client()
        with patch.object(dash, 'is_user_logged_in', return_value=True), \
             patch.object(dash, 'get_username_for_email', return_value='alice'):
            with client.session_transaction() as sess:
                sess['email'] = 'alice@example.com'
            resp = client.get('/img/alice/tracks/..%5C..%5Csecret.txt')
        self.assertEqual(resp.status_code, 404)


if __name__ == '__main__':
    unittest.main()
