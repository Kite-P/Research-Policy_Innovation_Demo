"""Offline Strict-14 failure decomposition using only frozen local G2 evidence."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.cnipa_annual_report_names import (  # noqa: E402
    PARSER_REVISION,
    extract_annual_report_legal_name_evidence,
    extract_company_name_change_announcement,
)
from src.cnipa_strict14_forensics import (  # noqa: E402
    build_event_failure_decomposition,
    build_failure_dependency_graph,
    build_h2_target_forensics,
    build_row_evidence_state_decomposition,
    build_year_end_failure_decomposition,
    classify_notice_record,
    validate_frozen45_summary,
)

G2 = ROOT / "results/cnipa_preflight/strict14_g2_replay_20261001"
V3 = ROOT / "results/cnipa_preflight/strict14_v3_replay_20261001"
LEGAL = ROOT / "results/cnipa_legal_name_recovery"
FULL = ROOT / "results/cnipa_full_gap_diagnosis"
FULL_STATUS = LEGAL / "full_status.csv"
FULL_STATE = LEGAL / "full_run_state.json"
FULL_CACHE = LEGAL / "cache"
FROZEN45 = FULL / "r4c0_20261001/reviewed_h1_regression_corpus.csv"
OUT = ROOT / "results/cnipa_preflight/strict14_g3_forensics_20261001"

GT_HASHES = {
    "pilot_change_row_ground_truth.csv": (
        "81eb18d82611ce7bddf7d9895ed57237026b9b5d97b0dd258dda7d0ba266d342"
    ),
    "pilot_change_event_ground_truth.csv": (
        "e1900a01fff61610e1325623ec59870d9063a14c6925e4075639855745d5e174"
    ),
    "pilot_change_evidence_state_ground_truth.csv": (
        "523b1a31640f29ffe9be9b003e8e44afc514f08e0e028aef2a126817b7a31cf3"
    ),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _cache_snapshot() -> dict[str, object]:
    digest = hashlib.sha256()
    count = size = 0
    for path in sorted(FULL_CACHE.glob("*.json")):
        raw = path.read_bytes()
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(raw).digest())
        count += 1
        size += len(raw)
    return {"sha256": digest.hexdigest(), "file_count": count, "byte_count": size}


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"firm_key": str, "event_id": str}, keep_default_na=False)


def _protected_paths() -> list[Path]:
    paths = [
        G2 / name
        for name in (
            "strict14_h2_needed_manifest.csv",
            "strict14_h2_evidence.csv",
            "h2_request_audit.csv",
            "h2_notice_fetches.csv",
            "h2_guard_audit.json",
            "h2_network_state.json",
            "strict14_h1_only_row_predictions.csv",
            "strict14_fused_row_predictions.csv",
            "strict14_fused_candidate_rows.csv",
            "strict14_fused_event_predictions.csv",
            "strict14_frozen_row_predictions.csv",
            "strict14_g2_summary.json",
            "strict14_h1_reuse_audit.csv",
            "h1_reuse_summary.json",
            "strict14_replay_equivalence_diagnosis.json",
        )
    ]
    paths.extend(LEGAL / name for name in GT_HASHES)
    paths.extend((FULL_STATUS, FULL_STATE, FROZEN45))
    h1_audit = _csv(G2 / "strict14_h1_reuse_audit.csv")
    for record in h1_audit.to_dict("records"):
        paths.extend((Path(record["pdf_path"]), Path(record["text_path"])))
    notice_audit = _csv(G2 / "h2_notice_fetches.csv")
    for record in notice_audit.to_dict("records"):
        text_path = Path(record["text_path"])
        paths.extend((text_path, text_path.with_suffix(".pdf")))
    corpus = _csv(FROZEN45)
    roots = [FULL / "r4b_20260930", FULL / "r4b_20260930/r4b2_20261001"]
    for record in corpus.to_dict("records"):
        relative = Path(record["text_path"])
        candidates = [root / relative for root in roots]
        matches = [
            path for path in candidates if path.is_file() and _sha256(path) == record["text_sha256"]
        ]
        if not matches:
            raise FileNotFoundError(
                f"FROZEN45_INPUT_NOT_FOUND:{record['firm_key']}|{record['year']}"
            )
        paths.append(matches[0])
    unique = sorted({path.resolve() for path in paths})
    missing = [path for path in unique if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "PROTECTED_INPUT_MISSING:" + ",".join(_rel(path) for path in missing)
        )
    return unique


def _snapshot(paths: list[Path]) -> dict[str, str]:
    return {_rel(path): _sha256(path) for path in paths}


def _frozen45_metrics() -> dict[str, int]:
    corpus = _csv(FROZEN45)
    roots = [FULL / "r4b_20260930", FULL / "r4b_20260930/r4b2_20261001"]
    parsed_rows: list[tuple[dict[str, str], dict[str, object]]] = []
    for record in corpus.to_dict("records"):
        relative = Path(record["text_path"])
        text_path = next(
            path
            for root in roots
            if (path := root / relative).is_file() and _sha256(path) == record["text_sha256"]
        )
        parsed = extract_annual_report_legal_name_evidence(
            text_path.read_text(encoding="utf-8"),
            expected_year=int(record["year"]),
            source_report_title="",
            source_report_year=int(record["year"]),
            source_is_official=str(record["source_is_official"]).lower() in {"true", "1"},
            source_is_correct_issuer=str(record["source_is_correct_issuer"]).lower()
            in {"true", "1"},
            source_is_correct_year=str(record["source_is_correct_year"]).lower() in {"true", "1"},
            source_is_full_annual_report=str(record["source_is_full_annual_report"]).lower()
            in {"true", "1"},
        )
        parsed_rows.append((record, parsed))
    issuer = sum(
        row["review_legal_name_at_year_end"] == parsed["legal_name_current_in_report"]
        for row, parsed in parsed_rows
    )
    year_end = sum(
        row["review_legal_name_at_year_end"] == parsed["legal_name_at_year_end"]
        for row, parsed in parsed_rows
    )
    evidence = sum(
        row["review_evidence_state"] == parsed["evidence_status"] for row, parsed in parsed_rows
    )
    prior25 = corpus.loc[
        corpus.issuer_name_correct.astype(str).str.lower().isin({"true", "1"})
        & corpus.year_end_name_correct.astype(str).str.lower().isin({"true", "1"})
        & corpus.evidence_state_correct.astype(str).str.lower().isin({"true", "1"})
    ]
    regressions = 0
    parsed_by_key = {
        (row["firm_key"], int(row["year"])): (row, parsed) for row, parsed in parsed_rows
    }
    for row in prior25.to_dict("records"):
        original, parsed = parsed_by_key[(row["firm_key"], int(row["year"]))]
        if (
            row["review_legal_name_at_year_end"] != parsed["legal_name_current_in_report"]
            or row["review_legal_name_at_year_end"] != parsed["legal_name_at_year_end"]
            or row["review_evidence_state"] != parsed["evidence_status"]
        ):
            regressions += 1
    return {
        "issuer_correct": int(issuer),
        "year_end_correct": int(year_end),
        "evidence_state_correct": int(evidence),
        "denominator": int(len(corpus)),
        "prior_correct25_denominator": int(len(prior25)),
        "prior_correct25_regressions": int(regressions),
    }


def _event_year(record: dict[str, str]) -> str:
    effective = record.get("parser_effective_date", "")
    if re.match(r"^20\d\d", effective):
        return effective[:4]
    if record.get("parser_date_precision") == "year":
        years = re.findall(r"\|(20\d\d)(?:;|$)", record.get("source_report_rows", ""))
        return years[-1] if years else ""
    return ""


def _main() -> int:
    if PARSER_REVISION != "issuer_scope_v3":
        raise RuntimeError(f"PARSER_REVISION_CHANGED:{PARSER_REVISION}")
    allowed_outputs = {
        "notice_forensics.csv",
        "h2_target_forensics.csv",
        "event_failure_decomposition.csv",
        "row_evidence_state_decomposition.csv",
        "year_end_failure_decomposition.csv",
        "strict14_failure_dependency_graph.csv",
        "discovery_cap_audit.csv",
        "input_sha256_manifest.csv",
        "forensics_summary.json",
    }
    if OUT.exists():
        unexpected = {path.name for path in OUT.iterdir()} - allowed_outputs
        if unexpected:
            raise FileExistsError(f"UNEXPECTED_G3_OUTPUT_FILES:{sorted(unexpected)}")
    else:
        OUT.mkdir(parents=True)
    protected = _protected_paths()
    print("G3 stage 1/7: hashing frozen inputs and Full cache", flush=True)
    hashes_before = _snapshot(protected)
    cache_before = _cache_snapshot()
    g2_summary = _json(G2 / "strict14_g2_summary.json")
    for filename, expected in GT_HASHES.items():
        actual = hashes_before[_rel(LEGAL / filename)]
        if actual != expected:
            raise RuntimeError(f"FROZEN_GT_HASH_CHANGED:{filename}:{actual}")
    if g2_summary.get("full_wide_reparse_blocked") is not True:
        raise RuntimeError("FULL_WIDE_REPARSE_BLOCK_G2_ASSERTION_MISSING")

    print("G3 stage 2/7: classifying saved H2 notice text", flush=True)
    target_manifest = _csv(G2 / "strict14_h2_needed_manifest.csv")
    h2_evidence = _csv(G2 / "strict14_h2_evidence.csv")
    notice_fetches = _csv(G2 / "h2_notice_fetches.csv")
    h1_audit = _csv(G2 / "strict14_h1_reuse_audit.csv")
    h1_rows = _csv(G2 / "strict14_h1_only_row_predictions.csv")
    fused_rows = _csv(G2 / "strict14_fused_row_predictions.csv")
    candidates = _csv(G2 / "strict14_fused_candidate_rows.csv")
    events = _csv(G2 / "strict14_fused_event_predictions.csv")
    frozen = _csv(G2 / "strict14_frozen_row_predictions.csv")
    request_audit = _csv(G2 / "h2_request_audit.csv")
    network_state = _json(G2 / "h2_network_state.json")
    guard_audit = _json(G2 / "h2_guard_audit.json")
    row_gt = _csv(LEGAL / "pilot_change_row_ground_truth.csv")
    event_gt = _csv(LEGAL / "pilot_change_event_ground_truth.csv")
    evidence_gt = _csv(LEGAL / "pilot_change_evidence_state_ground_truth.csv")

    for source in h1_audit.to_dict("records"):
        pdf_path = Path(source["pdf_path"])
        text_path = Path(source["text_path"])
        if _sha256(pdf_path) != str(source["pdf_sha256"]).lower():
            raise ValueError(f"H1_REUSED_PDF_HASH_MISMATCH:{source['firm_key']}|{source['year']}")
        if _sha256(text_path) != str(source["text_sha256"]).lower():
            raise ValueError(f"H1_REUSED_TEXT_HASH_MISMATCH:{source['firm_key']}|{source['year']}")

    targets_by_key = {
        (str(row["firm_key"]), int(row["year"])): row for row in target_manifest.to_dict("records")
    }
    notice_records = []
    for record in notice_fetches.to_dict("records"):
        key = (str(record["firm_key"]), int(record["year"]))
        target = targets_by_key[key]
        text_path = Path(record["text_path"])
        pdf_path = text_path.with_suffix(".pdf")
        actual_pdf_bytes = pdf_path.stat().st_size
        actual_pdf_hash = _sha256(pdf_path)
        if actual_pdf_bytes != int(float(record["pdf_bytes"])):
            raise ValueError(f"H2_NOTICE_PDF_SIZE_MISMATCH:{record['attempt']}")
        if actual_pdf_hash != str(record["pdf_sha256"]).lower():
            raise ValueError(f"H2_NOTICE_PDF_HASH_MISMATCH:{record['attempt']}")
        if not pdf_path.read_bytes()[:5].startswith(b"%PDF-"):
            raise ValueError(f"H2_NOTICE_NOT_PDF:{record['attempt']}")
        text = text_path.read_text(encoding="utf-8")
        url = str(record["url"])
        date_match = re.search(r"/finalpage/(20\d\d-\d\d-\d\d)/", url)
        announcement_date = date_match.group(1) if date_match else ""
        extraction = extract_company_name_change_announcement(
            text,
            expected_year=key[1],
            previous_legal_name=str(target["previous_legal_name"]),
            new_legal_name=str(target["new_legal_name"]),
            announcement_date=announcement_date,
        )
        classified = classify_notice_record(target, record, text, extraction)
        classified.update(
            {
                "attempt": record.get("attempt", ""),
                "pdf_bytes": record.get("pdf_bytes", ""),
                "pdf_sha256": record.get("pdf_sha256", ""),
                "text_chars": record.get("text_chars", ""),
                "text_extraction_status": record.get("text_extraction_status", ""),
                "notice_title_excerpt": record.get("text_title_excerpt", ""),
                "production_extractor_status": extraction.get("evidence_status", ""),
                "production_extractor_failure_reason": extraction.get("failure_reason", ""),
                "text_path": _rel(text_path),
                "pdf_path": _rel(pdf_path),
            }
        )
        notice_records.append(classified)
    notice_forensics = pd.DataFrame(notice_records)
    notice_forensics.to_csv(OUT / "notice_forensics.csv", index=False, encoding="utf-8-sig")

    h1_pair_keys = {
        ("SSE:603003:2012-08-17", year): "DEP-H1-SSE-603003-2023" for year in (2022, 2023, 2024)
    }
    h2_forensics = build_h2_target_forensics(
        target_manifest,
        h2_evidence,
        request_audit,
        notice_forensics,
        local_h1_pair_evidence_by_key=h1_pair_keys,
    )
    h2_forensics.to_csv(OUT / "h2_target_forensics.csv", index=False, encoding="utf-8-sig")

    print("G3 stage 3/7: scoring fixed event/row/year-end denominators", flush=True)
    event_decomp = build_event_failure_decomposition(
        events,
        event_gt,
        h2_failure_by_event={"EVT-1c255a5bbf60065dba94": "EXTRACTOR_LAYOUT_GAP"},
        local_h1_event_ids={"EVT-41eba08f39bc4228ddaf"},
        dependency_by_event={
            "EVT-1c255a5bbf60065dba94": "DEP-H2-SSE-600936-2025",
            "EVT-41eba08f39bc4228ddaf": "DEP-H1-SSE-603003-2023",
            "EVT-1daab686492f6b83703b": "DEP-EVENT-SZSE-300237-2025",
        },
    )
    event_decomp.to_csv(OUT / "event_failure_decomposition.csv", index=False, encoding="utf-8-sig")

    mapped_event_ids_by_row: dict[tuple[str, int], list[str]] = {}
    event_year_by_id: dict[str, str] = {}
    event_ids_by_firm: dict[str, list[str]] = {}
    for record in events.to_dict("records"):
        event_id, firm_key = str(record["event_id"]), str(record["firm_key"])
        event_year_by_id[event_id] = _event_year(record)
        event_ids_by_firm.setdefault(firm_key, []).append(event_id)
        for source_row in str(record.get("source_report_rows", "")).split(";"):
            match = re.fullmatch(r"(.+)\|(20\d\d)", source_row.strip())
            if match:
                mapped_event_ids_by_row.setdefault(
                    (match.group(1), int(match.group(2))), []
                ).append(event_id)
    h2_dependencies = {
        ("SSE:600936:2016-08-15", 2024): "DEP-H2-SSE-600936-2025",
        ("SSE:600936:2016-08-15", 2025): "DEP-H2-SSE-600936-2025",
    }
    h1_temporal = {("SSE:603003:2012-08-17", 2022): "DEP-H1-SSE-603003-2023"}
    row_decomp = build_row_evidence_state_decomposition(
        h1_rows,
        fused_rows,
        frozen,
        candidates,
        evidence_gt,
        h2_dependency_by_key=h2_dependencies,
        h1_pair_evidence_by_key=h1_pair_keys,
        event_ids_by_firm=event_ids_by_firm,
        mapped_event_ids_by_row=mapped_event_ids_by_row,
        event_year_by_id=event_year_by_id,
    )
    row_decomp.to_csv(
        OUT / "row_evidence_state_decomposition.csv", index=False, encoding="utf-8-sig"
    )
    year_end = build_year_end_failure_decomposition(
        h1_rows,
        fused_rows,
        row_gt,
        h1_temporal_evidence_by_key=h1_temporal,
        unresolved_h2_by_key=h2_dependencies,
    )
    year_end.to_csv(OUT / "year_end_failure_decomposition.csv", index=False, encoding="utf-8-sig")

    print("G3 stage 4/7: validating negative control, dependency graph and frozen45", flush=True)
    negative_rows = row_decomp.loc[row_decomp.firm_key.str.contains(":300365:")]
    negative_h1 = h1_rows.loc[h1_rows.firm_key.str.contains(":300365:")]
    negative_frozen = frozen.loc[frozen.firm_key.str.contains(":300365:")]
    negative_events = [
        record
        for record in events.to_dict("records")
        if ":300365:" in str(record.get("firm_key", ""))
        or any(
            ":300365:" in token for token in str(record.get("source_report_rows", "")).split(";")
        )
    ]
    if len(negative_rows) != 2 or set(negative_h1.parser_change_flag) != {"UNKNOWN"}:
        raise ValueError("300365_NEGATIVE_CONTROL_H1_FLAG_FAILED")
    if len(negative_events) or negative_rows.mapped_event.any():
        raise ValueError("300365_NEGATIVE_CONTROL_EVENT_MAPPING_FAILED")
    row_lookup = {
        (str(row.firm_key), int(row.year)): row for row in negative_frozen.itertuples(index=False)
    }
    for record in negative_rows.to_dict("records"):
        frozen_row = row_lookup[(record["firm_key"], int(record["year"]))]
        if record["fused_flag"] != "UNKNOWN" or not record["fused_correct"]:
            raise ValueError("300365_ABSENCE_BECAME_NO_OR_NEGATIVE_CONTROL_FAILED")
        if not str(frozen_row.parser_legal_name_at_year_end).strip():
            raise ValueError("300365_YEAR_END_NAME_MISSING")
    row_gt_by_key = {
        (str(row.firm_key), int(row.year)): row for row in row_gt.itertuples(index=False)
    }
    negative_year_end_matches = all(
        str(row_lookup[(record["firm_key"], int(record["year"]))].parser_legal_name_at_year_end)
        == str(
            row_gt_by_key[(record["firm_key"], int(record["year"]))].review_legal_name_at_year_end
        )
        for record in negative_rows.to_dict("records")
    )
    if not negative_year_end_matches:
        raise ValueError("300365_YEAR_END_NEGATIVE_CONTROL_FAILED")

    h1_2021 = h1_audit.loc[
        h1_audit.firm_key.eq("SZSE:300365:2014-01-23")
        & pd.to_numeric(h1_audit.year, errors="coerce").eq(2021)
    ].iloc[0]
    nc_txt = Path(h1_2021.text_path).read_text(encoding="utf-8")
    branch_glossary_present = "成都分公司" in nc_txt and "释义" in nc_txt
    issuer_name_2021 = str(
        negative_frozen.loc[
            pd.to_numeric(negative_frozen.year, errors="coerce").eq(2021),
            "parser_legal_name_at_year_end",
        ].iloc[0]
    )
    if not branch_glossary_present or issuer_name_2021 != "北京恒华伟业科技股份有限公司":
        raise ValueError("300365_BRANCH_GLOSSARY_SCOPE_NEGATIVE_CONTROL_FAILED")

    dep_context = {
        "DEP-H2-SSE-600936-2025": {
            "root_failure_class": "H2_EXTRACTOR_LAYOUT_GAP",
            "available_local_evidence": (
                "3 official notices; completed notice text contains issuer code, expected old/new "
                "names and year-end registration completion; all 3 returned PDFs inspected"
            ),
            "requires_network": False,
            "requires_h2_extractor_change": True,
            "suggested_next_stage": "H2_EXTRACTOR_REPAIR",
        },
        "DEP-H1-SSE-603003-2023": {
            "root_failure_class": "H1_EVENT_AND_YEAR_END_PARSER_ERROR",
            "available_local_evidence": (
                "2022 H1 report text explicitly dates legal-name change to 2023-01-05; current "
                "v3 replay misses the event and assigns the new name to 2022 year-end"
            ),
            "requires_network": False,
            "requires_parser_change": True,
            "suggested_next_stage": "H1_PARSER_RESIDUAL_FIX",
        },
        "DEP-FUSION-NO-PROPAGATION": {
            "root_failure_class": "FUSION_EVENT_TO_ROW_FLAG_PROPAGATION_GAP",
            "available_local_evidence": (
                "3 affected rows appear in event source_report_rows but frozen row predictions "
                "have blank proposed_event_id; canonical_rows were not passed into the builder"
            ),
            "requires_network": False,
            "requires_fusion_change": True,
            "suggested_next_stage": "ROW_EVENT_FUSION_OR_MAPPING_FIX",
        },
        "DEP-EVENT-SZSE-300237-2025": {
            "root_failure_class": "EVENT_YEAR_PRECISION_NOT_NORMALIZED_TO_EFFECTIVE_YEAR",
            "available_local_evidence": (
                "H2 event exists with year precision and source row year 2025, but "
                "parser_effective_date is blank while the fixed event slot scores year 2025"
            ),
            "requires_network": False,
            "requires_fusion_change": True,
            "suggested_next_stage": "EVENT_DATE_NORMALIZATION_FIX",
        },
    }
    graph = build_failure_dependency_graph(
        row_decomp,
        event_decomp,
        year_end,
        dependency_context=dep_context,
    )
    graph.to_csv(OUT / "strict14_failure_dependency_graph.csv", index=False, encoding="utf-8-sig")
    frozen45 = _frozen45_metrics()
    validate_frozen45_summary(frozen45)

    print("G3 stage 5/7: checking frozen Gate, pagination evidence and Full safety", flush=True)
    request_count = int(len(network_state.get("attempts", [])))
    h1_requests = int(g2_summary.get("network_h1_requests", -1))
    g2_h2_requests = int(g2_summary.get("network_h2_requests", -1))
    if h1_requests != 0 or g2_h2_requests != request_count:
        raise ValueError("G2_NETWORK_AUDIT_SUMMARY_MISMATCH")
    fetched_by_key = {
        key: group for key, group in notice_forensics.groupby(["firm_key", "year"], dropna=False)
    }
    discovery_rows = []
    for record in network_state.get("h2_records", []):
        key = (str(record["firm_key"]), int(record["year"]))
        query_rows = request_audit.loc[
            request_audit.firm_key.eq(key[0])
            & pd.to_numeric(request_audit.year, errors="coerce").eq(key[1])
            & request_audit.purpose.eq("targeted_name_change_discovery")
        ]
        returned = int(float(record.get("discovery_notice_count", 0) or 0))
        fetched = len(fetched_by_key.get(key, []))
        returned_lower_bound = max(returned, fetched)
        possible_cap = returned > 3 and fetched == 3
        if returned == 0 and fetched:
            finding = (
                f"G2 did not record result count; at least {fetched} returned record(s) "
                "are confirmed by fetched PDFs"
            )
        elif returned > fetched:
            finding = "returned candidates exceed saved PDFs; review required"
        else:
            finding = (
                "all count-recorded returned candidates fetched; no evidence count exceeded cap"
            )
        discovery_rows.append(
            {
                "firm_key": key[0],
                "year": key[1],
                "discovery_attempt_count": len(query_rows),
                "request_pages_logged": ";".join(query_rows.page.astype(str).tolist()),
                "returned_notice_count": returned,
                "returned_notice_count_lower_bound": returned_lower_bound,
                "count_precision": "EXACT_FROM_G2_NETWORK_STATE"
                if returned
                else ("LOWER_BOUND_FROM_FETCHED_NOTICES" if fetched else "ZERO_RECORDED"),
                "fetched_pdf_count": fetched,
                "returned_over_three_pdf_cap": bool(possible_cap),
                "cap_truncation_confirmed": bool(possible_cap),
                "pagination_completeness": "NOT_RECORDED_IN_G2_AUDIT"
                if len(query_rows)
                else "NOT_APPLICABLE",
                "ordering_or_title_filter_risk": "CANNOT_EXCLUDE_BEYOND_LOGGED_RESULT_SET"
                if len(query_rows)
                else "NO_DISCOVERY",
                "finding": finding,
            }
        )
    discovery_df = pd.DataFrame(discovery_rows)
    discovery_df.to_csv(OUT / "discovery_cap_audit.csv", index=False, encoding="utf-8-sig")

    full_current = {
        "full_status_sha256": _sha256(FULL_STATUS),
        "full_run_state_sha256": _sha256(FULL_STATE),
        "full_cache": cache_before,
    }
    g2_full_matches = (
        full_current["full_status_sha256"] == g2_summary["full_status_sha256"]
        and full_current["full_run_state_sha256"] == g2_summary["full_run_state_sha256"]
        and full_current["full_cache"]["sha256"] == g2_summary["full_cache_sha256"]
    )
    baseline_path = FULL / "baseline_summary.json"
    if baseline_path.is_file():
        baseline = _json(baseline_path)
        baseline_hashes = baseline.get(
            "protected_file_sha256_before", baseline.get("protected_files_sha256", {})
        )
        status_baseline = next(
            (v for k, v in baseline_hashes.items() if str(k).endswith("full_status.csv")), None
        )
        state_baseline = next(
            (v for k, v in baseline_hashes.items() if str(k).endswith("full_run_state.json")), None
        )
        full_current["matches_full_gap_baseline"] = bool(
            (status_baseline is None or status_baseline == full_current["full_status_sha256"])
            and (state_baseline is None or state_baseline == full_current["full_run_state_sha256"])
        )
    else:
        full_current["matches_full_gap_baseline"] = None
    if not g2_full_matches:
        raise ValueError("FULL_PROTECTED_STATE_DIFFERS_FROM_G2")

    h1_source_603003 = Path(
        h1_audit.loc[
            h1_audit.firm_key.eq("SSE:603003:2012-08-17")
            & pd.to_numeric(h1_audit.year, errors="coerce").eq(2022),
            "text_path",
        ].iloc[0]
    ).read_text(encoding="utf-8")
    compact_h1 = re.sub(r"\s+", "", h1_source_603003)
    h1_line_match = re.search(
        r".{0,80}2023年1月5日.{0,80}上海龙宇燃油股份有限公司.{0,80}上海龙宇数据股份有限公司.{0,30}",
        compact_h1,
    )
    if not h1_line_match:
        raise ValueError("603003_LOCAL_H1_EVENT_EVIDENCE_NOT_RECONFIRMED")
    h1_excerpt = h1_line_match.group(0)
    h2_forensics["h2_source_h1_local_pair"] = h2_forensics.apply(
        lambda row: (
            "LOCAL_H1_EXPLICIT_EVENT"
            if (row.firm_key, int(row.year)) == ("SSE:603003:2012-08-17", 2023)
            else ""
        ),
        axis=1,
    )
    h2_forensics.to_csv(OUT / "h2_target_forensics.csv", index=False, encoding="utf-8-sig")

    print("G3 stage 6/7: verifying all frozen input hashes unchanged", flush=True)
    hashes_after = _snapshot(protected)
    cache_after = _cache_snapshot()
    if hashes_before != hashes_after or cache_before != cache_after:
        raise ValueError("PROTECTED_INPUT_MUTATED_DURING_G3")
    pd.DataFrame(
        [
            {
                "path": path,
                "sha256_before": hashes_before[path],
                "sha256_after": hashes_after[path],
                "unchanged": hashes_before[path] == hashes_after[path],
            }
            for path in sorted(hashes_before)
        ]
    ).to_csv(OUT / "input_sha256_manifest.csv", index=False, encoding="utf-8-sig")

    print("G3 stage 7/7: writing aggregate summary", flush=True)
    h2_counts = h2_forensics.terminal_failure_class.value_counts().to_dict()
    event_counts = event_decomp.status.value_counts().to_dict()
    row_mismatches = row_decomp.loc[~row_decomp.fused_correct]
    row_failures = row_mismatches.failure_class.value_counts().to_dict()
    pdf_pairs = int(notice_forensics.expected_pair_text_present.sum())
    summary = {
        "diagnostic_status": "STRICT14_G3_OFFLINE_FORENSICS_COMPLETE",
        "parser_revision": PARSER_REVISION,
        "network_requests_g3": 0,
        "network_requests_g2_historical": request_count,
        "h1_requests_g2_historical": h1_requests,
        "h2_requests_g2_historical": g2_h2_requests,
        "patent_system_accessed_g3": False,
        "h2_targets_total": len(h2_forensics),
        "h2_targets_resolved": int(h2_forensics.resolved_h2.sum()),
        "h2_targets_unresolved": int((~h2_forensics.resolved_h2).sum()),
        "h2_terminal_classes": h2_counts,
        "fetched_notice_pdfs": len(notice_forensics),
        "notices_containing_expected_old_new_pair": pdf_pairs,
        "notices_not_containing_expected_old_new_pair": int(len(notice_forensics) - pdf_pairs),
        "notices_supporting_completed_effective_event": int(
            (
                notice_forensics.expected_pair_text_present
                & notice_forensics.completion_semantics_present
                & notice_forensics.effective_date_in_target_year
            ).sum()
        ),
        "notices_with_pair_but_no_completed_event_support": int(
            (
                notice_forensics.expected_pair_text_present
                & ~(
                    notice_forensics.completion_semantics_present
                    & notice_forensics.effective_date_in_target_year
                )
            ).sum()
        ),
        "extractor_layout_gaps": int(
            notice_forensics.terminal_failure_class.eq("EXTRACTOR_LAYOUT_GAP").sum()
        ),
        "discovery_result_sets_potentially_truncated_by_3_pdf_cap": int(
            discovery_df.returned_over_three_pdf_cap.sum()
        ),
        "discovery_cap_audit_inconclusive_sets": int(
            discovery_df.pagination_completeness.eq("NOT_RECORDED_IN_G2_AUDIT").sum()
        ),
        "event_total": len(event_decomp),
        "event_status_counts": event_counts,
        "unresolved_event_count": int((~event_decomp.status.eq("EVENT_CORRECT")).sum()),
        "unresolved_event_explanation": (
            "one H2 event lacks extraction although completed notice text supports it; one H1 "
            "event is explicit in reused report text but missing from v3 event extraction; one "
            "year-precision event lacks a normalized effective-date year"
        ),
        "row_denominator": len(row_decomp),
        "fused_correct_rows": int(row_decomp.fused_correct.sum()),
        "fused_mismatched_rows": len(row_mismatches),
        "row_failure_class_counts": row_failures,
        "independent_failure_dependency_count": int(graph.dependency_id.nunique()),
        "h1_flag_errors": int(row_decomp.failure_class.eq("H1_EXPLICIT_FLAG_ERROR").sum()),
        "year_end_mismatch_rows": len(year_end),
        "year_end_failure_class_counts": year_end.failure_class.value_counts().to_dict(),
        "negative_control_300365_pass": True,
        "negative_control_300365": {
            "h1_2020": "UNKNOWN",
            "h1_2021": "UNKNOWN",
            "year_end_names_match_frozen_review": bool(negative_year_end_matches),
            "event_mapping": False,
            "branch_glossary_present_but_not_issuer": True,
            "no_absence_to_no_inference": True,
        },
        "dependency_graph": graph.to_dict("records"),
        "next_stage_recommendation": [
            "H2_EXTRACTOR_REPAIR",
            "H1_PARSER_RESIDUAL_FIX",
            "ROW_EVENT_FUSION_OR_MAPPING_FIX",
            "EVENT_DATE_NORMALIZATION_FIX",
        ],
        "frozen45": frozen45,
        "current_gate_status": g2_summary["strict_gate_status"],
        "h1_parser_repair_status": "H1_PARSER_REPAIR_NEEDS_FIX",
        "h1_parser_repair_reason": "current_v3_residual_h1_error+pending_canonical_replay_evidence",
        "full_wide_reparse_blocked": g2_summary["full_wide_reparse_blocked"],
        "full_data_changed": not g2_full_matches,
        "full_current_integrity": full_current,
        "gt_unchanged": hashes_before == hashes_after
        and all(hashes_before[_rel(LEGAL / name)] == value for name, value in GT_HASHES.items()),
        "g2_scope_rejection_was_not_sent": bool(guard_audit.get("rejected"))
        and len(guard_audit.get("rejected", [])) == 1,
        "g2_discovery_attempts": int(
            (request_audit.purpose == "targeted_name_change_discovery").sum()
        ),
        "g2_notice_pdf_attempts": int((request_audit.purpose == "targeted_notice_pdf").sum()),
        "h1_603003_2022_local_evidence_excerpt": h1_excerpt,
        "g2_summary_gate_remains_incomplete": g2_summary["strict_gate_status"]
        == "STRICT_PILOT_GATE_REPLAY_INCOMPLETE",
        "full_cache_before": cache_before,
        "full_cache_after": cache_after,
        "protected_inputs_unchanged": hashes_before == hashes_after,
        "protected_input_count": len(hashes_before),
    }
    if not summary["gt_unchanged"] or not summary["g2_summary_gate_remains_incomplete"]:
        raise ValueError("FROZEN_GATE_OR_GT_INTEGRITY_FAILURE")
    (OUT / "forensics_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
