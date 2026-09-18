"""Compatibility baseline analysis for the frozen Chapter 3 specifications."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

CONTROLS = ["size_ln", "leverage", "roa", "cash_ratio", "employee_ln"]
WEBB_SUPPORT = np.array(
    [-np.sqrt(1.5), -1.0, -np.sqrt(0.5), np.sqrt(0.5), 1.0, np.sqrt(1.5)]
)


def _design(
    frame: pd.DataFrame,
    outcome: str,
    regressors: list[str],
) -> tuple[np.ndarray, np.ndarray, list[int]]:
    columns = list(regressors)
    numeric = frame[["stock_code", "year", "province", outcome, *columns]].dropna().copy()
    x = numeric[columns].to_numpy(float)
    firm = pd.get_dummies(numeric["stock_code"], drop_first=True, dtype=float).to_numpy()
    year = pd.get_dummies(numeric["year"], drop_first=True, dtype=float).to_numpy()
    design = np.column_stack([np.ones(len(numeric)), x, firm, year])
    return design, numeric[outcome].to_numpy(float), numeric.index.tolist()


def _fit(
    frame: pd.DataFrame,
    outcome: str,
    controls: bool = True,
    policy: str = "policy_continuity_tfidf",
    extra_controls: list[str] | None = None,
) -> dict[str, object]:
    regressors = [policy]
    if controls:
        regressors.extend(CONTROLS)
    regressors.extend(extra_controls or [])
    design, y, indices = _design(frame, outcome, regressors)
    beta, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
    residual = y - design @ beta
    bread = np.linalg.pinv(design.T @ design)
    leverage = np.einsum("ij,jk,ik->i", design, bread, design)
    return {
        "design": design,
        "y": y,
        "residual": residual,
        "beta": beta,
        "bread": bread,
        "leverage": leverage,
        "indices": indices,
        "frame": frame.loc[indices].copy(),
        "regressor_names": regressors,
    }


def _cluster_cov(fit: dict[str, object], cluster: pd.Series, hc2: bool = False) -> np.ndarray:
    x = fit["design"]
    residual = fit["residual"].copy()
    if hc2:
        residual = residual / np.sqrt(np.maximum(1.0 - fit["leverage"], 1e-8))
    meat = np.zeros((x.shape[1], x.shape[1]))
    grouped = cluster.loc[fit["indices"]]
    for value in grouped.unique():
        mask = grouped.eq(value).to_numpy()
        score = x[mask].T @ residual[mask]
        meat += np.outer(score, score)
    groups = grouped.nunique()
    n, k = len(residual), x.shape[1]
    correction = (groups / (groups - 1)) * ((n - 1) / max(n - k, 1))
    return fit["bread"] @ meat @ fit["bread"] * correction


def _legacy_wcb_compatibility_only(
    fit: dict[str, object], cluster: pd.Series, reps: int, seed: int, weight: str = "Webb"
) -> tuple[float, float, float]:
    """Legacy diagnostic only; never use for reported inference."""
    x, y = fit["design"], fit["y"]
    restricted = x[:, [i for i in range(x.shape[1]) if i != 1]]
    restricted_beta, _, _, _ = np.linalg.lstsq(restricted, y, rcond=None)
    null_fit = restricted @ restricted_beta
    residual = y - null_fit
    inverse = fit["bread"] @ x.T
    clusters = cluster.loc[fit["indices"]].to_numpy()
    unique = pd.unique(clusters)
    weights = np.array([-1.0, 1.0]) if weight.lower() == "rademacher" else WEBB_SUPPORT
    rng = np.random.default_rng(seed)
    draws = np.empty(reps)
    for iteration in range(reps):
        selected = rng.choice(weights, size=len(unique), replace=True)
        multiplier = dict(zip(unique, selected))
        bootstrap_y = null_fit + residual * np.array([multiplier[item] for item in clusters])
        draws[iteration] = float((inverse @ bootstrap_y)[1])
    observed = float(fit["beta"][1])
    p_value = float(np.mean(np.abs(draws) >= abs(observed)))
    low, high = np.quantile(draws, [0.025, 0.975])
    return p_value, float(low), float(high)


def _normal_p(beta: float, se: float) -> float:
    if se == 0:
        return 0.0
    return float(math.erfc(abs(beta / se) / np.sqrt(2.0)))


def run_baseline_models(
    panel: pd.DataFrame, reps: int = 10_000, seed: int = 20260918
) -> dict[str, pd.DataFrame]:
    models = [
        ("MODEL_0", "patent_total_ln", False),
        ("BASE_PRIMARY", "patent_total_ln", True),
        ("BASE_SECONDARY_INV", "invention_ln", True),
        ("BASE_SECONDARY_CIT", "citation_ln", True),
    ]
    rows = []
    for model, outcome, controls in models:
        fit = _fit(panel, outcome, controls)
        frame = fit["frame"]
        beta = float(fit["beta"][1])
        n, firms, provinces = len(frame), frame.stock_code.nunique(), frame.province.nunique()
        rows.append(
            {
                "model": model,
                "outcome": outcome,
                "beta": beta,
                "N": n,
                "firms": firms,
                "province_clusters": provinces,
                "regressor_names": ",".join(fit["regressor_names"]),
            }
        )
    return {"baseline": pd.DataFrame(rows)}


def write_baseline_results(
    panel_path: str | Path, output_dir: str | Path = "results/chapter3", reps: int = 10_000
) -> dict[str, pd.DataFrame]:
    panel = pd.read_parquet(panel_path)
    results = run_baseline_models(panel, reps=reps)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    results["baseline"].to_csv(output / "python_baseline_point_estimates.csv", index=False)
    return results
