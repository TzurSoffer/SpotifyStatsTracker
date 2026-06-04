import json
try:
    from Database.Migrators.base import BaseMigrator
    from Database.utils import msToString
except ModuleNotFoundError:
    from Migrators.base import BaseMigrator
    from utils import msToString

class Migrator(BaseMigrator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def checkPreconditions(self):
        super().checkPreconditions()
        if self.entriesPath.exists() == False:
            raise FileExistsError("Entries file doesn't exist. You might be on an older version.")

    def migrate(self):
        users = [
            p.name
            for p in (self.baseDir / ".." / "Users").iterdir()
            if p.is_dir()
        ]
        for user in users:
            baseDir = self.baseDir / ".." / "Users" / user
            self.entriesPath =  baseDir / "entries.json"
            self.checkPreconditions()

            with open(self.entriesPath, "r") as f:
                entries = json.load(f)

            for index, entry in enumerate(entries):
                entry["timePlayedText"] = msToString(entry["timePlayed"])

                print(f"Processed {index+1}/{len(entries)} entries", end="\r")

            with open(self.entriesPath, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=4, ensure_ascii=False)
        
        self.updateAppVersion("1.2.0")



if __name__ == "__main__":
    migrator = Migrator()
    result = migrator.migrate()

    print(
        f"Migration complete. "
        f"Created {result['entries']} entries and "
        f"{result['tracks']} unique tracks."
    )