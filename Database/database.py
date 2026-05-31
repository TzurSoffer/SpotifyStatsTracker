import requests
import json
from PIL import Image
from io import BytesIO

downloadedImagesPath = "./img/metadata.json"
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
        img.save(f"./img/{id}.{ext}")
        downloadedImages.append(id)
        with open(downloadedImagesPath, "w") as f:
            json.dump(downloadedImages, f, indent=4)
    except requests.exceptions.RequestException as e:
        print(f"Error fetching image from {url}: {e}")
    except Exception as e:
        print(f"Error saving image: {e}")

def formatData(timestamp, track):
    return {"timestamp": timestamp,
            "name": track["name"],
            "id": track["id"],
            "url": track["external_urls"]["spotify"],
            "external_urls": {"spotify": track["external_urls"]["spotify"]},
            "image_url": track["album"]["images"][0]["url"],
            "disc_number": track["disc_number"],
            "track_number": track["track_number"],
            "duration_ms": track["duration_ms"],
            "album": track["album"],
            "explicit": track["explicit"],
            "popularity": track["popularity"],
            "type": track["type"],
            "isrc": track["external_ids"]["isrc"],
            "external_ids": {"isrc": track["external_ids"]["isrc"]},
            }

def addToHistoryFromRaw(timestamp, track):
    meta = formatData(timestamp, track)
    saveImg(meta["image_url"], meta["id"])
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