from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_full_financial_manifest import build_manifest  # noqa: E402
from scripts.finalize_phase_a_financial_panel import finalize  # noqa: E402
from scripts.run_historical_province_full import _prepare_stata_export  # noqa: E402
from src.build_real_company_universe import (  # noqa: E402
    VERIFIED_B_SHARE_LISTING_ALIAS_KEYS,
    _stata_ready,
    exclude_verified_b_share_listing_aliases,
)
from src.historical_province import (  # noqa: E402
    assign_historical_province_chunks,
    build_historical_province_target,
    build_policy_geography_coverage,
    evaluate_historical_province_full_gate,
    summarize_historical_province_coverage,
)
from src.real_financial_full import (  # noqa: E402
    DATA_COMPLETE,
    DATA_FAILED,
    DATA_PARTIAL,
    manifest_fingerprint,
    universe_fingerprint,
)

DATA = ROOT / "data" / "processed"
FINANCIAL = ROOT / "results" / "real_financial_full"
HISTORICAL = ROOT / "results" / "historical_province"
BACKUP = ROOT / "results" / "entity_key_reconciliation_backup_20260928"


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _backup(paths: list[Path]) -> None:
    BACKUP.mkdir(parents=True, exist_ok=True)
    for path in paths:
        if path.exists():
            destination = BACKUP / path.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                shutil.copy2(path, destination)


def _write_universe_audit(universe: pd.DataFrame) -> None:
    firms = universe.drop_duplicates("firm_key").copy()
    prior_path = DATA / "real_company_universe_audit.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8")) if prior_path.exists() else [{}]
    old = prior[0] if isinstance(prior, list) and prior else {}
    audit = {
        "company_count": int(len(firms)),
        "current_firms": int(firms.profile_status.eq("LISTING_SOURCE_ONLY").sum()),
        "delisted_firms": int(firms.profile_status.eq("DELISTED_PROFILE_UNAVAILABLE").sum()),
        "firm_year_count": int(len(universe)),
        "exchange_distribution": firms.exchange.value_counts().to_dict(),
        "year_distribution": universe.year.value_counts().sort_index().to_dict(),
        "province_coverage": firms.groupby("exchange").province.apply(
            lambda values: int(values.notna().sum())
        ).to_dict(),
        "industry_coverage": firms.groupby("exchange").industry_name.apply(
            lambda values: int(values.notna().sum())
        ).to_dict(),
        "legal_name_coverage": firms.groupby("exchange").company_name_legal.apply(
            lambda values: int(values.notna().sum())
        ).to_dict(),
        "bse_mapping_source": old.get("bse_mapping_source", ""),
        "bse_mapping_rows": int(old.get("bse_mapping_rows", 0)),
        "bse_unmatched": int(firms.bse_mapping_status.eq("unmatched_official_mapping").sum()),
    }
    _write_json(prior_path, [audit])


def _rebuild_financial_statuses(universe: pd.DataFrame) -> dict[str, object]:
    manifest_path = FINANCIAL / "target_manifest.parquet"
    manifest = pd.read_parquet(manifest_path)
    status_path = FINANCIAL / "firm_status.csv"
    statuses = pd.read_csv(status_path, dtype={"firm_key": str})
    target = manifest.loc[manifest.formal_ready].copy()
    keys = set(target.firm_key.astype(str))
    statuses = statuses.loc[statuses.firm_key.astype(str).isin(keys)].copy()
    if set(statuses.firm_key.astype(str)) != keys or statuses.firm_key.duplicated().any():
        raise ValueError("FINANCIAL_STATUS_KEY_SET_MISMATCH")
    chunk_lookup = target.set_index("firm_key").chunk_id
    statuses["chunk_id"] = statuses.firm_key.map(chunk_lookup)
    statuses.to_csv(status_path, index=False)

    state_path = FINANCIAL / "phase_a_run_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update(
        target_firms=int(target.firm_key.nunique()),
        completed_firms=int(statuses.firm_key.nunique()),
        successful_firms=int(statuses.data_status.eq(DATA_COMPLETE).sum()),
        partial_firms=int(statuses.data_status.eq(DATA_PARTIAL).sum()),
        failed_firms=int(statuses.data_status.eq(DATA_FAILED).sum()),
        not_fetched_firms=int(
            (~statuses.data_status.isin([DATA_COMPLETE, DATA_PARTIAL, DATA_FAILED])).sum()
        ),
        completed_chunks=sorted(target.chunk_id.dropna().unique().tolist()),
        universe_fingerprint=universe_fingerprint(universe),
        manifest_fingerprint=manifest_fingerprint(manifest),
        blocked=bool(statuses.retrieval_status.eq("SOURCE_BLOCKED").any()),
    )
    _write_json(state_path, state)
    return finalize()


