"""CLI behavior: the single `pipeline` entry point."""

import pytest

from nonprofit_benchmark.cli import main


def test_init_creates_sqlite_database(tmp_path):
    db_path = tmp_path / "benchmark.db"

    exit_code = main(["init", "--db", str(db_path)])

    assert exit_code == 0
    assert db_path.read_bytes()[:16] == b"SQLite format 3\x00"


def test_init_can_be_re_run_safely(tmp_path):
    db_path = tmp_path / "benchmark.db"
    main(["init", "--db", str(db_path)])

    assert main(["init", "--db", str(db_path)]) == 0


def test_help_lists_commands_and_exits_zero(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])

    assert excinfo.value.code == 0
    assert "init" in capsys.readouterr().out
