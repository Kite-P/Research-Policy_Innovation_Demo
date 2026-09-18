"""Measurement and sample robustness diagnostics for Chapter 3."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.chapter3_analysis import _cluster_cov, _fit, _normal_p, _wcb


def missing_patent_diagnostic(panel: pd.DataFrame) -> dict[str, object]:
    absent = panel["patent_record_present"].eq(0)
    return {
        "missing_firm_years": int(absent.sum()),
        "outcome_missing_when_absent": int(panel.loc[absent, "patent_total_ln"].isna().sum()),
        "by_year": panel.loc[absent].groupby("year").size().to_dict(),
        "by_province": panel.loc[absent].groupby("province").size().to_dict(),
        "mean_continuity_present": float(panel.loc[~absent, "policy_continuity_tfidf"].mean()),
        "mean_continuity_absent": float(panel.loc[absent, "policy_continuity_tfidf"].mean()),
    }


def _estimate(
    panel: pd.DataFrame, model: str, extra_controls: list[str] | None = None
) -> dict[str, object]:
    extra_controls = extra_controls or []
    fit = _fit(panel, "patent_total_ln", True, "policy_continuity_tfidf", extra_controls)
    covariance = _cluster_cov(fit, panel["province"])
    beta = float(fit["beta"][1])
    se = float(covariance[1, 1] ** 0.5)
    wcb_p, low, high = _wcb(fit, panel["province"], 10_000, 20260918)
    return {
        "model": model,
        "beta": beta,
        "province_cluster_se": se,
        "province_cluster_p": _normal_p(beta, se),
        "wcb_p": wcb_p,
        "wcb_ci_low": low,
        "wcb_ci_high": high,
        "N": len(fit["y"]),
        "province_clusters": fit["frame"].province.nunique(),
    }


def run_measurement_robustness(panel: pd.DataFrame) -> dict[str, pd.DataFrame | dict[str, object]]:
    rows = [
        _estimate(
            panel,
            "industry_volume",
            ["pair_mean_log_industry_chars", "abs_log_industry_length_change"],
        ),
        _estimate(panel, "full_volume", ["pair_mean_log_full_chars", "abs_log_full_length_change"]),
        _estimate(panel, "source_quality", ["both_direct_official"]),
    ]
    restricted = panel[panel["both_direct_official"].eq(1)].copy()
    restricted_result = pd.DataFrame([_estimate(restricted, "direct_source_restricted")])
    influence = []
    for province in sorted(panel["province"].unique()):
        subset = panel[panel["province"] != province].copy()
        result = _estimate(subset, f"leave_out_{province}")
        result["excluded_province"] = province
        influence.append(result)
    diagnostic = missing_patent_diagnostic(panel)
    fit = _fit(panel, "patent_total_ln", True, "policy_continuity_tfidf")
    weight_rows = []
    for weight in ["Webb", "Rademacher"]:
        p_value, low, high = _wcb(fit, panel["province"], 10_000, 20260918, weight)
        weight_rows.append(
            {"weight": weight, "reps": 10_000, "seed": 20260918, "wcb_p": p_value,
             "wcb_ci_low": low, "wcb_ci_high": high, "clusters": panel.province.nunique()}
        )
    return {
        "text_volume": pd.DataFrame(rows),
        "source_quality": pd.DataFrame(rows[2:]),
        "restricted": restricted_result,
        "influence": pd.DataFrame(influence),
        "missingness": diagnostic,
        "weight_sensitivity": pd.DataFrame(weight_rows),
    }


def write_measurement_robustness(
    panel_path: str | Path, output_dir: str | Path = "results/chapter3"
) -> dict[str, pd.DataFrame | dict[str, object]]:
    panel = pd.read_parquet(panel_path)
    results = run_measurement_robustness(panel)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    results["text_volume"].to_csv(output / "text_volume_robustness.csv", index=False)
    results["source_quality"].to_csv(output / "source_quality_robustness.csv", index=False)
    results["restricted"].to_csv(output / "direct_source_restricted.csv", index=False)
    results["influence"].to_csv(output / "leave_one_province_out.csv", index=False)
    results["weight_sensitivity"].to_csv(output / "bootstrap_weight_sensitivity.csv", index=False)
    pd.DataFrame([results["missingness"]]).to_json(
        output / "missingness_diagnostics.json", orient="records", force_ascii=False
    )
    return results
