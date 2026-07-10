import unittest
from unittest.mock import patch, MagicMock, mock_open
import sys
import os
from pathlib import Path

# Ensure we can import app.py
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock database imports to avoid side effects
sys.modules["Database.database"] = MagicMock()
sys.modules["Database.Migrators.migrate"] = MagicMock()
sys.modules["Database.utils"] = MagicMock()
sys.modules["SpotipyFree"] = MagicMock()

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
        self.assertEqual(username, "Tzur")

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

if __name__ == '__main__':
    unittest.main()
