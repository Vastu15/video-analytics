import requests
import os
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

global found_count
# Config
API_TEMPLATE = "https://backend.blackstonemechanical.com/blackstone-new-backend/api/WorkOrders/GetFiles/{}"
API_HEADERS = {
    "x-api-key": "0imfnc8mVLWwsAawjYr4Rx-Af50DDqtlx",
    "User-Agent": "curl/8.0.1",
    "Accept": "*/*",
}
WORKORDER_FILE = "/Users/vastu/Downloads/workorders.txt"
SAVE_DIR = "downloaded_files"
MAX_WITH_FILES = 20
MAX_THREADS = 10  # number of parallel requests

# Ensure save directory exists
os.makedirs(SAVE_DIR, exist_ok=True)

# Shared state for thread safety
found_count = 0
processed_count = 9300
lock = Lock()


def get_files_for_workorder(workorder):
    """Fetch files for a work order; return (workorder, files_list or None)."""
    url = API_TEMPLATE.format(workorder)
    try:
        resp = requests.post(url, headers=API_HEADERS)

        # Debug: print raw content (truncate for readability)
        raw_preview = resp.content[:200]  # first 200 bytes
        print(f"🔍 {workorder} → HTTP {resp.status_code}, Raw: {raw_preview!r}")

        if resp.status_code != 200 or not resp.content.strip():
            return workorder, None
        if "application/json" in resp.headers.get("Content-Type", "").lower():
            return workorder, resp.json()
        return workorder, None
    except Exception as e:
        print(f"❌ Error fetching {workorder}: {e}")
        return workorder, None


def save_files(workorder, files):
    """Save files locally from API response."""
    for idx, f in enumerate(files):
        if "FileUrl" in f:
            try:
                r = requests.get(f["FileUrl"], timeout=20)
                r.raise_for_status()
                ext = os.path.splitext(f["FileUrl"])[1] or ".bin"
                filename = f"{workorder}_{idx}{ext}"
                with open(os.path.join(SAVE_DIR, filename), "wb") as out:
                    out.write(r.content)
            except:
                pass
        elif "FileContent" in f:
            try:
                content = base64.b64decode(f["FileContent"])
                filename = f"{workorder}_{idx}.bin"
                with open(os.path.join(SAVE_DIR, filename), "wb") as out:
                    out.write(content)
            except:
                pass


def process_workorder(workorder):
    """Thread worker: fetch and save files if found."""
    global found_count, processed_count
    wo, data = get_files_for_workorder(workorder)

    # Determine if files exist
    if isinstance(data, dict):
        files = data.get("data") or data.get("files") or []
    elif isinstance(data, list):
        files = data
    else:
        files = []

    with lock:
        processed_count += 1
        if files:
            found_count += 1
            print(
                f"✅ {wo}: {len(files)} files found "
                f"(Found: {found_count}/{MAX_WITH_FILES}, Processed: {processed_count})"
            )
        else:
            print(
                f"❌ {wo}: no files "
                f"(Found: {found_count}/{MAX_WITH_FILES}, Processed: {processed_count})"
            )

    if files:
        save_files(wo, files)


with open(WORKORDER_FILE) as f:
    workorders = [line.strip() for line in f if line.strip()]

workorders = workorders[9300:]

with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
    futures = {executor.submit(process_workorder, wo): wo for wo in workorders}

    for future in as_completed(futures):
        with lock:
            if found_count >= MAX_WITH_FILES:
                break
