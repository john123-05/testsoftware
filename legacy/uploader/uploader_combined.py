import os
import time
import json
import shutil
import hashlib
import fnmatch
import re
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List

from dotenv import load_dotenv
from supabase import create_client
from storage3.exceptions import StorageApiError


# =========================
# ENV / CONFIG
# =========================
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

# Bilder: bisheriger Bucket
IMAGE_BUCKET = os.getenv("IMAGE_BUCKET") or os.getenv("BUCKET")
# Neue Rohdaten: neuer Bucket
DATA_BUCKET = os.getenv("DATA_BUCKET", "daten")

# Bestehende Bildlogik
WEBOUT_DIR = os.getenv("WEBOUT_DIR", r"C:\liftpic\fotos\webout")
OUT_DIR = os.getenv("OUT_DIR", r"C:\liftpic\fotos\out")
TARGET_DIR = os.getenv("TARGET_DIR", r"C:\liftpic\fotos\webout1")

# Falls TARGET_DIR leer ist, als Fallback weiterhin SOURCE_DIR zulassen
LEGACY_SOURCE_DIR = os.getenv("SOURCE_DIR")
if not os.getenv("TARGET_DIR") and LEGACY_SOURCE_DIR:
    TARGET_DIR = LEGACY_SOURCE_DIR

POLL_SECONDS = float(os.getenv("POLL_SECONDS", "2"))
PER_FILE_DELAY = float(os.getenv("PER_FILE_DELAY", "0.2"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "5"))
RETRY_DELAY = float(os.getenv("RETRY_DELAY", "2"))
STATE_FILE = os.getenv("STATE_FILE", "uploader_state.json")

LOOKBACK_SECONDS = float(os.getenv("LOOKBACK_SECONDS", "120"))
MAX_TIME_DELTA_S = float(os.getenv("MAX_TIME_DELTA_S", "10"))
BRIDGE_POLL_SECONDS = float(os.getenv("BRIDGE_POLL_SECONDS", "0.5"))

# Datenquellen
# Append-Dateien = bestehende Datei wächst weiter
APPEND_SOURCES_JSON = os.getenv("APPEND_SOURCES_JSON", "[]")
# File-drop Patterns = neue Dateien kommen in einen Ordner
DROP_SOURCES_JSON = os.getenv("DROP_SOURCES_JSON", "[]")

DEFAULT_APPEND = [
    {"path": r"C:\liftpic\samuel_neu\Statistic.txt", "source_type": "statistic"},
    {"path": r"C:\liftpic\samuel_neu\debug.log", "source_type": "debug"},
    {"path": r"C:\liftpic\samuel_neu\errors.log", "source_type": "errors"},
    {"path": r"C:\liftpic\3GerTis\3gerlog.txt", "source_type": "3gerlog"},
]

DEFAULT_DROP = [
    {"dir": r"C:\liftpic\terminal", "pattern": "ZvtLog_*.txt", "source_type": "zvtlog"},
    {"dir": r"C:\liftpic\samuel_neu\Log", "pattern": "NRI.CoinCharger_*.txt", "source_type": "coincharger"},
]


def _parse_json_list(value: str, fallback: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    value = (value or "").strip()
    if not value:
        return fallback
    try:
        data = json.loads(value)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return fallback


APPEND_SOURCES = _parse_json_list(APPEND_SOURCES_JSON, DEFAULT_APPEND)
DROP_SOURCES = _parse_json_list(DROP_SOURCES_JSON, DEFAULT_DROP)

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL oder SUPABASE_SERVICE_KEY fehlt in .env")
if not IMAGE_BUCKET:
    raise RuntimeError("IMAGE_BUCKET oder BUCKET fehlt in .env")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
os.makedirs(TARGET_DIR, exist_ok=True)


# =========================
# STATE
# =========================

def load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        return {
            "bridge_processed": [],
            "uploaded_images": [],
            "append_offsets": {},
            "drop_uploaded": []
        }
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("bridge_processed", [])
            data.setdefault("uploaded_images", [])
            data.setdefault("append_offsets", {})
            data.setdefault("drop_uploaded", [])
            return data
    except Exception:
        return {
            "bridge_processed": [],
            "uploaded_images": [],
            "append_offsets": {},
            "drop_uploaded": []
        }


STATE = load_state()


def save_state() -> None:
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(STATE, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


# =========================
# HELPERS
# =========================

def now_stamp() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def safe_name(s: str) -> str:
    s = s.replace(":", "_").replace("\\", "_").replace("/", "_")
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s)


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:12]


def is_duplicate_error(e: Exception) -> bool:
    msg = str(e).lower()
    return "duplicate" in msg or "409" in msg or "already exists" in msg


