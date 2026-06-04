import os
import sys
import datetime

def parseError(e):
    excType, excObj, excTb = sys.exc_info()
    fname = os.path.basename(excTb.tb_frame.f_code.co_filename)
    lineno = excTb.tb_lineno
    return(f"{excType.__name__} in {fname} at line {lineno}: {e}")

def convertToDatetime(timestamp):
    try:
        playedAt = datetime.datetime.fromtimestamp(float(timestamp), datetime.timezone.utc)
    except (ValueError, TypeError):
        try:
            dt = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                playedAt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            else:
                playedAt = dt
        except Exception:
            playedAt = datetime.datetime.fromtimestamp(float(timestamp), datetime.timezone.utc)
    return playedAt

def timeToInt(timestampOrStr):
    """ Convert ISO string or datetime to int """
    try:
        return int(float(timestampOrStr))
    except (ValueError, TypeError):
        try:
            dt = datetime.datetime.fromisoformat(timestampOrStr.replace("Z", "+00:00"))
            return int(dt.timestamp())
        except:
            return 0

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

if __name__ == "__main__":
    import pysole
    pysole.probe(runRemainingCode=True)
    print("un = timeToInt('2022-09-22T03:29:43Z')")
    print("dt = convertToDatetime(un)")