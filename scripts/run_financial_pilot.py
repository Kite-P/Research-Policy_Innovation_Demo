from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.build_real_financial_panel import (  # noqa: E402
    CORE_FIELDS,
    SourceBlocked,
    _stata_ready,
    coverage_table,
    financial_cache_path,
    run_financial_panel,
)
from src.real_financial_gate import (  # noqa: E402
    build_financial_stress_test_sample,
    failure_decomposition_by_group,
)

OUTPUT_DIR = ROOT / "results" / "real_financial_pilot"
UNIVERSE_PATH = ROOT / "data" / "processed" / "real_company_universe_enriched.parquet"
YEARS = tuple(range(2020, 2026))
REPORT_FIELDS = CORE_FIELDS + ("rd_expense",)


def select_pilot_universe_years(universe: pd.DataFrame) -> pd.DataFrame:
    return universe.loc[universe["year"].between(min(YEARS), max(YEARS))].copy()


def _json_value(value: object) -> object:
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if pd.isna(value):
        return None
    return value


def _write_summary(summary: dict[str, object], output_dir: Path) -> None:
    (output_dir / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=_json_value), encoding="utf-8"
    )


def _failure_output(panel: pd.DataFrame) -> pd.DataFrame:
    grouped = failure_decomposition_by_group(panel)
    if grouped.empty:
        grouped = pd.DataFrame()
    result = grouped.rename(columns={"rows": "missing_count"}).copy()
    if not result.empty:
        result = result[
            ["exchange", "pilot_stratum", "year", "field", "missing_count", "failure_reason"]
        ]
    rd_rows = []
    base = panel.copy()
    base["current_status"] = base["delisting_date"].isna().map(
        {True: "current", False: "delisted"}
    )
    for (exchange, stratum, status, year), group in base.groupby(
        ["exchange", "pilot_stratum", "current_status", "year"], dropna=False
    ):
        rd_rows.append(
            {
                "exchange": exchange,
                "pilot_stratum": stratum,
                "year": year,
                "field": "rd_expense",
                "missing_count": int(group["rd_expense"].isna().sum()),
                "failure_reason": "FIELD_MISSING:rd_expense",
            }
        )
    result = pd.concat([result, pd.DataFrame(rd_rows)], ignore_index=True)
    return result.sort_values(
        ["exchange", "pilot_stratum", "year", "field", "failure_reason"]
    ).reset_index(drop=True)


def _field_quality(panel: pd.DataFrame) -> dict[str, object]:
    invalid = {}
    for field in ("size_ln", "leverage", "roa", "cash_ratio", "employee_ln", "rd_intensity"):
        values = pd.to_numeric(panel[field], errors="coerce")
        invalid[field] = int(np.isinf(values.to_numpy(dtype=float, na_value=np.nan)).sum())
    invalid_inputs = {
        field: int((pd.to_numeric(panel[field], errors="coerce") <= 0).sum())
        for field in ("total_assets", "employees", "revenue")
    }
    coverage = {
        field: float(panel[field].notna().mean()) if len(panel) else 0.0 for field in REPORT_FIELDS
    }
    return {
        "coverage": coverage,
        "invalid_infinite_counts": invalid,
        "nonpositive_inputs": invalid_inputs,
    }


def _bse_summary(sample: pd.DataFrame, panel: pd.DataFrame) -> dict[str, object]:
    bse = sample.loc[sample["exchange"].eq("BSE")]
    bse_panel = panel.loc[panel["exchange"].eq("BSE")] if not panel.empty else panel
    transferred = int(bse["pilot_stratum"].eq("bse_transferred").sum())
    native = int(bse["pilot_stratum"].eq("bse_post_2021").sum())
    query_codes = (
        bse_panel.get("financial_query_code", pd.Series(dtype="string"))
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )
    current_codes = (
        bse.get("stock_code_current", pd.Series(dtype="string")).astype(str).unique().tolist()
    )
    return {
        "BSE transferred queried": transferred,
        "BSE native queried": native,
        "old code used": 0,
        "new code used": 0,
        "fallback used": False,
        "current code queried": current_codes,
        "query codes observed": query_codes,
        "status": "BSE_MAPPING_REQUIRED",
    }