def _rebuild_historical_panel(universe: pd.DataFrame) -> dict[str, object]:
    target = build_historical_province_target(universe)
    firms = target.sort_values("firm_key").drop_duplicates("firm_key").reset_index(drop=True)
    chunk_map = {
        firm_key: chunk_id
        for chunk_id, firm_keys in assign_historical_province_chunks(
            firms, chunk_size=100
        ).items()
        for firm_key in firm_keys
    }
    panel_path = DATA / "firm_year_historical_province.parquet"
    panel = pd.read_parquet(panel_path)
    panel = exclude_verified_b_share_listing_aliases(panel)
    expected = set(zip(target.firm_key.astype(str), target.year.astype(int)))
    actual = set(zip(panel.firm_key.astype(str), panel.year.astype(int)))
    if actual != expected or panel.duplicated(["firm_key", "year"]).any():
        raise ValueError("HISTORICAL_PROVINCE_KEY_SET_MISMATCH")
    _write_parquet(panel, panel_path)
    _prepare_stata_export(panel).to_stata(
        DATA / "firm_year_historical_province.dta", write_index=False, version=118
    )
    coverage = summarize_historical_province_coverage(panel)
    coverage.to_csv(HISTORICAL / "full_coverage.csv", index=False)
    panel.to_csv(HISTORICAL / "full_panel_audit.csv", index=False, encoding="utf-8-sig")

    status_path = HISTORICAL / "firm_status.csv"
    status = pd.read_csv(status_path, dtype={"firm_key": str})
    status = status.loc[status.firm_key.astype(str).isin(set(firms.firm_key.astype(str)))].copy()
    if set(status.firm_key.astype(str)) != set(firms.firm_key.astype(str)):
        raise ValueError("HISTORICAL_STATUS_KEY_SET_MISMATCH")
    status["chunk_id"] = status.firm_key.map(chunk_map)
    counts = target.groupby("firm_key").size()
    status["firm_years"] = status.firm_key.map(counts)
    status.to_csv(status_path, index=False, encoding="utf-8-sig")

    conflicts_path = HISTORICAL / "conflicts.csv"
    if conflicts_path.exists():
        conflicts = pd.read_csv(conflicts_path, dtype={"firm_key": str})
        conflicts = exclude_verified_b_share_listing_aliases(conflicts)
        conflicts.to_csv(conflicts_path, index=False, encoding="utf-8-sig")
    changes_path = HISTORICAL / "province_changes.csv"
    if changes_path.exists():
        changes = pd.read_csv(changes_path, dtype={"firm_key": str})
        exclude_verified_b_share_listing_aliases(changes).to_csv(
            changes_path, index=False, encoding="utf-8-sig"
        )

    policy_path = DATA / "policy_reports_clean.parquet"
    policy_provinces: set[str] = set()
    if policy_path.exists():
        policy = pd.read_parquet(policy_path)
        years = policy.groupby("province").report_year.agg(set)
        policy_provinces = {
            province for province, observed in years.items()
            if set(range(2019, 2026)).issubset(set(map(int, observed)))
        }
    build_policy_geography_coverage(panel, policy_provinces).to_csv(
        HISTORICAL / "policy_geography_coverage.csv", index=False, encoding="utf-8-sig"
    )
    gate_status, gate = evaluate_historical_province_full_gate(panel, target)
    _write_json(HISTORICAL / "full_gate.json", {"status": gate_status, "gate": gate})
    state_path = HISTORICAL / "full_run_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    target_fingerprint = pd.util.hash_pandas_object(
        target[["firm_key", "year"]], index=False
    ).astype("uint64").to_numpy().tobytes().hex()
    manifest_fingerprint_value = pd.util.hash_pandas_object(
        firms[["firm_key"]], index=False
    ).astype("uint64").to_numpy().tobytes().hex()
    state.update(
        status=gate_status,
        target_firms=int(firms.firm_key.nunique()),
        target_firm_years=len(target),
        total_chunks=int(status.chunk_id.nunique()),
        completed_chunks=sorted(status.chunk_id.dropna().unique().tolist()),
        completed_firms=int(status.firm_key.nunique()),
        final_firms=int(panel.firm_key.nunique()),
        final_firm_years=len(panel),
        duplicate_keys=int(panel.duplicated(["firm_key", "year"]).sum()),
        source_records=len(panel),
        target_fingerprint=target_fingerprint,
        manifest_fingerprint=manifest_fingerprint_value,
        unresolved_conflicts=int(panel.province_conflict.sum()),
    )
    _write_json(state_path, state)
    return {"status": gate_status, **gate}


