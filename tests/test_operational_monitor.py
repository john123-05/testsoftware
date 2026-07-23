from pathlib import Path

from liftpic_sync.config import Settings
from liftpic_sync.operational_monitor import read_operational_status
from liftpic_sync.service import LiftpicService


def make_settings(tmp_path: Path, globs: tuple[str, ...]) -> Settings:
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
        operational_log_globs=globs,
        operational_log_tail_lines=20,
        operational_log_stale_minutes=240,
    )


def test_coin_error_is_reported_as_down(tmp_path: Path):
    log_dir = tmp_path / "imageloader"
    log_dir.mkdir()
    log_file = log_dir / "coin.log"
    log_file.write_text(
        "15.07.2026 10:00:00 CoinChangerStatus ready\n"
        "15.07.2026 10:01:00 CoinChangerError no response\n",
        encoding="utf-8",
    )

    status = read_operational_status(make_settings(tmp_path, (str(log_dir / "*.log"),)))

    assert status.coin_status == "down"
    assert status.devices[0].name == "Cash / Coin"
    assert "CoinChangerError" in status.devices[0].detail


def test_later_ready_line_restores_operational_status(tmp_path: Path):
    log_dir = tmp_path / "imageloader"
    log_dir.mkdir()
    log_file = log_dir / "coin.log"
    log_file.write_text(
        "15.07.2026 10:00:00 CoinChangerError no response\n"
        "15.07.2026 10:02:00 CoinChangerStatus ready\n",
        encoding="utf-8",
    )

    status = read_operational_status(make_settings(tmp_path, (str(log_dir / "*.log"),)))

    assert status.coin_status == "operational"


def test_old_error_line_is_not_reported_as_live_fault(tmp_path: Path):
    import os
    import time

    log_dir = tmp_path / "3GerTis"
    log_dir.mkdir()
    log_file = log_dir / "Speedshot.log"
    # A defunct camera log whose last line is a year-old error.
    log_file.write_text("04.06.2025 11:29:36.355: Error 45\n", encoding="utf-8")
    old = time.time() - 400 * 24 * 3600  # ~400 days ago
    os.utime(log_file, (old, old))

    status = read_operational_status(make_settings(tmp_path, (str(log_dir / "*.log"),)))

    # No false "camera down" from a year-old line.
    assert status.camera_status is None
    assert status.devices == []


def test_health_payload_includes_operational_devices(tmp_path: Path):
    log_dir = tmp_path / "logs-source"
    log_dir.mkdir()
    log_file = log_dir / "zvt.log"
    log_file.write_text("15.07.2026 10:02:00 Terminal bereit\n", encoding="utf-8")
    service = LiftpicService(make_settings(tmp_path, (str(log_dir / "*.log"),)))

    health = service.health()

    assert health["terminal_status"] == "operational"
    assert health["operational_devices"]
