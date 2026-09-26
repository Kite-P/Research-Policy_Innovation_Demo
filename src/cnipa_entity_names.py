from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import pandas as pd

from .cnipa_company_names import normalize_company_name, normalize_company_names
from .cnipa_patent_queries import build_applicant_query, split_company_queries

NAME_TYPES = {
    "current_legal",
    "historical_legal",
    "rejected_stock_abbreviation",
    "rejected_nonlegal_name",
    "unresolved",
}
VERIFICATION_STATUSES = {"VERIFIED", "REJECTED", "UNRESOLVED"}
DATE_PRECISIONS = {"unknown", "year", "exact_date"}
HISTORICAL_TIERS = {"H1", "H2", "H3"}
REQUIRED_PROFILE_COLUMNS = {
    "firm_key",
    "exchange",
    "stock_code_current",
    "company_name_legal_profile",
    "former_names_raw",
    "source_org_code",
    "profile_source_profile",
    "profile_status_profile",
}
OUTPUT_COLUMNS = [
    "firm_key",
    "exchange",
    "stock_code_current",
    "current_legal_name",
    "candidate_name_raw",
    "candidate_name_normalized",
    "name_type",
    "valid_from",
    "valid_to",
    "date_precision",
    "evidence_tier",
    "evidence_source",
    "evidence_url",
    "verification_status",
    "query_eligible",
    "temporal_match_uncertain",
    "rejection_reason",
    "source_field",
    "source_org_code",
]


def _text(value: Any, default: str = "") -> str:
    if value is None or pd.isna(value):
        return default
    return str(value)


@dataclass(frozen=True)
class QueryArtifacts:
    query_names: pd.DataFrame
    query_batches: pd.DataFrame
    name_firm_map: pd.DataFrame


def parse_formername_candidates(value: Any) -> list[str]:
    """Split the observed EastMoney arrow-delimited former security-name field."""
    if value is None or pd.isna(value):
        return []
    text = str(value).strip()
    if not text:
        return []
    candidates: list[str] = []
    seen: set[str] = set()
    for part in text.split("→"):
        raw = part.strip()
        normalized = normalize_company_name(raw)
        if normalized and normalized not in seen:
            candidates.append(raw)
            seen.add(normalized)
    return candidates


def _profile_url(exchange: str, stock_code: str) -> str:
    suffix = {"SSE": "SH", "SZSE": "SZ", "BSE": "BJ"}.get(exchange)
    if suffix is None:
        return ""
    secucode = f"{str(stock_code).zfill(6)}.{suffix}"
    params = {
        "reportName": "RPT_F10_BASIC_ORGINFO",
        "columns": "ALL",
        "pageNumber": "1",
        "pageSize": "1",
        "source": "HSF10",
        "client": "PC",
        "filter": f'(SECUCODE="{secucode}")',
    }
    return "https://datacenter.eastmoney.com/securities/api/data/v1/get?" + urlencode(params)


def _is_true_profile(row: pd.Series) -> bool:
    return (
        normalize_company_name(row.get("company_name_legal_profile")) != ""
        and normalize_company_name(row.get("source_org_code")) != ""
        and normalize_company_name(row.get("profile_status_profile")).upper() == "PASS"
        and normalize_company_name(row.get("profile_source_profile"))
        == "EastMoney F10 RPT_F10_BASIC_ORGINFO"
    )


def _base_record(row: pd.Series, raw_name: str, source_field: str) -> dict[str, Any]:
    current_name = normalize_company_name(row.get("company_name_legal_profile"))
    return {
        "firm_key": str(row["firm_key"]),
        "exchange": str(row.get("exchange", "")),
        "stock_code_current": str(row.get("stock_code_current", "")),
        "current_legal_name": current_name,
        "candidate_name_raw": raw_name,
        "candidate_name_normalized": normalize_company_name(raw_name),
        "name_type": "unresolved",
        "valid_from": "",
        "valid_to": "",
        "date_precision": "unknown",
        "evidence_tier": "",
        "evidence_source": "",
        "evidence_url": "",
        "verification_status": "UNRESOLVED",
        "query_eligible": 0,
        "temporal_match_uncertain": 1,
        "rejection_reason": "候选来源不能单独证明历史法人身份",
        "source_field": source_field,
        "source_org_code": normalize_company_name(row.get("source_org_code")),
    }


