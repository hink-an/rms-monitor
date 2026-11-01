# RMS Official Source Connection Test
# Read-only test: no files are modified.

import urllib.request
import urllib.error
from datetime import datetime, timezone

SOURCES = {
    "Ministry of the Environment": "https://www.env.go.jp/",
    "Ministry of Health, Labour and Welfare": "https://www.mhlw.go.jp/",
}

def check_source(name, url):
    print("--------------------------------")
    print("Source:", name)
    print("URL:", url)

    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 RMS-Source-Check/1.0"
            }
        )

        with urllib.request.urlopen(
            request, timeout=15
        ) as response:

            status = response.status
            data = response.read(4096)

            print("HTTP Status:", status)
            print("Data received:", len(data), "bytes")

            if status == 200 and len(data) > 0:
                print("Connection: SUCCESS")
            else:
                print("Connection: CHECK REQUIRED")

    except Exception as error:
        print("Connection: FAILED")
        print("Reason:", str(error))


def main():
    print("RMS Official Source Connection Test")
    print("UTC:", datetime.now(timezone.utc).isoformat())

    for name, url in SOURCES.items():
        check_source(name, url)

    print("--------------------------------")
    print("Test completed.")
    print("No RMS data was modified.")


if __name__ == "__main__":
    main()
