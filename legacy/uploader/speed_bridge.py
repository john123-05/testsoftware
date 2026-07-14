import os
import time
import shutil
import re
from typing import Optional, Tuple

WEBOUT_DIR = r"C:\liftpic\fotos\webout"
OUT_DIR    = r"C:\liftpic\fotos\out"
TARGET_DIR = r"C:\liftpic\fotos\webout1"

POLL_SECONDS = 0.5

# Matching-Regeln
LOOKBACK_SECONDS = 120
MAX_TIME_DELTA_S = 10.0

os.makedirs(TARGET_DIR, exist_ok=True)

processed = set()


def extract_speed_from_out_filename(filename: str) -> Optional[str]:
    """
    Erwartung: 00016_202602241036236462.jpg
    -> ignoriert alles vor dem ersten "_"
    -> nimmt die letzten 4 Ziffern vom rechten Teil
    """
    base = os.path.splitext(filename)[0]
    if "_" not in base:
        return None

    _, right = base.split("_", 1)
    m = re.search(r"(\d{4})$", right)

    return m.group(1) if m else None


def list_recent_out_files(now: float):
    items = []

    try:
        for fn in os.listdir(OUT_DIR):
            path = os.path.join(OUT_DIR, fn)

            if not os.path.isfile(path):
                continue

            mtime = os.path.getmtime(path)

            if now - mtime > LOOKBACK_SECONDS:
                continue

            speed = extract_speed_from_out_filename(fn)

            if not speed:
                continue

            items.append((path, mtime, speed))

    except FileNotFoundError:
        return []

    return items


def find_nearest_speed(photo_mtime: float) -> Optional[Tuple[str, float]]:
    now = time.time()
    candidates = list_recent_out_files(now)

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
        return (best_speed, best_delta)

    return None


while True:
    try:
        for fn in os.listdir(WEBOUT_DIR):

            src = os.path.join(WEBOUT_DIR, fn)

            if not os.path.isfile(src):
                continue

            if fn in processed:
                continue

            # warten bis Datei stabil ist
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

            # 🔥 HIER OHNE UNTERSTRICH
            dst_name = f"{name}{speed}{ext}"

            dst = os.path.join(TARGET_DIR, dst_name)

            if not os.path.exists(dst):
                shutil.copy2(src, dst)

            processed.add(fn)

            print(f"Bridge: {fn} -> {dst_name} (Δ {delta:.2f}s)")

    except Exception as e:
        print("Bridge error:", e)

    time.sleep(POLL_SECONDS)