def run_pilot(
    universe_path: Path = UNIVERSE_PATH,
    output_dir: Path = OUTPUT_DIR,
    request_spacing: float = 1.0,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    universe = pd.read_parquet(universe_path)
    sample = build_financial_stress_test_sample(universe)
    sample.to_csv(output_dir / "sample.csv", index=False, encoding="utf-8-sig")
    selected_keys = sample["firm_key"].drop_duplicates().tolist()
    pilot_universe = select_pilot_universe_years(
        universe.loc[universe["firm_key"].isin(selected_keys)]
    )
    pilot_universe = pilot_universe.merge(
        sample[["firm_key", "pilot_stratum"]], on="firm_key", how="left", validate="many_to_one"
    )
    cache_dir = output_dir / "cache"
    cache_before = sum(
        financial_cache_path(cache_dir, firm_key).exists() for firm_key in selected_keys
    )
    summary: dict[str, object] = {
        "requested_years": list(YEARS),
        "sample_firms": int(sample["firm_key"].nunique()),
        "sample_firm_years": int(len(pilot_universe)),
        "exchange_distribution": sample["exchange"].value_counts().to_dict(),
        "strata_distribution": sample["pilot_stratum"].value_counts().to_dict(),
        "cache_hits_before_run": int(cache_before),
        "cache_misses_before_run": int(len(selected_keys) - cache_before),
        "blocked_requests": 0,
    }
    try:
        panel = run_financial_panel(pilot_universe, cache_dir, request_spacing=request_spacing)
    except SourceBlocked as exc:
        summary["blocked_requests"] = 1
        summary["status"] = "SOURCE_BLOCKED"
        summary["blocked_error"] = str(exc)
        _write_summary(summary, output_dir)
        raise
    panel = panel.merge(
        sample[["firm_key", "pilot_stratum"]], on="firm_key", how="left", validate="many_to_one"
    )
    metadata = universe.drop_duplicates("firm_key")[
        [
            "firm_key",
            "listing_date",
            "delisting_date",
            "industry_known",
            "is_financial_industry",
        ]
    ]
    panel = panel.drop(columns=["listing_date", "delisting_date"], errors="ignore").merge(
        metadata, on="firm_key", how="left", validate="many_to_one"
    )
    panel.to_parquet(output_dir / "financial_pilot.parquet", index=False)
    _stata_ready(panel).to_stata(output_dir / "financial_pilot.dta", write_index=False, version=118)
    coverage = coverage_table(panel)
    overall_coverage = pd.DataFrame(
        {
            "exchange": ["ALL"] * len(REPORT_FIELDS),
            "year": ["ALL"] * len(REPORT_FIELDS),
            "field": list(REPORT_FIELDS),
            "coverage": [int(panel[field].notna().sum()) for field in REPORT_FIELDS],
            "denominator": [len(panel)] * len(REPORT_FIELDS),
        }
    )
    pd.concat([coverage, overall_coverage], ignore_index=True).to_csv(
        output_dir / "coverage.csv", index=False
    )
    _failure_output(panel).to_csv(output_dir / "failure_decomposition.csv", index=False)
    cache_after = sum(
        financial_cache_path(cache_dir, firm_key).exists() for firm_key in selected_keys
    )
    successful = panel.groupby("firm_key")["financial_success"].all()
    summary.update(
        {
            "successful_firms": int(successful.sum()),
            "failed_firms": int((~successful).sum()),
            "cache_hits_after_run": int(cache_after),
            "cache_files": int(len(list(cache_dir.glob("*.parquet")))),
            "field_quality": _field_quality(panel),
            "bse": _bse_summary(sample, panel),
            "panel_rows": int(len(panel)),
            "status": "COMPLETED",
        }
    )
    _write_summary(summary, output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=_json_value))
    return summary


if __name__ == "__main__":
    run_pilot()
