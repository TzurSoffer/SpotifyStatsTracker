import requests
import json
from PIL import Image
from io import BytesIO

from Database.Formatters.spotifyClient import Client

USER = "Tzur"

downloadedImagesPath = f"./img/{USER}/tracks/metadata.json"
with open(downloadedImagesPath, "r") as f:
    downloadedImages = json.load(f)

def saveImg(url, id):
    if id in downloadedImages:
        print(f"Image for {id} already downloaded.")
        return
    try:
        response = requests.get(url)
        response.raise_for_status()
        img = Image.open(BytesIO(response.content))
        ext = img.format.lower() if img.format else "jpg"
        img.save(f"./img/{USER}/tracks/{id}.{ext}")
        downloadedImages.append(id)
        with open(downloadedImagesPath, "w") as f:
            json.dump(downloadedImages, f, indent=4)
    except requests.exceptions.RequestException as e:
        print(f"Error fetching image from {url}: {e}")
    except Exception as e:
        print(f"Error saving image: {e}")

def addToHistoryFromData(meta):
    saveImg(meta["imageUrl"], meta["imageId"])
    with open('history.json', 'r') as f:
        history = json.load(f)
    history.append(meta)
    with open('history.json', 'w') as f:
        json.dump(history, f, indent=4)

def addToHistoryFromTrackData(timestamp, track):
    addToHistoryFromData(Client.formatTrack(timestamp, track))

def addToHistoryFromImport(importedTrack):
    timestamp = importedTrack.get("timestamp", str(datetime.datetime.now().timestamp()))
    meta = Client.formatTrack(timestamp, importedTrack)
    saveImg(meta["imageUrl"], meta["imageId"])
    with open('history.json', 'r') as f:
        history = json.load(f)
    history.append(meta)
    with open('history.json', 'w') as f:
        json.dump(history, f, indent=4)

if __name__ == "__main__":
    import SpotipyFree
    import datetime
    import pysole
    sp = SpotipyFree.Spotify()
    sp.login()

    # pysole.probe(runRemainingCode=True, printStartupCode=True)
    # track = sp.track("67Hna13dNDkZvBpTXRIaOJ")
    with open('track.json', 'r') as f:
        track = json.load(f)
    addToHistoryFromRaw(str(datetime.datetime.now().timestamp()), track)