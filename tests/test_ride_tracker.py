from pathlib import Path

from liftpic_sync.config import Settings
from liftpic_sync.ride_tracker import RideTracker
from liftpic_sync.state import PhotoEvent, StateStore


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
        upload_source="qrcode",
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
        camera_code="cam1",
    )


def test_ride_tracker_dedupes_raw_and_processed(tmp_path: Path):
    settings = make_settings(tmp_path)
    raw = settings.raw_dir / "00047.jpg"
    raw.write_bytes(b"raw")
    processed = settings.processed_dir / "00047_202607141813242069.jpg"
    processed.write_bytes(b"processed")

    store = StateStore(settings.state_db)
    tracker = RideTracker(settings, store)

    result = tracker.scan_once()
    # The capture is counted once from the first file seen; the same capture_id
    # in the other folder is skipped (stable per-capture dedup).
    assert result.seen == 1
    assert result.new == 1
    assert store.ride_counts() == {"2026-07-14": 1}

    second = tracker.scan_once()
    # Already counted -> skipped entirely, never recounted (even on a later day).
    assert second.seen == 0
    assert second.new == 0


def test_ride_rollup_combines_taken_and_sold_counts(tmp_path: Path):
    settings = make_settings(tmp_path)
    processed = settings.processed_dir / "00047_202607141813242069.jpg"
    processed.write_bytes(b"processed")
    store = StateStore(settings.state_db)
    RideTracker(settings, store).scan_once()

    store.upsert_event(
        PhotoEvent(
            capture_id="00047",
            raw_path=None,
            processed_path=str(processed),
            legacy_filename="2443106774002027.jpg",
            captured_at="2026-07-14T18:13:24",
            speed_kmh=20.69,
            speed_status="ok",
            upload_status="queued",
        ),
        {"capture_id": "00047"},
    )

    rollups = store.ride_rollups(
        park_id=settings.park_id,
        park_slug=settings.park_slug,
        machine_id=settings.machine_id,
        default_camera_code=settings.camera_code,
        days=365,
    )
    assert rollups[0]["business_date"] == "2026-07-14"
    assert rollups[0]["photos_taken_count"] == 1
    assert rollups[0]["photos_sold_count"] == 1
    assert rollups[0]["conversion_rate"] == 1.0


def test_ride_count_parity_even_only_counts_speed_camera(tmp_path: Path):
    """Plose: two independent cameras cover the same ride (even/odd capture
    numbers) - counting both as separate rides would double the real total."""
    from dataclasses import replace

    settings = make_settings(tmp_path)
    settings = replace(settings, ride_count_parity="even")

    # Same ride, two cameras: one even (speed), one odd (no speed).
    (settings.processed_dir / "00226_202610031200003673.jpg").write_bytes(b"x")
    (settings.raw_dir / "00227.jpg").write_bytes(b"x")

    store = StateStore(settings.state_db)
    result = RideTracker(settings, store).scan_once()

    assert result.seen == 1
    assert result.new == 1
    rows = store.conn.execute("SELECT capture_id FROM ride_events").fetchall()
    assert [r["capture_id"] for r in rows] == ["00226"]


def test_ride_count_parity_all_counts_every_capture(tmp_path: Path):
    """Default (every other machine): unchanged, both cameras count."""
    settings = make_settings(tmp_path)
    (settings.processed_dir / "00226_202610031200003673.jpg").write_bytes(b"x")
    (settings.raw_dir / "00227.jpg").write_bytes(b"x")

    store = StateStore(settings.state_db)
    result = RideTracker(settings, store).scan_once()

    assert result.seen == 2
