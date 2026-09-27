import subprocess
import sys

import pandas as pd
import pytest

from src.cnipa_entity_names import (
    attach_collision_listing_details,
    audit_name_collisions,
    build_deterministic_pilot_sample,
    build_entity_name_universe,
    build_entity_year_name_coverage,
    build_query_artifacts,
    parse_formername_candidates,
    resolve_listing_collision_types,
    validate_firm_profile_consistency,
    validate_full_target_set,
    validate_query_artifacts,
)


def _firms():
    return pd.DataFrame(
        [
            {
                "firm_key": "SSE:600048:2006-07-31",
                "exchange": "SSE",
                "stock_code_current": "600048",
                "delisting_date": pd.NaT,
                "company_name_legal_profile": "示例甲方股份有限公司",
                "former_names_raw": "示例甲方简称→示例甲方（集团）股份有限公司",
                "source_org_code": "10095671",
                "profile_source_profile": "EastMoney F10 RPT_F10_BASIC_ORGINFO",
                "profile_status_profile": "PASS",
            },
            {
                "firm_key": "SZSE:000001:1991-04-03",
                "exchange": "SZSE",
                "stock_code_current": "000001",
                "delisting_date": pd.NaT,
                "company_name_legal_profile": "示例乙方股份有限公司",
                "former_names_raw": "示例乙方旧称",
                "source_org_code": "10000001",
                "profile_source_profile": "EastMoney F10 RPT_F10_BASIC_ORGINFO",
                "profile_status_profile": "PASS",
            },
            {
                "firm_key": "SSE:600049:2000-01-01",
                "exchange": "SSE",
                "stock_code_current": "600049",
                "delisting_date": pd.Timestamp("2024-01-01"),
                "company_name_legal_profile": "示例乙方股份有限公司",
                "former_names_raw": None,
                "source_org_code": "10000001",
                "profile_source_profile": "EastMoney F10 RPT_F10_BASIC_ORGINFO",
                "profile_status_profile": "PASS",
            },
        ]
    )


def _evidence():
    return pd.DataFrame(
        [
            {
                "firm_key": "SSE:600048:2006-07-31",
                "candidate_name_raw": "示例甲方简称",
                "name_type": "rejected_stock_abbreviation",
                "verification_status": "REJECTED",
                "evidence_tier": "H2",
                "evidence_source": "official issuer disclosure",
                "evidence_url": "https://example.gov/evidence",
                "rejection_reason": "虚构测试材料标为股票简称，非公司法定名称",
                "date_precision": "unknown",
            },
            {
                "firm_key": "SSE:600048:2006-07-31",
                "candidate_name_raw": "示例甲方（集团）股份有限公司",
                "name_type": "historical_legal",
                "verification_status": "VERIFIED",
                "evidence_tier": "H2",
                "evidence_source": "official issuer disclosure",
                "evidence_url": "https://example.gov/evidence",
                "valid_from": "2006",
                "valid_to": "2018",
                "date_precision": "year",
            },
        ]
    )


def test_formername_parser_uses_observed_arrow_delimiter_and_empty_is_valid():
    assert parse_formername_candidates(" 甲 → G甲→*ST甲 ") == ["甲", "G甲", "*ST甲"]
    assert parse_formername_candidates(None) == []
    assert parse_formername_candidates("  ") == []


def test_unresolved_formername_candidate_is_not_query_eligible():
    names = build_entity_name_universe(_firms(), pd.DataFrame())
    aliases = names.loc[names.source_field.eq("FORMERNAME")]
    assert len(aliases) == 3
    assert aliases.name_type.eq("unresolved").all()
    assert aliases.verification_status.eq("UNRESOLVED").all()
    assert aliases.query_eligible.eq(0).all()


