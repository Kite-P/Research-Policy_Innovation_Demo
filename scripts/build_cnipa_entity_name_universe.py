from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.cnipa_entity_names import (  # noqa: E402
    audit_name_collisions,
    build_deterministic_pilot_sample,
    build_entity_name_universe,
    build_query_artifacts,
    parse_formername_candidates,
    validate_firm_profile_consistency,
    validate_full_target_set,
    validate_query_artifacts,
)
from src.real_financial_full import PHASE_A  # noqa: E402

DEFAULT_TARGET = Path("data/processed/real_financials_sse_szse_nonfinancial.parquet")
DEFAULT_PROFILES = Path("data/processed/real_company_universe_enriched.parquet")
DEFAULT_MANIFEST = Path("results/real_financial_full/target_manifest.parquet")
DEFAULT_EVIDENCE = Path("data/external/cnipa_historical_name_evidence.csv")
DEFAULT_OUTPUT = Path("results/cnipa_preflight")
DEFAULT_PARQUET = Path("data/processed/cnipa_entity_name_universe.parquet")


def _read_evidence(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def build_preflight(
    target_path: Path = DEFAULT_TARGET,
    profiles_path: Path = DEFAULT_PROFILES,
    manifest_path: Path = DEFAULT_MANIFEST,
    evidence_path: Path = DEFAULT_EVIDENCE,
    output_dir: Path = DEFAULT_OUTPUT,
    parquet_path: Path = DEFAULT_PARQUET,
    seed: str = "20260927",
    max_names: int = 20,
    max_chars: int = 1500,
) -> dict[str, Any]:
    target_panel = pd.read_parquet(target_path)
    profiles_all = pd.read_parquet(profiles_path)
    manifest = pd.read_parquet(manifest_path)
    if not {"firm_key", "year", "exchange", "is_financial_industry"}.issubset(
        target_panel.columns
    ):
        raise ValueError("Phase A financial panel lacks required target scope fields")
    if target_panel.duplicated(["firm_key", "year"]).any():
        raise ValueError("Phase A financial target contains duplicate firm-year keys")
    years = set(pd.to_numeric(target_panel.year, errors="raise").astype(int))
    if not years or min(years) < 2020 or max(years) > 2025:
        raise ValueError("Phase A target year range must be within 2020-2025")
    if not target_panel.exchange.isin({"SSE", "SZSE"}).all():
        raise ValueError("Phase A target unexpectedly includes an exchange outside SSE/SZSE")
    if target_panel.is_financial_industry.fillna(True).astype(bool).any():
        raise ValueError("Phase A target unexpectedly includes financial-industry firms")

    if not {"firm_key", "fetch_phase", "formal_ready"}.issubset(manifest.columns):
        raise ValueError("Phase A manifest lacks required scope fields")
    phase_a = manifest.loc[
        manifest.fetch_phase.eq(PHASE_A) & manifest.formal_ready.fillna(False).astype(bool)
    ]
    if phase_a.firm_key.duplicated().any():
        raise ValueError("Phase A manifest contains duplicate firm_key records")
    expected_firms = set(phase_a.firm_key.astype(str))
    validate_full_target_set(expected_firms, set(target_panel.firm_key.astype(str)))
    target_firm_years = len(target_panel)
    profiles = validate_firm_profile_consistency(profiles_all)
    profiles["firm_key"] = profiles.firm_key.astype(str)
    selected_profiles = profiles.loc[profiles.firm_key.isin(expected_firms)].copy()
    validate_full_target_set(expected_firms, set(selected_profiles.firm_key))
    evidence = _read_evidence(evidence_path)
    names = build_entity_name_universe(selected_profiles, evidence)
    current_profile_keys = set(
        names.loc[names.name_type.eq("current_legal"), "firm_key"]
    )
    validate_full_target_set(expected_firms, current_profile_keys)

    output_dir.mkdir(parents=True, exist_ok=True)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    names.to_parquet(parquet_path, index=False)
    names.to_csv(output_dir / "entity_name_audit.csv", index=False, encoding="utf-8-sig")

    evidence_history_keys = set(
        evidence.loc[
            evidence.get("name_type", pd.Series(dtype=str)).eq("historical_legal")
            & evidence.get("verification_status", pd.Series(dtype=str)).eq("VERIFIED"),
            "firm_key",
        ].astype(str)
    ) if not evidence.empty else set()
    pilot = build_deterministic_pilot_sample(
        selected_profiles,
        seed=seed,
        n_per_stratum=10,
        forced_firm_keys=evidence_history_keys,
    )
    pilot.to_csv(output_dir / "pilot_sample.csv", index=False, encoding="utf-8-sig")
    pilot_keys = set(pilot.firm_key.astype(str))
    pilot_candidates = names.loc[names.firm_key.astype(str).isin(pilot_keys)].copy()
    pilot_candidates.to_csv(
        output_dir / "pilot_candidate_name_audit.csv", index=False, encoding="utf-8-sig"
    )

    collisions = audit_name_collisions(names)
    collisions.to_csv(
        output_dir / "name_collision_audit.csv", index=False, encoding="utf-8-sig"
    )
    query_artifacts = build_query_artifacts(names, max_names=max_names, max_chars=max_chars)
    query_gate = validate_query_artifacts(
        names, query_artifacts, max_names=max_names, max_chars=max_chars
    )
    query_artifacts.query_names.to_csv(
        output_dir / "cnipa_query_names.csv", index=False, encoding="utf-8-sig"
    )
    query_artifacts.query_batches.to_csv(
        output_dir / "cnipa_query_batches.csv", index=False, encoding="utf-8-sig"
    )
    query_artifacts.name_firm_map.to_csv(
        output_dir / "cnipa_query_name_firm_map.csv", index=False, encoding="utf-8-sig"
    )

    former_nonempty = selected_profiles.former_names_raw.map(
        lambda value: bool(parse_formername_candidates(value))
    )
    former_rows = names.loc[names.source_field.eq("FORMERNAME")]
    current = names.loc[names.name_type.eq("current_legal")]
    verified_history = names.loc[
        names.name_type.eq("historical_legal") & names.verification_status.eq("VERIFIED")
    ]
    unresolved_candidates = names.loc[
        names.source_field.eq("FORMERNAME")
        & names.verification_status.eq("UNRESOLVED")
    ]
    rejected_stock = names.loc[names.name_type.eq("rejected_stock_abbreviation")]
    current_coverage = int(
        current.loc[current.verification_status.eq("VERIFIED"), "firm_key"].nunique()
    )
    unresolved_collisions = int(collisions.collision_status.eq("UNRESOLVED").sum())
    status = (
        "CNIPA_ENTITY_NAME_UNIVERSE_READY"
        if current_coverage == len(expected_firms)
        and unresolved_candidates.empty
        and unresolved_collisions == 0
        else "CNIPA_ENTITY_NAME_NEEDS_FIX"
    )
    stratum_counts: dict[str, int] = {}
    for strata in pilot.pilot_strata:
        for stratum in str(strata).split("|"):
            if stratum:
                stratum_counts[stratum] = stratum_counts.get(stratum, 0) + 1

    summary = {
        "status": status,
        "seed": seed,
        "target_firms": len(expected_firms),
        "target_firm_years": target_firm_years,
        "target_firm_key_set_exact": True,
        "target_manifest_phase": PHASE_A,
        "current_legal_name_coverage_firms": current_coverage,
        "current_legal_name_coverage_rate": current_coverage / len(expected_firms),
        "former_names_raw_nonempty_firms": int(
            selected_profiles.loc[former_nonempty, "firm_key"].nunique()
        ),
        "formername_candidate_rows": len(former_rows),
        "formername_unique_firms_with_candidate": int(former_rows.firm_key.nunique()),
        "historical_legal_names_verified": int(
            verified_history.candidate_name_normalized.nunique()
        ),
        "firms_with_verified_historical_legal_name": int(verified_history.firm_key.nunique()),
        "rejected_stock_abbreviations": int(rejected_stock.candidate_name_normalized.nunique()),
        "unresolved_historical_name_candidates": int(
            unresolved_candidates[["firm_key", "candidate_name_normalized"]]
            .drop_duplicates()
            .shape[0]
        ),
        "normalized_name_collision_groups": len(collisions),
        "unresolved_collision_groups": unresolved_collisions,
        "query_limits": {"max_names": max_names, "max_chars": max_chars},
        "query_limit_status": "CNIPA_QUERY_LIMIT_UNCONFIRMED",
        "query_gate": query_gate,
        "query_names_exact_once": True,
        "pilot_firms": len(pilot),
        "pilot_strata_firm_counts": stratum_counts,
        "pilot_formername_classification_counts": pilot_candidates.loc[
            pilot_candidates.source_field.eq("FORMERNAME"), "name_type"
        ].value_counts().to_dict(),
        "zero_semantics": "pending",
        "missing_semantics": "pending",
        "cnipa_login_performed": False,
        "cnipa_patent_download_performed": False,
        "regression_or_final_panel_performed": False,
        "bse_processed": False,
    }
    (output_dir / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build local CNIPA entity-name preflight artifacts"
    )
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--parquet", type=Path, default=DEFAULT_PARQUET)
    parser.add_argument("--seed", default="20260927")
    parser.add_argument("--max-names", type=int, default=20)
    parser.add_argument("--max-chars", type=int, default=1500)
    args = parser.parse_args()
    build_preflight(
        target_path=args.target,
        profiles_path=args.profiles,
        manifest_path=args.manifest,
        evidence_path=args.evidence,
        output_dir=args.output,
        parquet_path=args.parquet,
        seed=args.seed,
        max_names=args.max_names,
        max_chars=args.max_chars,
    )


if __name__ == "__main__":
    main()
