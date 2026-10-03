"""Resume and verify the core Maple Collections dataset download."""

from pathlib import Path
import shutil
import time
from urllib.request import Request, urlopen

URL = "https://huggingface.co/datasets/nuxsh/maple-collections-hackathon/resolve/main/maple_collections_release.zip"
TARGET = Path(__file__).parent / "maple_data" / "maple_collections_release.zip"
TARGET.parent.mkdir(exist_ok=True)

for attempt in range(1, 21):
    current = TARGET.stat().st_size if TARGET.exists() else 0
    request = Request(URL, headers={"Range": f"bytes={current}-"} if current else {})
    try:
        with urlopen(request, timeout=120) as source:
            status = source.status
            total = source.headers.get("Content-Range", "").split("/")[-1]
            if not total.isdigit():
                total = str(int(source.headers["Content-Length"]) + (current if status == 206 else 0))
            total = int(total)
            if current and status != 206:
                raise RuntimeError("Server did not honor resume request")
            with TARGET.open("ab" if current else "wb") as destination:
                while True:
                    block = source.read(1024 * 1024)
                    if not block:
                        break
                    destination.write(block)
                    current += len(block)
                    if current // (100 * 1024 * 1024) != (current - len(block)) // (100 * 1024 * 1024):
                        print(f"Downloaded {current / 1e9:.2f}/{total / 1e9:.2f} GB", flush=True)
            if current == total:
                print(f"Complete: {TARGET} ({current} bytes)", flush=True)
                break
            raise IOError(f"Incomplete response: {current}/{total}")
    except Exception as exc:
        print(f"Attempt {attempt}: {exc}; resume from {current} bytes", flush=True)
        if attempt == 20:
            raise
        time.sleep(min(30, attempt * 2))
