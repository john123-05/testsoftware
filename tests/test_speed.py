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


def test_speedshot_log_matches_number_and_day(tmp_path: Path):
    from datetime import date

    from liftpic_sync.speed import speed_from_speedshot_log

    log = tmp_path / "test.txt"
    log.write_bytes(
        b"00092.jpg;27.10.2026 15:00:00;5,00 m/s(=18,00 km/h);\r\n"
        b"00091.jpg;28.10.2026 16:54:51;6,36 m/s(=22,88 km/h);\r\n"
        b"00092.jpg;28.10.2026 16:55:00;7,81 m/s(=28,13 km/h);\r\n"
    )
    assert speed_from_speedshot_log(log, "00092", date(2026, 10, 28)).speed_kmh == 28.13
    assert speed_from_speedshot_log(log, "92", date(2026, 10, 27)).speed_kmh == 18.0
    missing = speed_from_speedshot_log(log, "00093", date(2026, 10, 28))
    assert missing.status == "missing" and missing.speed_kmh is None
    assert speed_from_speedshot_log(tmp_path / "fehlt.txt", "00092", date(2026, 10, 28)).status == "missing"


def test_speedshot_log_reads_new_lines_after_change(tmp_path: Path):
    from datetime import date

    from liftpic_sync.speed import speed_from_speedshot_log

    log = tmp_path / "test.txt"
    log.write_bytes(b"00001.jpg;28.10.2026 10:00:00;5,00 m/s(=18,00 km/h);\r\n")
    assert speed_from_speedshot_log(log, "00002", date(2026, 10, 28)).status == "missing"
    with log.open("ab") as handle:
        handle.write(b"00002.jpg;28.10.2026 10:01:00;6,00 m/s(=21,60 km/h);\r\n")
    assert speed_from_speedshot_log(log, "00002", date(2026, 10, 28)).speed_kmh == 21.6
