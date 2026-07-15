from pathlib import Path

from liftpic_sync.config import Settings
from liftpic_sync.service import LiftpicService


class FakeStatusClient:
    def __init__(self):
        self.payloads: list[dict[str, object]] = []

    def status(self, payload: dict[str, object]) -> dict[str, object]:
        self.payloads.append(payload)
        return {"ok": True}


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


def test_shadow_mode_still_sends_status_heartbeat(tmp_path: Path):
    service = LiftpicService(make_settings(tmp_path))
    client = FakeStatusClient()
    service.client = client

    service._heartbeat_if_due({"queued": 2, "retry": 1})

    assert len(client.payloads) == 1
    assert client.payloads[0]["shadow_mode"] is True
    assert client.payloads[0]["queue_count"] == 3
