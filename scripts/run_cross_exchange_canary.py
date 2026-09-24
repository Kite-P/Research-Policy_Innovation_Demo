from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.build_real_financial_panel import CORE_FIELDS, SourceBlocked, _stata_ready  # noqa: E402
from src.real_financial_full import (  # noqa: E402
    RETRIEVAL_CACHE_HIT,
    assemble_full_financial_panel,
    manifest_fingerprint,
    run_full_fetch,
    select_cross_exchange_canary,
    universe_fingerprint,
)

UNIVERSE = ROOT / "data" / "processed" / "real_company_universe_enriched.parquet"
OUTPUT = ROOT / "results" / "real_financial_full"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--spacing", type=float, default=1.0)
    args = parser.parse_args()
    universe = pd.read_parquet(UNIVERSE)
    manifest = pd.read_parquet(OUTPUT / "target_manifest.parquet")
    summary = json.loads((OUTPUT / "manifest_summary.json").read_text(encoding="utf-8"))
    if summary["universe fingerprint"] != universe_fingerprint(universe):
        raise ValueError("UNIVERSE_FINGERPRINT_MISMATCH")
    if summary["manifest fingerprint"] != manifest_fingerprint(manifest):
        raise ValueError("MANIFEST_FINGERPRINT_MISMATCH")
    selected = select_cross_exchange_canary(manifest)
    state_path = OUTPUT / "canary_cross_run_state.json"
    status_path = OUTPUT / "canary_cross_firm_status.csv"
    if state_path.exists() and not args.resume:
        raise ValueError("RUN_STATE_EXISTS_USE_RESUME")
    chunks = selected["chunk_id"].drop_duplicates().tolist()
    started = time.perf_counter()
    statuses = pd.DataFrame()
    try:
        for chunk_id in chunks:
            statuses = run_full_fetch(
                universe, manifest, OUTPUT / "cache", chunk_id,
                spacing=args.spacing, state_path=state_path, status_path=status_path,
                resume=state_path.exists(), expected_fingerprint=summary["universe fingerprint"],
                expected_manifest_fingerprint=summary["manifest fingerprint"],
            )
    except SourceBlocked:
        return 2
    statuses = pd.read_csv(status_path)
    statuses = statuses.loc[statuses["firm_key"].isin(selected["firm_key"])].copy()
    panel = assemble_full_financial_panel(
        universe.loc[universe["firm_key"].isin(statuses["firm_key"])], OUTPUT / "cache", manifest
    )
    dta = OUTPUT / "canary_cross_200.dta"
    _stata_ready(panel).to_stata(dta, write_index=False, version=118)
    current = panel.loc[panel["delisting_date"].isna()]
    report = {
        "firms": int(len(statuses)), "firm_years": int(len(panel)),
        "SSE firms": int(statuses["exchange"].eq("SSE").sum()),
        "SZSE firms": int(statuses["exchange"].eq("SZSE").sum()),
        "second_run_cache_hit": bool(statuses["retrieval_status"].eq(RETRIEVAL_CACHE_HIT).all()),
        "network_requests": int((~statuses["retrieval_status"].eq(RETRIEVAL_CACHE_HIT)).sum()),
        "duplicate_firm_year": int(panel.duplicated(["firm_key", "year"]).sum()),
        "current_core_by_exchange": current.groupby("exchange")["financial_success"]
        .mean()
        .to_dict(),
        "core_coverage": {field: float(panel[field].notna().mean()) for field in CORE_FIELDS},
        "rd_coverage": float(panel["rd_expense"].notna().mean()),
        "blocked": int(statuses["retrieval_status"].eq("SOURCE_BLOCKED").sum()),
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "status": "CROSS_EXCHANGE_CANARY_READY",
    }
    (OUTPUT / "canary_cross_200_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
