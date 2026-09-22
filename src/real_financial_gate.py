from __future__ import annotations

import pandas as pd

PILOT_TARGETS = {
    "seasoned_current_sse": 15,
    "seasoned_current_szse": 15,
    "recent_ipo_sse": 10,
    "recent_ipo_szse": 10,
    "delisted_sse": 5,
    "delisted_szse": 5,
    "bse_transferred": 10,
    "bse_post_2021": 10,
}


def build_financial_pilot_sample(universe: pd.DataFrame) -> pd.DataFrame:
    firms = universe.drop_duplicates("firm_key").copy()
    listing_year = pd.to_datetime(firms["listing_date"], errors="coerce").dt.year
    current = firms["delisting_date"].isna()
    recent = listing_year.ge(2021)
    strata = {
        "seasoned_current_sse": firms["exchange"].eq("SSE") & current & ~recent,
        "seasoned_current_szse": firms["exchange"].eq("SZSE") & current & ~recent,
        "recent_ipo_sse": firms["exchange"].eq("SSE") & current & recent,
        "recent_ipo_szse": firms["exchange"].eq("SZSE") & current & recent,
        "delisted_sse": firms["exchange"].eq("SSE") & ~current,
        "delisted_szse": firms["exchange"].eq("SZSE") & ~current,
        "bse_transferred": firms["exchange"].eq("BSE") & firms["predecessor_listing_date"].notna(),
        "bse_post_2021": firms["exchange"].eq("BSE") & firms["predecessor_listing_date"].isna(),
    }
    selected = []
    for name, mask in strata.items():
        group = firms.loc[mask].sort_values("firm_key").head(PILOT_TARGETS[name]).copy()
        group["pilot_stratum"] = name
        selected.append(group)
    return (
        pd.concat(selected, ignore_index=True)
        if selected
        else firms.iloc[0:0].assign(pilot_stratum="")
    )


def failure_decomposition(panel: pd.DataFrame) -> pd.DataFrame:
    fields = (
        "total_assets",
        "total_liabilities",
        "cash",
        "revenue",
        "net_profit",
        "employees",
        "rd_expense",
    )
    rows = []
    for field in fields:
        rows.append(
            {
                "failure_type": f"FIELD_MISSING:{field}",
                "rows": int(panel[field].isna().sum()),
                "share": float(panel[field].isna().mean()) if len(panel) else None,
            }
        )
    if "financial_success" in panel:
        rows.append(
            {
                "failure_type": "FINANCIAL_SUCCESS_FALSE",
                "rows": int((~panel["financial_success"].fillna(False)).sum()),
                "share": float((~panel["financial_success"].fillna(False)).mean())
                if len(panel)
                else None,
            }
        )
    if "failure_reason" in panel:
        reasons = panel["failure_reason"].fillna("").astype(str)
        exploded = reasons.str.split(";").explode()
        for reason, count in exploded[exploded.ne("")].value_counts().items():
            rows.append(
                {
                    "failure_type": reason,
                    "rows": int(count),
                    "share": float(count / len(panel)) if len(panel) else None,
                }
            )
    return (
        pd.DataFrame(rows)
        .drop_duplicates("failure_type")
        .sort_values("failure_type")
        .reset_index(drop=True)
    )


def financial_gate(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (exchange, stratum), group in panel.groupby(["exchange", "pilot_stratum"], dropna=False):
        rows.append(
            {
                "exchange": exchange,
                "pilot_stratum": stratum,
                "firms": int(group["firm_key"].nunique()),
                "rows": int(len(group)),
                "core_complete_rate": float(group["financial_success"].fillna(False).mean())
                if len(group)
                else None,
                "rd_coverage": float(group["rd_expense"].notna().mean()) if len(group) else None,
                "gate_pass_90pct_core": bool(
                    group["financial_success"].fillna(False).mean() >= 0.90
                )
                if len(group)
                else False,
            }
        )
    return pd.DataFrame(rows)