def is_retryable_error(e: Exception) -> bool:
    msg = str(e).lower()
    return any(x in msg for x in [
        "timeout", "readtimeout", "timed out", "502", "503", "504",
        "bad gateway", "service unavailable", "connection reset", "connection aborted"
    ])


def upload_bytes_with_retry(bucket: str, remote_name: str, data: bytes, content_type: str = "text/plain") -> None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            supabase.storage.from_(bucket).upload(
                remote_name,
                data,
                {"content-type": content_type}
            )
            print("Hochgeladen:", bucket, remote_name)
            return
        except StorageApiError as e:
            if is_duplicate_error(e):
                print("Übersprungen (existiert):", bucket, remote_name)
                return
            raise
        except Exception as e:
            if is_duplicate_error(e):
                print("Übersprungen (existiert):", bucket, remote_name)
                return
            if is_retryable_error(e):
                print(f"Retry {attempt}/{MAX_RETRIES}: {bucket}/{remote_name}")
                time.sleep(RETRY_DELAY)
                continue
            raise
    print("Upload dauerhaft fehlgeschlagen:", bucket, remote_name)


def upload_file_with_retry(bucket: str, remote_name: str, local_path: str) -> None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with open(local_path, "rb") as f:
                supabase.storage.from_(bucket).upload(remote_name, f)
            print("Hochgeladen:", bucket, remote_name)
            return
        except StorageApiError as e:
            if is_duplicate_error(e):
                print("Übersprungen (existiert):", bucket, remote_name)
                return
            raise
        except Exception as e:
            if is_duplicate_error(e):
                print("Übersprungen (existiert):", bucket, remote_name)
                return
            if is_retryable_error(e):
                print(f"Retry {attempt}/{MAX_RETRIES}: {bucket}/{remote_name}")
                time.sleep(RETRY_DELAY)
                continue
            raise
    print("Upload dauerhaft fehlgeschlagen:", bucket, remote_name)


def read_text_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


# =========================
# BESTEHENDE BRIDGE-LOGIK
# =========================

def extract_speed_from_out_filename(filename: str) -> Optional[str]:
    base = os.path.splitext(filename)[0]
    if "_" not in base:
        return None
    _, right = base.split("_", 1)
    m = re.search(r"(\d{4})$", right)
    return m.group(1) if m else None


def list_recent_out_files(now_ts: float):
    items = []
    try:
        for fn in os.listdir(OUT_DIR):
            path = os.path.join(OUT_DIR, fn)
            if not os.path.isfile(path):
                continue
            mtime = os.path.getmtime(path)
            if now_ts - mtime > LOOKBACK_SECONDS:
                continue
            speed = extract_speed_from_out_filename(fn)
            if not speed:
                continue
            items.append((path, mtime, speed))
    except FileNotFoundError:
        return []
    return items


def find_nearest_speed(photo_mtime: float) -> Optional[Tuple[str, float]]:
    now_ts = time.time()
    candidates = list_recent_out_files(now_ts)
    if not candidates:
        return None

    best_speed = None
    best_delta = None
    for _, out_mtime, speed in candidates:
        delta = abs(out_mtime - photo_mtime)
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_speed = speed

    if best_delta is None or best_speed is None:
        return None
    if best_delta <= MAX_TIME_DELTA_S:
        return best_speed, best_delta
    return None


def bridge_step() -> None:
    processed = set(STATE["bridge_processed"])
    try:
        for fn in os.listdir(WEBOUT_DIR):
            src = os.path.join(WEBOUT_DIR, fn)
            if not os.path.isfile(src):
                continue
            if fn in processed:
                continue

            try:
                size1 = os.path.getsize(src)
                time.sleep(0.05)
                size2 = os.path.getsize(src)
                if size2 != size1:
                    continue
            except OSError:
                continue

            photo_mtime = os.path.getmtime(src)
            match = find_nearest_speed(photo_mtime)
            if not match:
                continue

            speed, delta = match
            name, ext = os.path.splitext(fn)
            dst_name = f"{name}{speed}{ext}"
            dst = os.path.join(TARGET_DIR, dst_name)
            if not os.path.exists(dst):
                shutil.copy2(src, dst)
                print(f"Bridge: {fn} -> {dst_name} (Δ {delta:.2f}s)")

            processed.add(fn)
            STATE["bridge_processed"] = list(processed)
            save_state()
    except Exception as e:
        print("Bridge error:", e)


# =========================
# BILD-UPLOADER (wie bisher, nur auf TARGET_DIR)
# =========================

