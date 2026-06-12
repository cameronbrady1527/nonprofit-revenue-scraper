"""Seeding the organization roster from IRS Business Master File extracts."""

from pathlib import Path

from nonprofit_benchmark.cli import main
from nonprofit_benchmark.db import get_engine, list_organizations

FIXTURES = Path(__file__).parent / "fixtures"


def seeded_db(tmp_path, fixture_name):
    db_path = tmp_path / "benchmark.db"
    main(["init", "--db", str(db_path)])
    main(["seed", "--state", "NY", "--file", str(FIXTURES / fixture_name), "--db", str(db_path)])
    return db_path


def test_seed_stores_501c3_orgs_with_profile_fields(tmp_path):
    db_path = seeded_db(tmp_path, "bmf_ny_sample.csv")

    orgs = {o.ein: o for o in list_organizations(get_engine(db_path))}

    arts = orgs["111000001"]
    assert arts.name == "HUDSON VALLEY YOUTH ARTS"
    assert arts.city == "POUGHKEEPSIE"
    assert arts.state == "NY"
    assert arts.ntee_code == "A65"
    assert arts.income_code == 4
    assert arts.revenue_amount == 480000


def test_seed_excludes_non_501c3_orgs(tmp_path):
    db_path = seeded_db(tmp_path, "bmf_ny_sample.csv")

    eins = {o.ein for o in list_organizations(get_engine(db_path))}

    assert eins == {"111000001", "111000002", "111000003"}  # 04-subsection org excluded


def test_seed_skips_malformed_rows_without_failing(tmp_path, capsys):
    db_path = seeded_db(tmp_path, "bmf_ny_malformed.csv")

    eins = {o.ein for o in list_organizations(get_engine(db_path))}

    assert eins == {"111000001", "111000008"}
    assert "4 malformed rows skipped" in capsys.readouterr().out


def test_seed_is_idempotent(tmp_path):
    db_path = seeded_db(tmp_path, "bmf_ny_sample.csv")
    fixture = str(FIXTURES / "bmf_ny_sample.csv")

    exit_code = main(["seed", "--state", "NY", "--file", fixture, "--db", str(db_path)])

    assert exit_code == 0
    assert len(list_organizations(get_engine(db_path))) == 3
