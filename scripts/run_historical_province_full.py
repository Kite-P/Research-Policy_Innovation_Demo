from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.historical_province import (  # noqa: E402
    assign_historical_province_chunks,
    build_historical_province_target,
    province_from_address,
    resolve_historical_province_panel,
    summarize_historical_province_coverage,
)
from src.historical_province_sources import (  # noqa: E402
    CNINFOAnnualReportClient,
    SourceBlocked,
    parse_address_change_events,
)

UNIVERSE = ROOT / "data" / "processed" / "real_company_universe_enriched.parquet"
OUTPUT = ROOT / "results" / "historical_province"
CHUNK_SIZE = 100


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    temporary.replace(path)


def _write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8-sig")
    temporary.replace(path)


def run(args: argparse.Namespace) -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    gate_path = OUTPUT / "pilot_gate.json"
    gate_result = json.loads(gate_path.read_text(encoding="utf-8"))
    if gate_result.get("status") != "HISTORICAL_PROVINCE_PILOT_PASS":
        raise ValueError("PILOT_GATE_NOT_PASSED")

    universe = pd.read_parquet(args.universe)
    target = build_historical_province_target(universe)
    firms = target.sort_values("firm_key").drop_duplicates("firm_key").reset_index(drop=True)
    if len(firms) != 5272 or len(target) != 28548:
        raise ValueError(f"FULL_TARGET_MISMATCH firms={len(firms)} firm_years={len(target)}")
    chunk_members = assign_historical_province_chunks(firms, chunk_size=CHUNK_SIZE)
    target_fingerprint = pd.util.hash_pandas_object(
        target[["firm_key", "year"]], index=False
    ).astype("uint64").to_numpy().tobytes().hex()
    manifest_fingerprint = pd.util.hash_pandas_object(
        firms[["firm_key"]], index=False
    ).astype("uint64").to_numpy().tobytes().hex()
    state_path = OUTPUT / "full_run_state.json"
    status_path = OUTPUT / "firm_status.csv"
    if state_path.exists() and not args.resume:
        raise ValueError("FULL_RUN_STATE_EXISTS_USE_RESUME")
    prior = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    for key, expected in (
        ("target_fingerprint", target_fingerprint),
        ("manifest_fingerprint", manifest_fingerprint),
    ):
        if prior.get(key, expected) != expected:
            raise ValueError(f"{key.upper()}_MISMATCH")
    status_frame = pd.read_csv(status_path) if status_path.exists() else pd.DataFrame(
        columns=["firm_key", "chunk_id", "firm_years", "historical_resolved", "status"]
    )
    if len(status_frame) and set(status_frame.firm_key) - set(firms.firm_key):
        raise ValueError("STATUS_HAS_KEYS_OUTSIDE_TARGET")
    completed = set(status_frame.loc[status_frame.status.eq("COMPLETE"), "firm_key"])
    completed_chunks = set(prior.get("completed_chunks", []))
    client = CNINFOAnnualReportClient(OUTPUT / "cache", request_spacing=args.spacing)
    started_at = prior.get("started_at", datetime.now(timezone.utc).isoformat())

    def save_state(status: str, **extra: object) -> None:
        _atomic_json(state_path, {
            "status": status,
            "target_firms": len(firms),
            "target_firm_years": len(target),
            "chunk_size": CHUNK_SIZE,
            "total_chunks": len(chunk_members),
            "completed_chunks": sorted(completed_chunks),
            "completed_firms": len(completed),
            "target_fingerprint": target_fingerprint,
            "manifest_fingerprint": manifest_fingerprint,
            "started_at": started_at,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **extra,
        })

    save_state("HISTORICAL_PROVINCE_FULL_RUNNING")
    for chunk_id, member_keys in chunk_members.items():
        if chunk_id in completed_chunks and set(member_keys).issubset(completed):
            continue
        print(f"START {chunk_id} firms={len(member_keys)}", flush=True)
        chunk = firms.loc[firms.firm_key.isin(member_keys)]
        for firm in chunk.to_dict("records"):
            firm_key = str(firm["firm_key"])
            if firm_key in completed:
                continue
            years = sorted(
                target.loc[target.firm_key.eq(firm_key), "year"].astype(int).tolist()
            )
            try:
                client.fetch_firm_reports(firm, years=years)
            except SourceBlocked as exc:
                save_state(
                    "HISTORICAL_PROVINCE_PAUSED_SOURCE_BLOCKED",
                    active_chunk=chunk_id,
                    last_completed_firm=(
                        status_frame.iloc[-1].firm_key if len(status_frame) else None
                    ),
                    source_block_reason=str(exc),
                )
                print("HISTORICAL_PROVINCE_PAUSED_SOURCE_BLOCKED", flush=True)
                return 2
            completed.add(firm_key)
            records_path = client.cache_dir / (
                re.sub(r"[^A-Za-z0-9_.-]+", "_", firm_key) + ".json"
            )
            records = json.loads(records_path.read_text(encoding="utf-8")).get("records", [])
            status_frame = pd.concat(
                [
                    status_frame.loc[status_frame.firm_key.ne(firm_key)],
                    pd.DataFrame([{
                        "firm_key": firm_key,
                        "chunk_id": chunk_id,
                        "firm_years": len(years),
                        "historical_resolved": sum(
                            bool(row.get("province_raw")) for row in records
                            if row.get("source_report_year") in years
                        ),
                        "status": "COMPLETE",
                    }]),
                ],
                ignore_index=True,
            )
            _write_csv_atomic(status_frame, status_path)
            if len(completed) % 25 == 0:
                save_state(
                    "HISTORICAL_PROVINCE_FULL_RUNNING",
                    active_chunk=chunk_id,
                    last_completed_firm=firm_key,
                )
                print(
                    f"PROGRESS firms={len(completed)}/{len(firms)} "
                    f"chunks={len(completed_chunks)}/{len(chunk_members)}",
                    flush=True,
                )
        completed_chunks.add(chunk_id)
        save_state(
            "HISTORICAL_PROVINCE_FULL_RUNNING",
            active_chunk=None,
            last_completed_firm=(status_frame.iloc[-1].firm_key if len(status_frame) else None),
        )
        print(
            f"DONE {chunk_id} chunks={len(completed_chunks)}/{len(chunk_members)} "
            f"firms={len(completed)}",
            flush=True,
        )

    # Reload only the full target's firm caches; probe-only firms are ignored.
    target_keys = set(firms.firm_key.astype(str))
    source_records: list[dict[str, object]] = []
    for cache_path in sorted((OUTPUT / "cache").glob("*.json")):
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            source_records.extend(
                row for row in cache.get("records", []) if row.get("firm_key") in target_keys
            )
        except (OSError, ValueError, TypeError):
            continue
    panel, conflicts = resolve_historical_province_panel(target, source_records)
    expected_keys = set(zip(target.firm_key, target.year))
    actual_keys = set(zip(panel.firm_key, panel.year))
    if len(panel) != len(target) or actual_keys != expected_keys:
        raise ValueError("FINAL_PANEL_KEY_SET_MISMATCH")
    coverage = summarize_historical_province_coverage(panel)
    panel.to_parquet(
        ROOT / "data" / "processed" / "firm_year_historical_province.parquet",
        index=False,
    )
    stata_panel = panel.drop(columns=["province_source_temporal_adjusted"], errors="ignore")
    stata_panel.to_stata(
        ROOT / "data" / "processed" / "firm_year_historical_province.dta",
        write_index=False,
        version=118,
    )
    _write_csv_atomic(panel, OUTPUT / "full_panel_audit.csv")
    _write_csv_atomic(coverage, OUTPUT / "full_coverage.csv")
    _write_csv_atomic(conflicts, OUTPUT / "conflicts.csv")
    _write_csv_atomic(status_frame, status_path)
    event_rows = []
    for record in source_records:
        for event in parse_address_change_events(record.get("registered_address_history_raw")):
            event_rows.append({
                "firm_key": record["firm_key"],
                "old_province": province_from_address(event["old_address"]),
                "new_province": province_from_address(event["new_address"]),
                "change_year": int(event["effective_date"][:4]),
                "effective_date": event["effective_date"],
                "source_url_or_id": record.get("source_url_or_id"),
                "evidence": f"{event['old_address']} -> {event['new_address']}",
            })
    changes = pd.DataFrame(event_rows)
    if len(changes):
        changes = changes.drop_duplicates(
            ["firm_key", "effective_date", "old_province", "new_province"]
        )
        changes = changes.loc[
            changes.old_province.notna()
            & changes.new_province.notna()
            & changes.old_province.ne(changes.new_province)
        ]
    _write_csv_atomic(changes, OUTPUT / "province_changes.csv")

    policy_path = ROOT / "data" / "processed" / "policy_reports_clean.parquet"
    if policy_path.exists():
        policy = pd.read_parquet(policy_path)
        required_policy_years = set(range(2019, 2026))
        policy_years = policy.groupby("province")["report_year"].agg(set)
        policy_provinces = {
            province for province, years in policy_years.items()
            if required_policy_years.issubset(set(map(int, years)))
        }
    else:
        policy_provinces = set()
    historical_rows = panel.loc[
        panel.province_historical.notna()
        & panel.province_status.isin({"historical_confirmed", "historical_inferred"})
    ]
    policy_rows = []
    for province, group in historical_rows.groupby("province_historical"):
        firms_in_province = set(group.firm_key)
        firm_cohort = panel.loc[panel.firm_key.isin(firms_in_province)]
        resolved_cohort = firm_cohort.province_status.isin(
            {"historical_confirmed", "historical_inferred"}
        )
        policy_rows.append({
            "province": province,
            "firms": int(group.firm_key.nunique()),
            "firm_years": int(len(group)),
            "primary_historical_coverage": (
                float(resolved_cohort.mean()) if len(firm_cohort) else 0.0
            ),
            "existing_policy_corpus_available": province in policy_provinces,
        })
    _write_csv_atomic(pd.DataFrame(policy_rows), OUTPUT / "policy_geography_coverage.csv")
    save_state(
        "HISTORICAL_PROVINCE_FULL_FETCH_COMPLETE",
        completed_chunks=sorted(completed_chunks),
        final_firms=int(panel.firm_key.nunique()),
        final_firm_years=len(panel),
        duplicate_keys=int(panel.duplicated(["firm_key", "year"]).sum()),
        source_records=len(source_records),
        unresolved_conflicts=len(conflicts),
    )
    print("HISTORICAL_PROVINCE_FULL_FETCH_COMPLETE", flush=True)
    print(coverage.to_string(index=False), flush=True)
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
