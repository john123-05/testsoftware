from pathlib import Path

from liftpic_sync.speed import find_matching_processed_file, parse_aidatest_log_tail, speed_from_processed_name


def test_speed_from_processed_name():
    match = speed_from_processed_name("00046_202607141349431395.jpg")
    assert match.status == "ok"
    assert match.speed_kmh == 13.95


def test_speed_from_processed_name_without_underscore():
    match = speed_from_processed_name("00046202607141349431395.jpg")
    assert match.status == "ok"
    assert match.speed_kmh == 13.95


def test_find_matching_processed_file(tmp_path: Path):
    raw = tmp_path / "00046.jpg"
    out = tmp_path / "out"
    out.mkdir()
    raw.write_bytes(b"raw")
    processed = out / "00046_202607141349431395.jpg"
    processed.write_bytes(b"processed")
    path, match = find_matching_processed_file(out, "00046", raw.stat().st_mtime, 12)
    assert path == processed
    assert match.speed_kmh == 13.95


def test_parse_aidatest_log_tail():
    matches = parse_aidatest_log_tail(
        [
            "14.07.2026 13:49:40.709: Measured speed: 13,95 km/h",
            "14.07.2026 13:49:43.525: Newest file is 00046.jpg",
        ]
    )
    assert len(matches) == 1
    assert matches[0].speed_kmh == 13.95
