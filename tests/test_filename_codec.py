from datetime import datetime

from liftpic_sync.filename_codec import (
    build_legacy_filename,
    mix_customer_time_capture,
    parse_capture_filename,
    parse_legacy_filename,
)


def test_parse_legacy_filename():
    parsed = parse_legacy_filename("1963186224002020.jpg")
    assert parsed is not None
    assert parsed.legacy_code == "1963"
    assert parsed.time_code == "18622400"
    assert parsed.file_code == "2020"


def test_parse_processed_capture_filename_with_speed():
    parsed = parse_capture_filename("00046_202607141349431395.jpg")
    assert parsed is not None
    assert parsed.capture_id == "00046"
    assert parsed.speed_kmh == 13.95


def test_parse_processed_capture_filename_without_underscore():
    parsed = parse_capture_filename("00046202607141349431395.jpg")
    assert parsed is not None
    assert parsed.capture_id == "00046"
    assert parsed.speed_kmh == 13.95


def test_parse_raw_capture_filename():
    parsed = parse_capture_filename("46.jpg")
    assert parsed is not None
    assert parsed.capture_id == "00046"
    assert parsed.speed_kmh is None


def test_mix_customer_time_capture_matches_known_formula_example():
    assert mix_customer_time_capture("1234", "19022026", "0860") == "1963186224002020"


def test_build_legacy_filename_uses_interleaving_formula():
    legacy = build_legacy_filename(
        customer_code="2734",
        capture_id="00047",
        captured_at=datetime(2026, 7, 14, 18, 13, 24),
    )
    assert legacy.filename == "2443106774002027.jpg"
    assert legacy.time_code == "14072026"
    assert legacy.file_code == "0047"
