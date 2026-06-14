"""Expansion Advisor (pure, no I/O).

When the current filters return too few peers, proposes widening steps in
a fixed order — revenue band ±50%, then NTEE relaxed to its major group,
then neighboring states added — one step at a time, each reported with the
organization-count delta it would add. The advisor only proposes; applying
a step is the caller's job, one confirmed step at a time. Filters are
never changed silently.
"""

from collections.abc import Callable, Collection
from dataclasses import dataclass

MIN_PEER_COUNT = 10

STEP_REVENUE = "widen_revenue"
STEP_NTEE = "relax_ntee"
STEP_STATES = "add_neighboring_states"

# US state land-border adjacency (50 states + DC). States with no land
# neighbors (AK, HI) map to the empty set and expand to nothing.
STATE_NEIGHBORS: dict[str, frozenset[str]] = {
    "AL": frozenset({"FL", "GA", "MS", "TN"}),
    "AK": frozenset(),
    "AZ": frozenset({"CA", "CO", "NM", "NV", "UT"}),
    "AR": frozenset({"LA", "MO", "MS", "OK", "TN", "TX"}),
    "CA": frozenset({"AZ", "NV", "OR"}),
    "CO": frozenset({"AZ", "KS", "NE", "NM", "OK", "UT", "WY"}),
    "CT": frozenset({"MA", "NY", "RI"}),
    "DE": frozenset({"MD", "NJ", "PA"}),
    "DC": frozenset({"MD", "VA"}),
    "FL": frozenset({"AL", "GA"}),
    "GA": frozenset({"AL", "FL", "NC", "SC", "TN"}),
    "HI": frozenset(),
    "ID": frozenset({"MT", "NV", "OR", "UT", "WA", "WY"}),
    "IL": frozenset({"IA", "IN", "KY", "MO", "WI"}),
    "IN": frozenset({"IL", "KY", "MI", "OH"}),
    "IA": frozenset({"IL", "MN", "MO", "NE", "SD", "WI"}),
    "KS": frozenset({"CO", "MO", "NE", "OK"}),
    "KY": frozenset({"IL", "IN", "MO", "OH", "TN", "VA", "WV"}),
    "LA": frozenset({"AR", "MS", "TX"}),
    "ME": frozenset({"NH"}),
    "MD": frozenset({"DC", "DE", "PA", "VA", "WV"}),
    "MA": frozenset({"CT", "NH", "NY", "RI", "VT"}),
    "MI": frozenset({"IN", "OH", "WI"}),
    "MN": frozenset({"IA", "ND", "SD", "WI"}),
    "MS": frozenset({"AL", "AR", "LA", "TN"}),
    "MO": frozenset({"AR", "IA", "IL", "KS", "KY", "NE", "OK", "TN"}),
    "MT": frozenset({"ID", "ND", "SD", "WY"}),
    "NE": frozenset({"CO", "IA", "KS", "MO", "SD", "WY"}),
    "NV": frozenset({"AZ", "CA", "ID", "OR", "UT"}),
    "NH": frozenset({"MA", "ME", "VT"}),
    "NJ": frozenset({"DE", "NY", "PA"}),
    "NM": frozenset({"AZ", "CO", "OK", "TX"}),
    "NY": frozenset({"CT", "MA", "NJ", "PA", "VT"}),
    "NC": frozenset({"GA", "SC", "TN", "VA"}),
    "ND": frozenset({"MN", "MT", "SD"}),
    "OH": frozenset({"IN", "KY", "MI", "PA", "WV"}),
    "OK": frozenset({"AR", "CO", "KS", "MO", "NM", "TX"}),
    "OR": frozenset({"CA", "ID", "NV", "WA"}),
    "PA": frozenset({"DE", "MD", "NJ", "NY", "OH", "WV"}),
    "RI": frozenset({"CT", "MA"}),
    "SC": frozenset({"GA", "NC"}),
    "SD": frozenset({"IA", "MN", "MT", "ND", "NE", "WY"}),
    "TN": frozenset({"AL", "AR", "GA", "KY", "MO", "MS", "NC", "VA"}),
    "TX": frozenset({"AR", "LA", "NM", "OK"}),
    "UT": frozenset({"AZ", "CO", "ID", "NV", "WY"}),
    "VT": frozenset({"MA", "NH", "NY"}),
    "VA": frozenset({"DC", "KY", "MD", "NC", "TN", "WV"}),
    "WA": frozenset({"ID", "OR"}),
    "WV": frozenset({"KY", "MD", "OH", "PA", "VA"}),
    "WI": frozenset({"IA", "IL", "MI", "MN"}),
    "WY": frozenset({"CO", "ID", "MT", "NE", "SD", "UT"}),
}


@dataclass(frozen=True)
class Filters:
    """The peer filter set the advisor reasons over."""

    states: tuple[str, ...] = ()  # empty means all states
    revenue_min: int | None = None
    revenue_max: int | None = None
    ntee: str | None = None


@dataclass(frozen=True)
class ExpansionStep:
    kind: str
    label: str
    filters: Filters  # the filters with this step applied
    delta: int  # organizations this step would add


def _widen_revenue(filters: Filters) -> Filters | None:
    if filters.revenue_min is None and filters.revenue_max is None:
        return None
    return Filters(
        states=filters.states,
        revenue_min=None if filters.revenue_min is None else int(filters.revenue_min * 0.5),
        revenue_max=None if filters.revenue_max is None else int(filters.revenue_max * 1.5),
        ntee=filters.ntee,
    )


def _relax_ntee(filters: Filters) -> Filters | None:
    if filters.ntee is None or len(filters.ntee) <= 1:
        return None
    return Filters(
        states=filters.states,
        revenue_min=filters.revenue_min,
        revenue_max=filters.revenue_max,
        ntee=filters.ntee[0],
    )


def _add_neighboring_states(filters: Filters) -> Filters | None:
    neighbors = sorted(
        {
            neighbor
            for state in filters.states
            for neighbor in STATE_NEIGHBORS.get(state.upper(), frozenset())
        }
        - {state.upper() for state in filters.states}
    )
    if not neighbors:  # no state filter, or no state has neighbors (AK, HI)
        return None
    return Filters(
        states=(*filters.states, *neighbors),
        revenue_min=filters.revenue_min,
        revenue_max=filters.revenue_max,
        ntee=filters.ntee,
    )


_STEPS: list[tuple[str, str, Callable[[Filters], Filters]]] = [
    (STEP_REVENUE, "Widen revenue band", _widen_revenue),
    (STEP_NTEE, "Broaden NTEE to its major group", _relax_ntee),
    (STEP_STATES, "Add neighboring states", _add_neighboring_states),
]


def propose_next_step(
    filters: Filters,
    count_peers: Callable[[Filters], int],
    applied: Collection[str] = (),
    min_peer_count: int = MIN_PEER_COUNT,
) -> ExpansionStep | None:
    current = count_peers(filters)
    if current >= min_peer_count:
        return None
    for kind, label, widen in _STEPS:
        if kind in applied:
            continue
        widened = widen(filters)
        if widened is None:  # inapplicable step: nothing to widen
            continue
        return ExpansionStep(
            kind=kind,
            label=label,
            filters=widened,
            delta=count_peers(widened) - current,
        )
    return None
