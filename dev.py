import time
import requests

def testResponseTime(count=5):
    """
    Test the response time of the Spotify API by making multiple requests and measuring the time taken for each request.
    """
    responseTimes = 0.0
    for _ in range(count):
        start_time = time.time()
        requests.get("http://127.0.0.1:5000/")
        responseTimes += time.time() - start_time

    averageResponseTime = responseTimes / count
    print(f"Average response time over {count} requests: {averageResponseTime:.4f} seconds")
    return averageResponseTime

if __name__ == "__main__":
    import os
    os.environ["IMPORT_KEYWORD"] = "Weekly"
    os.environ["TZ"] = "America/Los_Angeles"

    import pysole
    pysole.probe(runRemainingCode=True, printStartupCode=True, primaryPrompt="[SpotifyStats] ")
    testResponseTime(10)