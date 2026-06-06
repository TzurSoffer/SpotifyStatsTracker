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
        if not self.historyFile.exists():
            raise FileNotFoundError(f"History file not found at {self.historyFile}")
        if self.entriesPath.exists() or self.tracksPath.exists():
            raise FileExistsError("Entries or tracks file already exists. Migration may have already been run.")

    def migrate(self):
        users = [
            p.name
            for p in (self.baseDir / ".." / "Users").iterdir()
            if p.is_dir()
        ]
        for user in users:
            baseDir = self.baseDir / ".." / "Users" / user
            self.entriesPath =  baseDir / "entries.json"
            self.tracksPath = baseDir / "tracks.json"
            self.historyFile = baseDir / "history.json"
            self.checkPreconditions()

            with open(self.historyFile, "r", encoding="utf-8") as f:
                history = json.load(f)

            entries = []
            tracks = {}

            for index, item in enumerate(history):
                trackId = item["id"]

                entries.append({
                    "id": trackId,
                    "playedAt": item.get("playedAt"),
                    "playedAtText": item.get("playedAtText"),
                    "timePlayed": item.get("timePlayed")
                })
                
                if trackId not in tracks:
                    item.pop("playedAt", None)
                    item.pop("playedAtText", None)
                    item.pop("timePlayed", None)

                    tracks[trackId] = item

                print(f"Processed {index+1}/{len(history)} entries", end="\r")

            with open(self.entriesPath, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=4, ensure_ascii=False)

            with open(self.tracksPath, "w", encoding="utf-8") as f:
                json.dump(tracks, f, indent=4, ensure_ascii=False)
        
        self.updateAppVersion("1.1.0")



if __name__ == "__main__":
    migrator = Migrator()
    result = migrator.migrate()

    print(
        f"Migration complete. "
        f"Created {result['entries']} entries and "
        f"{result['tracks']} unique tracks."
    )