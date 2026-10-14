import os
from datetime import datetime
from pathlib import Path

from liftpic_sync.config import Settings
from liftpic_sync.scanner import FolderScanner
from liftpic_sync.state import StateStore


def _write_taken(path: Path, content: bytes, taken: datetime) -> Path:
    """A camera file as it really is on disk: mtime = moment of capture."""
    path.write_bytes(content)
    stamp = taken.timestamp()
    os.utime(path, (stamp, stamp))
    return path


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


def test_statistic_source_resolves_sold_photo_without_speed(tmp_path: Path):
    """Sale software with no qrcode step (Plose): a Statistic.txt sale line
    must resolve back to the raw capture and queue it."""
    from dataclasses import replace

    settings = make_settings(tmp_path)
    settings = replace(
        settings,
        upload_source="statistic",
        statistic_file=tmp_path / "Statistic.txt",
    )
    _write_taken(settings.raw_dir / "00295.jpg", b"raw", datetime(2026, 10, 3, 15, 50))
    settings.statistic_file.write_text(
        "03.10.2026 15:54:57::C:\\liftpic\\fotos\\00295.jpg::3\n",
        encoding="utf-8",
    )

    store = StateStore(settings.state_db)
    result = FolderScanner(settings, store).scan_once()

    assert result.queued == 1
    row = store.conn.execute("SELECT * FROM photo_events WHERE capture_id='00295'").fetchone()
    assert row["speed_status"] == "missing"
    # Without this, liftpic-ingest-commit silently skips writing a claimable
    # photos row at all for statistic-sourced sales (it requires
    # sold_source_path as proof of sale, normally the qrcode folder).
    import json as _json
    assert _json.loads(row["metadata_json"])["sold_source_path"]


def test_statistic_source_resolves_sold_photo_with_speed(tmp_path: Path):
    """A sale line for an even capture (speed camera) must find the
    speed-stamped processed copy, not just the raw file."""
    from dataclasses import replace

    settings = make_settings(tmp_path)
    settings = replace(
        settings,
        upload_source="statistic",
        statistic_file=tmp_path / "Statistic.txt",
    )
    (settings.processed_dir / "00302_202610031538093871.jpg").write_bytes(b"processed")
    settings.statistic_file.write_text(
        "03.10.2026 16:00:28::C:\\liftpic\\fotos\\00302_202610031538093871.jpg::3\n",
        encoding="utf-8",
    )

    store = StateStore(settings.state_db)
    result = FolderScanner(settings, store).scan_once()

    assert result.queued == 1
    row = store.conn.execute("SELECT * FROM photo_events WHERE capture_id='00302'").fetchone()
    assert row["speed_status"] == "ok"
    assert row["speed_kmh"] == 38.71


def test_statistic_source_ignores_unmatched_and_duplicate_lines(tmp_path: Path):
    from dataclasses import replace

    settings = make_settings(tmp_path)
    settings = replace(
        settings,
        upload_source="statistic",
        statistic_file=tmp_path / "Statistic.txt",
    )
    _write_taken(settings.raw_dir / "00295.jpg", b"raw", datetime(2026, 10, 3, 15, 50))
    settings.statistic_file.write_text(
        "\n".join(
            [
                "not a sale line at all",
                "03.10.2026 15:54:57::C:\\liftpic\\fotos\\00295.jpg::3",
                "03.10.2026 15:54:58::C:\\liftpic\\fotos\\00295.jpg::3",  # duplicate
                "03.10.2026 15:55:00::C:\\liftpic\\fotos\\00999.jpg::3",  # file never arrived
            ]
        ),
        encoding="utf-8",
    )

    store = StateStore(settings.state_db)
    result = FolderScanner(settings, store).scan_once()

    assert result.queued == 1  # only the one real, resolvable, non-duplicate sale


def _qrcode_settings(tmp_path: Path) -> Settings:
    from dataclasses import replace

    settings = make_settings(tmp_path)
    qrcode = settings.raw_dir / "qrcode"
    qrcode.mkdir()
    return replace(settings, qrcode_dir=qrcode, upload_source="qrcode")


