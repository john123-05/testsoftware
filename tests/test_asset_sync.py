from __future__ import annotations

import hashlib
from pathlib import Path

from liftpic_sync.asset_sync import AssetSyncWorker
from liftpic_sync.config import Settings
from liftpic_sync.state import StateStore


class FakeAssetClient:
    def __init__(self, assets: list[dict[str, object]], payload: bytes = b"new"):
        self._assets = assets
        self.payload = payload
        self.downloads = 0

    def assets(self) -> dict[str, object]:
        return {"assets": self._assets}

    def download_signed_url(self, signed_url: str) -> bytes:
        assert signed_url == "memory://asset"
        self.downloads += 1
        return self.payload


def make_settings(tmp_path: Path, allowed_root: Path) -> Settings:
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
        asset_sync_enabled=True,
        asset_sync_seconds=1,
        asset_backup_dir=tmp_path / "backups",
        asset_allowed_roots=(allowed_root,),
    )


def test_asset_sync_applies_with_backup_and_hash(tmp_path: Path):
    viewer = tmp_path / "samuel_neu"
    viewer.mkdir()
    target = viewer / "image1.png"
    target.write_bytes(b"old")
    payload = b"new overlay"
    digest = hashlib.sha256(payload).hexdigest()
    asset = {
        "id": "asset-1",
        "slot": "viewer_print_overlay",
        "target_path": str(target),
        "bucket": "liftpic-assets",
        "storage_path": "parks/test/image1.png",
        "signed_url": "memory://asset",
        "sha256": digest,
        "updated_at": "2026-07-15T12:00:00Z",
    }
    settings = make_settings(tmp_path, viewer)
    store = StateStore(settings.state_db)

    result = AssetSyncWorker(settings, store, FakeAssetClient([asset], payload)).sync_once()

    assert result.applied == 1
    assert result.failed == 0
    assert target.read_bytes() == payload
    backups = list((tmp_path / "backups").rglob("image1.png"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"old"
    assert store.asset_counts() == {"applied": 1}


def test_asset_sync_skips_current_asset_without_download(tmp_path: Path):
    viewer = tmp_path / "samuel_neu"
    viewer.mkdir()
    target = viewer / "logo.png"
    payload = b"logo"
    digest = hashlib.sha256(payload).hexdigest()
    target.write_bytes(payload)
    asset = {
        "id": "asset-2",
        "slot": "viewer_main_logo",
        "target_path": str(target),
        "signed_url": "memory://asset",
        "sha256": digest,
        "updated_at": "2026-07-15T12:00:00Z",
    }
    settings = make_settings(tmp_path, viewer)
    store = StateStore(settings.state_db)
    client = FakeAssetClient([asset], payload)

    first = AssetSyncWorker(settings, store, client).sync_once()
    second = AssetSyncWorker(settings, store, client).sync_once()

    assert first.skipped == 1
    assert second.skipped == 1
    assert client.downloads == 0
    assert store.asset_counts() == {"applied": 1}


def test_asset_sync_rejects_target_outside_allowed_roots(tmp_path: Path):
    viewer = tmp_path / "samuel_neu"
    outside = tmp_path / "other" / "logo.png"
    viewer.mkdir()
    asset = {
        "id": "asset-3",
        "slot": "bad",
        "target_path": str(outside),
        "signed_url": "memory://asset",
    }
    settings = make_settings(tmp_path, viewer)
    store = StateStore(settings.state_db)

    result = AssetSyncWorker(settings, store, FakeAssetClient([asset])).sync_once()

    assert result.failed == 1
    assert not outside.exists()
    assert store.asset_counts() == {"failed": 1}
