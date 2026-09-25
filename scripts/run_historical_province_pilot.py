from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.historical_province import (  # noqa: E402
    build_historical_province_target,
    evaluate_historical_province_pilot_gate,
    resolve_historical_province_panel,
    select_historical_province_pilot,
    summarize_historical_province_coverage,
)
from src.historical_province_sources import (  # noqa: E402
    CNINFOAnnualReportClient,
    SourceBlocked,
)

UNIVERSE = ROOT / "data" / "processed" / "real_company_universe_enriched.parquet"
OUTPUT = ROOT / "results" / "historical_province"
SOURCE_PROBE = OUTPUT / "source_probe.json"
SEED = "20260925"


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    temporary.replace(path)


def run(args: argparse.Namespace) -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    probe = json.loads(SOURCE_PROBE.read_text(encoding="utf-8"))
    if probe.get("status") != "SOURCE_PROBE_PASS":
        raise ValueError("SOURCE_PROBE_NOT_PASSED")
    if len([case for case in probe.get("change_case_audits", [])
            if case.get("audit_status") == "PASS"]) < 5:
        raise ValueError("FIVE_CHANGE_CASES_NOT_VERIFIED")

    universe = pd.read_parquet(args.universe)
    target = build_historical_province_target(universe)
    firms = target.sort_values("year").drop_duplicates("firm_key").copy()
    pilot = select_historical_province_pilot(firms, seed=SEED)
    pilot_keys = set(pilot["firm_key"])
    sample_target = target.loc[target["firm_key"].isin(pilot_keys)].copy()
    sample_target = sample_target.merge(
        pilot[["firm_key", "pilot_stratum", "current_status"]],
        on="firm_key",
        how="left",
        validate="many_to_one",
    )
    sample_target.to_csv(OUTPUT / "pilot_sample.csv", index=False, encoding="utf-8-sig")

    state_path = OUTPUT / "pilot_run_state.json"
    if state_path.exists() and not args.resume:
        raise ValueError("PILOT_STATE_EXISTS_USE_RESUME")
    old_state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    if old_state.get("seed", SEED) != SEED:
        raise ValueError("PILOT_SEED_MISMATCH")
    cached_records: list[dict[str, object]] = []
    cache_dir = OUTPUT / "cache"
    if args.resume and cache_dir.exists():
        for cache_path in sorted(cache_dir.glob("*.json")):
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                cached_records.extend(cached.get("records", []))
            except (OSError, ValueError, TypeError):
                continue
    cached_records = [row for row in cached_records if row.get("firm_key") in pilot_keys]
    completed = set(old_state.get("completed_firms", []))
    client = CNINFOAnnualReportClient(cache_dir, request_spacing=args.spacing)
    _atomic_json(state_path, {
        "status": "HISTORICAL_PROVINCE_PILOT_RUNNING",
        "seed": SEED,
        "sample_firms": len(pilot),
        "sample_firm_years": len(sample_target),
        "completed_firms": sorted(completed),
        "started_at": old_state.get("started_at", datetime.now(timezone.utc).isoformat()),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })

    all_records = list(cached_records)
    try:
        for idx, firm in enumerate(pilot.to_dict("records"), start=1):
            firm_key = str(firm["firm_key"])
            if firm_key in completed:
                continue
            years = sorted(
                sample_target.loc[sample_target["firm_key"].eq(firm_key), "year"].astype(int)
            )
            print(f"START {idx}/{len(pilot)} {firm_key} years={len(years)}", flush=True)
            firm_records = client.fetch_firm_reports(firm, years=years)
            all_records = [row for row in all_records if row.get("firm_key") != firm_key]
            all_records.extend(firm_records)
            completed.add(firm_key)
            state = {
                "status": "HISTORICAL_PROVINCE_PILOT_RUNNING",
                "seed": SEED,
                "sample_firms": len(pilot),
                "sample_firm_years": len(sample_target),
                "completed_firms": sorted(completed),
                "started_at": old_state.get("started_at", datetime.now(timezone.utc).isoformat()),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "last_completed_firm": firm_key,
            }
            _atomic_json(state_path, state)
            print(f"DONE {idx}/{len(pilot)} {firm_key}", flush=True)
    except SourceBlocked as exc:
        _atomic_json(state_path, {
            **json.loads(state_path.read_text(encoding="utf-8")),
            "status": "HISTORICAL_PROVINCE_PAUSED_SOURCE_BLOCKED",
            "source_block_reason": str(exc),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        print("HISTORICAL_PROVINCE_PAUSED_SOURCE_BLOCKED", flush=True)
        return 2
    except Exception as exc:
        _atomic_json(state_path, {
            **json.loads(state_path.read_text(encoding="utf-8")),
            "status": "HISTORICAL_PROVINCE_PILOT_INTERRUPTED",
            "last_error": f"{type(exc).__name__}: {exc}",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        raise

    panel, conflicts = resolve_historical_province_panel(sample_target, all_records)
    coverage = summarize_historical_province_coverage(panel)
    final_status, gate = evaluate_historical_province_pilot_gate(
        panel, change_cases_verified=sum(
            case.get("audit_status") == "PASS" for case in probe["change_case_audits"]
        )
    )
    panel.to_parquet(OUTPUT / "pilot_status.parquet", index=False)
    panel.to_csv(OUTPUT / "pilot_status.csv", index=False, encoding="utf-8-sig")
    coverage.to_csv(OUTPUT / "pilot_coverage.csv", index=False, encoding="utf-8-sig")
    conflicts.to_csv(OUTPUT / "pilot_conflicts.csv", index=False, encoding="utf-8-sig")
    _atomic_json(OUTPUT / "pilot_gate.json", {
        "status": final_status,
        "gate": gate,
        "firms": int(panel["firm_key"].nunique()),
        "firm_years": len(panel),
        "source_probe_status": probe["status"],
        "finished_at": datetime.now(timezone.utc).isoformat(),
    })
    _atomic_json(state_path, {
        **json.loads(state_path.read_text(encoding="utf-8")),
        "status": final_status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    })
    print(final_status, flush=True)
    print(json.dumps(gate, ensure_ascii=False, indent=2), flush=True)
    return 0 if final_status == "HISTORICAL_PROVINCE_PILOT_PASS" else 3


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
