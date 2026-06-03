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
        playedAt = datetime.datetime.fromtimestamp(float(timestamp))
    except ValueError:
        playedAt = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except:
        playedAt = datetime.datetime.fromtimestamp(0)
    return playedAt