"""Validate policy continuity metrics independently of enterprise outcomes."""

from __future__ import annotations

from argparse import ArgumentParser
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from src.policy_continuity import cosine_similarity, normalize_vectorization_text, tfidf_matrix
except ModuleNotFoundError:
    from policy_continuity import cosine_similarity, normalize_vectorization_text, tfidf_matrix

CONTINUITY_COLUMNS = [
    "policy_continuity_tfidf",
    "policy_continuity_full_tfidf",
    "policy_continuity_theme",
]


def validate_coverage(
    metrics: pd.DataFrame, provinces: list[str], years: range
) -> dict[str, object]:
    expected = pd.MultiIndex.from_product([provinces, list(years)], names=["province", "year"])
    actual = pd.MultiIndex.from_frame(metrics[["province", "year"]])
    missing = expected.difference(actual)
    available = int(metrics["policy_continuity_tfidf"].notna().sum())
    expected_metric = len(provinces) * (len(list(years)) - 1)
    return {
        "expected_cells": len(expected),
        "expected_continuity_cells": expected_metric,
        "available_primary_cells": available,
        "missing_primary_cells": expected_metric - available,
        "first_year_missing_cells": len(provinces),
        "missing_keys": [list(key) for key in missing],
    }


def distribution_summary(metrics: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    rows = []
    for column in columns:
        series = metrics[column].dropna()
        rows.append(
            {
                "metric": column,
                "N": int(series.size),
                "missing": int(metrics[column].isna().sum()),
                "mean": series.mean(),
                "std": series.std(),
                "min": series.min(),
                "p1": series.quantile(0.01),
                "p5": series.quantile(0.05),
                "p25": series.quantile(0.25),
                "median": series.median(),
                "p75": series.quantile(0.75),
                "p95": series.quantile(0.95),
                "p99": series.quantile(0.99),
                "max": series.max(),
                "share_equal_one": float((series == 1).mean()) if len(series) else np.nan,
            }
        )
    return pd.DataFrame(rows)


def rank_correlation(left: pd.Series, right: pd.Series) -> float:
    pair = pd.concat([left, right], axis=1).dropna()
    if len(pair) < 2:
        return float("nan")
    return float(pair.iloc[:, 0].rank().corr(pair.iloc[:, 1].rank()))


def _continuity_by_range(
    clean: pd.DataFrame, column: str, ngram_range: tuple[int, int]
) -> pd.Series:
    ordered = clean.sort_values(["province", "report_year"]).reset_index()
    matrix, _ = tfidf_matrix(ordered[column].tolist(), ngram_range=ngram_range, min_df=2)
    values: dict[str, float] = {}
    for position, row in ordered.iterrows():
        prior = ordered.index[
            ordered["province"].eq(row["province"])
            & ordered["report_year"].eq(int(row["report_year"]) - 1)
        ]
        value = (
            float("nan")
            if len(prior) != 1
            else cosine_similarity(matrix[position], matrix[int(prior[0])])
        )
        values[str(row["policy_id"])] = value
    return pd.Series(values, name=f"continuity_{ngram_range[0]}_{ngram_range[1]}")


def _ngrams(text: str, ngram_range: tuple[int, int]) -> Counter[str]:
    value = normalize_vectorization_text(text)
    return Counter(
        value[start : start + size]
        for size in range(ngram_range[0], ngram_range[1] + 1)
        for start in range(len(value) - size + 1)
    )


def select_manual_cases(metrics: pd.DataFrame, clean: pd.DataFrame) -> pd.DataFrame:
    valid = metrics.dropna(subset=["policy_continuity_tfidf"]).copy()
    top = valid.nlargest(3, "policy_continuity_tfidf")
    bottom = valid.nsmallest(3, "policy_continuity_tfidf")
    middle = valid.drop(pd.concat([top, bottom]).index).sample(
        n=min(4, len(valid) - len(top) - len(bottom)), random_state=20260918
    )
    selected = pd.concat([top, bottom, middle]).drop_duplicates(["province", "year"])
    lookup = clean.set_index(["province", "report_year"])
    rows = []
    for _, row in selected.iterrows():
        previous = lookup.loc[(row["province"], int(row["year"]) - 1)]
        current = lookup.loc[(row["province"], int(row["year"]))]
        shared = _ngrams(previous["industry_text_clean"], (2, 4)) & _ngrams(
            current["industry_text_clean"], (2, 4)
        )
        rows.append(
            {
                "province": row["province"],
                "year_previous": int(row["year"]) - 1,
                "year_current": int(row["year"]),
                "continuity": row["policy_continuity_tfidf"],
                "industry_chars_previous": previous["industry_text_chars"],
                "industry_chars_current": current["industry_text_chars"],
                "keyword_hits_previous": previous["keyword_hits_total"],
                "keyword_hits_current": current["keyword_hits_total"],
                "top_overlapping_ngrams": ",".join(term for term, _ in shared.most_common(10)),
            }
        )
    return pd.DataFrame(rows).sort_values("continuity", ascending=False)


def write_validation_outputs(
    metrics_path: str | Path,
    clean_path: str | Path,
    output_dir: str | Path = "results/policy_continuity",
) -> dict[str, pd.DataFrame]:
    metrics = pd.read_parquet(metrics_path)
    clean = pd.read_parquet(clean_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    coverage = validate_coverage(metrics, sorted(metrics.province.unique()), range(2019, 2026))
    coverage_frame = pd.DataFrame(
        [{key: value for key, value in coverage.items() if key != "missing_keys"}]
    )
    distribution = distribution_summary(metrics, CONTINUITY_COLUMNS)
    trajectory = metrics.pivot(index="province", columns="year", values="policy_continuity_tfidf")
    year_distribution = metrics.groupby("year")[CONTINUITY_COLUMNS].agg(["mean", "median", "std"])
    cases = select_manual_cases(metrics, clean)
    alternative_23 = _continuity_by_range(clean, "industry_text_clean", (2, 3))
    alternative_35 = _continuity_by_range(clean, "industry_text_clean", (3, 5))
    key_map = clean[["policy_id", "province", "report_year"]].rename(
        columns={"report_year": "year"}
    )
    primary_by_id = (
        key_map.merge(metrics, on=["province", "year"], validate="one_to_one")
        .set_index("policy_id")["policy_continuity_tfidf"]
    )
    rank = pd.DataFrame(
        {
            "comparison": ["alt_2_3", "alt_3_5", "theme", "full_report"],
            "rank_correlation": [
                rank_correlation(primary_by_id, alternative_23),
                rank_correlation(primary_by_id, alternative_35),
                rank_correlation(
                    primary_by_id,
                    key_map.merge(metrics, on=["province", "year"], validate="one_to_one")
                    .set_index("policy_id")["policy_continuity_theme"],
                ),
                rank_correlation(
                    primary_by_id,
                    key_map.merge(metrics, on=["province", "year"], validate="one_to_one")
                    .set_index("policy_id")["policy_continuity_full_tfidf"],
                ),
            ],
        }
    )
    volume = metrics.copy()
    volume["year_to_year_full_chars_change"] = volume.groupby("province")[
        "policy_full_text_chars"
    ].diff()
    volume["year_to_year_industry_chars_change"] = volume.groupby("province")[
        "policy_industry_text_chars"
    ].diff()
    volume_audit = pd.DataFrame(
        [
            {
                "variable": variable,
                "pearson_correlation": volume["policy_continuity_tfidf"].corr(volume[variable]),
            }
            for variable in [
                "policy_full_text_chars",
                "policy_industry_text_chars",
                "policy_industry_text_share",
                "policy_keyword_hits",
                "year_to_year_full_chars_change",
                "year_to_year_industry_chars_change",
            ]
        ]
    )
    frames = {
        "coverage": coverage_frame,
        "distribution": distribution,
        "trajectory": trajectory.reset_index(),
        "year_distribution": year_distribution.reset_index(),
        "manual_cases": cases,
        "rank_consistency": rank,
        "volume_audit": volume_audit,
    }
    for name, frame in frames.items():
        frame.to_csv(output / f"{name}.csv", index=False, encoding="utf-8-sig")
    return frames


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", default="data/processed/province_year_policy_metrics.parquet")
    parser.add_argument("--clean", default="data/processed/policy_reports_clean.parquet")
    parser.add_argument("--output", default="results/policy_continuity")
    args = parser.parse_args()
    write_validation_outputs(args.metrics, args.clean, args.output)
