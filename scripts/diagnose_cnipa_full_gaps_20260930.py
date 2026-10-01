"""Offline, deterministic diagnostics for CNINFO Full name gaps and stale cache rows."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from src.cnipa_annual_report_names import PARSER_REVISION

ROOT = Path(__file__).resolve().parents[1]
FULL_DIR = ROOT / "results/cnipa_legal_name_recovery"
FULL_STATUS = FULL_DIR / "full_status.csv"
FULL_STATE = FULL_DIR / "full_run_state.json"
CACHE_DIR = FULL_DIR / "cache"
ENTITY_COVERAGE = ROOT / "results/cnipa_preflight/entity_year_name_coverage.csv"
ENTITY_NAME_AUDIT = ROOT / "results/cnipa_preflight/entity_name_audit.csv"
UNIVERSE = ROOT / "data/processed/real_company_universe_enriched.parquet"
TARGET_MANIFEST = ROOT / "results/real_financial_full/target_manifest.csv"
HISTORICAL_SOURCE_CACHE = ROOT / "results/historical_province/cache"
OUTPUT_DIR = ROOT / "results/cnipa_full_gap_diagnosis"
CURRENT_PARSER_REVISION = PARSER_REVISION
PILOT_SEED = "20260930"
EXPECTED_FULL_ROWS = 23448

COVERAGE_FAMILIES = (
    "CONFIRMED_YEAR_END_NAME_ONLY",
    "CONFIRMED_NAME_CHANGE",
    "CONFIRMED_NO_CHANGE",
    "TEMPORAL_UNRESOLVED",
    "REPORT_NOT_FOUND",
    "LEGAL_NAME_EXTRACTION_FAILED",
    "REPORT_FETCH_FAILED",
    "SOURCE_BLOCKED",
)
GAP_FAMILIES = frozenset(
    {
        "TEMPORAL_UNRESOLVED",
        "REPORT_NOT_FOUND",
        "LEGAL_NAME_EXTRACTION_FAILED",
        "REPORT_FETCH_FAILED",
    }
)
SUCCESSFUL_STATUSES = frozenset({"PENDING", "COMPLETE_NO_CHANGE", "COMPLETE_NAME_CHANGE"})
STALE_RISK_TIERS = (
    "HIGH",
    "MEDIUM",
    "LOW",
    "INSUFFICIENT_LOCAL_EVIDENCE",
)
ALLOWED_ACTIONS = frozenset(
    {
        "REFETCH_EXACT_H1_URL",
        "TARGETED_CNINFO_INDEX_LOOKUP",
        "TARGETED_H2_NAME_CHANGE_LOOKUP",
        "REPARSE_EXISTING_LOCAL_TEXT",
        "MANUAL_SOURCE_REVIEW",
        "NO_NETWORK_NEGATIVE_CONTROL",
        "SOURCE_UNRESOLVED",
    }
)
RISK_CONTEXT_TOKENS = (
    "分公司",
    "子公司",
    "控股子公司",
    "参股公司",
    "分支机构",
    "被投资单位",
    "孙公司",
)
GLOSSARY_TOKEN = "释义"
HIGH_PRECISION_LABELS = frozenset({"公司的中文名称", "公司中文名称"})
WIDE_LABELS = frozenset({"公司名称", "公司全称"})


def _text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _truth(value: object) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y"}


def _normalize_name(value: object) -> str:
    return re.sub(r"[^\w]", "", unicodedata.normalize("NFKC", _text(value)))


def _year(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _http_status(value: object) -> str:
    raw = _text(value)
    try:
        numeric = float(raw)
    except ValueError:
        return raw
    return str(int(numeric)) if numeric.is_integer() else raw


def derive_coverage_family(row: pd.Series | dict[str, Any]) -> str:
    get = row.get
    if _text(get("evidence_status")) == "TEMPORAL_UNRESOLVED":
        return "TEMPORAL_UNRESOLVED"
    status = _text(get("status"))
    return {
        "PENDING": "CONFIRMED_YEAR_END_NAME_ONLY",
        "COMPLETE_NAME_CHANGE": "CONFIRMED_NAME_CHANGE",
        "COMPLETE_NO_CHANGE": "CONFIRMED_NO_CHANGE",
        "REPORT_NOT_FOUND": "REPORT_NOT_FOUND",
        "LEGAL_NAME_NOT_FOUND": "LEGAL_NAME_EXTRACTION_FAILED",
        "PDF_FETCH_FAILED": "REPORT_FETCH_FAILED",
        "TEXT_EXTRACTION_FAILED": "REPORT_FETCH_FAILED",
        "SOURCE_BLOCKED": "SOURCE_BLOCKED",
    }.get(status, "UNCLASSIFIED")


def validate_coverage_partition(
    frame: pd.DataFrame, expected_pairs: set[tuple[str, int]]
) -> dict[str, Any]:
    keys = set(zip(frame.firm_key.astype(str), pd.to_numeric(frame.year).astype(int), strict=True))
    counts = frame.coverage_family.value_counts().to_dict()
    unique_keys = not frame.duplicated(["firm_key", "year"]).any()
    exhaustive = set(frame.coverage_family).issubset(set(COVERAGE_FAMILIES))
    temporal_keys = set(
        zip(
            frame.loc[frame.coverage_family.eq("TEMPORAL_UNRESOLVED"), "firm_key"].astype(str),
            pd.to_numeric(
                frame.loc[frame.coverage_family.eq("TEMPORAL_UNRESOLVED"), "year"]
            ).astype(int),
            strict=True,
        )
    )
    no_name = frame.coverage_family.isin(
        {"REPORT_NOT_FOUND", "LEGAL_NAME_EXTRACTION_FAILED", "REPORT_FETCH_FAILED"}
    )
    no_name_keys = set(
        zip(
            frame.loc[no_name, "firm_key"].astype(str),
            pd.to_numeric(frame.loc[no_name, "year"]).astype(int),
            strict=True,
        )
    )
    gap_keys = set(
        zip(
            frame.loc[frame.coverage_family.isin(GAP_FAMILIES), "firm_key"].astype(str),
            pd.to_numeric(frame.loc[frame.coverage_family.isin(GAP_FAMILIES), "year"]).astype(int),
            strict=True,
        )
    )
    valid = bool(
        unique_keys
        and exhaustive
        and keys == expected_pairs
        and sum(int(value) for value in counts.values()) == len(expected_pairs)
        and temporal_keys.isdisjoint(no_name_keys)
        and temporal_keys | no_name_keys == gap_keys
        and counts.get("SOURCE_BLOCKED", 0) == 0
    )
    return {
        "valid": valid,
        "baseline_rows": len(frame),
        "unique_keys": unique_keys,
        "key_set_exact": keys == expected_pairs,
        "families_exhaustive": exhaustive,
        "family_counts": {family: int(counts.get(family, 0)) for family in COVERAGE_FAMILIES},
        "temporal_unresolved_count": len(temporal_keys),
        "no_name_count": len(no_name_keys),
        "temporal_no_name_intersection_count": len(temporal_keys & no_name_keys),
        "gap_union_count": len(temporal_keys | no_name_keys),
        "gap_key_set": temporal_keys | no_name_keys,
    }


def build_primary_targets(universe: pd.DataFrame, manifest: pd.DataFrame) -> pd.DataFrame:
    required_universe = {"firm_key", "year"}
    required_manifest = {"firm_key", "formal_ready"}
    if not required_universe.issubset(universe.columns) or not required_manifest.issubset(
        manifest.columns
    ):
        raise ValueError("PRIMARY_TARGET_INPUT_COLUMNS_MISSING")
    ready_firms = set(manifest.loc[manifest.formal_ready.astype(bool), "firm_key"].astype(str))
    panel = universe.loc[universe.firm_key.astype(str).isin(ready_firms)].copy()
    years = pd.to_numeric(panel.year, errors="coerce")
    primary = panel.loc[years.between(2020, 2024)].copy()
    primary["year"] = pd.to_numeric(primary.year).astype(int)
    if primary.empty or primary.duplicated(["firm_key", "year"]).any():
        raise ValueError("PRIMARY_TARGET_KEY_SET_INVALID")
    return primary


def _event_timing(row: pd.Series | dict[str, Any]) -> str:
    year = _year(row.get("year"))
    raw_date = _text(row.get("change_effective_date"))
    if year is None or not raw_date:
        return "NO_DATE"
    precision = _text(row.get("date_precision")).lower()
    year_match = re.fullmatch(r"(?:19|20)\d{2}", raw_date)
    if precision == "year" or year_match:
        match = re.search(r"(?:19|20)\d{2}", raw_date)
        if not match:
            return "DATE_UNPARSEABLE"
        event_year = int(match.group())
        if event_year < year:
            return "PRE_TARGET_YEAR"
        if event_year > year:
            return "POST_YEAR_END"
        return "YEAR_PRECISION"
    parsed = pd.to_datetime(raw_date, errors="coerce")
    if pd.notna(parsed):
        if parsed.date() < date(year, 1, 1):
            return "PRE_TARGET_YEAR"
        if parsed.date() > date(year, 12, 31):
            return "POST_YEAR_END"
        return "IN_TARGET_YEAR"
    match = re.search(r"(19|20)\d{2}", raw_date)
    if not match:
        return "DATE_UNPARSEABLE"
    event_year = int(match.group())
    if event_year < year:
        return "PRE_TARGET_YEAR"
    if event_year > year:
        return "POST_YEAR_END"
    return "YEAR_PRECISION"


def classify_gap_subfamily(
    row: pd.Series | dict[str, Any],
    *,
    adjacent_name_change: bool = False,
    stale_parser: bool = False,
    h2_url_available: bool | None = None,
) -> str:
    get = row.get
    has_current = bool(_text(get("legal_name_current_in_report")))
    has_year_end = bool(_text(get("legal_name_at_year_end")))
    has_pair = bool(_text(get("legal_name_previous")) and _text(get("legal_name_new")))
    precision = _text(get("date_precision")).lower()
    change_date = _text(get("change_effective_date"))
    exact_date = precision == "exact_date" or bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", change_date))
    if has_pair:
        base = (
            "PAIR_EXACT_DATE"
            if exact_date
            else "PAIR_YEAR_PRECISION"
            if precision == "year"
            else "PAIR_NO_DATE"
        )
    elif has_current and has_year_end:
        base = "BOTH_NAMES_NO_EVENT_PAIR"
    elif has_current:
        base = "CURRENT_NAME_ONLY"
    elif has_year_end:
        base = "YEAR_END_NAME_ONLY"
    else:
        base = "NO_LEGAL_NAME_EVIDENCE"
    return f"{base}_{_event_timing(row)}"


def _report_not_found_subfamily(row: dict[str, Any]) -> str:
    if _text(row.get("historical_source_url")):
        return "HISTORICAL_EXACT_URL_AVAILABLE"
    if _text(row.get("historical_announcement_id")):
        return "HISTORICAL_ANNOUNCEMENT_ID_ONLY"
    hist_status = _text(row.get("historical_status")).lower()
    if "not_found" in hist_status or "not found" in hist_status:
        return "HISTORICAL_SOURCE_INDEX_NOT_FOUND"
    if row.get("listing_or_delisting_edge"):
        return "LISTING_OR_DELISTING_YEAR"
    if row.get("historical_source_record"):
        return "HISTORICAL_SOURCE_RECORD_WITHOUT_URL"
    if not _text(row.get("source_report_title")):
        return "REPORT_INDEX_METADATA_MISSING"
    return "OFFLINE_TITLE_OR_SOURCE_DISCOVERY_UNRESOLVED"


def _extraction_failure_subfamily(row: dict[str, Any]) -> str:
    text_chars = _year(row.get("text_chars")) or 0
    http = _http_status(row.get("http_status"))
    pdf_bytes = _year(row.get("pdf_bytes")) or 0
    if http and http != "200" or (http == "200" and pdf_bytes <= 0):
        return "SOURCE_OR_PDF_METADATA_ANOMALY"
    if text_chars < 200:
        return "TEXT_LAYER_SPARSE_OR_ABNORMAL"
    if not _text(row.get("matched_label")):
        title = _text(row.get("source_report_title"))
        year = _year(row.get("year"))
        if "年度报告" in title and year and str(year) in title:
            return "NORMAL_REPORT_TITLE_NO_ISSUER_LABEL_LAYOUT_UNMATCHED"
        return "TEXT_PRESENT_NO_MATCHED_LABEL"
    if not _text(row.get("evidence_context")):
        return "TEXT_PRESENT_NO_EVIDENCE_CONTEXT"
    reason = re.sub(r"[^a-z0-9]+", "_", _text(row.get("failure_reason")).lower()).strip("_")
    return f"OTHER_FAILURE_REASON_{reason or 'UNSPECIFIED'}"


def _fetch_failure_subfamily(row: dict[str, Any]) -> str:
    http = _http_status(row.get("http_status"))
    reason = _text(row.get("failure_reason")).lower()
    pdf_bytes = _year(row.get("pdf_bytes")) or 0
    url_known = bool(_text(row.get("source_url")))
    if (
        _text(row.get("raw_status")) == "TEXT_EXTRACTION_FAILED"
        and any(token in reason for token in ("pdftotext", "text extraction", "文本提取"))
    ):
        return "TEXT_EXTRACTION_FAILURE_MISCLASSIFIED_AS_FETCH_FAILURE"
    if http and http != "200":
        return f"KNOWN_URL_HTTP_{http}" if url_known else f"UNKNOWN_URL_HTTP_{http}"
    if http == "200" and pdf_bytes > 0 and _text(row.get("raw_status")) == "TEXT_EXTRACTION_FAILED":
        return "TEXT_EXTRACTION_FAILURE_AFTER_PDF_FETCH"
    if http == "200" and 0 < pdf_bytes < 1024:
        return "PDF_TOO_SMALL"
    if any(token in reason for token in ("timeout", "connection", "transport", "network")):
        return "TRANSPORT_ERROR"
    if http == "200" and pdf_bytes == 0:
        return "HTTP_200_EMPTY_OR_NON_PDF_RESPONSE"
    return "UNKNOWN_FETCH_FAILURE"


def classify_gap_row(row: dict[str, Any]) -> tuple[str, str, str]:
    family = _text(row.get("coverage_family"))
    if family == "TEMPORAL_UNRESOLVED":
        subfamily = classify_gap_subfamily(
            row,
            adjacent_name_change=bool(row.get("adjacent_year_legal_name_discontinuity")),
            stale_parser=bool(row.get("parser_revision_stale")),
            h2_url_available=bool(row.get("h2_url_available")),
        )
        action = (
            "REPARSE_EXISTING_LOCAL_TEXT"
            if _truth(row.get("pdf_content_persisted"))
            else "TARGETED_H2_NAME_CHANGE_LOOKUP"
            if bool(row.get("h2_url_available"))
            else "MANUAL_SOURCE_REVIEW"
        )
    elif family == "LEGAL_NAME_EXTRACTION_FAILED":
        subfamily = _extraction_failure_subfamily(row)
        action = (
            "REPARSE_EXISTING_LOCAL_TEXT"
            if _truth(row.get("pdf_content_persisted"))
            else "REFETCH_EXACT_H1_URL"
            if _text(row.get("source_url"))
            else "TARGETED_CNINFO_INDEX_LOOKUP"
        )
    elif family == "REPORT_NOT_FOUND":
        subfamily = _report_not_found_subfamily(row)
        action = (
            "REFETCH_EXACT_H1_URL"
            if _text(row.get("historical_source_url"))
            else "TARGETED_CNINFO_INDEX_LOOKUP"
            if row.get("historical_source_record") or _text(row.get("source_report_title"))
            else "SOURCE_UNRESOLVED"
        )
    elif family == "REPORT_FETCH_FAILED":
        subfamily = _fetch_failure_subfamily(row)
        action = "REFETCH_EXACT_H1_URL" if _text(row.get("source_url")) else "SOURCE_UNRESOLVED"
    elif family == "SOURCE_BLOCKED":
        subfamily = "SOURCE_BLOCKED_PREVIOUS_RUN"
        action = "MANUAL_SOURCE_REVIEW"
    else:
        raise ValueError(f"NOT_A_GAP_FAMILY:{family}")
    if action not in ALLOWED_ACTIONS:
        raise ValueError(f"UNSUPPORTED_PROPOSED_ACTION:{action}")
    return family, subfamily, action


def classify_stale_risk(row: dict[str, Any]) -> tuple[str, str]:
    label = _text(row.get("matched_label"))
    context = _text(row.get("evidence_context"))
    name = _text(row.get("legal_name_current_in_report")) or _text(
        row.get("legal_name_at_year_end")
    )
    normalized_context = unicodedata.normalize("NFKC", context)
    scope_terms = [term for term in RISK_CONTEXT_TOKENS if term in normalized_context]
    broad = label in WIDE_LABELS
    glossary_scope = GLOSSARY_TOKEN in normalized_context and broad
    suffix_scope = any(term in name for term in RISK_CONTEXT_TOKENS)
    if "identity_name_match" in row:
        identity_match = _truth(row.get("identity_name_match"))
    else:
        profile_name = _normalize_name(row.get("profile_legal_name"))
        candidate_name = _normalize_name(name)
        historical_match = _truth(row.get("verified_historical_name_match"))
        identity_match = bool(
            candidate_name and (candidate_name == profile_name or historical_match)
        )
    if scope_terms or glossary_scope or suffix_scope:
        return "HIGH", "R3F_LIKE_SCOPE_CONTEXT:" + ";".join(
            scope_terms or [GLOSSARY_TOKEN if glossary_scope else "LEGAL_NAME_SUFFIX"]
        )
    if not label or not context or not name:
        return "INSUFFICIENT_LOCAL_EVIDENCE", "MISSING_LABEL_CONTEXT_OR_ISSUER_NAME"
    if (
        broad
        or not identity_match
        or _truth(row.get("temporal_unresolved"))
        or _truth(row.get("adjacent_year_name_discontinuity"))
    ):
        reasons = []
        if broad:
            reasons.append("WIDE_LABEL")
        if not identity_match:
            reasons.append("IDENTITY_NAME_MISMATCH_OR_UNVERIFIED")
        if _truth(row.get("temporal_unresolved")):
            reasons.append("TEMPORAL_UNRESOLVED")
        if _truth(row.get("adjacent_year_name_discontinuity")):
            reasons.append("ADJACENT_YEAR_NAME_DISCONTINUITY")
        return "MEDIUM", ";".join(reasons)
    if label in HIGH_PRECISION_LABELS and identity_match:
        return "LOW", "PRECISE_ISSUER_LABEL_CLEAN_CONTEXT_IDENTITY_MATCH"
    return "MEDIUM", "LOCAL_EVIDENCE_REQUIRES_REVIEW"


def _stable_rank(seed: str, group: str, firm_key: str, year: int) -> str:
    return hashlib.sha256(f"{seed}|{group}|{firm_key}|{year}".encode("utf-8")).hexdigest()


def _choose_group_rows(
    frame: pd.DataFrame, group_col: str, group_value: str, seed: str, cap: int
) -> pd.DataFrame:
    subset = frame.loc[frame[group_col].eq(group_value)].copy()
    subset["_rank"] = subset.apply(
        lambda row: _stable_rank(seed, group_value, str(row.firm_key), int(row.year)), axis=1
    )
    return (
        subset.sort_values(["_rank", "firm_key", "year"], kind="stable")
        .head(cap)
        .drop(columns="_rank")
    )


def build_diagnostic_pilot(
    gap_roster: pd.DataFrame,
    stale_rows: pd.DataFrame,
    expected_pairs: set[tuple[str, int]],
    *,
    seed: str = PILOT_SEED,
    max_rows: int = 150,
) -> pd.DataFrame:
    selected: list[dict[str, Any]] = []
    gap_groups = sorted(gap_roster.gap_subfamily.dropna().astype(str).unique())
    stale_groups = [
        tier
        for tier in ("HIGH", "MEDIUM", "INSUFFICIENT_LOCAL_EVIDENCE")
        if tier in set(stale_rows.risk_tier)
    ]
    if "LOW" in set(stale_rows.risk_tier):
        stale_groups.append("LOW")
    group_specs: list[tuple[str, str, pd.DataFrame, str]] = []
    for subfamily in gap_groups:
        group_specs.append(("GAP", subfamily, gap_roster, "gap_subfamily"))
    for tier in stale_groups:
        group_specs.append(("STALE_SUCCESS", tier, stale_rows, "risk_tier"))
    if len(group_specs) > max_rows:
        raise ValueError("DIAGNOSTIC_PILOT_REQUIRED_GROUPS_EXCEED_MAX_ROWS")
    per_group_cap = 10
    quotas = {
        key: min(len(frame.loc[frame[col].eq(value)]), per_group_cap)
        for _, value, frame, col in group_specs
        for key in [(value, col)]
    }
    budget = max_rows - len(group_specs)
    while sum(quotas.values()) > budget:
        reducible = [key for key, value in quotas.items() if value > 1]
        if not reducible:
            break
        for key in sorted(
            reducible,
            key=lambda item: hashlib.sha256(f"{seed}|{item}".encode()).hexdigest(),
            reverse=True,
        ):
            if sum(quotas.values()) <= budget:
                break
            quotas[key] -= 1
    for diagnosis_group, value, frame, group_col in group_specs:
        selected_group = _choose_group_rows(
            frame, group_col, value, seed, quotas[(value, group_col)]
        )
        for row in selected_group.to_dict("records"):
            is_gap = diagnosis_group == "GAP"
            selected.append(
                {
                    "firm_key": str(row["firm_key"]),
                    "year": int(row["year"]),
                    "diagnosis_group": diagnosis_group,
                    "subfamily": value if is_gap else f"STALE_SUCCESS_{value}",
                    "risk_tier": _text(row.get("risk_tier")) or "NOT_APPLICABLE",
                    "reason": _text(row.get("diagnosis_basis"))
                    if is_gap
                    else _text(row.get("risk_reason")),
                    "proposed_network_action": _text(row.get("suggested_next_action")),
                    "priority": "P1"
                    if (is_gap and value.startswith("PAIR_")) or (not is_gap and value == "HIGH")
                    else "P2"
                    if diagnosis_group == "STALE_SUCCESS" and value != "LOW"
                    else "P3",
                }
            )
    rows = pd.DataFrame(selected)
    if rows.empty:
        return pd.DataFrame(
            columns=[
                "firm_key",
                "year",
                "diagnosis_group",
                "subfamily",
                "risk_tier",
                "reason",
                "proposed_network_action",
                "priority",
            ]
        )
    merged: list[dict[str, Any]] = []
    for (firm_key, year), group in rows.groupby(["firm_key", "year"], sort=True):
        actions = list(dict.fromkeys(group.proposed_network_action.astype(str)))
        action_order = [
            "TARGETED_H2_NAME_CHANGE_LOOKUP",
            "REFETCH_EXACT_H1_URL",
            "TARGETED_CNINFO_INDEX_LOOKUP",
            "REPARSE_EXISTING_LOCAL_TEXT",
            "MANUAL_SOURCE_REVIEW",
            "SOURCE_UNRESOLVED",
            "NO_NETWORK_NEGATIVE_CONTROL",
        ]
        action = min(actions, key=action_order.index)
        groups = set(group.diagnosis_group)
        merged.append(
            {
                "firm_key": firm_key,
                "year": int(year),
                "diagnosis_group": "GAP_AND_STALE_SUCCESS"
                if len(groups) > 1
                else next(iter(groups)),
                "subfamily": ";".join(sorted(set(group.subfamily.astype(str)))),
                "risk_tier": ";".join(sorted(set(group.risk_tier.astype(str)))),
                "reason": ";".join(sorted(set(group.reason.astype(str))))[:1000],
                "proposed_network_action": action,
                "priority": min(
                    group.priority, key=lambda value: {"P1": 1, "P2": 2, "P3": 3}[value]
                ),
            }
        )
    result = (
        pd.DataFrame(merged)
        .sort_values(["priority", "firm_key", "year"], kind="stable")
        .reset_index(drop=True)
    )
    result_pairs = set(zip(result.firm_key.astype(str), result.year.astype(int), strict=True))
    if result.duplicated(["firm_key", "year"]).any() or not result_pairs.issubset(expected_pairs):
        raise ValueError("DIAGNOSTIC_PILOT_KEY_INVARIANT_FAILED")
    if not set(gap_groups).issubset(set(";".join(result.subfamily).split(";"))):
        raise ValueError("DIAGNOSTIC_PILOT_MISSING_GAP_SUBFAMILY")
    if not set(stale_groups).issubset(set(";".join(result.risk_tier).split(";"))):
        raise ValueError("DIAGNOSTIC_PILOT_MISSING_STALE_RISK_TIER")
    if len(result) > max_rows:
        raise ValueError("DIAGNOSTIC_PILOT_EXCEEDS_MAX_ROWS")
    return result


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path_label(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return f"test_fixture/{path.name}"


def _hash_cache_tree(cache_dir: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    file_count = 0
    byte_count = 0
    for path in sorted(cache_dir.glob("*.json")):
        raw = path.read_bytes()
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(raw).digest())
        file_count += 1
        byte_count += len(raw)
    return {"sha256": digest.hexdigest(), "file_count": file_count, "byte_count": byte_count}


def _load_cache_index(
    cache_dir: Path, target_pairs: set[tuple[str, int]]
) -> tuple[dict[tuple[str, int], dict[str, Any]], dict[str, Any]]:
    index: dict[tuple[str, int], dict[str, Any]] = {}
    digest = hashlib.sha256()
    file_count = 0
    byte_count = 0
    for path in sorted(cache_dir.glob("*.json")):
        raw = path.read_bytes()
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(raw).digest())
        file_count += 1
        byte_count += len(raw)
        try:
            record = json.loads(raw)
            key = (str(record["firm_key"]), int(record["year"]))
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue
        if key not in target_pairs:
            continue
        if key in index:
            raise ValueError(f"DUPLICATE_CACHE_KEY:{key}")
        index[key] = record
    return index, {"sha256": digest.hexdigest(), "file_count": file_count, "byte_count": byte_count}


def _load_historical_source_index(cache_dir: Path) -> dict[tuple[str, int], dict[str, Any]]:
    candidates: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for path in sorted(cache_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for row in payload.get("records", []):
            try:
                key = (str(row["firm_key"]), int(row["source_report_year"]))
            except (KeyError, TypeError, ValueError):
                continue
            candidates[key].append(row)
    result: dict[tuple[str, int], dict[str, Any]] = {}
    for key, values in candidates.items():
        result[key] = sorted(
            values,
            key=lambda row: (
                bool(_text(row.get("source_url_or_id")).startswith("https://")),
                bool(_text(row.get("source_announcement_id"))),
                _text(row.get("source_report_date")),
                _text(row.get("source_url_or_id")),
            ),
            reverse=True,
        )[0]
    return result


def _load_profile_index(universe: pd.DataFrame) -> dict[str, str]:
    result: dict[str, str] = {}
    ordered = universe.sort_values(["firm_key", "year"], kind="stable")
    for firm_key, group in ordered.groupby("firm_key", sort=True):
        last = group.iloc[-1]
        result[str(firm_key)] = _text(last.get("company_name_legal_profile")) or _text(
            last.get("company_name_legal")
        )
    return result


def _load_verified_historical_names(path: Path) -> dict[str, set[str]]:
    frame = pd.read_csv(path, dtype=str).fillna("")
    selected = frame.loc[
        frame.verification_status.eq("VERIFIED") & frame.name_type.eq("historical_legal")
    ]
    result: dict[str, set[str]] = defaultdict(set)
    for row in selected.to_dict("records"):
        normalized = _normalize_name(
            row.get("candidate_name_normalized") or row.get("candidate_name_raw")
        )
        if normalized:
            result[str(row["firm_key"])].add(normalized)
    return result


def _adjacent_name_discontinuities(frame: pd.DataFrame) -> dict[tuple[str, int], bool]:
    result: dict[tuple[str, int], bool] = {}
    for firm_key, group in frame.sort_values(["firm_key", "year"], kind="stable").groupby(
        "firm_key", sort=True
    ):
        previous: pd.Series | None = None
        for _, row in group.iterrows():
            year = int(row.year)
            current_name = _text(row.get("legal_name_at_year_end")) or _text(
                row.get("legal_name_current_in_report")
            )
            changed = False
            if previous is not None and year == int(previous.year) + 1:
                previous_name = _text(previous.get("legal_name_at_year_end")) or _text(
                    previous.get("legal_name_current_in_report")
                )
                changed = bool(
                    current_name
                    and previous_name
                    and _normalize_name(current_name) != _normalize_name(previous_name)
                )
            result[(str(firm_key), year)] = changed
            previous = row
    return result


def _has_listing_delisting_edge(row: dict[str, Any], profile_row: pd.Series | None) -> bool:
    year = _year(row.get("year"))
    if year is None or profile_row is None:
        return False
    for field in ("listing_date", "delisting_date", "market_listing_date"):
        parsed = pd.to_datetime(profile_row.get(field), errors="coerce")
        if pd.notna(parsed) and parsed.year in {year, year - 1}:
            return True
    return False


def _source_fields(source: dict[str, Any] | None) -> dict[str, Any]:
    source = source or {}
    url_or_id = _text(source.get("source_url_or_id"))
    return {
        "historical_source_available": bool(
            url_or_id or _text(source.get("source_announcement_id"))
        ),
        "historical_source_url": url_or_id if url_or_id.startswith("https://") else "",
        "historical_announcement_id": _text(source.get("source_announcement_id"))
        or ("" if url_or_id.startswith("https://") else url_or_id),
        "historical_status": _text(source.get("historical_status")),
        "historical_source_record": bool(source),
        "historical_source_name": _text(source.get("source_name")),
    }


def _enrich_rows(
    baseline: pd.DataFrame,
    cache_index: dict[tuple[str, int], dict[str, Any]],
    historical_sources: dict[tuple[str, int], dict[str, Any]],
    profile_index: dict[str, str],
    profile_by_firm: pd.DataFrame,
    verified_historical_names: dict[str, set[str]],
    adjacent: dict[tuple[str, int], bool],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for original in baseline.to_dict("records"):
        row = dict(original)
        key = (str(row["firm_key"]), int(row["year"]))
        cache = cache_index.get(key, {})
        hist = historical_sources.get(key)
        source = _source_fields(hist)
        row.update(source)
        row["raw_status"] = _text(row.get("status"))
        row["coverage_family"] = derive_coverage_family(row)
        row["parser_revision"] = _text(cache.get("parser_revision", row.get("parser_revision")))
        row["parser_revision_stale"] = row["parser_revision"] != CURRENT_PARSER_REVISION
        row["historical_source_available"] = source["historical_source_available"]
        row["historical_source_url"] = source["historical_source_url"]
        row["historical_announcement_id"] = source["historical_announcement_id"]
        row["historical_status"] = source["historical_status"]
        row["historical_source_record"] = source["historical_source_record"]
        row["historical_source_name"] = source["historical_source_name"]
        row["profile_legal_name"] = profile_index.get(key[0], "")
        name = _text(row.get("legal_name_current_in_report")) or _text(
            row.get("legal_name_at_year_end")
        )
        allowed_names = {
            _normalize_name(row["profile_legal_name"])
        } | verified_historical_names.get(key[0], set())
        normalized_name = _normalize_name(name)
        profile_normalized = _normalize_name(row["profile_legal_name"])
        row["current_profile_name_match"] = bool(
            normalized_name and normalized_name == profile_normalized
        )
        row["verified_historical_name_match"] = normalized_name in verified_historical_names.get(
            key[0], set()
        )
        row["identity_name_match"] = bool(normalized_name and normalized_name in allowed_names)
        row["adjacent_year_legal_name_discontinuity"] = adjacent.get(key, False)
        row["adjacent_year_name_discontinuity"] = adjacent.get(key, False)
        row["temporal_unresolved"] = row["coverage_family"] == "TEMPORAL_UNRESOLVED"
        row["h2_url_available"] = bool(
            ("H2" in _text(row.get("change_evidence_tier")).split("+"))
            and _text(row.get("change_evidence_url"))
        )
        row["listing_or_delisting_edge"] = False
        profile_row = profile_by_firm.loc[key[0]] if key[0] in profile_by_firm.index else None
        row["listing_or_delisting_edge"] = _has_listing_delisting_edge(row, profile_row)
        rows.append(row)
    return pd.DataFrame(rows)


def _build_gap_roster(enriched: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "firm_key",
        "exchange",
        "stock_code",
        "year",
        "coverage_status",
        "raw_status",
        "failure_reason",
        "legal_name_current_in_report",
        "legal_name_at_year_end",
        "legal_name_previous",
        "legal_name_new",
        "company_name_change_flag",
        "change_effective_date",
        "date_precision",
        "temporal_match_uncertain",
        "matched_label",
        "evidence_context",
        "source_url",
        "source_announcement_id",
        "source_report_title",
        "source_report_date",
        "http_status",
        "pdf_bytes",
        "pdf_sha256",
        "text_chars",
        "pdf_content_persisted",
        "parser_revision",
        "historical_source_available",
        "historical_source_url",
        "historical_announcement_id",
        "gap_family",
        "gap_subfamily",
        "diagnosis_basis",
        "suggested_next_action",
        "has_current_name",
        "has_year_end_name",
        "has_old_new_pair",
        "has_change_flag",
        "has_exact_change_date",
        "year_precision_only",
        "h2_url_available",
        "adjacent_year_legal_name_discontinuity",
        "event_timing_relation",
        "post_year_end_change",
        "pre_year_change",
        "failure_reason_is_temporal",
        "parser_revision_stale",
        "content_persistence_status",
        "historical_status",
        "historical_source_name",
    ]
    gap = enriched.loc[enriched.coverage_family.isin(GAP_FAMILIES)].copy()
    records: list[dict[str, Any]] = []
    for row in gap.to_dict("records"):
        row["coverage_status"] = row["coverage_family"]
        row["gap_family"], row["gap_subfamily"], row["suggested_next_action"] = classify_gap_row(
            row
        )
        row["has_current_name"] = bool(_text(row.get("legal_name_current_in_report")))
        row["has_year_end_name"] = bool(_text(row.get("legal_name_at_year_end")))
        row["has_old_new_pair"] = bool(
            _text(row.get("legal_name_previous")) and _text(row.get("legal_name_new"))
        )
        row["has_change_flag"] = bool(_text(row.get("company_name_change_flag")))
        date_value = _text(row.get("change_effective_date"))
        row["has_exact_change_date"] = bool(
            _text(row.get("date_precision")) == "exact_date"
            or re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value)
        )
        row["year_precision_only"] = _text(row.get("date_precision")) == "year"
        timing = _event_timing(row)
        row["event_timing_relation"] = timing
        row["post_year_end_change"] = timing == "POST_YEAR_END"
        row["pre_year_change"] = timing == "PRE_TARGET_YEAR"
        row["failure_reason_is_temporal"] = bool(
            re.search(
                r"temporal|year|date|effective|时间|年份|日期|生效",
                _text(row.get("failure_reason")),
                re.I,
            )
        )
        row["content_persistence_status"] = (
            "PERSISTED" if _truth(row.get("pdf_content_persisted")) else "CONTENT_NOT_PERSISTED"
        )
        row["diagnosis_basis"] = (
            ";".join(
                token
                for token, condition in (
                    ("name_current_present", row["has_current_name"]),
                    ("year_end_present", row["has_year_end_name"]),
                    ("old_new_pair_present", row["has_old_new_pair"]),
                    ("h2_url_available", row.get("h2_url_available")),
                    (
                        "adjacent_name_discontinuity",
                        row.get("adjacent_year_legal_name_discontinuity"),
                    ),
                    ("stale_parser_revision", row.get("parser_revision_stale")),
                    ("content_not_persisted", not _truth(row.get("pdf_content_persisted"))),
                )
                if condition
            )
            or "no_positive_local_diagnostic_feature"
        )
        records.append(row)
    result = pd.DataFrame(records)
    for column in cols:
        if column not in result:
            result[column] = ""
    return (
        result[cols]
        .sort_values(["gap_family", "gap_subfamily", "firm_key", "year"], kind="stable")
        .reset_index(drop=True)
    )


def _build_stale_rows(enriched: pd.DataFrame) -> pd.DataFrame:
    selected = enriched.loc[
        enriched.raw_status.isin(SUCCESSFUL_STATUSES)
        & enriched.parser_revision.ne(CURRENT_PARSER_REVISION)
    ].copy()
    result: list[dict[str, Any]] = []
    for row in selected.to_dict("records"):
        tier, reason = classify_stale_risk(row)
        suspicious_tokens = [
            token for token in RISK_CONTEXT_TOKENS if token in _text(row.get("evidence_context"))
        ]
        glossary = GLOSSARY_TOKEN in _text(row.get("evidence_context"))
        broad = _text(row.get("matched_label")) in WIDE_LABELS
        row.update(
            {
                "risk_tier": tier,
                "risk_reason": reason,
                "matched_label_precision": "HIGH_PRECISION"
                if _text(row.get("matched_label")) in HIGH_PRECISION_LABELS
                else "WIDE"
                if broad
                else "MISSING_OR_OTHER",
                "suspicious_context_tokens": ";".join(suspicious_tokens),
                "glossary_context_present": glossary,
                "branch_glossary_risk": bool(suspicious_tokens or (glossary and broad)),
                "legal_name_branch_suffix": any(
                    token
                    in (
                        _text(row.get("legal_name_current_in_report"))
                        or _text(row.get("legal_name_at_year_end"))
                    )
                    for token in RISK_CONTEXT_TOKENS
                ),
                "current_profile_name_match": bool(row.get("current_profile_name_match")),
                "verified_historical_name_match": bool(row.get("verified_historical_name_match")),
                "adjacent_year_name_discontinuity": bool(
                    row.get("adjacent_year_name_discontinuity")
                ),
                "temporal_unresolved_signal": bool(row.get("temporal_unresolved")),
                "evidence_context_missing": not bool(_text(row.get("evidence_context"))),
                "matched_label_missing": not bool(_text(row.get("matched_label"))),
                "source_url_available": bool(_text(row.get("source_url"))),
                "pdf_hash_available": bool(_text(row.get("pdf_sha256"))),
                "text_available_metadata": (_year(row.get("text_chars")) or 0) > 0,
                "suggested_next_action": "NO_NETWORK_NEGATIVE_CONTROL"
                if tier == "LOW"
                else "REPARSE_EXISTING_LOCAL_TEXT"
                if _truth(row.get("pdf_content_persisted"))
                else "REFETCH_EXACT_H1_URL"
                if _text(row.get("source_url"))
                else "MANUAL_SOURCE_REVIEW",
            }
        )
        result.append(row)
    frame = pd.DataFrame(result)
    expected_cols = [
        "firm_key",
        "exchange",
        "stock_code",
        "year",
        "raw_status",
        "parser_revision",
        "risk_tier",
        "risk_reason",
        "matched_label",
        "matched_label_precision",
        "evidence_context",
        "suspicious_context_tokens",
        "glossary_context_present",
        "branch_glossary_risk",
        "legal_name_current_in_report",
        "legal_name_at_year_end",
        "legal_name_branch_suffix",
        "profile_legal_name",
        "current_profile_name_match",
        "verified_historical_name_match",
        "adjacent_year_name_discontinuity",
        "temporal_unresolved_signal",
        "evidence_context_missing",
        "matched_label_missing",
        "identity_name_match",
        "source_url",
        "source_url_available",
        "pdf_sha256",
        "pdf_hash_available",
        "pdf_bytes",
        "http_status",
        "text_chars",
        "text_available_metadata",
        "pdf_content_persisted",
        "failure_reason",
        "source_report_title",
        "suggested_next_action",
    ]
    if frame.empty:
        return pd.DataFrame(columns=expected_cols)
    for column in expected_cols:
        if column not in frame:
            frame[column] = ""
    return (
        frame[expected_cols]
        .sort_values(["risk_tier", "firm_key", "year"], kind="stable")
        .reset_index(drop=True)
    )


def _json_distribution(frame: pd.DataFrame, column: str) -> str:
    values = {
        str(key): int(value) for key, value in frame[column].fillna("").value_counts().items()
    }
    return json.dumps(values, ensure_ascii=False, sort_keys=True)


def _make_gap_summary(gap: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for (family, subfamily), group in gap.groupby(
        ["gap_family", "gap_subfamily"], dropna=False, sort=True
    ):
        records.append(
            {
                "gap_family": family,
                "gap_subfamily": subfamily,
                "firm_years": len(group),
                "firms": group.firm_key.nunique(),
                "years": _json_distribution(group, "year"),
                "current_parser_revision_count": int(
                    group.parser_revision.eq(CURRENT_PARSER_REVISION).sum()
                ),
                "stale_parser_revision_count": int(
                    group.parser_revision.ne(CURRENT_PARSER_REVISION).sum()
                ),
                "source_url_available_count": int(
                    (
                        group.source_url.fillna("").astype(str).str.startswith("https://")
                        | group.historical_source_url.fillna("").astype(str).str.startswith("https://")
                    ).sum()
                ),
                "pdf_hash_available_count": int(
                    group.pdf_sha256.fillna("").astype(str).str.len().gt(0).sum()
                ),
                "text_available_metadata_count": int(
                    pd.to_numeric(group.text_chars, errors="coerce").fillna(0).gt(0).sum()
                ),
                "suggested_next_action": ";".join(
                    sorted(set(group.suggested_next_action.astype(str)))
                ),
            }
        )
    return pd.DataFrame(records)


def _make_stale_summary(stale: pd.DataFrame) -> pd.DataFrame:
    records = []
    for tier in STALE_RISK_TIERS:
        group = stale.loc[stale.risk_tier.eq(tier)]
        if group.empty:
            continue
        records.append(
            {
                "risk_tier": tier,
                "firm_years": len(group),
                "firms": group.firm_key.nunique(),
                "year_distribution": _json_distribution(group, "year"),
                "exchange_distribution": _json_distribution(group, "exchange"),
                "suggested_next_action_distribution": _json_distribution(
                    group, "suggested_next_action"
                ),
            }
        )
    return pd.DataFrame(records)


def _snapshot_protected_files(cache_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    paths = [FULL_STATUS, FULL_STATE, ENTITY_COVERAGE]
    paths.extend(sorted(FULL_DIR.glob("pilot_*.csv")))
    paths.extend(sorted(FULL_DIR.glob("pilot_*.json")))
    files = {_path_label(path): _hash_file(path) for path in paths if path.exists()}
    files["cnipa_full_cache_tree"] = (
        cache_snapshot["sha256"]
        if cache_snapshot is not None
        else _hash_cache_tree(CACHE_DIR)["sha256"]
    )
    return files


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def run_offline_diagnosis() -> dict[str, Any]:
    """Run local-only diagnostics; no network client or mutation path is used."""
    if OUTPUT_DIR.exists() and any(OUTPUT_DIR.iterdir()):
        raise ValueError("DIAGNOSIS_OUTPUT_DIRECTORY_NOT_EMPTY")
    baseline = pd.read_csv(FULL_STATUS, dtype={"firm_key": str}).fillna("")
    state = json.loads(FULL_STATE.read_text(encoding="utf-8"))
    universe = pd.read_parquet(UNIVERSE)
    manifest = pd.read_csv(TARGET_MANIFEST, dtype={"firm_key": str})
    primary = build_primary_targets(universe, manifest)
    expected_pairs = set(zip(primary.firm_key.astype(str), primary.year.astype(int), strict=True))
    if (
        state.get("stage") != "full"
        or state.get("status") != "COMPLETE"
        or state.get("status_key_set_exact") is not True
        or int(state.get("target_firm_years", -1)) != len(expected_pairs)
        or len(expected_pairs) != EXPECTED_FULL_ROWS
    ):
        raise ValueError("FULL_RUN_STATE_GATE_FAILED")
    if len(baseline) != len(expected_pairs) or baseline.duplicated(["firm_key", "year"]).any():
        raise ValueError("FULL_BASELINE_ROW_OR_DUPLICATE_GATE_FAILED")
    enriched_base = baseline.copy()
    enriched_base["coverage_family"] = enriched_base.apply(derive_coverage_family, axis=1)
    partition = validate_coverage_partition(enriched_base, expected_pairs)
    if not partition["valid"]:
        raise ValueError("FULL_COVERAGE_PARTITION_GATE_FAILED")
    cache_index, cache_before = _load_cache_index(CACHE_DIR, expected_pairs)
    baseline_before = _snapshot_protected_files(cache_before)
    entity_coverage = pd.read_csv(ENTITY_COVERAGE, dtype={"firm_key": str}).fillna("")
    if entity_coverage.duplicated(["firm_key", "year"]).any():
        raise ValueError("ENTITY_YEAR_COVERAGE_DUPLICATE_KEYS")
    entity_coverage["year"] = pd.to_numeric(entity_coverage.year).astype(int)
    entity_coverage["firm_key"] = entity_coverage.firm_key.astype(str)
    in_primary_scope = entity_coverage.apply(
        lambda row: (row.firm_key, int(row.year)) in expected_pairs, axis=1
    )
    primary_entity_coverage = entity_coverage.loc[in_primary_scope].copy()
    coverage_keys = set(
        zip(
            primary_entity_coverage.firm_key,
            primary_entity_coverage.year,
            strict=True,
        )
    )
    if coverage_keys != expected_pairs:
        raise ValueError("ENTITY_YEAR_COVERAGE_KEY_SET_MISMATCH")
    crosscheck = primary_entity_coverage[["firm_key", "year", "coverage_status"]].copy()
    crosscheck = crosscheck.merge(
        enriched_base[["firm_key", "year", "coverage_family"]],
        on=["firm_key", "year"],
        how="outer",
        validate="one_to_one",
        indicator=True,
    )
    if (
        not crosscheck._merge.eq("both").all()
        or not crosscheck.coverage_status.eq(crosscheck.coverage_family).all()
    ):
        raise ValueError("ENTITY_YEAR_COVERAGE_STATUS_MISMATCH")

    successful_keys = set(
        zip(
            baseline.loc[baseline.status.isin(SUCCESSFUL_STATUSES), "firm_key"].astype(str),
            baseline.loc[baseline.status.isin(SUCCESSFUL_STATUSES), "year"].astype(int),
            strict=True,
        )
    )
    if not successful_keys.issubset(cache_index):
        raise ValueError("SUCCESSFUL_FULL_ROWS_MISSING_CACHE_METADATA")
    historical_sources = _load_historical_source_index(HISTORICAL_SOURCE_CACHE)
    profile_index = _load_profile_index(universe)
    historical_names = _load_verified_historical_names(ENTITY_NAME_AUDIT)
    adjacent = _adjacent_name_discontinuities(baseline)
    profile_by_firm = (
        universe.sort_values(["firm_key", "year"])
        .groupby("firm_key", sort=True)
        .tail(1)
        .set_index("firm_key")
    )
    enriched = _enrich_rows(
        baseline,
        cache_index,
        historical_sources,
        profile_index,
        profile_by_firm,
        historical_names,
        adjacent,
    )

    gap = _build_gap_roster(enriched)
    stale = _build_stale_rows(enriched)
    expected_gap = partition["gap_key_set"]
    actual_gap = set(zip(gap.firm_key.astype(str), gap.year.astype(int), strict=True))
    if actual_gap != expected_gap or len(gap) != partition["gap_union_count"]:
        raise ValueError("GAP_ROSTER_KEY_SET_MISMATCH")
    if len(stale) != len(set(zip(stale.firm_key, stale.year, strict=True))) or not set(
        stale.risk_tier
    ).issubset(STALE_RISK_TIERS):
        raise ValueError("STALE_SUCCESS_RISK_TIER_PARTITION_INVALID")
    cache_stale_keys = {
        key
        for key, record in cache_index.items()
        if key in successful_keys
        and _text(record.get("parser_revision")) != CURRENT_PARSER_REVISION
    }
    stale_keys = set(zip(stale.firm_key.astype(str), stale.year.astype(int), strict=True))
    if stale_keys != cache_stale_keys:
        raise ValueError("STALE_SUCCESS_CACHE_SET_MISMATCH")
    if len(stale) != len(cache_stale_keys) or sum(
        int(stale.risk_tier.eq(tier).sum()) for tier in STALE_RISK_TIERS
    ) != len(stale):
        raise ValueError("STALE_SUCCESS_RISK_TIERS_NOT_EXHAUSTIVE")

    gap_summary = _make_gap_summary(gap)
    stale_summary = _make_stale_summary(stale)
    pilot = build_diagnostic_pilot(gap, stale, expected_pairs, seed=PILOT_SEED)
    if not set(ALLOWED_ACTIONS).issuperset(set(pilot.proposed_network_action)):
        raise ValueError("DIAGNOSTIC_PILOT_HAS_DISALLOWED_ACTION")
    family_subfamilies = set(gap.gap_subfamily)
    pilot_subfamilies = set(";".join(pilot.subfamily.astype(str)).split(";"))
    pilot_subfamilies_complete = family_subfamilies.issubset(pilot_subfamilies)
    required_tiers = {"HIGH", "MEDIUM", "INSUFFICIENT_LOCAL_EVIDENCE"} & set(stale.risk_tier)
    pilot_tiers = set(";".join(pilot.risk_tier.astype(str)).split(";"))
    pilot_tiers_complete = required_tiers.issubset(pilot_tiers)
    gap_union = partition["gap_union_count"]
    stale_tier_counts = {tier: int(stale.risk_tier.eq(tier).sum()) for tier in STALE_RISK_TIERS}
    stale_r3f_count = int(stale.branch_glossary_risk.sum())
    family_subfamily_count = int(gap.groupby(["gap_family", "gap_subfamily"], dropna=False).ngroups)
    status_ready = bool(
        len(baseline) == EXPECTED_FULL_ROWS
        and partition["valid"]
        and gap_union == len(expected_gap)
        and sum(stale_tier_counts.values()) == len(stale)
        and pilot_subfamilies_complete
        and pilot_tiers_complete
        and set(zip(pilot.firm_key, pilot.year, strict=True)).issubset(expected_pairs)
    )
    protected_after = _snapshot_protected_files()
    cache_after = _hash_cache_tree(CACHE_DIR)
    if baseline_before != protected_after or cache_before["sha256"] != cache_after["sha256"]:
        raise ValueError("PROTECTED_FULL_OR_PILOT_INPUT_MUTATED_DURING_DIAGNOSIS")
    result = {
        "diagnosis_status": "FULL_NAME_DIAGNOSIS_READY_FOR_TARGETED_PILOT"
        if status_ready
        else "FULL_NAME_DIAGNOSIS_NEEDS_FIX",
        "baseline_rows": len(baseline),
        "primary_target_rows": len(expected_pairs),
        "baseline_key_set_exact": partition["key_set_exact"],
        "full_status_sha256_before": baseline_before[_path_label(FULL_STATUS)],
        "full_status_sha256_after": protected_after[_path_label(FULL_STATUS)],
        "full_run_state_sha256_before": baseline_before[_path_label(FULL_STATE)],
        "full_run_state_sha256_after": protected_after[_path_label(FULL_STATE)],
        "protected_file_sha256_before": baseline_before,
        "protected_file_sha256_after": protected_after,
        "full_cache_tree_sha256_before": cache_before["sha256"],
        "full_cache_tree_sha256_after": cache_after["sha256"],
        "full_cache_json_count": cache_before["file_count"],
        "entity_coverage_rows_outside_primary_target": int(
            len(entity_coverage) - len(primary_entity_coverage)
        ),
        "network_requests": 0,
        "coverage_family_counts": partition["family_counts"],
        "temporal_unresolved_count": partition["temporal_unresolved_count"],
        "no_name_count": partition["no_name_count"],
        "temporal_no_name_intersection_count": partition["temporal_no_name_intersection_count"],
        "gap_union_count": gap_union,
        "gap_subfamily_count": family_subfamily_count,
        "gap_subfamily_counts": {
            f"{row.gap_family}|{row.gap_subfamily}": int(row.firm_years)
            for row in gap_summary.itertuples(index=False)
        },
        "report_not_found_subfamily_counts": {
            str(key): int(value)
            for key, value in gap.loc[gap.gap_family.eq("REPORT_NOT_FOUND"), "gap_subfamily"]
            .value_counts()
            .items()
        },
        "legal_name_extraction_failed_subfamily_counts": {
            str(key): int(value)
            for key, value in gap.loc[
                gap.gap_family.eq("LEGAL_NAME_EXTRACTION_FAILED"), "gap_subfamily"
            ]
            .value_counts()
            .items()
        },
        "report_fetch_failed_subfamily_counts": {
            str(key): int(value)
            for key, value in gap.loc[gap.gap_family.eq("REPORT_FETCH_FAILED"), "gap_subfamily"]
            .value_counts()
            .items()
        },
        "stale_success_count": len(stale),
        "stale_risk_tier_counts": stale_tier_counts,
        "r3f_like_branch_glossary_risk_count": stale_r3f_count,
        "diagnostic_pilot_rows": len(pilot),
        "diagnostic_pilot_firms": int(pilot.firm_key.nunique()),
        "diagnostic_pilot_seed": PILOT_SEED,
        "all_gap_subfamilies_covered": pilot_subfamilies_complete,
        "required_stale_risk_tiers_covered": pilot_tiers_complete,
        "pilot_action_counts": {
            str(key): int(value)
            for key, value in pilot.proposed_network_action.value_counts().items()
        },
        "pilot_unique_key_count": int(len(pilot.drop_duplicates(["firm_key", "year"]))),
        "pilot_keys_within_primary_target": set(
            zip(pilot.firm_key, pilot.year, strict=True)
        ).issubset(expected_pairs),
        "pilot_gate_status": "STRICT_PILOT_GATE_PASS",
        "cnipa_entity_name_scope_status": "CNIPA_ENTITY_NAME_NEEDS_FIX",
        "zero_semantics": "pending",
        "missing_semantics": "pending",
        "cnipa_patent_system_accessed": False,
        "full_and_pilot_inputs_unchanged": baseline_before == protected_after,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    baseline_summary = {
        "full_status_rows": len(baseline),
        "full_run_state": {
            key: state.get(key)
            for key in ("stage", "status", "status_key_set_exact", "target_firm_years")
        },
        "key_set_exact": partition["key_set_exact"],
        "protected_sha256_before": baseline_before,
        "protected_sha256_after": protected_after,
        "full_cache_tree_sha256_before": cache_before["sha256"],
        "full_cache_tree_sha256_after": cache_after["sha256"],
        "cache_json_files": cache_before["file_count"],
        "coverage_partition": {
            key: value for key, value in partition.items() if key != "gap_key_set"
        },
        "entity_coverage_rows_outside_primary_target": result[
            "entity_coverage_rows_outside_primary_target"
        ],
        "full_name_diagnosis_status": result["diagnosis_status"],
    }
    _write_csv(gap, OUTPUT_DIR / "full_gap_roster.csv")
    _write_csv(gap_summary, OUTPUT_DIR / "gap_family_summary.csv")
    _write_csv(stale, OUTPUT_DIR / "stale_success_risk.csv")
    _write_csv(stale_summary, OUTPUT_DIR / "stale_success_risk_summary.csv")
    _write_csv(pilot, OUTPUT_DIR / "diagnostic_pilot_manifest.csv")
    (OUTPUT_DIR / "baseline_summary.json").write_text(
        json.dumps(baseline_summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUTPUT_DIR / "diagnosis_summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    print(json.dumps(run_offline_diagnosis(), ensure_ascii=False, indent=2))
