import json
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
            raise FileExistsError("Entries file doesn't exist. You might be on an older version.")

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

            for index, key in enumerate(tracks):
                for artist in tracks[key]["artists"]:
                    artist["imageId"] = artist["id"]

                print(f"Processed {index+1}/{len(tracks)} entries", end="\r")

            for index, key in enumerate(tracks):
                tracks[key]["album"]["imageId"] = tracks[key]["album"]["id"]

                print(f"Processed {index+1}/{len(tracks)} entries", end="\r")

            with open(self.tracksPath, "w", encoding="utf-8") as f:
                json.dump(tracks, f, indent=4, ensure_ascii=False)
        
        self.updateAppVersion("1.4.0")



if __name__ == "__main__":
    migrator = Migrator()
    result = migrator.migrate()

    print(
        f"Migration complete. "
        f"Created {result['entries']} entries and "
        f"{result['tracks']} unique tracks."
    )