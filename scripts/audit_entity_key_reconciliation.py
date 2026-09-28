from __future__ import annotations

import json
from collections.abc import Hashable, Iterable
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ALIASES = {
    "SSE:600555:1999-01-18": "SSE:600555:2001-03-28",
    "SSE:600190:1998-05-19": "SSE:600190:1999-06-09",
    "SSE:600614:1992-07-28": "SSE:600614:1992-08-28",
}
EXPECTED_ALIAS_FIRM_YEARS = {
    ("SSE:600190:1998-05-19", year) for year in range(2020, 2026)
} | {
    ("SSE:600555:1999-01-18", year) for year in range(2020, 2023)
} | {("SSE:600614:1992-07-28", year) for year in range(2020, 2022)}
BACKUP = ROOT / "results/entity_key_reconciliation_backup_20260928"
OUTPUT = ROOT / "results/entity_key_reconciliation"


def compare_key_sets(
    old_keys: Iterable[Hashable],
    new_keys: Iterable[Hashable],
    verified_removals: Iterable[Hashable],
) -> dict[str, Any]:
    """Compare target key sets and reject any unverified addition or removal."""
    old = set(old_keys)
    new = set(new_keys)
    verified = set(verified_removals)
    removed = sorted(old - new)
    added = sorted(new - old)
    if set(removed) != verified or added:
        raise ValueError(
            "UNVERIFIED_KEY_DIFFERENCE:"
            f"removed={removed!r}; added={added!r}; verified={sorted(verified)!r}"
        )
    return {
        "removed": removed,
        "added": added,
        "exact_verified_removal": True,
    }


def _pairs(frame: pd.DataFrame) -> set[tuple[str, int]]:
    return set(zip(frame.firm_key.astype(str), pd.to_numeric(frame.year).astype(int)))


def _read(relative: str, *, backup: bool = False) -> pd.DataFrame:
    root = BACKUP if backup else ROOT
    return pd.read_parquet(root / relative)


def _assert_only_alias_rows(old: pd.DataFrame, new: pd.DataFrame, name: str) -> dict[str, Any]:
    old_firms = set(old.firm_key.astype(str))
    new_firms = set(new.firm_key.astype(str))
    firm_diff = compare_key_sets(old_firms, new_firms, ALIASES)
    old_pairs = _pairs(old)
    new_pairs = _pairs(new)
    removed_pairs = sorted(old_pairs - new_pairs)
    added_pairs = sorted(new_pairs - old_pairs)
    pair_diff = compare_key_sets(old_pairs, new_pairs, EXPECTED_ALIAS_FIRM_YEARS)
    if len(removed_pairs) != 11 or added_pairs:
        raise ValueError(f"{name}_FIRM_YEAR_DIFF_INVALID:{len(removed_pairs)}:{added_pairs}")
    if {key for key, _ in removed_pairs} != set(ALIASES):
        raise ValueError(f"{name}_FIRM_YEAR_ALIAS_SCOPE_INVALID")
    return {
        "dataset": name,
        "old_firms": len(old_firms),
        "new_firms": len(new_firms),
        "firm_keys_removed": firm_diff["removed"],
        "firm_keys_added": firm_diff["added"],
        "old_firm_years": len(old_pairs),
        "new_firm_years": len(new_pairs),
        "firm_years_removed": len(removed_pairs),
        "firm_years_added": len(added_pairs),
        "firm_year_diff": pair_diff,
    }


def _rows_for_diff(dataset: str, old: pd.DataFrame, new: pd.DataFrame) -> list[dict[str, Any]]:
    old_firms = set(old.firm_key.astype(str))
    new_firms = set(new.firm_key.astype(str))
    old_pairs = _pairs(old)
    new_pairs = _pairs(new)
    rows: list[dict[str, Any]] = []
    rows.extend(
        {"dataset": dataset, "change_type": "firm_key_removed", "firm_key": key, "year": ""}
        for key in sorted(old_firms - new_firms)
    )
    rows.extend(
        {"dataset": dataset, "change_type": "firm_year_removed", "firm_key": key, "year": year}
        for key, year in sorted(old_pairs - new_pairs)
    )
    rows.extend(
        {"dataset": dataset, "change_type": "firm_key_added", "firm_key": key, "year": ""}
        for key in sorted(new_firms - old_firms)
    )
    rows.extend(
        {"dataset": dataset, "change_type": "firm_year_added", "firm_key": key, "year": year}
        for key, year in sorted(new_pairs - old_pairs)
    )
    return rows


