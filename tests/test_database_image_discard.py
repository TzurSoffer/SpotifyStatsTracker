import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import threading
from pathlib import Path
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Database.database import Database

class TestDatabaseImageDiscard(unittest.TestCase):
    def test_download_image_task_discards_id_on_failure(self):
        # Create a bare database instance
        db = Database.__new__(Database)
        db._imageIdsLock = threading.RLock()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            imgDir = Path(tmpdir)
            metadataPath = imgDir / "metadata.json"
            
            cachedSet = {"failed-id"}
            
            # Mock requests.get to raise a RequestException
            with patch("Database.database.requests.get", side_effect=Exception("network error")), \
                 patch("builtins.print"):
                db._downloadImageTask(imgDir, "https://example.com/bad", "failed-id", metadataPath, cachedSet)
                
            # Verify that failed-id was discarded from the set
            self.assertNotIn("failed-id", cachedSet)

if __name__ == "__main__":
    unittest.main()
