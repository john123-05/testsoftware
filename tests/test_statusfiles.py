from pathlib import Path

from liftpic_sync.statusfiles import read_local_status


def test_read_local_status_counts_printed_and_tails_statistic(tmp_path: Path):
    statistic = tmp_path / "Statistic.txt"
    print_count = tmp_path / "PrintCount.txt"
    statistic.write_text("line1\nline2\n", encoding="utf-8")
    print_count.write_text("237\n", encoding="utf-8")

    # No capacity configured -> we know how many were printed, but not remaining.
    status = read_local_status(statistic, print_count)
    assert status.paper_printed == 237
    assert status.paper_remaining is None
    assert status.paper_status == "unknown"
    assert status.statistic_file_size is not None
    assert status.statistic_last_line == "line2"


def test_read_local_status_remaining_is_capacity_minus_printed(tmp_path: Path):
    print_count = tmp_path / "PrintCount.txt"
    print_count.write_text("237\n", encoding="utf-8")

    status = read_local_status(None, print_count, paper_capacity=700, paper_warn_remaining=50)
    assert status.paper_printed == 237
    assert status.paper_capacity == 700
    assert status.paper_remaining == 463
    assert status.paper_status == "ok"


def test_read_local_status_warns_and_empties(tmp_path: Path):
    print_count = tmp_path / "PrintCount.txt"

    print_count.write_text("680\n", encoding="utf-8")
    low = read_local_status(None, print_count, paper_capacity=700, paper_warn_remaining=50)
    assert low.paper_remaining == 20
    assert low.paper_status == "low"

    print_count.write_text("750\n", encoding="utf-8")
    empty = read_local_status(None, print_count, paper_capacity=700, paper_warn_remaining=50)
    assert empty.paper_remaining == 0
    assert empty.paper_status == "empty"