def _apply_review(record: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
    reviewed_type = _text(review.get("name_type"), "unresolved")
    status = _text(review.get("verification_status"), "UNRESOLVED").upper()
    if reviewed_type not in NAME_TYPES:
        raise ValueError(f"invalid name_type: {reviewed_type}")
    if reviewed_type == "current_legal" and record.get("source_field") != "ORG_NAME":
        raise ValueError("current_legal names must originate from ORG_NAME")
    if status not in VERIFICATION_STATUSES:
        raise ValueError(f"invalid verification_status: {status}")
    precision = _text(review.get("date_precision"), "unknown") or "unknown"
    if precision not in DATE_PRECISIONS:
        raise ValueError(f"invalid date_precision: {precision}")
    tier = _text(review.get("evidence_tier"))
    valid_from = _text(review.get("valid_from"))
    valid_to = _text(review.get("valid_to"))
    if precision == "unknown" and (valid_from or valid_to):
        raise ValueError("unknown date_precision cannot carry valid_from/valid_to")
    if precision == "year" and any(
        value and re.fullmatch(r"\d{4}", value) is None for value in (valid_from, valid_to)
    ):
        raise ValueError("year date_precision requires YYYY valid_from/valid_to")
    if precision == "exact_date" and any(
        value and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None
        for value in (valid_from, valid_to)
    ):
        raise ValueError("exact_date precision requires YYYY-MM-DD valid_from/valid_to")
    source_url = _text(review.get("evidence_url")).strip()
    if status == "VERIFIED" and reviewed_type in {"historical_legal", "current_legal"}:
        if tier not in HISTORICAL_TIERS or not source_url.startswith(("https://", "http://")):
            raise ValueError("verified legal name requires evidence_tier and evidence_url")
    if reviewed_type == "historical_legal" and status == "VERIFIED" and not _text(
        review.get("evidence_source")
    ).strip():
        raise ValueError("verified historical_legal requires evidence_source")
    if status == "REJECTED" and not _text(review.get("rejection_reason")).strip():
        raise ValueError("rejected candidate requires rejection_reason")

    record.update(
        {
            "name_type": reviewed_type,
            "valid_from": valid_from,
            "valid_to": valid_to,
            "date_precision": precision,
            "evidence_tier": tier,
            "evidence_source": _text(review.get("evidence_source")),
            "evidence_url": source_url,
            "verification_status": status,
            "query_eligible": int(
                status == "VERIFIED" and reviewed_type in {"current_legal", "historical_legal"}
            ),
            "temporal_match_uncertain": int(
                reviewed_type == "historical_legal"
                and (precision != "exact_date" or not valid_from or not valid_to)
            ),
            "rejection_reason": _text(review.get("rejection_reason")),
            "source_field": _text(review.get("source_field"), record["source_field"]),
        }
    )
    if status != "VERIFIED" or reviewed_type not in {"historical_legal", "current_legal"}:
        record["query_eligible"] = 0
    return record


def build_entity_name_universe(
    firm_profiles: pd.DataFrame, reviewed_evidence: pd.DataFrame
) -> pd.DataFrame:
    missing = REQUIRED_PROFILE_COLUMNS.difference(firm_profiles.columns)
    if missing:
        raise ValueError(f"firm profile is missing columns: {sorted(missing)}")
    firms = firm_profiles.drop_duplicates("firm_key").copy()
    if firm_profiles["firm_key"].duplicated().any():
        raise ValueError("firm profile contains duplicate firm_key records")
    rows: list[dict[str, Any]] = []
    for _, row in firms.iterrows():
        current_raw = normalize_company_name(row.get("company_name_legal_profile"))
        if current_raw:
            current = _base_record(row, str(row["company_name_legal_profile"]), "ORG_NAME")
            current.update(
                {
                    "name_type": "current_legal",
                    "date_precision": "unknown",
                    "evidence_tier": "PROFILE_CURRENT",
                    "evidence_source": "EastMoney F10 RPT_F10_BASIC_ORGINFO current profile",
                    "evidence_url": _profile_url(
                        str(row["exchange"]), str(row["stock_code_current"])
                    ),
                    "verification_status": "VERIFIED" if _is_true_profile(row) else "UNRESOLVED",
                    "query_eligible": int(_is_true_profile(row)),
                    "temporal_match_uncertain": 1,
                    "rejection_reason": (
                        "" if _is_true_profile(row) else "当前法人名称来源或状态未通过校验"
                    ),
                }
            )
            rows.append(current)
        for candidate in parse_formername_candidates(row.get("former_names_raw")):
            rows.append(_base_record(row, candidate, "FORMERNAME"))

    result = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    if result.empty:
        result = pd.DataFrame(columns=OUTPUT_COLUMNS)

    if not reviewed_evidence.empty:
        required = {"firm_key", "candidate_name_raw", "name_type", "verification_status"}
        missing_evidence = required.difference(reviewed_evidence.columns)
        if missing_evidence:
            raise ValueError(f"reviewed evidence is missing columns: {sorted(missing_evidence)}")
        evidence = reviewed_evidence.copy()
        evidence["candidate_name_normalized"] = evidence["candidate_name_raw"].map(
            normalize_company_name
        )
        evidence_keys = list(zip(evidence.firm_key.astype(str), evidence.candidate_name_normalized))
        if len(evidence_keys) != len(set(evidence_keys)):
            raise ValueError("reviewed evidence has duplicate firm/name keys")
        for review in evidence.to_dict(orient="records"):
            match = result.index[
                result.firm_key.astype(str).eq(str(review["firm_key"]))
                & result.candidate_name_normalized.eq(review["candidate_name_normalized"])
            ].tolist()
            is_history = review["name_type"] == "historical_legal"
            if not match and not is_history:
                raise ValueError("reviewed candidate is absent from FORMERNAME candidates")
            if len(match) > 1:
                raise ValueError("reviewed evidence matches duplicate firm/name candidates")
            if match:
                idx = match[0]
                record = result.loc[idx].to_dict()
                result.loc[idx, list(OUTPUT_COLUMNS)] = pd.Series(
                    _apply_review(record, review)
                ).reindex(OUTPUT_COLUMNS)
            elif is_history:
                firm = firms.loc[firms.firm_key.astype(str).eq(str(review["firm_key"]))]
                if firm.empty:
                    raise ValueError("historical evidence references firm outside target profiles")
                record = _base_record(
                    firm.iloc[0], str(review["candidate_name_raw"]), "reviewed_evidence"
                )
                result = pd.concat(
                    [result, pd.DataFrame([_apply_review(record, review)], columns=OUTPUT_COLUMNS)],
                    ignore_index=True,
                )

    if not result.empty:
        result["query_eligible"] = pd.to_numeric(result.query_eligible, errors="raise").astype(int)
        allowed = result.name_type.isin({"current_legal", "historical_legal"})
        valid = result.verification_status.eq("VERIFIED")
        if result.loc[~(allowed & valid), "query_eligible"].ne(0).any():
            raise ValueError("unverified or nonlegal name was made query eligible")
        if not result.name_type.isin(NAME_TYPES).all():
            raise ValueError("invalid name_type in entity-name universe")
        result = result.sort_values(
            ["firm_key", "candidate_name_normalized", "source_field"], kind="mergesort"
        ).reset_index(drop=True)
    return result[OUTPUT_COLUMNS]


def build_deterministic_pilot_sample(
    firm_profiles: pd.DataFrame,
    seed: str = "20260927",
    n_per_stratum: int = 10,
    forced_firm_keys: set[str] | None = None,
) -> pd.DataFrame:
    firms = firm_profiles.drop_duplicates("firm_key").copy()
    forced = forced_firm_keys or set()
    memberships: dict[str, set[str]] = {}
    candidates = {
        "SSE_current": firms.exchange.eq("SSE") & firms.delisting_date.isna(),
        "SZSE_current": firms.exchange.eq("SZSE") & firms.delisting_date.isna(),
        "SSE_delisted": firms.exchange.eq("SSE") & firms.delisting_date.notna(),
        "SZSE_delisted": firms.exchange.eq("SZSE") & firms.delisting_date.notna(),
        "former_nonempty": firms.former_names_raw.map(
            lambda value: bool(parse_formername_candidates(value))
        ),
        "former_multiple": firms.former_names_raw.map(
            lambda value: len(parse_formername_candidates(value)) > 1
        ),
    }
    for stratum, mask in candidates.items():
        frame = firms.loc[mask].copy()
        frame["_rank"] = frame.firm_key.map(
            lambda key: hashlib.sha256(f"{seed}|{stratum}|{key}".encode("utf-8")).hexdigest()
        )
        for key in frame.sort_values(["_rank", "firm_key"]).firm_key.head(n_per_stratum):
            memberships.setdefault(str(key), set()).add(stratum)
    for key in forced:
        if key in set(firms.firm_key.astype(str)):
            memberships.setdefault(key, set()).add("verified_legal_rename")
    by_key = firms.set_index(firms.firm_key.astype(str), drop=False)
    selected = by_key.loc[sorted(memberships)].copy()
    selected["pilot_strata"] = [
        "|".join(sorted(memberships[key])) for key in selected.firm_key.astype(str)
    ]
    return selected.reset_index(drop=True)


def audit_name_collisions(name_universe: pd.DataFrame) -> pd.DataFrame:
    eligible = name_universe.loc[name_universe.query_eligible.eq(1)].copy()
    columns = [
        "collision_id",
        "normalized_name",
        "firm_keys",
        "firm_count",
        "collision_type",
        "collision_status",
        "review_reason",
    ]
    records: list[dict[str, Any]] = []
    for name, group in eligible.groupby("candidate_name_normalized", sort=True):
        firms = group.drop_duplicates("firm_key")
        if len(firms) < 2:
            continue
        org_codes = set(firms.source_org_code.fillna("").astype(str)) - {""}
        same_org = len(org_codes) == 1 and firms.source_org_code.notna().all()
        security_ids = set(
            firms.exchange.fillna("").astype(str)
            + ":"
            + firms.stock_code_current.fillna("").astype(str)
        )
        distinct_securities = len(security_ids) > 1
        collision_type = (
            "same_legal_entity_different_listing_instance"
            if same_org and distinct_securities
            else "unresolved"
        )
        reason = (
            "F10 ORG_CODE一致且证券代码不同；保留全部映射且不自动分配结果"
            if same_org and distinct_securities
            else "normalized legal name跨多个firm_key；无法排除同证券键重复或数据问题"
        )
        collision_id = hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]
        records.append(
            {
                "collision_id": collision_id,
                "normalized_name": name,
                "firm_keys": "|".join(sorted(firms.firm_key.astype(str))),
                "firm_count": len(firms),
                "collision_type": collision_type,
                "collision_status": "UNRESOLVED",
                "review_reason": reason,
            }
        )
    return pd.DataFrame(records, columns=columns)


