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


def write_canary_meta(meta_path: Path, run_number: int, status: str) -> None:
    from src.real_financial_full import atomic_write_json

    atomic_write_json(meta_path, {
        "canary_run_count": run_number,
        "last_run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "last_status": status,
    })


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
    meta_path = OUTPUT / "canary_cross_meta.json"
    status_path = OUTPUT / "canary_cross_firm_status.csv"
    if state_path.exists() and not args.resume:
        raise ValueError("RUN_STATE_EXISTS_USE_RESUME")
    previous_meta = (
        json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    )
    run_number = int(previous_meta.get("canary_run_count", 0)) + 1
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
    listing = pd.to_datetime(panel["listing_date"], errors="coerce").dt.year
    delisting = pd.to_datetime(panel["delisting_date"], errors="coerce").dt.year
    illegal = int(
        ((panel["year"] < listing) | (delisting.notna() & (panel["year"] > delisting))).sum()
    )
    current_core = current.groupby("exchange")["financial_success"].mean().to_dict()
    second_cache_hit = run_number >= 2 and bool(
        statuses["retrieval_status"].eq(RETRIEVAL_CACHE_HIT).all()
    )
    data_gate = (
        len(statuses) == 200
        and statuses["exchange"].value_counts().to_dict() == {"SSE": 100, "SZSE": 100}
        and int(panel.duplicated(["firm_key", "year"]).sum()) == 0
        and illegal == 0
        and int(statuses["retrieval_status"].eq("SOURCE_BLOCKED").sum()) == 0
        and all(float(current_core.get(exchange, 0)) >= 0.90 for exchange in ("SSE", "SZSE"))
    )
    report = {
        "firms": int(len(statuses)), "firm_years": int(len(panel)),
        "SSE firms": int(statuses["exchange"].eq("SSE").sum()),
        "SZSE firms": int(statuses["exchange"].eq("SZSE").sum()),
        "run_number": run_number,
        "second_run_cache_hit": second_cache_hit,
        "network_requests": int((~statuses["retrieval_status"].eq(RETRIEVAL_CACHE_HIT)).sum()),
        "duplicate_firm_year": int(panel.duplicated(["firm_key", "year"]).sum()),
        "current_core_by_exchange": current_core,
        "illegal_firm_year": illegal,
        "core_coverage": {field: float(panel[field].notna().mean()) for field in CORE_FIELDS},
        "rd_coverage": float(panel["rd_expense"].notna().mean()),
        "blocked": int(statuses["retrieval_status"].eq("SOURCE_BLOCKED").sum()),
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "status": (
            "CROSS_EXCHANGE_CANARY_READY" if data_gate and second_cache_hit
            else "CROSS_EXCHANGE_CANARY_FIRST_PASS" if data_gate and run_number == 1
            else "CROSS_EXCHANGE_CANARY_NEEDS_FIX"
        ),
    }
    write_canary_meta(meta_path, run_number, report["status"])
    (OUTPUT / "canary_cross_200_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "CROSS_EXCHANGE_CANARY_READY" else (0 if run_number == 1 else 1)


if __name__ == "__main__":
    raise SystemExit(main())
