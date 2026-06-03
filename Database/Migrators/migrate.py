from pathlib import Path
import importlib.util

def getMiddleVersion(version):
    return int(version.split(".")[1])

def migrateIfNeeded():
    baseDir = Path(__file__).resolve().parent
    appVersionFile = baseDir / ".." / "VERSION"
    appVersion = appVersionFile.read_text().strip()
    databaseVersionFile = baseDir / ".." / "Users" / "VERSION"
    if databaseVersionFile.exists() == False:
        databaseVersionFile.write_text(appVersion)
        return   #< means this is first run, no migration needed
    databaseVersion = databaseVersionFile.read_text().strip()

    while getMiddleVersion(databaseVersion) != getMiddleVersion(appVersion):
        if databaseVersion == "1.0.0":
            print("Migrating from version 1.0.0")

            modulePath = baseDir / "migrate1_0_0.py"

            spec = importlib.util.spec_from_file_location("migrate1_0_0", modulePath)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            Migrator = module.Migrator
            Migrator().migrate()
        databaseVersion = databaseVersionFile.read_text().strip()