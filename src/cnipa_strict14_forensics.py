"""Pure, offline decomposition helpers for the frozen CNIPA Strict-14 replay."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import date
from urllib.parse import urlparse

import pandas as pd


def _text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _key(row: Mapping[str, object]) -> tuple[str, int]:
    return str(row.get("firm_key", "")), int(float(row.get("year", 0) or 0))


def _truth(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _integer(value: object, default: int = 0) -> int:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return default
    return int(float(value))


def _normalized(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def _url_date(url: str) -> date | None:
    match = re.search(r"/finalpage/(20\d{2})-(\d{2})-(\d{2})/", url)
    if not match:
        return None
    try:
        return date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def _effective_date(text: str) -> str:
    compact = _normalized(text)
    for match in re.finditer(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", compact):
        after_date = compact[match.end() : match.end() + 60]
        if not re.match(r"[,，。;；]?(?:公司)?完成.{0,40}(?:工商变更登记|工商登记)", after_date):
            continue
        year, month, day = (int(part) for part in match.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            continue
    return ""


def classify_notice_record(
    target: Mapping[str, object],
    notice: Mapping[str, object],
    text: str,
    extraction: Mapping[str, object],
) -> dict[str, object]:
    """Classify saved notice text against independently-derived target values."""
    firm_key, year = _key(target)
    stock_code = firm_key.split(":")[1].zfill(6) if ":" in firm_key else ""
    url = _text(notice.get("source_url", notice.get("url", "")))
    parsed_url = urlparse(url)
    status = int(float(notice.get("http_status", 0) or 0))
    extracted = _text(notice.get("text_extraction_status", ""))
    official = parsed_url.scheme == "https" and parsed_url.netloc == "static.cninfo.com.cn"
    announcement_match = re.search(r"/(\d{6,})\.pdf$", parsed_url.path, re.IGNORECASE)
    announcement_id = announcement_match.group(1) if announcement_match else ""
    code_pattern = re.compile(rf"证券代码\s*[:：]?\s*{re.escape(stock_code)}\b")
    issuer_code_match = bool(stock_code and code_pattern.search(text))
    old_name = _text(target.get("previous_legal_name", ""))
    new_name = _text(target.get("new_legal_name", ""))
    compact = _normalized(text)
    pair_present = bool(
        old_name
        and new_name
        and _normalized(old_name) in compact
        and _normalized(new_name) in compact
    )
    change_discussed = bool(re.search(r"公司名称|企业名称|名称变更|公司更名", compact)) and bool(
        re.search(r"变更|更名", compact)
    )
    effective_date = _effective_date(text)
    completion = bool(effective_date)
    source_date = _url_date(url)
    window_start = date(year, 1, 1)
    window_end = date(year + 1, 3, 31)
    date_in_window = source_date is not None and window_start <= source_date <= window_end
    effective_date_in_target_year = bool(effective_date and effective_date[:4] == str(year))
    extraction_status = _text(extraction.get("evidence_status", ""))
    extraction_reason = _text(extraction.get("failure_reason", ""))

    if (
        not official
        or status < 200
        or status >= 300
        or not announcement_id
        or not issuer_code_match
    ):
        failure_class = "NOTICE_SOURCE_IDENTITY_PROBLEM"
    elif source_date is None or not date_in_window:
        failure_class = "NOTICE_DATE_WINDOW_MISMATCH"
    elif extracted and extracted != "EXTRACTED":
        failure_class = "NOTICE_TEXT_EXTRACTION_FAILED"
    elif extraction_status in {"CONFIRMED_NAME_CHANGE", "CONFIRMED_NO_CHANGE"}:
        failure_class = "RESOLVED_H2"
    elif pair_present and change_discussed and completion and effective_date_in_target_year:
        failure_class = "EXTRACTOR_LAYOUT_GAP"
    else:
        failure_class = "NOTICE_RETURNED_PAIR_NOT_CONFIRMED"

    return {
        "firm_key": firm_key,
        "year": year,
        "source_url": url,
        "official_cninfo": bool(official),
        "http_status": status,
        "announcement_id_from_url": announcement_id,
        "issuer_stock_code_match": bool(issuer_code_match),
        "announcement_date_from_url": source_date.isoformat() if source_date else "",
        "target_window_match": bool(date_in_window),
        "expected_pair_text_present": bool(pair_present),
        "name_change_discussed": bool(change_discussed),
        "completion_semantics_present": bool(completion),
        "effective_date_text": effective_date,
        "effective_date_in_target_year": bool(effective_date_in_target_year),
        "production_extractor_status": extraction_status,
        "production_extractor_failure_reason": extraction_reason,
        "terminal_failure_class": failure_class,
    }


def build_h2_target_forensics(
    manifest: pd.DataFrame,
    evidence: pd.DataFrame,
    request_audit: pd.DataFrame,
    notice_forensics: pd.DataFrame,
    *,
    local_h1_pair_evidence_by_key: Mapping[tuple[str, int], str] | None = None,
) -> pd.DataFrame:
    """Produce exactly one terminal forensic row per frozen H2 manifest target."""
    local_h1_pair_evidence_by_key = local_h1_pair_evidence_by_key or {}
    evidence_by_key = {_key(row): row for row in evidence.to_dict("records")}
    targets: list[dict[str, object]] = []
    for target in manifest.to_dict("records"):
        key = _key(target)
        record = evidence_by_key.get(key, {})
        notice_rows = (
            notice_forensics.loc[
                notice_forensics.firm_key.astype(str).eq(key[0])
                & pd.to_numeric(notice_forensics.year, errors="coerce").eq(key[1])
            ]
            if len(notice_forensics)
            else pd.DataFrame()
        )
        request_rows = (
            request_audit.loc[
                request_audit.firm_key.astype(str).eq(key[0])
                & pd.to_numeric(request_audit.year, errors="coerce").eq(key[1])
                & request_audit.purpose.astype(str).eq("targeted_name_change_discovery")
            ]
            if len(request_audit)
            else pd.DataFrame()
        )
        notice_classes = (
            notice_rows.terminal_failure_class.astype(str).tolist() if len(notice_rows) else []
        )
        status = _text(record.get("status", ""))
        retrieval = _text(record.get("retrieval_mode", ""))
        carry = retrieval == "H2_LOCAL_CARRY" or _truth(
            target.get("existing_h2_status") == "RESOLVED_H2"
        )
        resolved = carry or status == "RESOLVED_H2" or "RESOLVED_H2" in notice_classes
        if resolved:
            terminal = "RESOLVED_H2"
            suggested = "NO_FURTHER_H2_ACTION"
        elif "EXTRACTOR_LAYOUT_GAP" in notice_classes:
            terminal = "EXTRACTOR_LAYOUT_GAP"
            suggested = "H2_EXTRACTOR_REPAIR"
        elif notice_classes:
            terminal = "NOTICE_RETURNED_PAIR_NOT_CONFIRMED"
            suggested = "SOURCE_PROVENANCE_REVIEW"
        elif _integer(record.get("discovery_notice_count", 0)) == 0:
            terminal = "NO_NOTICE_RETURNED"
            suggested = (
                "H1_PARSER_REPAIR"
                if key in local_h1_pair_evidence_by_key
                else "H2_SOURCE_DISCOVERY_REVIEW"
            )
        else:
            terminal = "SOURCE_PROVENANCE_INSUFFICIENT"
            suggested = "SOURCE_PROVENANCE_REVIEW"
        notice_count = len(notice_rows)
        raw_returned_count = _text(record.get("discovery_notice_count", ""))
        if raw_returned_count:
            returned_count = _integer(raw_returned_count)
            count_precision = "EXACT_G2_DISCOVERY_COUNT"
        elif carry:
            returned_count = 0
            count_precision = "NO_DISCOVERY_LOCAL_CARRY"
        elif notice_count:
            returned_count = notice_count
            count_precision = "LOWER_BOUND_FROM_FETCHED_NOTICES"
        else:
            returned_count = 0
            count_precision = "NOT_RECORDED"
        pdf_count = (
            int((notice_rows.get("pdf_sha256", pd.Series(dtype=str)).astype(str).ne("")).sum())
            if len(notice_rows)
            else 0
        )
        text_count = (
            int(
                (
                    notice_rows.get("text_extraction_status", pd.Series(dtype=str))
                    .astype(str)
                    .eq("EXTRACTED")
                ).sum()
            )
            if len(notice_rows)
            else 0
        )
        target_out = {
            **target,
            "existing_carry": bool(carry),
            "discovery_attempted": bool(len(request_rows)),
            "discovery_notice_count": returned_count,
            "discovery_notice_count_precision": count_precision,
            "notice_pdf_count": pdf_count,
            "notice_text_count": text_count,
            "resolved_h2": bool(resolved),
            "terminal_failure_class": terminal,
            "failure_detail": ";".join(notice_classes)
            if notice_classes
            else _text(record.get("failure_reason", "")),
            "suggested_next_stage": suggested,
            "local_h1_pair_evidence": key in local_h1_pair_evidence_by_key,
            "local_h1_evidence_dependency_id": local_h1_pair_evidence_by_key.get(key, ""),
            "notice_count_consistency": (
                "MATCH"
                if (
                    count_precision == "EXACT_G2_DISCOVERY_COUNT" and returned_count == notice_count
                )
                else "LOWER_BOUND_ONLY"
                if count_precision == "LOWER_BOUND_FROM_FETCHED_NOTICES"
                else "NO_DISCOVERY"
                if carry
                else "CHECK_ARTIFACT_SCOPE"
            ),
            "potentially_truncated_by_three_pdf_cap": bool(
                returned_count > pdf_count and pdf_count >= 3 and not resolved
            ),
        }
        targets.append(target_out)
    result = pd.DataFrame(targets)
    if len(result) != len(manifest) or result.duplicated(["firm_key", "year"]).any():
        raise ValueError("H2_TARGET_FORENSICS_NOT_EXHAUSTIVE")
    return result


def build_event_failure_decomposition(
    predictions: pd.DataFrame,
    event_gt: pd.DataFrame,
    *,
    h2_failure_by_event: Mapping[str, str],
    local_h1_event_ids: set[str],
    dependency_by_event: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """Score the six frozen event slots without using their values as predictions."""
    if len(event_gt) != 6 or event_gt.event_id.astype(str).duplicated().any():
        raise ValueError("FROZEN_EVENT_SLOTS_MUST_BE_SIX_UNIQUE")
    if len(predictions) and predictions.event_id.astype(str).duplicated().any():
        raise ValueError("DUPLICATE_EVENT_PREDICTION_ID")
    prediction_by_id = {str(row["event_id"]): row for row in predictions.to_dict("records")}
    dependency_by_event = dependency_by_event or {}
    records: list[dict[str, object]] = []
    for gt in event_gt.to_dict("records"):
        event_id = str(gt["event_id"])
        prediction = prediction_by_id.get(event_id, {})
        present = bool(prediction)
        predicted_old = _text(prediction.get("parser_previous_legal_name", ""))
        predicted_new = _text(prediction.get("parser_new_legal_name", ""))
        predicted_date = _text(prediction.get("parser_effective_date", ""))
        predicted_precision = _text(prediction.get("parser_date_precision", ""))
        old_match = present and predicted_old == _text(gt.get("review_previous_legal_name", ""))
        new_match = present and predicted_new == _text(gt.get("review_new_legal_name", ""))
        date_match = present and predicted_date == _text(gt.get("review_effective_date", ""))
        precision_match = present and predicted_precision == _text(
            gt.get("review_date_precision", "")
        )
        if present:
            status = (
                "EVENT_CORRECT"
                if all((old_match, new_match, date_match, precision_match))
                else "EVENT_FIELD_MISMATCH"
            )
        elif h2_failure_by_event.get(event_id) == "EXTRACTOR_LAYOUT_GAP":
            status = "EVENT_H2_EXTRACTOR_FAILURE"
        elif event_id in local_h1_event_ids:
            status = "EVENT_CANDIDATE_MAPPING_FAILURE"
        else:
            status = "EVENT_SOURCE_REPLAY_MISSING"
        records.append(
            {
                "event_id": event_id,
                "firm_key": str(gt.get("firm_key", "")),
                "event_prediction_present": bool(present),
                "prediction_source_tier": _text(prediction.get("source_evidence_tier", "")),
                "h1_derived": _text(prediction.get("source_evidence_tier", "")) == "H1",
                "h2_derived": _text(prediction.get("source_evidence_tier", "")) == "H2",
                "predicted_previous_name": predicted_old,
                "predicted_new_name": predicted_new,
                "predicted_effective_date": predicted_date,
                "predicted_date_precision": predicted_precision,
                "old_match": bool(old_match),
                "new_match": bool(new_match),
                "date_match": bool(date_match),
                "precision_match": bool(precision_match),
                "status": status,
                "failure_dependency_id": dependency_by_event.get(
                    event_id, f"DEP-EVENT-{event_id}" if status == "EVENT_FIELD_MISMATCH" else ""
                ),
            }
        )
    result = pd.DataFrame(records)
    if len(result) != 6 or result.event_id.nunique() != 6:
        raise ValueError("EVENT_DECOMPOSITION_NOT_EXHAUSTIVE")
    return result


def build_row_evidence_state_decomposition(
    h1_predictions: pd.DataFrame,
    fused_predictions: pd.DataFrame,
    frozen_predictions: pd.DataFrame,
    candidates: pd.DataFrame,
    evidence_gt: pd.DataFrame,
    *,
    h2_dependency_by_key: Mapping[tuple[str, int], str],
    h1_pair_evidence_by_key: Mapping[tuple[str, int], str],
    event_ids_by_firm: Mapping[str, Sequence[str]],
    mapped_event_ids_by_row: Mapping[tuple[str, int], Sequence[str]] | None = None,
    event_year_by_id: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """Compare H1/fused flags against frozen review labels; never edits predictions."""
    mapped_event_ids_by_row = mapped_event_ids_by_row or {}
    event_year_by_id = event_year_by_id or {}
    frames = (h1_predictions, fused_predictions, frozen_predictions, evidence_gt)
    maps: list[dict[tuple[str, int], dict[str, object]]] = []
    for frame in frames:
        rows = frame.to_dict("records")
        keyed = {_key(row): row for row in rows}
        if len(keyed) != len(rows):
            raise ValueError("DUPLICATE_ROW_FORENSICS_KEY")
        maps.append(keyed)
    keysets = [set(row_map) for row_map in maps]
    if any(keys != keysets[0] for keys in keysets[1:]):
        raise ValueError("ROW_FORENSICS_KEYSET_MISMATCH")
    candidates_by_key = {_key(row): row for row in candidates.to_dict("records")}
    records: list[dict[str, object]] = []
    for key in sorted(keysets[0]):
        h1 = maps[0][key]
        fused = maps[1][key]
        frozen = maps[2][key]
        gt = maps[3][key]
        expected = _text(gt.get("review_expected_parser_flag", ""))
        h1_flag = (
            _text(
                h1.get("parser_change_flag", h1.get("parser_company_name_change_flag", "UNKNOWN"))
            )
            or "UNKNOWN"
        )
        fused_flag = (
            _text(
                frozen.get(
                    "parser_change_flag", fused.get("parser_company_name_change_flag", "UNKNOWN")
                )
            )
            or "UNKNOWN"
        )
        h1_correct, fused_correct = h1_flag == expected, fused_flag == expected
        candidate = candidates_by_key.get(key, {})
        row_events = list(mapped_event_ids_by_row.get(key, []))
        frozen_event_id = _text(frozen.get("proposed_event_id", ""))
        if frozen_event_id and frozen_event_id not in row_events:
            row_events.append(frozen_event_id)
        h2_dependency = h2_dependency_by_key.get(key, "")
        h1_dependency = h1_pair_evidence_by_key.get(key, "")
        same_firm_events = list(event_ids_by_firm.get(key[0], []))
        if fused_correct:
            failure_class = "NEGATIVE_CONTROL_PASS" if ":300365:" in key[0] else "NONE"
            dependency = ""
        elif h1_dependency:
            failure_class, dependency = "H1_EXPLICIT_FLAG_ERROR", h1_dependency
        elif h2_dependency:
            failure_class, dependency = "WAITING_ON_UNRESOLVED_H2", h2_dependency
        elif row_events:
            failure_class, dependency = "WAITING_ON_EVENT_PROPAGATION", "DEP-FUSION-NO-PROPAGATION"
        elif same_firm_events:
            failure_class, dependency = "EVENT_MAPPING_FAILURE", "DEP-FUSION-EVENT-MAPPING"
        else:
            failure_class, dependency = "OTHER", f"DEP-UNCLASSIFIED-{key[0]}-{key[1]}"
        event_years = sorted(
            {
                str(event_year_by_id[event_id])
                for event_id in row_events
                if event_id in event_year_by_id
            }
        )
        records.append(
            {
                "firm_key": key[0],
                "year": key[1],
                "h1_flag": h1_flag,
                "fused_flag": fused_flag,
                "review_expected_flag": expected,
                "h1_correct": bool(h1_correct),
                "fused_correct": bool(fused_correct),
                "adjacent_candidate": _truth(candidate.get("adjacent_year_name_change", False)),
                "candidate_reason": _text(candidate.get("candidate_reason", "")),
                "mapped_event": bool(row_events),
                "mapped_event_id": ";".join(row_events),
                "frozen_row_proposed_event_id": frozen_event_id,
                "mapped_event_year": ";".join(event_years),
                "h2_dependency": h2_dependency,
                "failure_class": failure_class,
                "failure_dependency_id": dependency,
            }
        )
    result = pd.DataFrame(records)
    if len(result) != 14:
        raise ValueError("FROZEN_ROW_DENOMINATOR_MUST_BE_FOURTEEN")
    if result.loc[~result.fused_correct, "failure_dependency_id"].astype(str).eq("").any():
        raise ValueError("FUSED_MISMATCH_WITHOUT_FAILURE_DEPENDENCY")
    return result


def build_year_end_failure_decomposition(
    h1_predictions: pd.DataFrame,
    fused_predictions: pd.DataFrame,
    row_gt: pd.DataFrame,
    *,
    h1_temporal_evidence_by_key: Mapping[tuple[str, int], str],
    unresolved_h2_by_key: Mapping[tuple[str, int], str],
) -> pd.DataFrame:
    h1_by_key = {_key(row): row for row in h1_predictions.to_dict("records")}
    fused_by_key = {_key(row): row for row in fused_predictions.to_dict("records")}
    gt_by_key = {_key(row): row for row in row_gt.to_dict("records")}
    if set(h1_by_key) != set(fused_by_key) or set(h1_by_key) != set(gt_by_key):
        raise ValueError("YEAR_END_FORENSICS_KEYSET_MISMATCH")
    failures: list[dict[str, object]] = []
    for key in sorted(gt_by_key):
        review_name = _text(gt_by_key[key].get("review_legal_name_at_year_end", ""))
        h1_name = _text(h1_by_key[key].get("parser_legal_name_at_year_end", ""))
        fused_name = _text(fused_by_key[key].get("parser_legal_name_at_year_end", ""))
        if fused_name == review_name:
            continue
        if key in h1_temporal_evidence_by_key:
            failure_class, dependency = "H1_YEAR_END_PARSER_ERROR", h1_temporal_evidence_by_key[key]
        elif key in unresolved_h2_by_key:
            failure_class, dependency = "TEMPORAL_H2_EVIDENCE_MISSING", unresolved_h2_by_key[key]
        elif h1_name == review_name:
            failure_class, dependency = "FUSION_YEAR_END_ERROR", "DEP-FUSION-YEAR-END"
        else:
            failure_class, dependency = (
                "H1_YEAR_END_PARSER_ERROR",
                f"DEP-H1-YEAR-END-{key[0]}-{key[1]}",
            )
        failures.append(
            {
                "firm_key": key[0],
                "year": key[1],
                "h1_year_end_name": h1_name,
                "fused_year_end_name": fused_name,
                "review_year_end_name": review_name,
                "h2_dependency": unresolved_h2_by_key.get(key, ""),
                "failure_class": failure_class,
                "failure_dependency_id": dependency,
            }
        )
    return pd.DataFrame(failures)


def build_failure_dependency_graph(
    row_decomposition: pd.DataFrame,
    event_decomposition: pd.DataFrame,
    year_end_decomposition: pd.DataFrame,
    *,
    dependency_context: Mapping[str, Mapping[str, object]] | None = None,
) -> pd.DataFrame:
    """Aggregate row/event/year-end outcomes by independent root dependency."""
    dependency_context = dependency_context or {}
    ids: set[str] = set()
    for frame in (row_decomposition, event_decomposition, year_end_decomposition):
        if len(frame) and "failure_dependency_id" in frame:
            ids.update(value for value in frame.failure_dependency_id.astype(str) if value)
    records: list[dict[str, object]] = []
    for dependency_id in sorted(ids):
        row_matches = (
            row_decomposition.loc[
                row_decomposition.failure_dependency_id.astype(str).eq(dependency_id)
            ]
            if len(row_decomposition)
            else pd.DataFrame()
        )
        event_matches = (
            event_decomposition.loc[
                event_decomposition.failure_dependency_id.astype(str).eq(dependency_id)
            ]
            if len(event_decomposition)
            else pd.DataFrame()
        )
        year_matches = (
            year_end_decomposition.loc[
                year_end_decomposition.failure_dependency_id.astype(str).eq(dependency_id)
            ]
            if len(year_end_decomposition)
            else pd.DataFrame()
        )
        context = dependency_context.get(dependency_id, {})
        dep_type = (
            "H2_SOURCE_OR_EXTRACTION"
            if dependency_id.startswith("DEP-H2")
            else "H1_PARSER"
            if dependency_id.startswith("DEP-H1")
            else "ROW_EVENT_FUSION"
            if dependency_id.startswith("DEP-FUSION")
            else "EVENT_FIELD_MAPPING"
        )
        failure_classes = []
        for frame in (row_matches, event_matches, year_matches):
            if len(frame) and "failure_class" in frame:
                failure_classes.extend(frame.failure_class.astype(str).tolist())
            elif len(frame) and "status" in frame:
                failure_classes.extend(frame.status.astype(str).tolist())
        metrics = []
        if len(row_matches):
            metrics.append("row_evidence_state")
        if len(event_matches):
            metrics.append("event_replay")
        if len(year_matches):
            metrics.append("year_end_name")
        records.append(
            {
                "dependency_id": dependency_id,
                "dependency_type": dep_type,
                "affected_row_count": len(
                    {_key(row) for row in row_matches.to_dict("records")}
                    | {_key(row) for row in year_matches.to_dict("records")}
                ),
                "affected_event_count": int(event_matches.event_id.nunique())
                if len(event_matches)
                else 0,
                "affected_metrics": ";".join(sorted(set(metrics))),
                "root_failure_class": _text(
                    context.get("root_failure_class", ";".join(sorted(set(failure_classes))))
                ),
                "available_local_evidence": _text(context.get("available_local_evidence", "")),
                "requires_network": bool(context.get("requires_network", False)),
                "requires_parser_change": bool(
                    context.get("requires_parser_change", dep_type == "H1_PARSER")
                ),
                "requires_h2_extractor_change": bool(
                    context.get("requires_h2_extractor_change", "H2" in dep_type)
                ),
                "requires_fusion_change": bool(
                    context.get(
                        "requires_fusion_change",
                        dep_type in {"ROW_EVENT_FUSION", "EVENT_FIELD_MAPPING"},
                    )
                ),
                "suggested_next_stage": _text(context.get("suggested_next_stage", "")),
            }
        )
    return pd.DataFrame(records)


def validate_frozen45_summary(summary: Mapping[str, object]) -> None:
    expected = {
        "issuer_correct": 45,
        "year_end_correct": 45,
        "evidence_state_correct": 45,
        "denominator": 45,
        "prior_correct25_denominator": 25,
        "prior_correct25_regressions": 0,
    }
    if any(int(summary.get(key, -1)) != value for key, value in expected.items()):
        raise ValueError("FROZEN45_GATE_FAILED")
