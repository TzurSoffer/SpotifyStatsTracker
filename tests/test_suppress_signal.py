"""Tests for the _suppress_signal_in_thread context manager in spotifyListener."""
import signal
import threading
import unittest
from unittest.mock import patch, MagicMock

from Database.Listeners.spotifyListener import _suppress_signal_in_thread


class TestSuppressSignalInThread(unittest.TestCase):
    """Verify that _suppress_signal_in_thread correctly patches signal.signal
    when running on a non-main thread and is a no-op on the main thread."""

    def test_main_thread_does_not_patch(self):
        """On the main thread the context manager should not alter signal.signal."""
        original = signal.signal
        with _suppress_signal_in_thread():
            self.assertIs(signal.signal, original)
        self.assertIs(signal.signal, original)

    def test_worker_thread_suppresses_sigint(self):
        """On a worker thread, SIGINT registration should be silently skipped."""
        results = {}

        def _run():
            with _suppress_signal_in_thread():
                # Attempt to register a SIGINT handler – should NOT raise
                try:
                    ret = signal.signal(signal.SIGINT, signal.SIG_DFL)
                    results["raised"] = False
                    results["returned"] = ret
                except ValueError:
                    results["raised"] = True

        t = threading.Thread(target=_run)
        t.start()
        t.join()

        self.assertFalse(results.get("raised", True),
                         "signal.signal(SIGINT, ...) should not raise in the patched context")

    def test_worker_thread_allows_non_sigint(self):
        """On a worker thread, non-SIGINT signals should still go through
        the original signal.signal (which will raise on non-main thread)."""
        results = {}

        def _run():
            with _suppress_signal_in_thread():
                try:
                    # SIGTERM registration should still hit the real signal.signal
                    signal.signal(signal.SIGTERM, signal.SIG_DFL)
                    results["raised"] = False
                except ValueError:
                    # Expected: real signal.signal raises on non-main thread
                    results["raised"] = True

        t = threading.Thread(target=_run)
        t.start()
        t.join()

        self.assertTrue(results.get("raised", False),
                        "non-SIGINT signals should still go through original signal.signal")

    def test_signal_restored_after_context(self):
        """signal.signal should be restored to its original value after the
        context manager exits, even on a worker thread."""
        results = {}

        def _run():
            original = signal.signal
            with _suppress_signal_in_thread():
                pass
            results["restored"] = signal.signal is original

        t = threading.Thread(target=_run)
        t.start()
        t.join()

        self.assertTrue(results.get("restored", False),
                        "signal.signal should be restored after context exit")

    def test_signal_restored_on_exception(self):
        """signal.signal should be restored even if an exception occurs inside
        the context manager."""
        results = {}

        def _run():
            original = signal.signal
            try:
                with _suppress_signal_in_thread():
                    raise RuntimeError("boom")
            except RuntimeError:
                pass
            results["restored"] = signal.signal is original

        t = threading.Thread(target=_run)
        t.start()
        t.join()

        self.assertTrue(results.get("restored", False),
                        "signal.signal should be restored after exception")


if __name__ == "__main__":
    unittest.main()