def _alias_evidence(profiles: pd.DataFrame) -> pd.DataFrame:
    source_rows = profiles.loc[profiles.firm_key.astype(str).isin(ALIASES)].copy()
    if source_rows.firm_key.nunique() != 3 or source_rows.firm_key.duplicated().any():
        raise ValueError("PROFILE_ALIAS_EVIDENCE_INCOMPLETE")
    canonical_rows = profiles.loc[profiles.firm_key.astype(str).isin(ALIASES.values())].copy()
    if canonical_rows.firm_key.nunique() != 3 or canonical_rows.firm_key.duplicated().any():
        raise ValueError("PROFILE_CANONICAL_EVIDENCE_INCOMPLETE")
    aliases = source_rows.set_index("firm_key")
    canonicals = canonical_rows.set_index("firm_key")
    rows = [
        {
            "excluded_alias_key": alias,
            "canonical_a_key": canonical,
            "a_share_code": alias.split(":")[1],
            "b_share_code": {"600555": "900955", "600190": "900952", "600614": "900907"}[
                alias.split(":")[1]
            ],
            "a_share_listing_date": canonical.rsplit(":", 1)[1],
            "b_share_listing_date": alias.rsplit(":", 1)[1],
            "a_exchange": "SSE",
            "b_exchange": "SSE",
            "a_org_code": str(canonicals.loc[canonical, "source_org_code"]),
            "alias_org_code": str(aliases.loc[alias, "source_org_code"]),
            "org_code_equal": bool(
                aliases.loc[alias, "source_org_code"]
                == canonicals.loc[canonical, "source_org_code"]
            ),
            "legal_name_alias_profile": aliases.loc[alias, "company_name_legal"],
            "legal_name_canonical_profile": canonicals.loc[canonical, "company_name_legal"],
            "profile_status_alias": aliases.loc[alias, "profile_status"],
            "profile_status_canonical": canonicals.loc[canonical, "profile_status"],
            "annual_report_announcement_id": {
                "600555": "59259669",
                "600190": "1209857269",
                "600614": "1200813795",
            }[alias.split(":")[1]],
            "annual_report_title": {
                "600555": "上海九龙山股份有限公司2010年年度报告",
                "600190": "锦州港股份有限公司2020年年度报告",
                "600614": "上海鼎立科技发展（集团）股份有限公司2014年年度报告",
            }[alias.split(":")[1]],
            "annual_report_security_information": {
                "600555": (
                    "A股600555/B股900955，同一发行人；另有官方披露明确"
                    "B股1999-01-18、A股2001-03-28"
                ),
                "600190": (
                    "A股600190/B股900952，锦州港股份有限公司；官方披露分别于"
                    "1999-06-09和1998-05-19在上交所挂牌"
                ),
                "600614": (
                    "A股600614/B股900907，同一上市公司；官方年报列代码，"
                    "官方重组文件明确B股1992-07-28、A股1992-08-28"
                ),
            }[alias.split(":")[1]],
            "exchange_and_interval_evidence": {
                "600555": "SSE; B 1999-01-18 to A 2001-03-28",
                "600190": "SSE; B 1998-05-19 to A 1999-06-09",
                "600614": "SSE; B 1992-07-28 to A 1992-08-28",
            }[alias.split(":")[1]],
            "official_cninfo_evidence_urls": {
                "600555": "https://static.cninfo.com.cn/finalpage/2009-09-05/56893958.PDF; https://static.cninfo.com.cn/finalpage/2011-04-13/59259669.PDF",
                "600190": "https://static.cninfo.com.cn/finalpage/2012-04-06/60788268.PDF; https://static.cninfo.com.cn/finalpage/2021-04-29/1209857269.PDF",
                "600614": (
                    "https://static.cninfo.com.cn/finalpage/2015-04-11/1200813795.PDF; "
                    "https://static.cninfo.com.cn/finalpage/2014-04-12/63828007.PDF; "
                    "https://static.cninfo.com.cn/finalpage/2015-06-03/1201095930.PDF"
                ),
            }[alias.split(":")[1]],
            "same_legal_entity_supported": bool(
                aliases.loc[alias, "source_org_code"]
                == canonicals.loc[canonical, "source_org_code"]
                and aliases.loc[alias, "company_name_legal"]
                == canonicals.loc[canonical, "company_name_legal"]
            ),
            "correction_scope": (
                "仅排除经官方披露确认的A股代码+B股挂牌日别名；"
                "未按名称或ORG_CODE全局去重"
            ),
        }
        for alias, canonical in ALIASES.items()
    ]
    result = pd.DataFrame(rows)
    if not result.org_code_equal.all() or not result.same_legal_entity_supported.all():
        raise ValueError("OFFICIAL_ALIAS_IDENTITY_EVIDENCE_MISMATCH")
    return result


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def build_audit() -> dict[str, Any]:
    universe_old = _read("data/processed/real_company_universe.parquet", backup=True)
    universe_new = _read("data/processed/real_company_universe.parquet")
    enriched_old = _read("data/processed/real_company_universe_enriched.parquet", backup=True)
    enriched_new = _read("data/processed/real_company_universe_enriched.parquet")
    financial_old = _read(
        "data/processed/real_financials_sse_szse_nonfinancial.parquet", backup=True
    )
    financial_new = _read("data/processed/real_financials_sse_szse_nonfinancial.parquet")
    province_old = _read("data/processed/firm_year_historical_province.parquet", backup=True)
    province_new = _read("data/processed/firm_year_historical_province.parquet")

    universe_audit = _assert_only_alias_rows(universe_old, universe_new, "universe")
    enriched_audit = _assert_only_alias_rows(enriched_old, enriched_new, "enriched_universe")
    financial_audit = _assert_only_alias_rows(financial_old, financial_new, "phase_a_financial")
    province_audit = _assert_only_alias_rows(province_old, province_new, "historical_province")

    aliases = set(ALIASES)
    canonical_keys = set(ALIASES.values())
    profiles_old = pd.read_parquet(
        ROOT / "results/real_profile_fetch/eastmoney_profile_all.parquet"
    )
    active_profiles = enriched_new.drop_duplicates("firm_key").copy()
    active_keys = set(active_profiles.firm_key.astype(str))
    if active_keys != set(universe_new.firm_key.astype(str)):
        raise ValueError("ACTIVE_PROFILE_TARGET_KEY_MISMATCH")
    required_profile_fields = {
        "company_name_legal_profile": "company_name_legal_profile",
        "province": "province_profile",
        "INDUSTRYCSRC1": "industry_csrc",
        "ORG_CODE": "source_org_code",
        "profile_status": "profile_status_profile",
    }
    profile_missing = {
        label: int(active_profiles[column].isna().sum())
        for label, column in required_profile_fields.items()
    }
    if any(profile_missing.values()):
        raise ValueError(f"ACTIVE_PROFILE_REQUIRED_FIELDS_MISSING:{profile_missing}")

    phase_manifest = pd.read_parquet(ROOT / "results/real_financial_full/target_manifest.parquet")
    phase_a_firms = set(
        phase_manifest.loc[
            phase_manifest.fetch_phase.eq("sse_szse_nonfinancial")
            & phase_manifest.formal_ready.fillna(False).astype(bool),
            "firm_key",
        ].astype(str)
    )
    financial_firms = set(financial_new.firm_key.astype(str))
    if phase_a_firms != financial_firms or len(phase_a_firms) != 5269:
        raise ValueError("FINANCIAL_STATUS_TARGET_KEY_MISMATCH")
    if set(financial_new.firm_key.astype(str)) & aliases:
        raise ValueError("ALIAS_IN_FINANCIAL_PANEL")
    if set(financial_new.exchange.astype(str)) - {"SSE", "SZSE"}:
        raise ValueError("ILLEGAL_EXCHANGE_IN_FINANCIAL_PANEL")
    if financial_new.duplicated(["firm_key", "year"]).any():
        raise ValueError("DUPLICATE_FINANCIAL_FIRM_YEAR")

    status = pd.read_csv(
        ROOT / "results/real_financial_full/firm_status.csv", dtype={"firm_key": str}
    )
    status_counts = status.data_status.value_counts().to_dict()
    expected_status = {"COMPLETE": 5008, "PARTIAL": 4, "QUERY_FAILED": 257}
    if status_counts != expected_status or len(status) != 5269:
        raise ValueError(f"FINANCIAL_STATUS_COUNTS_MISMATCH:{status_counts}")

    current = financial_new.loc[financial_new.delisting_date.isna()].copy()
    core_fields = [
        "total_assets",
        "total_liabilities",
        "cash",
        "revenue",
        "net_profit",
        "employees",
    ]
    current["core_complete"] = current[core_fields].notna().all(axis=1)
    financial_coverage = current.groupby("exchange").core_complete.mean().to_dict()
    rd_coverage = (
        current.groupby("exchange").rd_expense.apply(lambda values: values.notna().mean()).to_dict()
    )

    province_counts = province_new.province_status.value_counts().to_dict()
    if len(province_new) != 28537 or sum(province_counts.values()) != 28537:
        raise ValueError("HISTORICAL_PROVINCE_TARGET_MISMATCH")
    if _pairs(financial_new) != _pairs(province_new):
        raise ValueError("FINANCIAL_HISTORICAL_KEY_MISMATCH")
    if province_new.duplicated(["firm_key", "year"]).any():
        raise ValueError("DUPLICATE_HISTORICAL_PROVINCE_KEY")
    policy_geo = pd.read_csv(ROOT / "results/historical_province/policy_geography_coverage.csv")
    policy_counts = (
        policy_geo.groupby("existing_policy_corpus_available").firm_years.sum().to_dict()
    )
    hk_firm_years = int(
        policy_geo.loc[policy_geo.province.eq("香港特别行政区"), "firm_years"].sum()
    )
    mainland_missing = len(province_new) - int(policy_counts.get(True, 0)) - hk_firm_years
    if policy_counts != {False: 11, True: 26388} or (mainland_missing, hk_firm_years) != (2138, 11):
        raise ValueError(f"POLICY_GEOGRAPHY_COUNTS_MISMATCH:{policy_counts}")

    cnipa_primary = pd.read_csv(
        ROOT / "results/cnipa_legal_name_recovery/full_status.csv", dtype={"firm_key": str}
    )
    cnipa_2025 = pd.read_csv(
        ROOT / "results/cnipa_legal_name_recovery/audit-2025_status.csv", dtype={"firm_key": str}
    )
    cnipa_coverage = pd.read_csv(
        ROOT / "results/cnipa_preflight/entity_year_name_coverage.csv",
        dtype={"firm_key": str},
    )
    primary_coverage = cnipa_coverage.loc[cnipa_coverage.year.between(2020, 2024)]
    audit_2025_coverage = cnipa_coverage.loc[cnipa_coverage.year.eq(2025)]
    primary_coverage_counts = primary_coverage.coverage_status.value_counts().to_dict()
    audit_2025_coverage_counts = audit_2025_coverage.coverage_status.value_counts().to_dict()
    if len(primary_coverage) != 23448 or len(audit_2025_coverage) != 5089:
        raise ValueError("CNIPA_EXISTING_COVERAGE_TARGET_COUNT_MISMATCH")
    cnipa_checks: dict[str, Any] = {}
    for label, frame, years in (
        ("primary_2020_2024", cnipa_primary, set(range(2020, 2025))),
        ("audit_2025", cnipa_2025, {2025}),
    ):
        period_target = financial_new.loc[financial_new.year.isin(years)]
        if _pairs(frame) != _pairs(period_target) or len(frame) != len(period_target):
            raise ValueError(f"CNIPA_{label.upper()}_TARGET_MISMATCH")
        if frame.duplicated(["firm_key", "year"]).any():
            raise ValueError(f"CNIPA_{label.upper()}_DUPLICATE_KEY")
        if (
            cnipa_coverage.loc[cnipa_coverage.year.isin(years)]
            .duplicated(["firm_key", "year"])
            .any()
        ):
            raise ValueError(f"CNIPA_{label.upper()}_COVERAGE_DUPLICATE_KEY")
        cnipa_checks[label] = {"firm_years": len(frame), "exact_target_key_match": True}

    profiles_all_keys = set(profiles_old.firm_key.astype(str))
    if active_keys - profiles_all_keys:
        raise ValueError("ACTIVE_FIRM_MISSING_PROFILE_CACHE")
    evidence = _alias_evidence(profiles_old)
    diff_rows = (
        _rows_for_diff("real_universe", universe_old, universe_new)
        + _rows_for_diff("enriched_universe", enriched_old, enriched_new)
        + _rows_for_diff("phase_a_financial", financial_old, financial_new)
        + _rows_for_diff("historical_province", province_old, province_new)
    )

    summary = {
        "identity_audit_status": "PASS",
        "alias_count": 3,
        "alias_keys_removed": sorted(aliases),
        "canonical_a_share_keys_retained": sorted(canonical_keys),
        "same_legal_entity_and_official_evidence": True,
        "global_deduplication_by_name_or_org_code": False,
        "real_universe": universe_audit,
        "enriched_universe": enriched_audit,
        "phase_a_financial": financial_audit,
        "historical_province": province_audit,
        "historical_profile_cache": {"firms": len(profiles_all_keys), "retained": True},
        "active_profile": {
            "firms": len(active_keys),
            "exact_universe_key_match": True,
            "required_field_missing_counts": profile_missing,
        },
        "phase_a_target": {"firms": len(phase_a_firms), "firm_years": len(financial_new)},
        "financial_status_counts": status_counts,
        "current_core_completeness": financial_coverage,
        "current_rd_coverage": rd_coverage,
        "historical_province_status_counts": province_counts,
        "policy_geography_firm_years": {
            "mainland_matched": int(policy_counts[True]),
            "mainland_missing": mainland_missing,
            "hong_kong_out_of_scope": hk_firm_years,
        },
        "cnipa_existing_evidence_only": cnipa_checks,
        "cnipa_pilot_gate": {
            "reported_status": False,
            "tracked_audit_basis": (
                "5个更名案例中各项准确率3/5；Full缓存不得作为严格Pilot Gate通过证明"
            ),
            "local_summary_conflict": (
                "ignored pilot_summary.json currently reports 6 cases and 1.0 accuracy; "
                "original Gate artifact left untouched and conflict is not treated as PASS"
            ),
        },
        "full_evidence_cache_status": "FULL_EVIDENCE_CACHE_PRE_GATE",
        "cnipa_entity_name_scope_status": "CNIPA_ENTITY_NAME_NEEDS_FIX",
        "cnipa_primary_firm_years": len(cnipa_primary),
        "cnipa_2025_firm_years": len(cnipa_2025),
        "cnipa_primary_coverage_status_counts": primary_coverage_counts,
        "cnipa_2025_coverage_status_counts": audit_2025_coverage_counts,
        "zero_semantics": "pending",
        "missing_semantics": "pending",
        "new_cnipa_patent_access": False,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    _write_csv(evidence, OUTPUT / "verified_alias_audit.csv")
    _write_csv(pd.DataFrame(diff_rows), OUTPUT / "old_new_target_diff.csv")
    (OUTPUT / "reconciliation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


if __name__ == "__main__":
    print(json.dumps(build_audit(), ensure_ascii=False, indent=2))
