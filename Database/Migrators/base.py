from pathlib import Path

class BaseMigrator:
    def __init__(self, *args, **kwargs):
        self.baseDir = Path(__file__).resolve().parent
        self.databaseVersionFile = self.baseDir / ".." / "Users" / "VERSION"
        self.databaseVersion = self.databaseVersionFile.read_text().strip()
        self.appVersionFile = self.baseDir / ".." / "VERSION"
        self.appVersion = self.appVersionFile.read_text().strip()

    def getMiddleVersion(self, version):
        return int(version.split(".")[1])

    def checkPreconditions(self):
        if self.getMiddleVersion(self.databaseVersion)+1 != self.getMiddleVersion(self.appVersion):
            raise Exception("Database and app versions are not compatible. Please run the migrator for the correct version first.")

    def updateAppVersion(self, newVersion):
        self.databaseVersion = newVersion
        self.databaseVersionFile.write_text(newVersion)

    def migrate(self):
        self.checkPreconditions()
