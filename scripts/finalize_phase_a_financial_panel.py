from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.build_real_financial_panel import CORE_FIELDS, _stata_ready  # noqa: E402
from src.real_financial_full import assemble_full_financial_panel  # noqa: E402

UNIVERSE = ROOT / "data" / "processed" / "real_company_universe_enriched.parquet"
OUTPUT = ROOT / "results" / "real_financial_full"


def finalize() -> dict[str, object]:
    universe = pd.read_parquet(UNIVERSE)
    manifest = pd.read_parquet(OUTPUT / "target_manifest.parquet")
    statuses = pd.read_csv(OUTPUT / "firm_status.csv")
    target = manifest.loc[manifest["formal_ready"]].copy()
    panel = assemble_full_financial_panel(universe, OUTPUT / "cache", manifest)
    processed = ROOT / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(processed / "real_financials_sse_szse_nonfinancial.parquet", index=False)
    _stata_ready(panel).to_stata(
        processed / "real_financials_sse_szse_nonfinancial.dta", write_index=False, version=118
    )
    coverage_rows = []
    for (exchange, sample_type), group in panel.assign(
        sample_type=panel["delisting_date"].isna().map({True: "current", False: "delisted"})
    ).groupby(["exchange", "sample_type"], dropna=False):
        for field in CORE_FIELDS + ("rd_expense",):
            coverage_rows.append({
                "exchange": exchange, "sample_type": sample_type, "field": field,
                "coverage": int(group[field].notna().sum()), "denominator": int(len(group)),
                "coverage_rate": float(group[field].notna().mean()) if len(group) else 0.0,
            })
    pd.DataFrame(coverage_rows).to_csv(OUTPUT / "final_coverage.csv", index=False)
    failures = panel.loc[~panel["financial_success"].fillna(False)].copy()
    failures.to_csv(OUTPUT / "final_failure_decomposition.csv", index=False)
    statuses.to_csv(OUTPUT / "final_firm_status_summary.csv", index=False)
    listing = pd.to_datetime(panel["listing_date"], errors="coerce").dt.year
    delisting = pd.to_datetime(panel["delisting_date"], errors="coerce").dt.year
    illegal = int(
        ((panel["year"] < listing) | (delisting.notna() & (panel["year"] > delisting))).sum()
    )
    current = panel.loc[panel["delisting_date"].isna()]
    current_rates = current.groupby("exchange")["financial_success"].mean().to_dict()
    summary = {
        "firms": int(panel["firm_key"].nunique()), "firm_years": int(len(panel)),
        "target_firms": int(target["firm_key"].nunique()),
        "target_firm_years": int(len(universe[universe["firm_key"].isin(target["firm_key"])])),
        "duplicate": int(panel.duplicated(["firm_key", "year"]).sum()),
        "illegal_firm_year": illegal,
        "exchange_only": sorted(panel["exchange"].dropna().unique().tolist()),
        "financial_missing": int(
            (~panel.get("industry_known", pd.Series(True, index=panel.index))).sum()
        ),
        "current_core_by_exchange": current_rates,
        "complete": int(statuses["data_status"].eq("COMPLETE").sum()),
        "partial": int(statuses["data_status"].eq("PARTIAL").sum()),
        "query_failed": int(statuses["data_status"].eq("QUERY_FAILED").sum()),
        "not_fetched": int(statuses["data_status"].eq("NOT_FETCHED").sum()),
        "source_blocked": int(statuses["retrieval_status"].eq("SOURCE_BLOCKED").sum()),
    }
    (OUTPUT / "phase_a_final_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


if __name__ == "__main__":
    print(json.dumps(finalize(), ensure_ascii=False, indent=2))