def image_upload_step() -> None:
    uploaded = set(STATE["uploaded_images"])
    try:
        for file in os.listdir(TARGET_DIR):
            path = os.path.join(TARGET_DIR, file)
            if not os.path.isfile(path):
                continue
            if file in uploaded:
                continue

            upload_file_with_retry(IMAGE_BUCKET, file, path)
            uploaded.add(file)
            STATE["uploaded_images"] = list(uploaded)
            save_state()
            time.sleep(PER_FILE_DELAY)
    except Exception as e:
        print("Image upload error:", e)


# =========================
# APPEND-ONLY DATEIEN
# =========================

def detect_encoding_and_decode(data: bytes) -> str:
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return data.decode("utf-8", errors="replace")


def upload_append_chunk(path: str, source_type: str, start_offset: int, end_offset: int, chunk_bytes: bytes) -> None:
    base = os.path.basename(path)
    text = detect_encoding_and_decode(chunk_bytes)
    digest = sha1_text(text)
    remote_name = (
        f"append/{source_type}/{safe_name(base)}/"
        f"{now_stamp()}__{start_offset}_{end_offset}__{digest}.txt"
    )
    upload_bytes_with_retry(DATA_BUCKET, remote_name, chunk_bytes, "text/plain")


def upload_snapshot(path: str, source_type: str) -> None:
    base = os.path.basename(path)
    snapshot_name = f"latest/{source_type}/{safe_name(base)}"

    # Snapshot überschreiben: erst löschen versuchen, dann hochladen
    try:
        supabase.storage.from_(DATA_BUCKET).remove([snapshot_name])
    except Exception:
        pass

    raw = read_text_bytes(path)
    upload_bytes_with_retry(DATA_BUCKET, snapshot_name, raw, "text/plain")


def append_sources_step() -> None:
    offsets = STATE["append_offsets"]

    for src in APPEND_SOURCES:
        path = src.get("path")
        source_type = src.get("source_type", "append")
        if not path:
            continue
        if not os.path.exists(path) or not os.path.isfile(path):
            continue

        try:
            current_size = os.path.getsize(path)
            last_offset = int(offsets.get(path, 0))

            # Datei wurde evtl. überschrieben / rotiert
            if current_size < last_offset:
                last_offset = 0

            if current_size == last_offset:
                continue

            with open(path, "rb") as f:
                f.seek(last_offset)
                chunk = f.read(current_size - last_offset)

            if not chunk:
                continue

            upload_append_chunk(path, source_type, last_offset, current_size, chunk)
            upload_snapshot(path, source_type)

            offsets[path] = current_size
            STATE["append_offsets"] = offsets
            save_state()
            print(f"Append erkannt: {path} ({last_offset} -> {current_size})")
            time.sleep(PER_FILE_DELAY)
        except Exception as e:
            print("Append source error:", path, e)


# =========================
# NEUE EINZELDATEIEN IN ORDNERN
# =========================

def drop_sources_step() -> None:
    uploaded = set(STATE["drop_uploaded"])

    for src in DROP_SOURCES:
        directory = src.get("dir")
        pattern = src.get("pattern", "*")
        source_type = src.get("source_type", "drop")
        if not directory or not os.path.isdir(directory):
            continue

        try:
            for name in os.listdir(directory):
                if not fnmatch.fnmatch(name, pattern):
                    continue
                full = os.path.join(directory, name)
                if not os.path.isfile(full):
                    continue

                key = f"{source_type}|{full}"
                if key in uploaded:
                    continue

                remote_name = f"files/{source_type}/{safe_name(name)}"
                upload_file_with_retry(DATA_BUCKET, remote_name, full)
                uploaded.add(key)
                STATE["drop_uploaded"] = list(uploaded)
                save_state()
                time.sleep(PER_FILE_DELAY)
        except Exception as e:
            print("Drop source error:", directory, e)


# =========================
# MAIN LOOP
# =========================

def print_startup() -> None:
    print("Uploader läuft.")
    print("Bridge:", WEBOUT_DIR, "->", TARGET_DIR, "mit OUT:", OUT_DIR)
    print("Bild-Bucket:", IMAGE_BUCKET)
    print("Daten-Bucket:", DATA_BUCKET)
    print("Append-Quellen:")
    for s in APPEND_SOURCES:
        print(" -", s.get("path"), f"[{s.get('source_type', 'append')}]")
    print("Drop-Quellen:")
    for s in DROP_SOURCES:
        print(" -", s.get("dir"), s.get("pattern"), f"[{s.get('source_type', 'drop')}]")


if __name__ == "__main__":
    print_startup()
    while True:
        bridge_step()
        image_upload_step()
        append_sources_step()
        drop_sources_step()
        time.sleep(min(POLL_SECONDS, BRIDGE_POLL_SECONDS))
