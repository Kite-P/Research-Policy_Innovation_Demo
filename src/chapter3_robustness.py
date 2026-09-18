"""Run the pre-specified Chapter 3 timing and metric robustness models."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.chapter3_analysis import _fit

OUTCOMES = ["patent_total_ln", "invention_ln", "citation_ln"]


def build_lagged_policy(panel: pd.DataFrame, policy: str) -> pd.DataFrame:
    policy_year = panel[["province", "year", policy]].drop_duplicates()
    if policy_year.duplicated(["province", "year"]).any():
        raise ValueError("policy must be unique at province-year level")
    policy_year = policy_year.sort_values(["province", "year"]).copy()
    policy_year["policy_lag"] = policy_year.groupby("province")[policy].shift(1)
    return panel.merge(
        policy_year[["province", "year", "policy_lag"]],
        on=["province", "year"],
        how="left",
        validate="many_to_one",
        sort=False,
    )


def _estimate(
    frame: pd.DataFrame,
    outcome: str,
    policy: str,
    model: str,
    reps: int,
    seed: int,
) -> dict[str, object]:
    fit = _fit(frame, outcome, True, policy)
    beta = float(fit["beta"][1])
    return {
        "model": model,
        "outcome": outcome,
        "beta": beta,
        "N": len(fit["y"]),
        "province_clusters": fit["frame"].province.nunique(),
        "regressor_names": ",".join(fit["regressor_names"]),
    }


def run_robustness(
    panel: pd.DataFrame, reps: int = 10_000, seed: int = 20260918
) -> pd.DataFrame:
    rows = []
    lagged = build_lagged_policy(panel, "policy_continuity_tfidf").dropna(subset=["policy_lag"])
    for outcome in OUTCOMES:
        rows.append(_estimate(lagged, outcome, "policy_lag", "lagged_primary", reps, seed))
    metric_map = {
        "expanding": "policy_continuity_tfidf_expanding",
        "full_report": "policy_continuity_full_tfidf",
        "theme": "policy_continuity_theme",
    }
    for outcome in OUTCOMES:
        rows.append(
            _estimate(
                panel,
                outcome,
                metric_map["expanding"],
                "expanding",
                reps,
                seed,
            )
        )
    for metric in ["full_report", "theme"]:
        rows.append(
            _estimate(panel, "patent_total_ln", metric_map[metric], metric, reps, seed)
        )
    return pd.DataFrame(rows)


def write_robustness_results(
    panel_path: str | Path, output_dir: str | Path = "results/chapter3", reps: int = 10_000
) -> pd.DataFrame:
    panel = pd.read_parquet(panel_path)
    results = run_robustness(panel, reps=reps)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    results[results.model == "lagged_primary"].to_csv(
        output / "python_timing_point_estimates.csv", index=False
    )
    results[results.model != "lagged_primary"].to_csv(
        output / "python_metric_point_estimates.csv", index=False
    )
    return results
