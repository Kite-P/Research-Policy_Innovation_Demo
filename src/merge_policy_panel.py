"""Merge validated province-year policy metrics into the enterprise panel."""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path

import pandas as pd

POLICY_COLUMNS = [
    "policy_continuity_tfidf",
    "policy_continuity_full_tfidf",
    "policy_continuity_theme",
    "policy_full_text_chars",
    "policy_industry_text_chars",
    "policy_industry_text_share",
    "policy_keyword_hits",
    "policy_continuity_tfidf_expanding",
    "source_tier_current",
    "source_tier_previous",
    "source_tier_max",
    "source_tier_changed",
    "both_direct_official",
    "pair_mean_log_industry_chars",
    "abs_log_industry_length_change",
    "pair_mean_log_full_chars",
    "abs_log_full_length_change",
]


def _require_columns(frame: pd.DataFrame, columns: set[str], label: str) -> None:
    missing = columns - set(frame.columns)
    if missing:
        raise ValueError(f"{label} missing columns: {sorted(missing)}")


def merge_policy_panel(enterprise: pd.DataFrame, policy: pd.DataFrame) -> pd.DataFrame:
    _require_columns(enterprise, {"stock_code", "year", "province"}, "enterprise panel")
    _require_columns(policy, {"province", "year", *POLICY_COLUMNS[:3]}, "policy metrics")
    if enterprise[["stock_code", "year"]].duplicated().any():
        raise ValueError("enterprise stock_code-year key is not unique")
    if policy[["province", "year"]].duplicated().any():
        raise ValueError("policy province-year key is not unique")
    policy_subset = policy.loc[policy["year"].between(2020, 2025)].copy()
    merged = enterprise.merge(
        policy_subset[["province", "year", *POLICY_COLUMNS]],
        on=["province", "year"],
        how="left",
        validate="many_to_one",
        indicator=True,
    )
    merged["policy_metric_present"] = merged["_merge"].eq("both").astype("int8")
    return merged.drop(columns="_merge")


def write_policy_panel(
    enterprise_path: str | Path,
    policy_path: str | Path,
    parquet_path: str | Path,
    dta_path: str | Path,
) -> pd.DataFrame:
    enterprise = pd.read_parquet(enterprise_path)
    policy = pd.read_parquet(policy_path)
    merged = merge_policy_panel(enterprise, policy)
    Path(parquet_path).parent.mkdir(parents=True, exist_ok=True)
    Path(dta_path).parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(parquet_path, index=False)
    stata_merged = merged.rename(
        columns={"policy_continuity_tfidf_expanding": "policy_cont_tfidf_exp"}
    )
    stata_merged.to_stata(dta_path, write_index=False, version=118)
    return merged


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--enterprise", default="data/processed/research_panel_variables.parquet")
    parser.add_argument("--policy", default="data/processed/province_year_policy_metrics.parquet")
    parser.add_argument("--parquet", default="data/processed/research_panel_policy.parquet")
    parser.add_argument("--dta", default="data/processed/research_panel_policy.dta")
    args = parser.parse_args()
    write_policy_panel(args.enterprise, args.policy, args.parquet, args.dta)
