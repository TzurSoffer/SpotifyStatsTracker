import json

try:
    from Database.Migrators.base import BaseMigrator
except ModuleNotFoundError:
    from Migrators.base import BaseMigrator

class Migrator(BaseMigrator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.entriesPath = self.baseDir / "Users" / self.user / "entries.json"
        self.tracksPath = self.baseDir / "Users" / self.user / "tracks.json"
        self.historyFile = self.baseDir / "Users" / self.user / "history.json"

    def checkPreconditions(self):
        super().checkPreconditions()
        if not self.historyFile.exists():
            raise FileNotFoundError(f"History file not found at {self.historyFile}")
        if self.entriesPath.exists() or self.tracksPath.exists():
            raise FileExistsError("Entries or tracks file already exists. Migration may have already been run.")

    def migrate(self):
        super().migrate()

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



if __name__ == "__main__":
    migrator = Migrator()
    result = migrator.migrate()

    print(
        f"Migration complete. "
        f"Created {result['entries']} entries and "
        f"{result['tracks']} unique tracks."
    )