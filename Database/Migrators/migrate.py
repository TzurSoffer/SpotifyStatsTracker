from pathlib import Path

def migrateIfNeeded():
    baseDir = Path(__file__).resolve().parent
    appVersionFile = baseDir / ".." / "VERSION"
    databaseVersionFile = baseDir / ".." / "Users" / "VERSION"
    databaseVersion = databaseVersionFile.read_text().strip()
    appVersion = appVersionFile.read_text().strip()

    while databaseVersion != appVersion:
        if databaseVersion == "1.1.0":
            from Database.Migrators.migrate1_1_0 import Migrator
            Migrator().migrate()
        databaseVersion = databaseVersionFile.read_text().strip()