def build_query_artifacts(
    name_universe: pd.DataFrame, max_names: int = 20, max_chars: int = 1500
) -> QueryArtifacts:
    eligible = name_universe.loc[name_universe.query_eligible.eq(1)].copy()
    if eligible.candidate_name_normalized.eq("").any():
        raise ValueError("empty eligible query name")
    names = normalize_company_names(eligible.candidate_name_normalized.tolist())
    batches = split_company_queries(names, max_names=max_names, max_chars=max_chars)
    name_to_batch = {
        name: f"batch_{idx:04d}"
        for idx, batch in enumerate(batches, start=1)
        for name in batch
    }
    collisions = audit_name_collisions(eligible)
    colliding_names = set(collisions.normalized_name) if not collisions.empty else set()
    query_names = pd.DataFrame(
        [
            {
                "query_name": name,
                "query_batch_id": name_to_batch[name],
                "name_type": "|".join(
                    sorted(
                        set(
                            eligible.loc[
                                eligible.candidate_name_normalized.eq(name), "name_type"
                            ]
                        )
                    )
                ),
                "firm_count": int(
                    eligible.loc[eligible.candidate_name_normalized.eq(name), "firm_key"].nunique()
                ),
                "collision": int(name in colliding_names),
            }
            for name in names
        ],
        columns=["query_name", "query_batch_id", "name_type", "firm_count", "collision"],
    )
    query_batches = pd.DataFrame(
        [
            {
                "query_batch_id": f"batch_{idx:04d}",
                "query_name_count": len(batch),
                "query_string": build_applicant_query(batch),
                "query_names_json": json.dumps(batch, ensure_ascii=False),
            }
            for idx, batch in enumerate(batches, start=1)
        ],
        columns=["query_batch_id", "query_name_count", "query_string", "query_names_json"],
    )
    name_firm_map = (
        eligible.groupby(["candidate_name_normalized", "firm_key"], as_index=False, sort=True)
        .agg(
            name_type=("name_type", lambda values: "|".join(sorted(set(values)))),
            temporal_match_uncertain=("temporal_match_uncertain", "max"),
        )
        .rename(columns={"candidate_name_normalized": "query_name"})
    )
    name_firm_map["query_batch_id"] = name_firm_map.query_name.map(name_to_batch)
    name_firm_map["collision"] = name_firm_map.query_name.isin(colliding_names).astype(int)
    name_firm_map["attribution_status"] = name_firm_map.collision.map(
        {1: "UNRESOLVED_COLLISION", 0: "TEMPORAL_REVIEW_REQUIRED"}
    )
    return QueryArtifacts(query_names, query_batches, name_firm_map.reset_index(drop=True))