def test_qrcode_reused_capture_number_on_next_day_is_uploaded(tmp_path: Path):
    """Counter restarts every night (Tarzans, Gruenberg, Plose): 00010 sold
    yesterday must not block today's, different 00010 - not even while
    yesterday's file is still sitting in the same folder."""
    settings = _qrcode_settings(tmp_path)
    store = StateStore(settings.state_db)
    scanner = FolderScanner(settings, store)

    yesterday = settings.qrcode_dir / "00010_202610061106161668.jpg"
    _write_taken(yesterday, b"yesterday's ride", datetime(2026, 10, 6, 11, 6, 16))
    assert scanner.scan_once().queued == 1
    first = store.conn.execute("SELECT event_key FROM photo_events").fetchone()["event_key"]
    store.mark_uploaded(first, "processed/test/a.jpg")

    today = settings.qrcode_dir / "00010_202610071106161668.jpg"
    _write_taken(today, b"today's ride", datetime(2026, 10, 7, 11, 6, 16))
    assert scanner.scan_once().queued == 1

    rows = store.conn.execute(
        "SELECT substr(captured_at, 1, 10) AS day, upload_status FROM photo_events ORDER BY day"
    ).fetchall()
    assert [(r["day"], r["upload_status"]) for r in rows] == [
        ("2026-10-06", "uploaded"),
        ("2026-10-07", "queued"),
    ]
    # Yesterday's file stays known: nothing new on the next pass.
    store.mark_uploaded(
        store.conn.execute("SELECT event_key FROM photo_events WHERE upload_status='queued'").fetchone()["event_key"],
        "processed/test/b.jpg",
    )
    assert scanner.scan_once().queued == 0


def test_qrcode_retouched_sold_photo_is_not_reuploaded(tmp_path: Path):
    settings = _qrcode_settings(tmp_path)
    store = StateStore(settings.state_db)
    scanner = FolderScanner(settings, store)

    sold = _write_taken(settings.qrcode_dir / "72917.jpg", b"sold", datetime(2026, 10, 4, 17, 8))
    assert scanner.scan_once().queued == 1
    key = store.conn.execute("SELECT event_key FROM photo_events").fetchone()["event_key"]
    store.mark_uploaded(key, "processed/test/72917.jpg")

    later = datetime(2026, 10, 5, 8, 0).timestamp()
    os.utime(sold, (later, later))  # jpeg4web re-touch: new mtime, same bytes

    assert scanner.scan_once().queued == 0
    assert store.conn.execute("SELECT COUNT(*) FROM photo_events").fetchone()[0] == 1


def test_statistic_old_sale_line_never_uploads_todays_unsold_photo(tmp_path: Path):
    """Plose: the sale log names 00043.jpg on every day it was sold, but the raw
    folder only ever holds the newest 00043.jpg. An old sale line must not turn
    today's unsold photo into a sale; today's own sale line must upload it."""
    from dataclasses import replace

    settings = replace(
        make_settings(tmp_path),
        upload_source="statistic",
        statistic_file=tmp_path / "Statistic.txt",
    )
    store = StateStore(settings.state_db)
    scanner = FolderScanner(settings, store)
    raw = settings.raw_dir / "00043.jpg"

    _write_taken(raw, b"03.10. ride", datetime(2026, 10, 3, 10, 57, 5))
    settings.statistic_file.write_text(
        "03.10.2026 10:58:00::C:\\liftpic\\fotos\\00043.jpg::3\n", encoding="utf-8"
    )
    assert scanner.scan_once().queued == 1
    key = store.conn.execute("SELECT event_key FROM photo_events").fetchone()["event_key"]
    store.mark_uploaded(key, "processed/test/00043.jpg")

    # Days later the camera overwrites 00043.jpg with a new, unsold ride.
    _write_taken(raw, b"07.10. ride", datetime(2026, 10, 7, 11, 40))
    assert scanner.scan_once().queued == 0

    with settings.statistic_file.open("a", encoding="utf-8") as log:
        log.write("07.10.2026 11:47:58::C:\\liftpic\\fotos\\00043.jpg::3\n")
    assert scanner.scan_once().queued == 1
    row = store.conn.execute(
        "SELECT captured_at FROM photo_events WHERE upload_status='queued'"
    ).fetchone()
    assert row["captured_at"].startswith("2026-10-07")