def test_frozen_formername_field_semantics_bulk_rejects_all_candidates():
    names = build_entity_name_universe(
        _firms(), pd.DataFrame(), formername_semantics="FORMER_SECURITY_NAME_ONLY"
    )
    aliases = names.loc[names.source_field.eq("FORMERNAME")]
    assert len(aliases) == 3
    assert aliases.name_type.eq("rejected_stock_abbreviation").all()
    assert aliases.verification_status.eq("REJECTED").all()
    assert aliases.query_eligible.eq(0).all()


def test_frozen_formername_semantics_rejects_mixed_legal_evidence_conflict():
    evidence = _evidence().iloc[[1]].copy()
    evidence.loc[:, "candidate_name_raw"] = "示例甲方简称"
    with pytest.raises(ValueError, match="semantics conflict"):
        build_entity_name_universe(
            _firms(), evidence, formername_semantics="FORMER_SECURITY_NAME_ONLY"
        )


def test_entity_year_report_unavailable_does_not_fall_back_to_current_name():
    target = pd.DataFrame({"firm_key": ["f1", "f1"], "year": [2020, 2021]})
    profiles = pd.DataFrame(
        {"firm_key": ["f1"], "company_name_legal_profile": ["当前法人全称"]}
    )
    cache = pd.DataFrame(
        {
            "firm_key": ["f1"],
            "source_report_year": [2020],
            "source_url_or_id": ["https://example.test/report.pdf"],
        }
    )
    result = build_entity_year_name_coverage(target, profiles, cache, years=range(2020, 2022))
    assert len(result) == 2
    assert result.legal_name.eq("").all()
    assert result.coverage_status.eq("REPORT_UNAVAILABLE").all()
    assert result.loc[result.year.eq(2020), "evidence_url"].item().startswith("https://")


def test_collision_resolution_only_accepts_same_entity_distinct_security_codes():
    collisions = pd.DataFrame(
        {
            "collision_type": [
                "same_legal_entity_different_listing_instance",
                "unresolved",
            ],
            "collision_status": ["UNRESOLVED", "UNRESOLVED"],
        }
    )
    result = resolve_listing_collision_types(collisions)
    assert result.collision_status.tolist() == [
        "RESOLVED_SHARED_QUERY_TEMPORAL_ALLOCATION",
        "UNRESOLVED",
    ]


def test_collision_details_include_listing_intervals_without_merging_firms():
    firms = _firms().copy()
    firms["market_listing_date"] = ["2020-01-01", "2010-01-01", "2015-01-01"]
    names = build_entity_name_universe(firms, pd.DataFrame())
    collisions = resolve_listing_collision_types(audit_name_collisions(names))
    details = attach_collision_listing_details(collisions, firms, names)
    assert len(details) == 1
    assert details.iloc[0].listing_intervals_overlap == 1
    assert '"stock_code": "000001"' in details.iloc[0].listing_details_json
    assert len(details.iloc[0].firm_keys.split("|")) == 2


def test_empty_formername_is_a_valid_empty_candidate_set():
    firms = _firms()
    firms.loc[:, "former_names_raw"] = [None, "", pd.NA]
    names = build_entity_name_universe(firms, pd.DataFrame())
    assert names.source_field.eq("ORG_NAME").all()
    assert names.query_eligible.eq(1).all()


def test_current_legal_name_uses_profile_provenance_without_name_rewriting():
    names = build_entity_name_universe(_firms(), pd.DataFrame())
    current = names.loc[names.name_type.eq("current_legal")].iloc[0]
    assert current.candidate_name_normalized == "示例甲方股份有限公司"
    assert current.evidence_tier == "PROFILE_CURRENT"
    assert current.evidence_source.startswith("EastMoney F10")
    assert current.evidence_url.startswith("https://datacenter.eastmoney.com/")


def test_fuzzy_or_unreviewed_alias_cannot_be_inserted_as_history():
    names = build_entity_name_universe(_firms(), pd.DataFrame())
    artifacts = build_query_artifacts(names)
    assert "示例甲方简称" not in set(artifacts.query_names.query_name)
    assert "示例甲方股份有限公司" in set(artifacts.query_names.query_name)