def reconcile() -> dict[str, object]:
    universe_paths = [
        DATA / "real_company_universe.parquet",
        DATA / "real_company_universe_enriched.parquet",
    ]
    universe_frames = [pd.read_parquet(path) for path in universe_paths]
    for frame in universe_frames:
        present = set(frame.firm_key.astype(str)) & VERIFIED_B_SHARE_LISTING_ALIAS_KEYS
        if present and present != VERIFIED_B_SHARE_LISTING_ALIAS_KEYS:
            raise ValueError(f"PARTIAL_ALIAS_KEY_SET:{sorted(present)}")
    backup_paths = [
        *universe_paths,
        DATA / "real_company_universe.dta",
        DATA / "real_company_universe_enriched.dta",
        DATA / "real_company_universe_audit.json",
        DATA / "real_financials_sse_szse_nonfinancial.parquet",
        DATA / "real_financials_sse_szse_nonfinancial.dta",
        DATA / "firm_year_historical_province.parquet",
        DATA / "firm_year_historical_province.dta",
        FINANCIAL / "target_manifest.parquet",
        FINANCIAL / "target_manifest.csv",
        FINANCIAL / "manifest_summary.json",
        FINANCIAL / "firm_status.csv",
        FINANCIAL / "phase_a_run_state.json",
        FINANCIAL / "final_coverage.csv",
        FINANCIAL / "final_failure_decomposition.csv",
        FINANCIAL / "final_firm_status_summary.csv",
        FINANCIAL / "phase_a_final_summary.json",
        HISTORICAL / "firm_status.csv",
        HISTORICAL / "full_run_state.json",
        HISTORICAL / "full_panel_audit.csv",
        HISTORICAL / "full_coverage.csv",
        HISTORICAL / "conflicts.csv",
        HISTORICAL / "province_changes.csv",
        HISTORICAL / "policy_geography_coverage.csv",
        HISTORICAL / "full_gate.json",
    ]
    _backup(backup_paths)

    corrected = []
    for frame, path in zip(universe_frames, universe_paths):
        output = exclude_verified_b_share_listing_aliases(frame)
        duplicated = (
            output["firm_key"].duplicated().any()
            if "year" not in output
            else output.duplicated(["firm_key", "year"]).any()
        )
        if duplicated:
            raise ValueError(f"DUPLICATE_KEY_AFTER_ALIAS_REMOVAL:{path.name}")
        _write_parquet(output, path)
        corrected.append(output)
    _stata_ready(corrected[0]).to_stata(
        DATA / "real_company_universe.dta", write_index=False, version=118
    )
    _stata_ready(corrected[1]).to_stata(
        DATA / "real_company_universe_enriched.dta", write_index=False, version=118
    )
    _write_universe_audit(corrected[0])
    summary = build_manifest()
    financial_summary = _rebuild_financial_statuses(corrected[1])
    province_summary = _rebuild_historical_panel(corrected[1])
    return {
        "source_universe_firms": int(corrected[0].firm_key.nunique()),
        "source_universe_firm_years": int(len(corrected[0])),
        "phase_a_firms": summary["target_firms"],
        "phase_a_firm_years": summary["target_firm_years"],
        "financial": financial_summary,
        "historical_province": province_summary,
        "backup": str(BACKUP.relative_to(ROOT)),
    }


if __name__ == "__main__":
    print(json.dumps(reconcile(), ensure_ascii=False, indent=2))