def validate_full_target_set(expected_firm_keys: set[str], observed_firm_keys: set[str]) -> None:
    expected = set(map(str, expected_firm_keys))
    observed = set(map(str, observed_firm_keys))
    if expected != observed:
        missing = sorted(expected - observed)[:5]
        extra = sorted(observed - expected)[:5]
        raise ValueError(
            f"target firm_key set mismatch: missing={missing}, extra={extra}, "
            f"expected_n={len(expected)}, observed_n={len(observed)}"
        )


def validate_firm_profile_consistency(firm_profiles: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED_PROFILE_COLUMNS.difference(firm_profiles.columns)
    if missing:
        raise ValueError(f"firm profile is missing columns: {sorted(missing)}")
    fields = sorted(REQUIRED_PROFILE_COLUMNS - {"firm_key"})
    distinct_values = firm_profiles.groupby("firm_key", dropna=False)[fields].nunique(
        dropna=False
    )
    varying = distinct_values.gt(1).any(axis=1)
    if varying.any():
        keys = sorted(map(str, distinct_values.index[varying]))[:5]
        raise ValueError(f"profile values vary within firm_key: {keys}")
    return firm_profiles.drop_duplicates("firm_key").copy()


def validate_query_artifacts(
    name_universe: pd.DataFrame,
    artifacts: QueryArtifacts,
    max_names: int = 20,
    max_chars: int = 1500,
) -> dict[str, int]:
    eligible = name_universe.loc[name_universe.query_eligible.eq(1)]
    if not eligible.name_type.isin({"current_legal", "historical_legal"}).all():
        raise ValueError("query-eligible names must be verified legal names")
    if not eligible.verification_status.eq("VERIFIED").all():
        raise ValueError("query-eligible names must have VERIFIED status")
    expected_names = set(eligible.candidate_name_normalized)
    actual_names = set(artifacts.query_names.query_name)
    if expected_names != actual_names:
        raise ValueError("eligible query name set mismatch")
    if artifacts.query_names.query_name.duplicated().any():
        raise ValueError("query_names contains duplicate names")
    if artifacts.name_firm_map.duplicated(["query_name", "firm_key"]).any():
        raise ValueError("query_name_firm_map contains duplicate mappings")
    mapping_names = set(artifacts.name_firm_map.query_name)
    if mapping_names != expected_names:
        raise ValueError("query name to firm_key map is incomplete")
    if artifacts.query_batches.query_batch_id.duplicated().any():
        raise ValueError("duplicate query batch id")
    flat_names: list[str] = []
    for _, batch in artifacts.query_batches.iterrows():
        batch_names = json.loads(batch.query_names_json)
        flat_names.extend(batch_names)
        if len(batch_names) > max_names:
            raise ValueError("query batch exceeds max_names")
        if len(str(batch.query_string)) > max_chars:
            raise ValueError("query batch exceeds max_chars")
        if str(batch.query_string) != build_applicant_query(batch_names):
            raise ValueError("query string differs from exact applicant-name list")
    if set(flat_names) != expected_names or len(flat_names) != len(expected_names):
        raise ValueError("each eligible query name must appear in exactly one batch")
    if artifacts.name_firm_map.query_batch_id.isna().any():
        raise ValueError("query map contains names without a batch")
    collision_counts = artifacts.name_firm_map.groupby("query_name").firm_key.nunique()
    for name, count in collision_counts.items():
        marked = artifacts.name_firm_map.loc[
            artifacts.name_firm_map.query_name.eq(name), "collision"
        ].eq(1).all()
        if (count > 1) != bool(marked):
            raise ValueError("cross-firm query-name collision is not explicitly flagged")
    return {
        "eligible_unique_names": len(expected_names),
        "query_batches": len(artifacts.query_batches),
        "query_name_firm_mappings": len(artifacts.name_firm_map),
        "every_name_exactly_once": 1,
    }
