from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.build_real_financial_panel import SourceBlocked  # noqa: E402
from src.real_financial_full import (  # noqa: E402
    assign_chunks,
    build_full_financial_target,
    chunk_is_complete,
    manifest_fingerprint,
    run_full_fetch,
    universe_fingerprint,
)

UNIVERSE = ROOT / "data" / "processed" / "real_company_universe_enriched.parquet"
OUTPUT = ROOT / "results" / "real_financial_full"


def run(args: argparse.Namespace) -> int:
    universe = pd.read_parquet(args.universe)
    manifest_path = OUTPUT / "target_manifest.parquet"
    manifest = pd.read_parquet(manifest_path) if manifest_path.exists() else assign_chunks(
        build_full_financial_target(universe)
    )
    summary = json.loads((OUTPUT / "manifest_summary.json").read_text(encoding="utf-8"))
    if summary.get("universe fingerprint") != universe_fingerprint(universe):
        raise ValueError("UNIVERSE_FINGERPRINT_MISMATCH")
    if summary.get("manifest fingerprint") != manifest_fingerprint(manifest):
        raise ValueError("MANIFEST_FINGERPRINT_MISMATCH")
    state_path = OUTPUT / "phase_a_run_state.json"
    status_path = OUTPUT / "firm_status.csv"
    if state_path.exists() and not args.resume:
        raise ValueError("RUN_STATE_EXISTS_USE_RESUME")
    prior = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    statuses = pd.read_csv(status_path) if status_path.exists() else pd.DataFrame()
    chunks = sorted(manifest.loc[manifest["formal_ready"], "chunk_id"].dropna().unique())
    completed = set(prior.get("completed_chunks", []))
    for chunk_id in chunks:
        if chunk_id in completed and chunk_is_complete(chunk_id, manifest, statuses):
            continue
        print(f"START {chunk_id}", flush=True)
        try:
            statuses = run_full_fetch(
                universe,
                manifest,
                OUTPUT / "cache",
                chunk_id,
                spacing=args.spacing,
                state_path=state_path,
                status_path=status_path,
                resume=state_path.exists(),
                expected_fingerprint=summary["universe fingerprint"],
                expected_manifest_fingerprint=summary["manifest fingerprint"],
            )
        except SourceBlocked:
            print("FULL_FETCH_PAUSED_SOURCE_BLOCKED", flush=True)
            return 2
        statuses = pd.read_csv(status_path)
        if not chunk_is_complete(chunk_id, manifest, statuses):
            raise RuntimeError(f"CHUNK_NOT_COMPLETE:{chunk_id}")
        completed.add(chunk_id)
        print(f"DONE {chunk_id} {len(completed)}/{len(chunks)}", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", type=Path, default=UNIVERSE)
    parser.add_argument("--spacing", type=float, default=1.0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.spacing < 1.0:
        raise ValueError("--spacing must be at least 1.0")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