def test_year_precision_requires_year_granular_validity_dates():
    evidence = _evidence().iloc[[1]].copy()
    evidence.loc[:, "valid_from"] = "2006-03-01"
    with pytest.raises(ValueError, match="year date_precision"):
        build_entity_name_universe(_firms(), evidence)


def test_exact_date_precision_without_interval_keeps_temporal_uncertainty():
    evidence = _evidence().iloc[[1]].copy()
    evidence.loc[:, "valid_from"] = ""
    evidence.loc[:, "valid_to"] = ""
    evidence.loc[:, "date_precision"] = "exact_date"
    names = build_entity_name_universe(_firms(), evidence)
    row = names.loc[names.candidate_name_raw.eq("示例甲方（集团）股份有限公司")].iloc[0]
    assert row.query_eligible == 1
    assert row.temporal_match_uncertain == 1


def test_verified_current_and_historical_name_map_has_one_row_per_firm_name():
    names = build_entity_name_universe(_firms(), _evidence())
    artifacts = build_query_artifacts(names, max_names=20, max_chars=1500)
    assert not artifacts.name_firm_map.duplicated(["query_name", "firm_key"]).any()


def test_verified_history_is_eligible_but_stock_abbreviation_is_rejected():
    names = build_entity_name_universe(_firms(), _evidence())
    history = names.loc[names.candidate_name_raw.eq("示例甲方（集团）股份有限公司")].iloc[0]
    abbreviation = names.loc[names.candidate_name_raw.eq("示例甲方简称")].iloc[0]
    assert history.name_type == "historical_legal"
    assert history.verification_status == "VERIFIED"
    assert history.query_eligible == 1
    assert history.date_precision == "year"
    assert history.temporal_match_uncertain == 1
    assert abbreviation.name_type == "rejected_stock_abbreviation"
    assert abbreviation.verification_status == "REJECTED"
    assert abbreviation.query_eligible == 0


def test_unverified_history_cannot_be_enabled_by_evidence_input():
    evidence = _evidence().iloc[[1]].copy()
    evidence.loc[:, "verification_status"] = "UNRESOLVED"
    names = build_entity_name_universe(_firms(), evidence)
    row = names.loc[names.candidate_name_raw.eq("示例甲方（集团）股份有限公司")].iloc[0]
    assert row.name_type == "historical_legal"
    assert row.verification_status == "UNRESOLVED"
    assert row.query_eligible == 0


def test_evidence_without_source_is_rejected():
    evidence = _evidence().iloc[[1]].copy()
    evidence.loc[:, "evidence_url"] = ""
    with pytest.raises(ValueError, match="evidence_url"):
        build_entity_name_universe(_firms(), evidence)


def test_same_normalized_name_across_firms_is_audited_not_merged():
    names = build_entity_name_universe(_firms(), pd.DataFrame())
    collisions = audit_name_collisions(names)
    assert len(collisions) == 1
    assert collisions.iloc[0].firm_count == 2
    assert collisions.iloc[0].collision_status == "UNRESOLVED"
    assert set(collisions.iloc[0].firm_keys.split("|")) == {
        "SSE:600049:2000-01-01",
        "SZSE:000001:1991-04-03",
    }
    assert collisions.iloc[0].collision_type == "same_legal_entity_different_listing_instance"


def test_same_security_code_with_multiple_firm_keys_is_not_assumed_valid_listing_instances():
    firms = _firms()
    firms.loc[2, "exchange"] = "SZSE"
    firms.loc[2, "stock_code_current"] = "000001"
    firms.loc[2, "source_org_code"] = "10000001"
    names = build_entity_name_universe(firms, pd.DataFrame())
    collision = audit_name_collisions(names).iloc[0]
    assert collision.collision_type == "unresolved"


