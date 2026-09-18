"""Run the pre-specified Chapter 3 timing and metric robustness models."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.chapter3_analysis import _cluster_cov, _fit, _normal_p, _wcb

OUTCOMES = ["patent_total_ln", "invention_ln", "citation_ln"]


def build_lagged_policy(panel: pd.DataFrame, policy: str) -> pd.DataFrame:
    ordered = panel.sort_values(["province", "year"]).copy()
    ordered["policy_lag"] = ordered.groupby("province")[policy].shift(1)
    return ordered


def _estimate(
    frame: pd.DataFrame,
    outcome: str,
    policy: str,
    model: str,
    reps: int,
    seed: int,
) -> dict[str, object]:
    fit = _fit(frame, outcome, True, policy)
    covariance = _cluster_cov(fit, frame["province"])
    beta = float(fit["beta"][1])
    se = float(covariance[1, 1] ** 0.5)
    p_value, low, high = _wcb(fit, frame["province"], reps, seed)
    return {
        "model": model,
        "outcome": outcome,
        "beta": beta,
        "province_cluster_se": se,
        "province_cluster_p": _normal_p(beta, se),
        "wcb_p": p_value,
        "wcb_ci_low": low,
        "wcb_ci_high": high,
        "N": len(fit["y"]),
        "province_clusters": fit["frame"].province.nunique(),
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
    for metric, policy in metric_map.items():
        rows.append(_estimate(panel, "patent_total_ln", policy, metric, reps, seed))
    return pd.DataFrame(rows)


def write_robustness_results(
    panel_path: str | Path, output_dir: str | Path = "results/chapter3", reps: int = 10_000
) -> pd.DataFrame:
    panel = pd.read_parquet(panel_path)
    results = run_robustness(panel, reps=reps)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    results[results.model == "lagged_primary"].to_csv(output / "timing_robustness.csv", index=False)
    results[results.model != "lagged_primary"].to_csv(output / "metric_robustness.csv", index=False)
    return results
