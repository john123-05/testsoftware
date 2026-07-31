from pathlib import Path

from liftpic_sync.config import Settings
from liftpic_sync.scanner import FolderScanner
from liftpic_sync.state import StateStore


def make_settings(tmp_path: Path) -> Settings:
    raw = tmp_path / "fotos"
    out = raw / "out"
    raw.mkdir()
    out.mkdir()
    return Settings(
        app_name="test",
        shadow_mode=True,
        park_slug="test-park",
        park_id="park-id",
        customer_code="1234",
        machine_id="machine",
        device_token="token",
        supabase_functions_url="http://example.test/functions/v1",
        supabase_url="http://example.test",
        supabase_anon_key="anon",
        raw_dir=raw,
        processed_dir=out,
        webout_dir=None,
        qrcode_dir=None,
        upload_source="all",
        stage_in_shadow=False,
        statistic_file=None,
        print_count_file=None,
        app_dir=tmp_path,
        state_db=tmp_path / "state.db",
        log_dir=tmp_path / "logs",
        poll_seconds=0.1,
        file_stable_seconds=0,
        speed_match_seconds=12,
        speed_timeout_seconds=30,
        upload_retry_seconds=1,
        heartbeat_seconds=60,
        archive_raw=False,
    )


def test_scan_queues_event_with_missing_speed(tmp_path: Path):
    settings = make_settings(tmp_path)
    raw = settings.raw_dir / "00047.jpg"
    raw.write_bytes(b"raw")
    store = StateStore(settings.state_db)
    result = FolderScanner(settings, store).scan_once()
    assert result.queued == 1
    row = store.conn.execute("SELECT * FROM photo_events WHERE capture_id='00047'").fetchone()
    assert row["speed_status"] == "missing"
    assert row["upload_status"] == "queued"


def test_scan_queues_event_with_processed_speed(tmp_path: Path):
    settings = make_settings(tmp_path)
    raw = settings.raw_dir / "00046.jpg"
    raw.write_bytes(b"raw")
    processed = settings.processed_dir / "00046_202607141349431395.jpg"
    processed.write_bytes(b"processed")
    store = StateStore(settings.state_db)
    result = FolderScanner(settings, store).scan_once()
    assert result.queued == 1
    row = store.conn.execute("SELECT * FROM photo_events WHERE capture_id='00046'").fetchone()
    assert row["speed_status"] == "ok"
    assert row["speed_kmh"] == 13.95


def test_scan_keeps_same_capture_id_on_different_days(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = StateStore(settings.state_db)
    scanner = FolderScanner(settings, store)

    day_one = settings.processed_dir / "00047_202607141813242069.jpg"
    day_one.write_bytes(b"day one")
    assert scanner.scan_once().queued == 1
    day_one.unlink()

    day_two = settings.processed_dir / "00047_202607151813242069.jpg"
    day_two.write_bytes(b"day two")
    assert scanner.scan_once().queued == 1

    count = store.conn.execute("SELECT COUNT(*) FROM photo_events WHERE capture_id='00047'").fetchone()[0]
    assert count == 2
    assert len(list(store.due_uploads())) == 2


def test_qrcode_source_uploads_readonly_without_staging(tmp_path: Path):
    raw = tmp_path / "fotos"
    out = raw / "out"
    qrcode = raw / "qrcode"
    webout = raw / "webout"
    for folder in (raw, out, qrcode, webout):
        folder.mkdir(exist_ok=True)
    sold = qrcode / "00047_202607141813242069.jpg"
    sold.write_bytes(b"sold")

    settings = Settings(
        app_name="test",
        shadow_mode=True,
        park_slug="test-park",
        park_id="park-id",
        customer_code="2734",
        machine_id="machine",
        device_token="token",
        supabase_functions_url="http://example.test/functions/v1",
        supabase_url="http://example.test",
        supabase_anon_key="anon",
        raw_dir=raw,
        processed_dir=out,
        webout_dir=webout,
        qrcode_dir=qrcode,
        upload_source="qrcode",
        stage_in_shadow=True,
        statistic_file=None,
        print_count_file=None,
        app_dir=tmp_path,
        state_db=tmp_path / "state-qrcode.db",
        log_dir=tmp_path / "logs",
        poll_seconds=0.1,
        file_stable_seconds=0,
        speed_match_seconds=12,
        speed_timeout_seconds=30,
        upload_retry_seconds=1,
        heartbeat_seconds=60,
        archive_raw=False,
    )
    store = StateStore(settings.state_db)
    result = FolderScanner(settings, store).scan_once()
    # Read-only: the purchased photo is uploaded straight from qrcode; nothing
    # is copied into the customer's webout folder (staged == 0).
    staged = webout / "2443106774002027.jpg"
    assert result.queued == 1
    assert result.staged == 0
    assert not staged.exists()
    row = store.conn.execute("SELECT * FROM photo_events WHERE capture_id='00047'").fetchone()
    # The uploaded name is still the computed legacy filename (server assigns it
    # from metadata), but the local source stays the untouched qrcode file.
    assert row["legacy_filename"] == "2443106774002027.jpg"
    assert row["processed_path"] == str(sold)


def test_scanner_skips_already_uploaded_capture_after_redate(tmp_path: Path):
    """A sold photo that stays in the folder and gets re-touched to a new date
    (jpeg4web) must NOT be re-queued as a phantom next-day duplicate."""
    import os
    import time as _time

    settings = make_settings(tmp_path)
    photo = settings.raw_dir / "00048.jpg"
    photo.write_bytes(b"x")

    store = StateStore(settings.state_db)
    scanner = FolderScanner(settings, store)

    first = scanner.scan_once()
    assert first.queued == 1
    rows = store.conn.execute("SELECT event_key FROM photo_events").fetchall()
    assert len(rows) == 1
    store.mark_uploaded(rows[0]["event_key"], "processed/test/00048.jpg")

    # Simulate the file being re-touched to the next day.
    new_mtime = _time.time() + 86400
    os.utime(photo, (new_mtime, new_mtime))

    second = scanner.scan_once()
    assert second.queued == 0  # already uploaded -> skipped, no phantom duplicate
    assert store.counts().get("queued", 0) == 0
    assert store.photos_sold_total() == 1  # still exactly one event, not two
