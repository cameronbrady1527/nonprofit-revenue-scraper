"""Benchmarking dashboard (Streamlit, local-first; manually tested).

Run with:
    streamlit run src/nonprofit_benchmark/dashboard/app.py

Requires the `dashboard` extra (`pip install -e .[dashboard]`) and a local
database built by the pipeline CLI. This file is presentation only: every
number on screen comes from `db.query_peers` and the pure Benchmark Engine
(`benchmark.build_rows` / `benchmark.summarize`).
"""

from datetime import date
from pathlib import Path

import streamlit as st

from nonprofit_benchmark.benchmark import (
    Peer,
    build_rows,
    ordinal,
    percentile_rank,
    summarize,
)
from nonprofit_benchmark.db import (
    find_org_by_ein,
    get_engine,
    query_peers_for_filters,
    search_organizations,
)
from nonprofit_benchmark.excel_export import export_workbook
from nonprofit_benchmark.expansion import MIN_PEER_COUNT, Filters, propose_next_step

STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN",
    "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY",
]

REVENUE_PRESETS = {
    "Custom": None,
    "$100K – $500K": (100_000, 500_000),
    "$250K – $1M": (250_000, 1_000_000),
    "$1M – $5M": (1_000_000, 5_000_000),
}


def money(value):
    return f"${value:,.0f}" if value is not None else "—"


st.set_page_config(page_title="Nonprofit Compensation Benchmark", layout="wide")
st.title("Executive Compensation Benchmark")

with st.sidebar:
    st.header("Peer filters")
    db_path = st.text_input("Database file", value="benchmark.db")
    state = st.selectbox("State", options=[None, *STATES], format_func=lambda s: s or "All states")

    preset_name = st.selectbox("Revenue preset", options=list(REVENUE_PRESETS))
    preset = REVENUE_PRESETS[preset_name]
    revenue_min = st.number_input(
        "Revenue minimum ($)", min_value=0, step=50_000,
        value=preset[0] if preset else 0,
        disabled=preset is not None,
    )
    revenue_max = st.number_input(
        "Revenue maximum ($)", min_value=0, step=50_000,
        value=preset[1] if preset else 0,
        disabled=preset is not None,
        help="0 means no maximum.",
    )
    if preset:
        revenue_min, revenue_max = preset

    ntee_prefix = st.text_input(
        "NTEE category", placeholder='Major group ("A") or full code ("A65")'
    ).strip() or None

if not Path(db_path).exists():
    st.warning(f"Database file not found: {db_path}. Run the pipeline CLI first.")
    st.stop()

engine = get_engine(db_path)

# Your organization: EIN auto-fill -> name-search fallback -> manual entry.
# Every value resolved here comes from db lookups and the Benchmark Engine;
# nothing is computed in this file.
with st.sidebar:
    st.header("Your organization")
    your_name = your_revenue = your_comp = None
    your_ein = st.text_input("EIN", help="Auto-fills your profile from the database.")
    your_ein = your_ein.replace("-", "").strip()
    lookup = find_org_by_ein(engine, your_ein) if your_ein else None
    if your_ein and lookup is None:
        st.caption("EIN not found — search by name or enter details below.")
        name_query = st.text_input("Search by name").strip()
        if name_query:
            candidates = search_organizations(engine, name_query, state=state)
            if candidates:
                chosen = st.selectbox(
                    "Matches", candidates, index=None,
                    format_func=lambda c: f"{c.name} ({c.ein})",
                )
                if chosen is not None:
                    lookup = find_org_by_ein(engine, chosen.ein)
            else:
                st.caption("No matches — enter details below.")
    if lookup is not None:
        your_name = lookup.organization.name
        if lookup.filing is not None:
            [your_row] = build_rows(
                [Peer(lookup.organization, lookup.filing, lookup.executives)],
                current_year=date.today().year,
            )
            your_revenue = your_row.total_revenue
            your_comp = your_row.executive_compensation
    your_name = st.text_input("Name", value=your_name or "").strip() or None
    your_revenue = st.number_input(
        "Total revenue ($)", min_value=0, step=10_000, value=your_revenue or 0,
        help="0 means unknown; you can fill this in later.",
    ) or None
    your_comp = st.number_input(
        "Executive compensation ($)", min_value=0, step=5_000, value=your_comp or 0,
        help="0 means unknown; the percentile callout appears once this is set.",
    ) or None

