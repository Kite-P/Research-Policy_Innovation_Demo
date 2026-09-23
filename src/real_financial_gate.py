from __future__ import annotations

import hashlib

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
PILOT_SEED = "20260923"


def classify_financial_industry(value: object) -> object:
    if pd.isna(value) or str(value).strip() == "":
        return pd.NA
    return str(value).strip() == "金融业" or str(value).strip().startswith("金融业-")


def add_industry_flags(universe: pd.DataFrame) -> pd.DataFrame:
    result = universe.copy()
    result["industry_known"] = result["industry_csrc"].notna() & result["industry_csrc"].astype(
        "string"
    ).str.strip().ne("")
    result["is_financial_industry"] = (
        result["industry_csrc"].map(classify_financial_industry).astype("boolean")
    )
    return result


def stable_pick(frame: pd.DataFrame, n: int, seed: str, stratum: str) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    candidates = frame.drop_duplicates("firm_key").copy()
    candidates["_stable_key"] = candidates["firm_key"].map(
        lambda value: hashlib.sha256(f"{seed}|{stratum}|{value}".encode()).hexdigest()
    )
    selected = candidates.sort_values(["_stable_key", "firm_key"]).head(n)
    return selected.drop(columns="_stable_key").assign(pilot_stratum=stratum).reset_index(drop=True)


def build_financial_pilot_sample(universe: pd.DataFrame) -> pd.DataFrame:
    firms = add_industry_flags(universe.drop_duplicates("firm_key").copy())
    firms = firms.loc[firms["industry_known"] & ~firms["is_financial_industry"]].copy()
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
        selected.append(stable_pick(firms.loc[mask], PILOT_TARGETS[name], PILOT_SEED, name))
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


def failure_decomposition_by_group(panel: pd.DataFrame) -> pd.DataFrame:
    fields = (
        "total_assets",
        "total_liabilities",
        "cash",
        "revenue",
        "net_profit",
        "employees",
    )
    rows = []
    base = panel.copy()
    base["current_status"] = base["delisting_date"].isna().map({True: "current", False: "delisted"})
    for (exchange, stratum, status, year), group in base.groupby(
        ["exchange", "pilot_stratum", "current_status", "year"], dropna=False
    ):
        for field in fields:
            rows.append(
                {
                    "exchange": exchange,
                    "pilot_stratum": stratum,
                    "current_status": status,
                    "year": year,
                    "field": field,
                    "failure_reason": f"FIELD_MISSING:{field}",
                    "rows": int(group[field].isna().sum()),
                }
            )
        reasons = (
            group.get("failure_reason", pd.Series("", index=group.index)).fillna("").astype(str)
        )
        for reason, count in (
            reasons.str.split(";").explode().loc[lambda s: s.ne("")].value_counts().items()
        ):
            rows.append(
                {
                    "exchange": exchange,
                    "pilot_stratum": stratum,
                    "current_status": status,
                    "year": year,
                    "field": "",
                    "failure_reason": reason,
                    "rows": int(count),
                }
            )
    return pd.DataFrame(rows)


def financial_gate(panel: pd.DataFrame) -> pd.DataFrame:
    if "industry_known" not in panel or "is_financial_industry" not in panel:
        panel = add_industry_flags(panel)
    eligible = panel.loc[
        panel["exchange"].isin(["SSE", "SZSE"])
        & panel["delisting_date"].isna()
        & panel["industry_known"]
        & ~panel["is_financial_industry"].fillna(False)
    ].copy()
    rows = []
    for (exchange, stratum), group in eligible.groupby(["exchange", "pilot_stratum"], dropna=False):
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
    for exchange in ("SSE", "SZSE"):
        group = eligible.loc[eligible["exchange"].eq(exchange)]
        rate = float(group["financial_success"].fillna(False).mean()) if len(group) else 0.0
        rows.append(
            {
                "exchange": exchange,
                "pilot_stratum": f"{exchange}_current_nonfinancial_combined",
                "firms": int(group["firm_key"].nunique()),
                "rows": int(len(group)),
                "core_complete_rate": rate,
                "rd_coverage": float(group["rd_expense"].notna().mean()) if len(group) else 0.0,
                "gate_pass_90pct_core": rate >= 0.90,
            }
        )
    return pd.DataFrame(rows)
