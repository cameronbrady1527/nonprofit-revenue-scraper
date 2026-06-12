"""Benchmark Engine: peer table rows + summary statistics (pure, no I/O)."""

from nonprofit_benchmark.benchmark import Peer, build_rows, summarize
from nonprofit_benchmark.models import Executive, Filing, Organization


def org(ein="111000001", **overrides):
    fields = dict(ein=ein, name=f"ORG {ein}", city="ALBANY", state="NY",
                  ntee_code="A65", income_code=4, revenue_amount=480000)
    fields.update(overrides)
    return Organization(**fields)


def filing(**overrides):
    fields = dict(ein="111000001", tax_year=2024, source="pdf",
                  pdf_url="https://pdf/1", total_revenue=512000,
                  officer_compensation=None, parse_status="parsed")
    fields.update(overrides)
    return Filing(**fields)


def executive(name="JANE DOE", title="EXECUTIVE DIRECTOR", comp=95000,
              related=0, other=8200):
    return Executive(name=name, title=title, compensation_org=comp,
                     compensation_related=related, compensation_other=other)


def test_gemini_parsed_org_yields_full_table_row():
    peer = Peer(
        organization=org(name="ARTS COUNCIL"),
        filing=filing(),
        executives=[executive()],
    )

    [row] = build_rows([peer], current_year=2026)

    assert row.ein == "111000001"
    assert row.name == "ARTS COUNCIL"
    assert (row.city, row.state) == ("ALBANY", "NY")
    assert row.ntee_code == "A65"
    assert row.total_revenue == 512000
    assert row.executive_title == "EXECUTIVE DIRECTOR"
    assert row.executive_compensation == 95000
    assert row.filing_year == 2024
    assert row.data_source == "ai"
    assert row.propublica_url == (
        "https://projects.propublica.org/nonprofits/organizations/111000001"
    )


def test_benchmark_is_highest_paid_executive_with_count_and_full_list():
    execs = [
        executive(name="JOHN ROE", title="CFO", comp=78000),
        executive(name="JANE DOE", title="EXECUTIVE DIRECTOR", comp=95000),
        executive(name="PAT VOLUNTEER", title="CHAIR", comp=0),
        executive(name="LEE UNKNOWN", title="TRUSTEE", comp=None),
    ]

    [row] = build_rows([Peer(org(), filing(), execs)], current_year=2026)

    assert row.executive_compensation == 95000  # never summed across people
    assert row.executive_title == "EXECUTIVE DIRECTOR"
    assert row.paid_executive_count == 2  # JANE and JOHN; zero/None are unpaid
    assert [e.name for e in row.executives] == [
        "JOHN ROE", "JANE DOE", "PAT VOLUNTEER", "LEE UNKNOWN",
    ]


def test_api_filing_falls_back_to_officer_compensation_aggregate():
    api_filing = filing(source="api", pdf_url=None, total_revenue=480000,
                        officer_compensation=120000)

    [row] = build_rows([Peer(org(), api_filing, [])], current_year=2026)

    assert row.executive_compensation == 120000
    assert row.executive_title is None
    assert row.data_source == "api"
    assert row.paid_executive_count is None  # individuals unknown from the API
    assert row.executives == ()


def test_compensation_as_percent_of_revenue():
    with_revenue = Peer(org(ein="111000001"), filing(total_revenue=500000),
                        [executive(comp=95000)])
    no_revenue = Peer(org(ein="111000002", revenue_amount=None),
                      filing(ein="111000002", total_revenue=None),
                      [executive(comp=95000)])
    zero_revenue = Peer(org(ein="111000003"),
                        filing(ein="111000003", total_revenue=0),
                        [executive(comp=95000)])

    rows = build_rows([with_revenue, no_revenue, zero_revenue], current_year=2026)

    assert rows[0].percent_of_revenue == 19.0
    assert rows[1].percent_of_revenue is None
    assert rows[2].percent_of_revenue is None


def test_filings_more_than_three_years_old_are_flagged_stale():
    peers = [
        Peer(org(ein="111000001"), filing(tax_year=2023), [executive()]),
        Peer(org(ein="111000002"), filing(ein="111000002", tax_year=2022),
             [executive()]),
    ]

    rows = build_rows(peers, current_year=2026)

    assert rows[0].stale is False  # exactly three years old: not flagged
    assert rows[1].stale is True  # more than three years old


def rows_with_compensation(*comps):
    peers = [
        Peer(org(ein=f"11100000{i}"), filing(ein=f"11100000{i}"),
             [executive(comp=comp)])
        for i, comp in enumerate(comps, start=1)
    ]
    return build_rows(peers, current_year=2026)


def test_summary_uses_median_and_quartiles_handling_ties():
    stats = summarize(rows_with_compensation(100000, 80000, 150000, 80000, 60000))

    assert stats.peer_count == 5
    assert stats.median == 80000
    assert stats.p25 == 80000  # tied values are kept, not collapsed
    assert stats.p75 == 100000
    assert stats.minimum == 60000
    assert stats.maximum == 150000


def test_summary_of_empty_peer_set_has_no_figures():
    stats = summarize([])

    assert stats.peer_count == 0
    assert (stats.median, stats.p25, stats.p75) == (None, None, None)
    assert (stats.minimum, stats.maximum) == (None, None)


def test_summary_of_single_peer_collapses_to_its_figure():
    stats = summarize(rows_with_compensation(95000))

    assert stats.peer_count == 1
    assert (stats.median, stats.p25, stats.p75) == (95000, 95000, 95000)
    assert (stats.minimum, stats.maximum) == (95000, 95000)


def test_missing_compensation_stays_in_table_but_out_of_stats():
    failed_parse = Peer(org(ein="111000002"),
                        filing(ein="111000002", parse_status="failed"), [])
    peers = [Peer(org(ein="111000001"), filing(), [executive(comp=95000)]),
             failed_parse]

    rows = build_rows(peers, current_year=2026)
    stats = summarize(rows)

    assert len(rows) == 2
    assert rows[1].executive_compensation is None
    assert stats.peer_count == 1
    assert stats.median == 95000
