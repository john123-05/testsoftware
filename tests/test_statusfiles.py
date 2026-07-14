from pathlib import Path

from liftpic_sync.statusfiles import read_local_status


def test_read_local_status(tmp_path: Path):
    statistic = tmp_path / "Statistic.txt"
    print_count = tmp_path / "PrintCount.txt"
    statistic.write_text("line1\nline2\n", encoding="utf-8")
    print_count.write_text("237\n", encoding="utf-8")

    status = read_local_status(statistic, print_count)
    assert status.paper_remaining == 237
    assert status.paper_status == "ok"
    assert status.statistic_file_size is not None
    assert status.statistic_last_line == "line2"