base_filters = Filters(
    states=(state,) if state else (),
    revenue_min=revenue_min or None,
    revenue_max=revenue_max or None,
    ntee=ntee_prefix,
)
if st.session_state.get("expansion_base") != base_filters:
    # Sidebar filters changed: any previously confirmed expansion steps reset.
    st.session_state["expansion_base"] = base_filters
    st.session_state["expansion_applied"] = ()
    st.session_state["expansion_filters"] = base_filters
filters = st.session_state["expansion_filters"]
peers = query_peers_for_filters(engine, filters)
rows = build_rows(peers, current_year=date.today().year)
stats = summarize(rows)


def offer_expansion_step():
    """Warn on a too-small peer set and offer the next widening step.

    Rendered after the results so the user sees what was found first. The
    advisor (pure, in nonprofit_benchmark.expansion) only proposes; nothing
    changes until the user confirms a step by clicking its button.
    """
    if len(peers) >= MIN_PEER_COUNT:
        return
    st.warning(f"Only {len(peers)} peers found (fewer than {MIN_PEER_COUNT}).")
    step = propose_next_step(
        filters,
        count_peers=lambda f: len(query_peers_for_filters(engine, f)),
        applied=st.session_state["expansion_applied"],
    )
    if step is None:
        return
    if st.button(f"{step.label}: +{step.delta} orgs"):
        st.session_state["expansion_applied"] = (
            *st.session_state["expansion_applied"],
            step.kind,
        )
        st.session_state["expansion_filters"] = step.filters
        st.rerun()

st.subheader("Summary")
metrics = st.columns(6)
metrics[0].metric("Peers", stats.peer_count)
metrics[1].metric("Median", money(stats.median))
metrics[2].metric("25th percentile", money(stats.p25))
metrics[3].metric("75th percentile", money(stats.p75))
metrics[4].metric("Minimum", money(stats.minimum))
metrics[5].metric("Maximum", money(stats.maximum))

if your_comp is not None:
    your_percentile = percentile_rank(your_comp, rows)
    if your_percentile is not None:
        st.info(
            f"**{your_name or 'Your organization'}** is at the "
            f"**{ordinal(round(your_percentile))} percentile** of this peer set "
            f"({money(your_comp)} vs. peer median {money(stats.median)})."
        )

st.subheader("Peer organizations")
if not rows:
    st.info("No organizations match the current filters.")
    offer_expansion_step()
    st.stop()

st.dataframe(
    [
        {
            "Organization": row.name,
            "ProPublica": row.propublica_url,
            "City": row.city,
            "State": row.state,
            "NTEE": row.ntee_code,
            "Total revenue": row.total_revenue,
            "Executive title": row.executive_title,
            "Executive compensation": row.executive_compensation,
            "% of revenue": row.percent_of_revenue,
            "Filing year": row.filing_year,
            "Stale (>3 yrs)": row.stale,
            "Source": row.data_source,
            "Paid execs": row.paid_executive_count,
        }
        for row in rows
    ],
    column_config={
        "ProPublica": st.column_config.LinkColumn(
            "ProPublica", display_text="View filing ↗",
            help="The organization's public ProPublica page",
        ),
        "Total revenue": st.column_config.NumberColumn(format="dollar"),
        "Executive compensation": st.column_config.NumberColumn(format="dollar"),
        "% of revenue": st.column_config.NumberColumn(format="%.1f%%"),
        "Filing year": st.column_config.NumberColumn(format="%d"),
    },
    hide_index=True,
)
st.caption(
    "Compensation is the organization's highest-paid executive "
    "(Form 990 Part VII column D) — never summed across people. "
    '"api" rows show the filing\'s aggregate officer compensation instead.'
)

st.download_button(
    "Export to Excel",
    data=export_workbook(
        rows,
        stats,
        filter_description=", ".join(
            part
            for part in [
                f"State: {state}" if state else "All states",
                f"Revenue: {money(revenue_min or None)} to {money(revenue_max or None)}",
                f"NTEE: {ntee_prefix}" if ntee_prefix else None,
            ]
            if part
        ),
    ),
    file_name=f"peer_benchmark_{date.today().isoformat()}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

st.subheader("Full executive lists")
for row in rows:
    if not row.executives:
        continue
    with st.expander(f"{row.name} — {row.paid_executive_count} paid executive(s)"):
        st.table(
            [
                {
                    "Name": executive.name,
                    "Title": executive.title,
                    "Compensation (org, col D)": money(executive.compensation_org),
                    "Related orgs (col E)": money(executive.compensation_related),
                    "Other/benefits (col F)": money(executive.compensation_other),
                }
                for executive in row.executives
            ]
        )

offer_expansion_step()
