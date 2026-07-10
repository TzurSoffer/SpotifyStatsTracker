import unittest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Database.Importers.AutoImporter import Watchdog


class TestWatchdogThread(unittest.TestCase):
    @patch("Database.Importers.AutoImporter.threading.Thread")
    def test_watch_folder_starts_a_daemon_thread(self, mock_thread_cls):
        """The watcher thread must be a daemon thread, or a graceful shutdown of the
        Flask process (Ctrl+C / SIGTERM) hangs forever waiting for its infinite
        polling loop to finish - which it never does on its own."""
        mock_thread_instance = MagicMock()
        mock_thread_cls.return_value = mock_thread_instance

        watchdog = Watchdog()
        watchdog.watchFolder("some/path", callback=lambda path: None, checkInterval=5)

        mock_thread_cls.assert_called_once()
        _, kwargs = mock_thread_cls.call_args
        self.assertTrue(kwargs.get("daemon"), "Watchdog thread must be created with daemon=True")
        mock_thread_instance.start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
