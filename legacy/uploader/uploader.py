import os
import time
import json
from supabase import create_client
from dotenv import load_dotenv
from storage3.exceptions import StorageApiError

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
BUCKET = os.getenv("BUCKET")
SOURCE_DIR = os.getenv("SOURCE_DIR")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "5"))

MAX_RETRIES = int(os.getenv("MAX_RETRIES", "5"))
RETRY_DELAY = float(os.getenv("RETRY_DELAY", "2"))
PER_FILE_DELAY = float(os.getenv("PER_FILE_DELAY", "0.2"))

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

print("Uploader läuft. Überwache Ordner:", SOURCE_DIR)

uploaded = set()

def is_duplicate_error(e: Exception) -> bool:
    msg = str(e).lower()
    return (
        "duplicate" in msg
        or "409" in msg
        or "already exists" in msg
    )

def is_retryable_error(e: Exception) -> bool:
    msg = str(e).lower()
    return (
        "timeout" in msg
        or "readtimeout" in msg
        or "timed out" in msg
        or "502" in msg
        or "503" in msg
        or "504" in msg
        or "bad gateway" in msg
        or "service unavailable" in msg
        or isinstance(e, json.JSONDecodeError)
        or "jsondecodeerror" in msg
    )

def upload_with_retry(bucket: str, remote_name: str, local_path: str):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with open(local_path, "rb") as f:
                supabase.storage.from_(bucket).upload(remote_name, f)

            print("Hochgeladen:", remote_name)
            return

        except StorageApiError as e:
            if is_duplicate_error(e):
                print("Übersprungen (existiert):", remote_name)
                return
            raise

        except Exception as e:
            if is_duplicate_error(e):
                print("Übersprungen (existiert):", remote_name)
                return

            if is_retryable_error(e):
                print(f"Retry {attempt}/{MAX_RETRIES} wegen Netzwerk/Server-Problem:", remote_name)
                time.sleep(RETRY_DELAY)
                continue

            raise

    print("Upload dauerhaft fehlgeschlagen:", remote_name)

while True:
    for file in os.listdir(SOURCE_DIR):
        if file in uploaded:
            continue

        path = os.path.join(SOURCE_DIR, file)
        if not os.path.isfile(path):
            continue

        upload_with_retry(BUCKET, file, path)

        uploaded.add(file)
        time.sleep(PER_FILE_DELAY)

    time.sleep(POLL_SECONDS)
