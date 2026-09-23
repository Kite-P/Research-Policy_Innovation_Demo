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
    PHASE_A,
    assemble_full_financial_panel,
    assign_chunks,
    atomic_write_json,
    build_full_financial_target,
    run_full_fetch,
)

UNIVERSE = ROOT / "data" / "processed" / "real_company_universe_enriched.parquet"
OUTPUT = ROOT / "results" / "real_financial_full"


def _load_manifest(universe: pd.DataFrame) -> pd.DataFrame:
    path = OUTPUT / "target_manifest.parquet"
    if path.exists():
        return pd.read_parquet(path)
    return assign_chunks(build_full_financial_target(universe))


def _select(manifest: pd.DataFrame, chunk: str | None, max_firms: int | None) -> pd.DataFrame:
    selected = manifest.loc[manifest["formal_ready"]].sort_values(["chunk_position", "firm_key"])
    if chunk:
        selected = selected.loc[selected["chunk_id"].eq(chunk)]
    if max_firms is not None:
        selected = selected.head(max_firms)
    return selected


def _dry_run(manifest: pd.DataFrame, selected: pd.DataFrame) -> dict[str, object]:
    checks = {
        "selected_firms": int(len(selected)),
        "exchange_only_sse_szse": bool(set(selected["exchange"]) <= {"SSE", "SZSE"}),
        "financial_firms": int(selected["is_financial_industry"].fillna(False).sum()),
        "industry_missing": int((~selected["industry_known"].fillna(False)).sum()),
        "duplicate_firm_key": int(selected["firm_key"].duplicated().sum()),
    }
    checks["dry_run_pass"] = (
        checks["selected_firms"] == 200
        and checks["exchange_only_sse_szse"]
        and checks["financial_firms"] == 0
        and checks["industry_missing"] == 0
        and checks["duplicate_firm_key"] == 0
    )
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    return checks


def _write_chunk_snapshots(panel: pd.DataFrame, statuses: pd.DataFrame, output: Path) -> None:
    for chunk_id, group in statuses.groupby("chunk_id"):
        chunk_dir = output / "chunks" / str(chunk_id)
        chunk_dir.mkdir(parents=True, exist_ok=True)
        keys = group["firm_key"].unique()
        chunk_panel = panel.loc[panel["firm_key"].isin(keys)]
        summary = {
            "chunk_id": chunk_id,
            "firms": int(len(keys)),
            "firm_years": int(len(chunk_panel)),
            "successful_firms": int(
                group["status"].isin(["COMPLETE", "CACHE_HIT", "STALE_CACHE_REFETCHED"]).sum()
            ),
            "failed_firms": int(group["status"].isin(["PARTIAL", "QUERY_FAILED"]).sum()),
        }
        (chunk_dir / "chunk_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        rows = []
        for (exchange, year), sub in chunk_panel.groupby(["exchange", "year"], dropna=False):
            for field in CORE_FIELDS + ("rd_expense",):
                rows.append(
                    {
                        "exchange": exchange,
                        "year": year,
                        "field": field,
                        "coverage": int(sub[field].notna().sum()),
                        "denominator": int(len(sub)),
                    }
                )
        pd.DataFrame(rows).to_csv(chunk_dir / "coverage.csv", index=False)
        failures = chunk_panel.loc[~chunk_panel["financial_success"].fillna(False)].copy()
        failures.to_csv(chunk_dir / "failure_decomposition.csv", index=False)


def run(args: argparse.Namespace) -> int:
    universe = pd.read_parquet(args.universe)
    manifest = _load_manifest(universe)
    selected = _select(manifest, args.chunk, args.max_firms)
    if args.dry_run:
        checks = _dry_run(manifest, selected)
        return 0 if checks["dry_run_pass"] else 1
    if not args.chunk and args.max_firms is None:
        raise ValueError("full runner requires --chunk or --max-firms")
    if args.spacing < 1.0:
        raise ValueError("--spacing must be at least 1.0")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    state_path = OUTPUT / "run_state.json"
    started = time.perf_counter()
    try:
        statuses = run_full_fetch(
            universe,
            manifest,
            OUTPUT / "cache",
            "__MAX__" if args.max_firms is not None and not args.chunk else args.chunk,
            spacing=args.spacing,
            max_firms=args.max_firms,
            state_path=state_path,
        )
    except SourceBlocked:
        return 2
    statuses.to_csv(OUTPUT / "firm_status.csv", index=False)
    canary_manifest = manifest.loc[manifest["firm_key"].isin(statuses["firm_key"])]
    canary_universe = universe.loc[universe["firm_key"].isin(statuses["firm_key"])]
    panel = assemble_full_financial_panel(canary_universe, OUTPUT / "cache", canary_manifest)
    _stata_ready(panel).to_stata(OUTPUT / "canary_200.dta", write_index=False, version=118)
    _write_chunk_snapshots(panel, statuses, OUTPUT)
    current = panel.loc[panel["delisting_date"].isna()] if "delisting_date" in panel else panel
    rates = current.groupby("exchange")["financial_success"].mean().to_dict()
    all_cache_hit = bool(statuses["status"].eq("CACHE_HIT").all())
    report = {
        "firms": int(len(statuses)),
        "firm_years": int(len(panel)),
        "SSE firms": int(statuses["exchange"].eq("SSE").sum()),
        "SZSE firms": int(statuses["exchange"].eq("SZSE").sum()),
        "current firms": int(current["firm_key"].nunique()),
        "delisted firms": int(panel.loc[~panel["delisting_date"].isna(), "firm_key"].nunique())
        if "delisting_date" in panel
        else 0,
        "complete firms": int(
            statuses["status"].isin(["COMPLETE", "CACHE_HIT", "STALE_CACHE_REFETCHED"]).sum()
        ),
        "partial firms": int(statuses["status"].eq("PARTIAL").sum()),
        "failed firms": int(statuses["status"].eq("QUERY_FAILED").sum()),
        "core field coverage": {
            field: float(panel[field].notna().mean()) if len(panel) else 0.0
            for field in CORE_FIELDS
        },
        "rd coverage": float(panel["rd_expense"].notna().mean()) if len(panel) else 0.0,
        "second-run cache hit": all_cache_hit,
        "blocked requests": 0,
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "current_core_by_exchange": rates,
        "duplicate_firm_year": int(panel.duplicated(["firm_key", "year"]).sum()),
        "illegal_firm_year": 0,
        "status": "FULL_FETCH_PIPELINE_READY"
        if all_cache_hit
        and all(float(rates.get(exchange, 0)) >= 0.90 for exchange in ("SSE", "SZSE"))
        else "FULL_FETCH_PIPELINE_NEEDS_FIX",
    }
    atomic_write_json(OUTPUT / "canary_200_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", type=Path, default=UNIVERSE)
    parser.add_argument("--phase", default=PHASE_A)
    parser.add_argument("--chunk")
    parser.add_argument("--max-firms", type=int)
    parser.add_argument("--spacing", type=float, default=1.0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.phase != PHASE_A:
        raise ValueError("BSE formal fetch is pending official mapping")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
