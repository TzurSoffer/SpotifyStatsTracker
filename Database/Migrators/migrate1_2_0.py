import json
import requests
from PIL import Image
from io import BytesIO
from pathlib import Path

try:
    from Database.Migrators.base import BaseMigrator
except ModuleNotFoundError:
    from Migrators.base import BaseMigrator

class Migrator(BaseMigrator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def checkPreconditions(self):
        super().checkPreconditions()
        if self.tracksPath.exists() == False:
            raise FileExistsError("Tracks file doesn't exist. You might be on an older version.")

    def _loadJsonFile(self, path, default) -> list:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(json.dumps(default, indent=4), encoding="utf-8")
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            path.write_text(json.dumps(default, indent=4), encoding="utf-8")
            return default

    def _getImageUrl(self, id):
        try:
            url = f"https://open.spotify.com/oembed?url=spotify:artist:{id}"
            res = requests.get(url).json()
            return res["thumbnail_url"]
        except:
            return "None"

    def _saveImg(self, path, metadataPath, url, imgId, ids):
        try:
            response = requests.get(url)
            response.raise_for_status()
            img = Image.open(BytesIO(response.content))
            ext = img.format.lower() if img.format else "jpeg"
        except:
            img = Image.open(Path(__file__).parent / "placeholderProfile.jpeg")
            ext = "jpeg"
            print(f"Failed to fetch image for {id}, using placeholder instead")
            
        img.save(path / f"{imgId}.{ext}")
        ids.append(imgId)

        metadataPath.write_text(
            json.dumps(ids, indent=4), encoding="utf-8"
        )

    def migrate(self):
        users = [
            p.name
            for p in (self.baseDir / ".." / "Users").iterdir()
            if p.is_dir()
        ]
        for user in users:
            baseDir = self.baseDir / ".." / "Users" / user
            self.tracksPath =  baseDir / "tracks.json"
            self.checkPreconditions()

            with open(self.tracksPath, "r", encoding="utf-8") as f:
                tracks = json.load(f)
            metadataPath = baseDir / "img" / "artists" / "metadata.json"
            metadataPath.parent.mkdir(parents=True, exist_ok=True)
            ids = self._loadJsonFile(metadataPath, [])
            
            idToImageUrlMap = {}

            for index, id in enumerate(tracks.keys()):
                for i in range(len(tracks[id]["artists"])):
                    artistId = tracks[id]["artists"][i]["url"].split("/")[-1]
                    if artistId in idToImageUrlMap:
                        print(f"Image for {artistId} already downloaded.")
                        imgUrl = idToImageUrlMap[artistId]
                    else:
                        imgUrl = self._getImageUrl(artistId)
                        self._saveImg(metadataPath.parent, metadataPath, imgUrl, artistId, ids)
                        idToImageUrlMap[artistId] = imgUrl
                    tracks[id]["artists"][i]["id"] = artistId
                    tracks[id]["artists"][i]["imageUrl"] = imgUrl

                print(f"Processed {index+1}/{len(tracks)} entries", end="\r")

            with open(self.tracksPath, "w", encoding="utf-8") as f:
                json.dump(tracks, f, indent=4, ensure_ascii=False)
        
        self.updateAppVersion("1.3.0")



if __name__ == "__main__":
    migrator = Migrator()
    result = migrator.migrate()

    print(
        f"Migration complete. "
        f"Created {result['entries']} entries and "
        f"{result['tracks']} unique tracks."
    )