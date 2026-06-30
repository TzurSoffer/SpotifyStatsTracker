import os
import sys
import traceback
import datetime
from zoneinfo import ZoneInfo

DATE_FORMATS = ("%Y-%m-%d", "%Y-%m", "%Y")

## TIMEZONE SETUP
try:
    tzName = os.environ.get("TZ")
    tz = datetime.datetime.now().astimezone().tzinfo
    if tzName:
        tz = ZoneInfo(tzName)
except Exception:
    print("Failed to get timezone from environment variable 'TZ'. Using UTC instead.")
    tz = datetime.timezone.utc

print("Using timezone:", tzName)


## ERROR PRINTING
def parseError(e):
    _, _, excTb = sys.exc_info()
    summary = traceback.extract_tb(excTb)

    if summary:
        lastFrame = summary[-1]
        fname = os.path.basename(lastFrame.filename)
        lineno = lastFrame.lineno
        funcName = lastFrame.name
        codeLine = lastFrame.line

        return f"{type(e).__name__} in {fname} -> {funcName}() at line {lineno}: '{codeLine}' -> Error: {e}"

    return f"{type(e).__name__}: {e}"


## DATETIME RELATED
def fromtimestamp(ts, tz=None):
    """
    Cross-platform safe timestamp conversion.
    Windows cannot handle negative timestamps, so we manually offset from epoch.
    """
    if tz is None:
        tz = datetime.timezone.utc

    try:
        # Works on Linux/macOS
        return datetime.datetime.fromtimestamp(ts, tz=tz)
    except (OSError, ValueError):
        # Windows fallback for negative timestamps
        epoch = datetime.datetime(1970, 1, 1, tzinfo=tz)
        return epoch + datetime.timedelta(seconds=ts)

def epoch():
    return fromtimestamp(0, tz=tz)

def parseIsoDatetime(value):
    """
    Handles ISO strings, including those ending with Z.
    """
    value = str(value).replace("Z", "+00:00")
    return datetime.datetime.fromisoformat(value)

def getTimezone():
    return tz

def now():
    return datetime.datetime.now(tz=tz)

def toTimezone(dt: datetime.datetime, tz=None):
    if tz is None:
        tz = getTimezone()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def startOfDay(dt: datetime.datetime = None):
    dt = toTimezone(dt or now())
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def parseDateString(dateText: str):
    for fmt in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(str(dateText), fmt).replace(tzinfo=tz)
        except ValueError:
            pass
    return None

def parseDatetime(value):
    try:
        return toTimezone(parseIsoDatetime(value), tz)
    except Exception:
        return parseDateString(value)

def convertToDatetime(timestamp):
    """
    Converts:
    - datetime → normalized
    - numeric timestamp → safe conversion
    - ISO string → parsed
    - date-only string → parsed
    - "0000-00-00" → epoch
    - invalid → epoch
    """
    if isinstance(timestamp, datetime.datetime):
        return toTimezone(timestamp)

    try:
        return fromtimestamp(float(timestamp), tz=tz)
    except (ValueError, TypeError):
        pass

    if timestamp == "0000-00-00":
        return epoch()

    parsed = parseDatetime(timestamp)
    return parsed if parsed is not None else epoch()

def dateToString(timestamp):
    if type(timestamp) in (float, int):
        timestamp = fromtimestamp(timestamp, tz=tz)
    elif type(timestamp) != datetime.datetime:
        timestamp = convertToDatetime(timestamp)

    timestamp = toTimezone(timestamp)
    return timestamp.strftime("%Y-%m-%d")

def timeToInt(timestampOrStr):
    """
    Converts datetime or string to integer timestamp.
    Handles negative timestamps safely.
    """
    if type(timestampOrStr) == datetime.datetime:
        return int(toTimezone(timestampOrStr).timestamp())

    try:
        return int(float(timestampOrStr))
    except (ValueError, TypeError):
        pass

    parsed = parseDatetime(timestampOrStr)
    return int(parsed.timestamp()) if parsed else 0

def msToString(ms: int | float) -> str:
    """ Converts milliseconds into a human-readable duration string. """
    if ms is None or ms <= 0:
        return "0ms"

    totalSeconds = int(ms) // 1000

    seconds = totalSeconds % 60
    minutes = (totalSeconds // 60) % 60
    hours = totalSeconds // 3600

    parts = []

    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0 or hours > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or minutes > 0 or hours > 0:
        parts.append(f"{seconds}s")

    return " ".join(parts)

def formatDuration(ms: int) -> str:
    seconds = max(0, ms // 1000)
    minutes = seconds // 60
    remaining = seconds % 60
    return f"{minutes}:{remaining:02d}"

def versionTuple(version: str) -> tuple:
    """ Can be used to compare versions with > and < """
    return tuple(int(x) for x in version.split("."))

if __name__ == "__main__":
    import pysole
    pysole.probe(runRemainingCode=True)
    print("un = timeToInt('2022-09-22T03:29:43Z')")
    print("dt = convertToDatetime(un)")
