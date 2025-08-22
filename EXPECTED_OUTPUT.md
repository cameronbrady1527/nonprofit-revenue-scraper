  The change I made should help by removing the overly strict expenses > 0 requirement. Now we should see:
  - $0 when pct_compnsatncurrofcr exists and is 0%
  - N/A when pct_compnsatncurrofcr is missing/null (often private foundations)
  - Actual amount when pct_compnsatncurrofcr exists and is > 0%