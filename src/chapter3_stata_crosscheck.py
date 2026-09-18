"""Cross-check point estimates against authoritative Stata outputs."""

from __future__ import annotations

import pandas as pd


def compare_point_estimates(
    python_results: pd.DataFrame,
    stata_results: pd.DataFrame,
    tolerance: float = 1e-7,
) -> pd.DataFrame:
    required = {"model", "beta", "N"}
    if not required.issubset(python_results.columns) or not required.issubset(
        stata_results.columns
    ):
        raise ValueError(f"both inputs require {sorted(required)}")
    if python_results["model"].duplicated().any() or stata_results["model"].duplicated().any():
        raise ValueError("model must be unique in each input")
    left = python_results[list(required)].rename(columns={"beta": "python_beta", "N": "python_N"})
    right = stata_results[list(required)].rename(columns={"beta": "stata_beta", "N": "stata_N"})
    merged = left.merge(right, on="model", how="outer", indicator=True)
    if not merged["_merge"].eq("both").all():
        raise AssertionError("Python and Stata model sets differ")
    merged["abs_diff"] = (merged["python_beta"] - merged["stata_beta"]).abs()
    merged["N_match"] = merged["python_N"].eq(merged["stata_N"])
    merged["passed"] = merged["N_match"] & merged["abs_diff"].le(tolerance)
    return merged.drop(columns="_merge")


def validate_wcb_coherence(results: pd.DataFrame) -> pd.DataFrame:
    required = {"model", "wcb_p", "wcb_ci_low", "wcb_ci_high"}
    missing = required.difference(results.columns)
    if missing:
        raise ValueError(f"missing WCB fields: {sorted(missing)}")
    output = results[["model", "wcb_p", "wcb_ci_low", "wcb_ci_high"]].copy()
    output["ci_contains_zero"] = output["wcb_ci_low"].le(0) & output["wcb_ci_high"].ge(0)
    output["coherent"] = output["wcb_p"].lt(0.05).eq(~output["ci_contains_zero"])
    return output
