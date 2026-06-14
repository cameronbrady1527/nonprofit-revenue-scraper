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

from nonprofit_benchmark.benchmark import build_rows, summarize
from nonprofit_benchmark.db import get_engine, query_peers

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

peers = query_peers(
    get_engine(db_path),
    state=state,
    revenue_min=revenue_min or None,
    revenue_max=revenue_max or None,
    ntee_prefix=ntee_prefix,
)
rows = build_rows(peers, current_year=date.today().year)
stats = summarize(rows)

st.subheader("Summary")
metrics = st.columns(6)
metrics[0].metric("Peers", stats.peer_count)
metrics[1].metric("Median", money(stats.median))
metrics[2].metric("25th percentile", money(stats.p25))
metrics[3].metric("75th percentile", money(stats.p75))
metrics[4].metric("Minimum", money(stats.minimum))
metrics[5].metric("Maximum", money(stats.maximum))

st.subheader("Peer organizations")
if not rows:
    st.info("No organizations match the current filters.")
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
