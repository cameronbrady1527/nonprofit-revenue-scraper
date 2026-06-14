"""Expansion Advisor: stepwise filter widening proposals (pure, no I/O)."""

from nonprofit_benchmark.expansion import (
    MIN_PEER_COUNT,
    STATE_NEIGHBORS,
    STEP_NTEE,
    STEP_REVENUE,
    STEP_STATES,
    Filters,
    propose_next_step,
)

NARROW = Filters(states=("NY",), revenue_min=250_000, revenue_max=1_000_000,
                 ntee="A65")


def counts(**table):
    """A count source backed by a fixture table keyed on the varying field."""

    def count_peers(filters):
        for key, value in table.items():
            if getattr(filters, key) in value:
                return value[getattr(filters, key)]
        raise AssertionError(f"unexpected filters: {filters}")

    return count_peers


def test_no_proposal_when_peer_count_meets_threshold():
    step = propose_next_step(NARROW, count_peers=lambda f: MIN_PEER_COUNT)

    assert step is None


def test_advisor_fires_just_below_default_threshold_of_ten():
    assert MIN_PEER_COUNT == 10

    step = propose_next_step(NARROW, count_peers=lambda f: 9)

    assert step is not None


def test_threshold_is_overridable_per_call():
    step = propose_next_step(NARROW, count_peers=lambda f: 9, min_peer_count=5)

    assert step is None


def test_first_step_widens_revenue_band_by_fifty_percent_with_delta():
    count_peers = counts(revenue_min={250_000: 4, 125_000: 16})

    step = propose_next_step(NARROW, count_peers)

    assert step.kind == STEP_REVENUE
    assert step.filters == Filters(states=("NY",), revenue_min=125_000,
                                   revenue_max=1_500_000, ntee="A65")
    assert step.delta == 12  # 16 with the step applied minus 4 now


def test_step_adding_zero_orgs_is_still_reported_with_delta_zero():
    count_peers = counts(revenue_min={250_000: 4, 125_000: 4})

    step = propose_next_step(NARROW, count_peers)

    assert step.kind == STEP_REVENUE
    assert step.delta == 0


def test_second_step_relaxes_ntee_to_its_major_group():
    count_peers = counts(ntee={"A65": 6, "A": 9})

    step = propose_next_step(NARROW, count_peers, applied=(STEP_REVENUE,))

    assert step.kind == STEP_NTEE
    assert step.filters == Filters(states=("NY",), revenue_min=250_000,
                                   revenue_max=1_000_000, ntee="A")
    assert step.delta == 3


def test_third_step_adds_neighboring_states():
    filters = Filters(states=("VT",), revenue_min=250_000,
                      revenue_max=1_000_000, ntee="A")
    count_peers = counts(states={("VT",): 5, ("VT", "MA", "NH", "NY"): 14})

    step = propose_next_step(filters, count_peers,
                             applied=(STEP_REVENUE, STEP_NTEE))

    assert step.kind == STEP_STATES
    assert step.filters == Filters(states=("VT", "MA", "NH", "NY"),
                                   revenue_min=250_000,
                                   revenue_max=1_000_000, ntee="A")
    assert step.delta == 9


def test_revenue_step_skipped_when_no_revenue_band_is_set():
    filters = Filters(states=("NY",), ntee="A65")
    count_peers = counts(ntee={"A65": 6, "A": 9})

    step = propose_next_step(filters, count_peers)

    assert step.kind == STEP_NTEE


def test_ntee_step_skipped_when_already_a_major_group_or_unset():
    major_group = Filters(states=("VT",), revenue_min=250_000,
                          revenue_max=1_000_000, ntee="A")
    no_ntee = Filters(states=("VT",), revenue_min=250_000,
                      revenue_max=1_000_000, ntee=None)

    for filters in (major_group, no_ntee):
        step = propose_next_step(filters, count_peers=lambda f: 2,
                                 applied=(STEP_REVENUE,))
        assert step.kind == STEP_STATES


def test_states_step_skipped_when_no_state_has_neighbors():
    alaska = Filters(states=("AK",), revenue_min=250_000,
                     revenue_max=1_000_000, ntee="A")
    all_states = Filters(states=(), revenue_min=250_000,
                         revenue_max=1_000_000, ntee="A")

    for filters in (alaska, all_states):
        step = propose_next_step(filters, count_peers=lambda f: 2,
                                 applied=(STEP_REVENUE, STEP_NTEE))
        assert step is None


def test_no_proposal_once_all_three_steps_are_applied():
    step = propose_next_step(NARROW, count_peers=lambda f: 2,
                             applied=(STEP_REVENUE, STEP_NTEE, STEP_STATES))

    assert step is None


def test_adjacency_map_covers_fifty_states_plus_dc_and_is_symmetric():
    assert len(STATE_NEIGHBORS) == 51
    assert STATE_NEIGHBORS["AK"] == frozenset()
    assert STATE_NEIGHBORS["HI"] == frozenset()
    for state, neighbors in STATE_NEIGHBORS.items():
        assert state not in neighbors
        for neighbor in neighbors:
            assert state in STATE_NEIGHBORS[neighbor], f"{state}->{neighbor}"


# --- Integration: the advisor counting through a real SQLite database ------

def seed_api_org(engine, ein, state, ntee_code, revenue):
    """An org whose newest filing carries structured API data."""
    from nonprofit_benchmark.bmf import BmfOrg
    from nonprofit_benchmark.db import record_selected_filing, upsert_organizations
    from nonprofit_benchmark.filing_selector import SelectedFiling

    upsert_organizations(engine, [BmfOrg(
        ein=ein, name=f"ORG {ein}", city="ALBANY", state=state,
        ntee_code=ntee_code, income_code=4, revenue_amount=revenue,
    )])
    record_selected_filing(engine, ein, SelectedFiling(
        tax_year=2024, source="api", pdf_url=None,
        total_revenue=revenue, officer_compensation=90000,
    ))


def test_full_expansion_walk_against_a_real_database(tmp_path):
    from nonprofit_benchmark.db import init_db, query_peers_for_filters

    engine = init_db(tmp_path / "benchmark.db")
    seed_api_org(engine, "111000001", "NY", "A65", 300_000)  # matches as-is
    seed_api_org(engine, "111000002", "NY", "A65", 900_000)  # matches as-is
    seed_api_org(engine, "111000003", "NY", "A65", 150_000)  # widened band only
    seed_api_org(engine, "111000004", "NY", "A65", 1_400_000)  # widened band only
    seed_api_org(engine, "111000005", "NY", "A20", 400_000)  # major group only
    seed_api_org(engine, "111000006", "VT", "A20", 400_000)  # neighbor state only
    seed_api_org(engine, "111000007", "CA", "A20", 400_000)  # never reached

    def count_peers(f):
        return len(query_peers_for_filters(engine, f))

    filters = Filters(states=("NY",), revenue_min=250_000,
                      revenue_max=1_000_000, ntee="A65")
    applied = []
    walk = []
    while (step := propose_next_step(filters, count_peers, applied)) is not None:
        walk.append((step.kind, step.delta))
        filters = step.filters
        applied.append(step.kind)

    assert walk == [(STEP_REVENUE, 2), (STEP_NTEE, 1), (STEP_STATES, 1)]
    assert count_peers(filters) == 6
    assert filters == Filters(states=("NY", "CT", "MA", "NJ", "PA", "VT"),
                              revenue_min=125_000, revenue_max=1_500_000,
                              ntee="A")
