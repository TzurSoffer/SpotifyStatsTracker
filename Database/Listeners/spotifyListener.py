import signal
import threading
import time
from contextlib import contextmanager
from SpotipyFree import Spotify
from Database.utils import parseError


@contextmanager
def _suppress_signal_in_thread():
    """Temporarily patch signal.signal to skip SIGINT registration when called
    from a non-main thread (e.g. Flask worker threads). The spotapi library
    unconditionally registers a SIGINT handler in its __init__, which raises
    ValueError on non-main threads."""
    original = signal.signal
    if threading.current_thread() is not threading.main_thread():
        def _patched(signalnum, handler):
            if signalnum == signal.SIGINT:
                return signal.getsignal(signalnum)
            return original(signalnum, handler)
        signal.signal = _patched
    try:
        yield
    finally:
        signal.signal = original


class Listener:
    def __init__(self, cookiesFile, refreshInterval=6, email=None):
        self.run = False
        with _suppress_signal_in_thread():
            self.sp = Spotify(cookiesFile=cookiesFile, email=email)
            self.sp.startRecentlyPlayedListener(refreshInterval=refreshInterval)
        self.recentlyPlayed_Z1 = self.sp.current_user_recently_played()

    def isLoggedIn(self):
        if self.sp.isLoggedIn() == False:
            return False
        try:
            self.sp.current_user()
            return True
        except:
            return False

    def getNewItems(self, new: list):
        oldTimes = [item["played_at"] for item in self.recentlyPlayed_Z1]

        for i, item in enumerate(new):
            # print("Comparing item played at:", item["played_at"], "with old times:", oldTimes)
            if item["played_at"] not in oldTimes:
                return new[i:]

        return None

    def track(self, id):
        return self.sp.track(id)
    
    def playlistName(self, playlistId):
        return self.sp.playlist(playlistId).get("name", "Unknown Playlist")
    def albumName(self, albumId):
        return self.sp.album(albumId).get("name", "Unknown Album")

    def startListener(self, callback):
        self.run = True
        while self.run:
            try:
                recentlyPlayed = self.sp.current_user_recently_played()    #< doesn't trigger any websocket requests (spam safe)
                if recentlyPlayed != self.recentlyPlayed_Z1:
                    callback(self.getNewItems(recentlyPlayed))
                    # print(f"New items found, callback executed. with {self.getNewItems(recentlyPlayed)}")
                    self.recentlyPlayed_Z1 = recentlyPlayed
                time.sleep(1)
            except Exception as e:
                print("Error in listener:", parseError(e))
                time.sleep(30)

    def startListener_thread(self, callback):
        thread = threading.Thread(target=self.startListener, args=(callback,), daemon=True)
        thread.start()
    
    def stop(self):
        self.run = False
