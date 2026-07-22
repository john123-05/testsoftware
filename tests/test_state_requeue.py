from liftpic_sync.state import PhotoEvent, StateStore


def _event(event_key: str, status: str) -> PhotoEvent:
    return PhotoEvent(
        capture_id=event_key,
        raw_path=None,
        processed_path=f"C:/liftpic/fotos/qrcode/{event_key}.jpg",
        legacy_filename=f"{event_key}.jpg",
        captured_at="2026-07-22T10:00:00",
        speed_kmh=None,
        speed_status="missing",
        upload_status=status,
        checksum="x",
        event_key=event_key,
    )


def test_requeue_shadowed_moves_shadowed_back_to_queued(tmp_path):
    store = StateStore(tmp_path / "state.db")
    try:
        store.upsert_event(_event("a", "shadowed"), {"k": "v"})
        store.upsert_event(_event("b", "shadowed"), {"k": "v"})
        store.upsert_event(_event("c", "uploaded"), {"k": "v"})

        moved = store.requeue_shadowed()

        counts = store.counts()
        assert moved == 2
        assert counts.get("queued") == 2
        assert counts.get("uploaded") == 1
        assert "shadowed" not in counts
    finally:
        store.close()
