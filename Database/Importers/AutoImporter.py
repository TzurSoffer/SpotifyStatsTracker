import os
import time
import threading
import shutil

try:
    from Database.utils import parseError
except ModuleNotFoundError:
    import sys
    folderPath = "../"
    if folderPath not in sys.path:
        sys.path.append(folderPath)
    from utils import parseError

class Watchdog:
    def __init__(self):
        self.run = True

    def watchFolder_blocking(self, pathToWatch, callback, checkInterval=5, callbackInitialFiles=True):
        print(f"Monitoring {pathToWatch} for new files (Polling)...")
        if not os.path.exists(pathToWatch):
            os.makedirs(pathToWatch)
        try:
            filesBefore = {f for f in os.listdir(pathToWatch) if os.path.isfile(os.path.join(pathToWatch, f))}
            if callbackInitialFiles:
                for path in filesBefore:
                    fullPath = os.path.join(pathToWatch, path)
                    print(f"File found: {fullPath}")
                    callback(fullPath)
        except FileNotFoundError:
            print(f"Error: The directory {pathToWatch} does not exist.")
            return
        try:
            while self.run:
                time.sleep(checkInterval)
                filesAfter = {f for f in os.listdir(pathToWatch) if os.path.isfile(os.path.join(pathToWatch, f))}
                filesAdded = filesAfter - filesBefore
                
                if filesAdded:
                    for targetFile in filesAdded:
                        fullPath = os.path.join(pathToWatch, targetFile)
                        print(f"New file created: {fullPath}")
                        callback(fullPath)
                filesBefore = filesAfter
            print("Watchdog stopped peacefully")

        except Exception as e:
            print(f"\nStopping monitor... {parseError(e)}")

    def watchFolder(self, pathToWatch, callback, checkInterval=5):
        threading.Thread(target=self.watchFolder_blocking, args=(pathToWatch, callback, checkInterval), daemon=True).start()
    
    def stop(self):
        self.run = False

class AutoImporter:
    def __init__(self, folderPath, importCallback, pollInterval=5, keyword=None):
        self.folderPath = folderPath
        self.pollInterval = pollInterval
        self.importCallback = importCallback
        self.keyword = keyword
        self.wd = Watchdog()

    def _handleImport(self, path):
        try:
            fileDirectory = os.path.dirname(path)
            fileName = os.path.basename(path)
            doneDirectory = os.path.join(fileDirectory, "DONE")
            if not os.path.exists(doneDirectory):
                os.makedirs(doneDirectory)
                print(f"Created directory: {doneDirectory}")
            destinationPath = os.path.join(doneDirectory, fileName)

            if self.keyword is not None and self.keyword not in fileName:
                print(f"Keyword '{self.keyword}' not found in '{fileName}'. Skipping import and moving directly to DONE.")
            else:
                # Import the file normally if keyword matches or keyword is None
                with open(path, "r", encoding="utf-8") as f:
                    self.importCallback(f.read())
                print(f"Successfully imported {fileName}")

            shutil.move(path, destinationPath)
            print(f"Successfully moved {fileName} to DONE/")
            
        except Exception as e:
            print(f"Error importing file {path}: {e}")

    def start(self):
        self.wd.watchFolder(self.folderPath, self._handleImport, self.pollInterval)


if __name__ == "__main__":
    autoImporter = AutoImporter("../../autoImport", print, pollInterval=1, keyword="Weekly")
    autoImporter.start()