def test_pilot_sample_is_deterministic_and_covers_required_strata():
    firms = _firms().copy()
    extra = pd.concat([firms] * 3, ignore_index=True)
    extra["firm_key"] = [
        f"{x.exchange}:{i:06d}:2000-01-01" for i, x in enumerate(extra.itertuples())
    ]
    extra.loc[extra.index[::2], "exchange"] = "SZSE"
    extra.loc[extra.index[1::3], "delisting_date"] = pd.Timestamp("2024-01-01")
    a = build_deterministic_pilot_sample(extra, seed="20260927", forced_firm_keys=[])
    shuffled = extra.sample(frac=1, random_state=8)
    b = build_deterministic_pilot_sample(
        shuffled, seed="20260927", forced_firm_keys=[]
    )
    assert a.firm_key.tolist() == b.firm_key.tolist()
    strata = "|".join(a.pilot_strata)
    for required in ("SSE_current", "SZSE_current", "SSE_delisted", "SZSE_delisted"):
        assert required in strata
    assert "former_nonempty" in strata
    assert "former_multiple" in strata


def test_full_target_key_set_requires_exact_equality():
    validate_full_target_set({"a", "b"}, {"a", "b"})
    with pytest.raises(ValueError, match="target firm_key set mismatch"):
        validate_full_target_set({"a", "b"}, {"a", "c"})


def test_query_validator_rejects_nonlegal_name_even_if_flagged_eligible():
    names = build_entity_name_universe(_firms(), pd.DataFrame())
    artifacts = build_query_artifacts(names)
    idx = names.index[names.source_field.eq("FORMERNAME")][0]
    names.loc[idx, "query_eligible"] = 1
    with pytest.raises(ValueError, match="verified legal names"):
        validate_query_artifacts(names, artifacts)


def test_profile_history_must_be_consistent_before_firm_deduplication():
    firms = _firms()
    duplicated = pd.concat([firms.iloc[[0]], firms.iloc[[0]]], ignore_index=True)
    assert len(validate_firm_profile_consistency(duplicated)) == 1
    duplicated.loc[1, "former_names_raw"] = "different former alias"
    with pytest.raises(ValueError, match="profile values vary within firm_key"):
        validate_firm_profile_consistency(duplicated)


def test_query_names_and_batches_are_deterministic_and_exactly_once():
    names = build_entity_name_universe(_firms(), _evidence())
    expected = set(names.loc[names.query_eligible.eq(1), "candidate_name_normalized"])
    first = build_query_artifacts(names, max_names=2, max_chars=50)
    second = build_query_artifacts(names.sample(frac=1, random_state=4), max_names=2, max_chars=50)
    validate_query_artifacts(names, first, max_names=2, max_chars=50)
    assert first.query_names.equals(second.query_names)
    assert first.query_batches.equals(second.query_batches)
    assert set(first.query_names.query_name) == expected
    assert first.name_firm_map.groupby("query_name").query_batch_id.nunique().max() == 1


def test_collision_names_map_to_every_firm_and_batches_enforce_character_limit():
    names = build_entity_name_universe(_firms(), _evidence())
    result = build_query_artifacts(names, max_names=2, max_chars=50)
    assert set(result.name_firm_map.loc[
        result.name_firm_map.query_name.eq("示例乙方股份有限公司"), "firm_key"
    ]) == {"SZSE:000001:1991-04-03", "SSE:600049:2000-01-01"}
    assert result.name_firm_map.loc[
        result.name_firm_map.query_name.eq("示例乙方股份有限公司"), "collision"
    ].all()
    assert result.query_batches.query_string.map(len).le(50).all()
    assert result.query_batches.query_name_count.le(2).all()
    assert not result.query_batches.query_string.str.contains(r"[*?]", regex=True).any()


def test_entity_name_builder_script_starts_from_repository_root():
    result = subprocess.run(
        [sys.executable, "scripts/build_cnipa_entity_name_universe.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Build local CNIPA entity-name preflight artifacts" in result.stdout
