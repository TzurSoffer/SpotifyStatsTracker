import unittest
from unittest.mock import MagicMock, patch
import threading
import websockets.sync.client
import spotapi.status
import spotapi.websocket


class TestPatches(unittest.TestCase):
    """Verify that monkey-patches are correctly applied to websockets and spotapi."""

    def test_websockets_connect_default_arguments(self):
        """websockets.sync.client.connect should default ping_interval/ping_timeout to None."""
        mock_connect = MagicMock()
        # Temporarily swap the original connect with our mock
        from Database.patches import original_connect
        try:
            with patch("Database.patches.original_connect", mock_connect):
                # When calling websockets.sync.client.connect with some arguments
                websockets.sync.client.connect("wss://example.com", user_agent_header="test-ua")
                
                # Check that original_connect was called with defaults overridden to None
                mock_connect.assert_called_once_with(
                    "wss://example.com",
                    user_agent_header="test-ua",
                    ping_interval=None,
                    ping_timeout=None
                )
        finally:
            pass

    def test_player_status_has_reconnect_method(self):
        """PlayerStatus class must have reconnect method injected."""
        self.assertTrue(hasattr(spotapi.status.PlayerStatus, "reconnect"))
        self.assertTrue(callable(spotapi.status.PlayerStatus.reconnect))

    @patch("websockets.sync.client.connect")
    def test_player_status_reconnect_flow(self, mock_ws_connect):
        """reconnect() must call close on old socket, renew sessions, connect, get init packet, and register."""
        # Create a mock PlayerStatus instance
        self.assertTrue(hasattr(spotapi.status.PlayerStatus, "reconnect"))
        
        # We will mock the required methods/attributes on PlayerStatus
        mock_ws = MagicMock()
        mock_ws_connect.return_value = mock_ws
        
        instance = MagicMock(spec=spotapi.status.PlayerStatus)
        instance.ws = mock_ws
        instance.base = MagicMock()
        
        # When get_init_packet is called, it returns a new connection ID
        instance.get_init_packet.return_value = "new-conn-id"
        
        # Thread status mock
        mock_thread = MagicMock(spec=threading.Thread)
        mock_thread.is_alive.return_value = False
        instance.keep_alive_thread = mock_thread
        
        # Call the reconnect function bound to the instance
        spotapi.status.PlayerStatus.reconnect(instance)
        
        # Verify old websocket is closed
        mock_ws.close.assert_called_once()
        
        # Verify sessions and tokens are renewed
        instance.base.get_session.assert_called_once()
        instance.base.get_client_token.assert_called_once()
        
        # Verify we connect to the new websocket URI
        mock_ws_connect.assert_called_once()
        
        # Verify connection_id was updated
        self.assertEqual(instance.connection_id, "new-conn-id")
        
        # Verify device registration and connection
        instance.register_device.assert_called_once()
        instance.connect_device.assert_called_once()
        
        # Verify keep alive thread was restarted
        mock_thread.is_alive.assert_called_once()

    def test_spotify_init_saves_email(self):
        """SpotipyFree.Spotify should store email on init."""
        import SpotipyFree
        
        # Test with kwarg
        sp1 = SpotipyFree.Spotify(email="user@test.com")
        self.assertEqual(sp1.email, "user@test.com")
        
        # Test with positional arg
        sp2 = SpotipyFree.Spotify(False, False, "dummy.json", "positional@test.com")
        self.assertEqual(sp2.email, "positional@test.com")

    @patch("spotapi.Login.from_saver")
    @patch("builtins.open")
    def test_spotify_login_retrieves_correct_session(self, mock_open, mock_from_saver):
        """SpotipyFree.Spotify.login should select the session matching self.email."""
        import SpotipyFree
        
        # Mock file content
        import json
        mock_file_data = json.dumps([
            {"identifier": "user1@test.com", "cookies": {}},
            {"identifier": "user2@test.com", "cookies": {}}
        ])
        
        mock_open.return_value.__enter__.return_value.read.return_value = mock_file_data
        
        sp = SpotipyFree.Spotify(cookiesFile="cookies.json", email="user2@test.com")
        
        # SpotipyFree.Spotify init might call login internally. Let's force it again to test.
        sp.login("cookies.json")
        
        # The from_saver call should have been called with identifier="user2@test.com"
        mock_from_saver.assert_called_with(unittest.mock.ANY, unittest.mock.ANY, "user2@test.com")

    @patch("spotapi.Login.from_saver")
    @patch("builtins.open")
    def test_spotify_login_fallback_to_first_session(self, mock_open, mock_from_saver):
        """SpotipyFree.Spotify.login should fallback to first session if email is not found."""
        import SpotipyFree
        import json
        
        mock_file_data = json.dumps([
            {"identifier": "user1@test.com", "cookies": {}},
            {"identifier": "user2@test.com", "cookies": {}}
        ])
        
        mock_open.return_value.__enter__.return_value.read.return_value = mock_file_data
        
        # With email not in sessions list
        sp = SpotipyFree.Spotify(cookiesFile="cookies.json", email="unknown@test.com")
        sp.login("cookies.json")
        mock_from_saver.assert_called_with(unittest.mock.ANY, unittest.mock.ANY, "user1@test.com")
        
        # With no email
        sp_no_email = SpotipyFree.Spotify(cookiesFile="cookies.json")
        sp_no_email.login("cookies.json")
        mock_from_saver.assert_called_with(unittest.mock.ANY, unittest.mock.ANY, "user1@test.com")


if __name__ == "__main__":
    unittest.main()

