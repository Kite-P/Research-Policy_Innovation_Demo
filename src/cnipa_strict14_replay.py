"""Offline-safe helpers for the frozen 14-row CNIPA H1 replay."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd

from src.cnipa_annual_report_names import validate_pdf_payload
from src.historical_province_sources import SourceBlocked, match_annual_report_title


def _fingerprint(frame: pd.DataFrame) -> str:
    records = (
        frame.fillna("")
        .astype(str)
        .sort_values(list(frame.columns), kind="stable")
        .to_dict("records")
        if len(frame)
        else []
    )
    payload = json.dumps(
        {"columns": list(frame.columns), "records": records},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def strict14_keys(row_ground_truth: pd.DataFrame, evidence_ground_truth: pd.DataFrame):
    required = {"firm_key", "year"}
    if not required.issubset(row_ground_truth) or not required.issubset(evidence_ground_truth):
        raise ValueError("STRICT14_KEY_COLUMNS_MISSING")
    rows = row_ground_truth[["firm_key", "year"]].copy()
    evidence = evidence_ground_truth[["firm_key", "year"]].copy()
    rows["year"] = pd.to_numeric(rows.year, errors="raise").astype(int)
    evidence["year"] = pd.to_numeric(evidence.year, errors="raise").astype(int)
    pairs = list(rows.itertuples(index=False, name=None))
    if len(set(pairs)) != len(pairs):
        raise ValueError("DUPLICATE_STRICT14_KEY")
    if len(pairs) != 14:
        raise ValueError("STRICT14_ROW_COUNT_MISMATCH")
    if set(pairs) != set(evidence.itertuples(index=False, name=None)):
        raise ValueError("STRICT14_EVIDENCE_KEY_SET_MISMATCH")
    return sorted(pairs), _fingerprint(rows)


def build_source_manifest(keys: Iterable[tuple[str, int]], source_frames: Iterable[pd.DataFrame]):
    statuses = pd.concat(list(source_frames), ignore_index=True, sort=False)
    output: list[dict[str, object]] = []
    for firm_key, year in sorted(set((str(key), int(report_year)) for key, report_year in keys)):
        matches = statuses[
            statuses.firm_key.astype(str).eq(firm_key)
            & pd.to_numeric(statuses.year, errors="coerce").eq(year)
        ]
        valid: list[dict[str, object]] = []
        for row in matches.to_dict("records"):
            url = str(row.get("source_url", "") or "").strip()
            title = str(row.get("source_report_title", row.get("title", "")) or "").strip()
            if not url:
                continue
            if re.search(r"/new/(?:hisAnnouncement/query|announcement)", url, re.I):
                raise ValueError("NON_DIRECT_H1_PDF_URL")
            if not re.match(
                r"^https://static\.cninfo\.com\.cn/finalpage/.+\.pdf(?:\?.*)?$", url, re.I
            ):
                raise ValueError("NON_OFFICIAL_H1_SOURCE_URL")
            if match_annual_report_title(title) != year:
                continue
            if str(row.get("source_tier", "H1")).upper() != "H1":
                continue
            if row.get("source_is_official", True) is False:
                continue
            valid.append(
                {
                    **row,
                    "firm_key": firm_key,
                    "year": year,
                    "stock_code": firm_key.split(":")[1],
                    "source_url": url,
                    "source_report_title": title,
                    "source_tier": "H1",
                    "source_is_official": True,
                }
            )
        by_url = {str(item["source_url"]): item for item in valid}
        if len(by_url) != 1:
            raise ValueError(
                "STRICT14_SOURCE_PROVENANCE_MISSING" if not by_url else "AMBIGUOUS_STRICT14_SOURCE"
            )
        output.append(next(iter(by_url.values())))
    if len(output) != len(set((row["firm_key"], row["year"]) for row in output)):
        raise ValueError("DUPLICATE_STRICT14_SOURCE_KEY")
    return output


def find_local_reusable_source(
    record: dict[str, object], local_records: Iterable[dict[str, object]]
):
    for local in local_records:
        if (str(local.get("firm_key")), int(local.get("year", -1))) != (
            str(record.get("firm_key")),
            int(record.get("year", -2)),
        ) or str(local.get("source_url", "")) != str(record.get("source_url", "")):
            continue
        pdf_path, text_path = (
            Path(str(local.get("pdf_path", ""))),
            Path(str(local.get("text_path", ""))),
        )
        if not pdf_path.is_file() or not text_path.is_file():
            continue
        pdf_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        text_hash = hashlib.sha256(text_path.read_bytes()).hexdigest()
        if pdf_hash != str(local.get("pdf_sha256", "")).lower():
            continue
        if text_hash != str(local.get("text_sha256", local.get("local_text_sha256", ""))).lower():
            continue
        if local.get("source_is_official") is not True:
            continue
        return {**local, "pdf_sha256": pdf_hash, "text_sha256": text_hash}
    return None


def validate_h1_document(record: dict[str, object], pdf_bytes: bytes, text: str):
    status = validate_pdf_payload(pdf_bytes)
    if status["failure_reason"]:
        return {"valid": False, "reason": str(status["failure_reason"]), **status}
    title = str(record.get("source_report_title", ""))
    year = int(record["year"])
    title_year = match_annual_report_title(title)
    if title_year != year or re.search(r"摘要|简版|节选", title):
        return {
            "valid": False,
            "reason": "ANNUAL_REPORT_SUMMARY_REJECTED"
            if re.search(r"摘要|简版|节选", title)
            else "REPORT_YEAR_MISMATCH",
            **status,
        }
    body_year = next(
        (
            match_annual_report_title(line.strip())
            for line in text.splitlines()[:100]
            if match_annual_report_title(line.strip()) is not None
        ),
        None,
    )
    if body_year is None:
        return {"valid": False, "reason": "FULL_ANNUAL_REPORT_TITLE_NOT_FOUND", **status}
    if body_year != year:
        return {"valid": False, "reason": "REPORT_YEAR_MISMATCH", **status}
    code = str(
        record.get(
            "stock_code",
            str(record.get("firm_key", "")).split(":")[1]
            if ":" in str(record.get("firm_key", ""))
            else "",
        )
    ).zfill(6)
    compact = re.sub(r"\s+", "", text[:12000])
    code_matches = re.findall(r"(?:股票代码|证券代码|公司代码|A股代码)[:：]?([0-9]{6})", compact)
    if not code_matches or code not in code_matches:
        return {"valid": False, "reason": "WRONG_ISSUER_STOCK_CODE", **status}
    return {"valid": True, "reason": "", **status}


def fetch_h1_sources(
    records: Iterable[dict[str, object]],
    fetcher: Callable[[str], dict[str, object]],
    output_dir: Path,
    *,
    max_gets: int = 14,
    local_records: Iterable[dict[str, object]] = (),
):
    records = list(records)
    if max_gets < 0 or max_gets > 14:
        raise ValueError("H1_GET_CAP_MUST_NOT_EXCEED_14")
    if any(str(row.get("source_tier", "H1")).upper() == "H2" for row in records):
        raise ValueError("H2_NOT_ALLOWED_IN_H1_REPLAY")
    urls = [str(row.get("source_url", "")) for row in records]
    if len(urls) != len(set(urls)):
        raise ValueError("DUPLICATE_H1_URL")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    local_records = list(local_records)
    details, get_count, reused, blocked, stopped = [], 0, 0, 0, ""
    for record in records:
        local = find_local_reusable_source(record, local_records)
        if local:
            reused += 1
            details.append({**record, **local, "retrieval": "LOCAL_REUSE", "valid": True})
            continue
        if get_count >= max_gets:
            stopped = "H1_GET_CAP_REACHED"
            break
        try:
            response = fetcher(str(record["source_url"]))
            get_count += 1
        except SourceBlocked as error:
            get_count += 1
            blocked += 1
            details.append({**record, "retrieval": "NETWORK", "valid": False, "reason": str(error)})
            stopped = "SOURCE_BLOCKED"
            break
        pdf = bytes(response.get("pdf_bytes", b""))
        text = str(response.get("text", ""))
        validation = validate_h1_document(record, pdf, text)
        stem = hashlib.sha256(f"{record['firm_key']}|{record['year']}".encode()).hexdigest()[:24]
        pdf_path, text_path = output_dir / f"{stem}.pdf", output_dir / f"{stem}.txt"
        pdf_path.write_bytes(pdf)
        text_path.write_text(text, encoding="utf-8")
        details.append(
            {
                **record,
                **response,
                **validation,
                "retrieval": "NETWORK",
                "pdf_path": str(pdf_path),
                "text_path": str(text_path),
            }
        )
        if not validation["valid"]:
            stopped = "INVALID_H1_SOURCE"
            break
    return {
        "sources": details,
        "h1_get_count": get_count,
        "local_reused_count": reused,
        "source_block_count": blocked,
        "stopped_reason": stopped,
    }


def build_complete_row_predictions(keys: Iterable[tuple[str, int]], parsed_rows: pd.DataFrame):
    key_frame = pd.DataFrame(
        sorted(set((str(key), int(year)) for key, year in keys)), columns=["firm_key", "year"]
    )
    if parsed_rows.duplicated(["firm_key", "year"]).any():
        raise ValueError("DUPLICATE_ROW_PREDICTION_KEY")
    forbidden = [column for column in parsed_rows if column.startswith("review_")]
    if forbidden:
        parsed_rows = parsed_rows.drop(columns=forbidden)
    merged = key_frame.merge(
        parsed_rows, on=["firm_key", "year"], how="left", validate="one_to_one"
    )
    if "parser_change_flag" not in merged:
        merged["parser_change_flag"] = "UNKNOWN"
    merged["parser_change_flag"] = merged.parser_change_flag.fillna("UNKNOWN")
    return merged


def score_strict_rows(
    predictions: pd.DataFrame, row_ground_truth: pd.DataFrame, evidence_ground_truth: pd.DataFrame
):
    merged = (
        row_ground_truth[["firm_key", "year", "review_legal_name_at_year_end"]]
        .merge(
            evidence_ground_truth[["firm_key", "year", "review_expected_parser_flag"]],
            on=["firm_key", "year"],
            validate="one_to_one",
        )
        .merge(predictions, on=["firm_key", "year"], how="left", validate="one_to_one")
    )
    evidence_ok = (
        merged.parser_change_flag.fillna("UNKNOWN")
        .astype(str)
        .eq(merged.review_expected_parser_flag.astype(str))
    )
    name_ok = (
        merged.parser_legal_name_at_year_end.fillna("")
        .astype(str)
        .str.strip()
        .eq(merged.review_legal_name_at_year_end.fillna("").astype(str).str.strip())
    )
    return {
        "evidence_state_denominator": len(merged),
        "evidence_state_correct": int(evidence_ok.sum()),
        "year_end_denominator": len(merged),
        "year_end_correct": int(name_ok.sum()),
        "unresolved_candidate_count": int(
            merged.parser_legal_name_at_year_end.fillna("").astype(str).str.strip().eq("").sum()
        ),
    }


def build_event_roster(predictions: pd.DataFrame, h2_records: Iterable[dict[str, object]]):

    rows: list[dict[str, object]] = []
    for item in predictions.to_dict("records"):
        if str(item.get("parser_change_flag", "")).upper() != "YES":
            continue
        if not item.get("parser_previous_name") or not item.get("parser_new_name"):
            continue
        rows.append(
            {
                **item,
                "legal_name_previous": item["parser_previous_name"],
                "legal_name_new": item["parser_new_name"],
                "change_effective_date": item.get("parser_effective_date", ""),
                "date_precision": item.get("parser_date_precision", "unknown"),
                "change_evidence_tier": "H1",
                "change_evidence_url": item.get("source_url", ""),
                "source_announcement_id": item.get("source_announcement_id", ""),
            }
        )
    for item in h2_records:
        url = str(item.get("notice_url", ""))
        digest = str(item.get("notice_pdf_sha256", "")).lower()
        if (
            str(item.get("status", "")) != "RESOLVED_H2"
            or not url.startswith("https://")
            or not item.get("announcement_id")
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or int(item.get("notice_pdf_bytes", 0) or 0) <= 0
        ):
            continue
        rows.append(
            {
                "firm_key": item.get("firm_key"),
                "year": item.get("year"),
                "legal_name_previous": item.get("previous_legal_name", ""),
                "legal_name_new": item.get("new_legal_name", ""),
                "change_effective_date": item.get("change_effective_date", ""),
                "date_precision": item.get("date_precision", "unknown"),
                "change_evidence_tier": "H2",
                "change_evidence_url": url,
                "source_announcement_id": item["announcement_id"],
            }
        )
    if not rows:
        return pd.DataFrame(
            columns=[
                "firm_key",
                "year",
                "parser_previous_legal_name",
                "parser_new_legal_name",
                "parser_effective_date",
                "parser_date_precision",
                "evidence_tier",
                "source_url",
                "source_announcement_id",
            ]
        )
    roster = pd.DataFrame(rows).drop_duplicates(
        ["firm_key", "year", "change_evidence_tier"], keep="first"
    )
    return roster.rename(
        columns={
            "legal_name_previous": "parser_previous_legal_name",
            "legal_name_new": "parser_new_legal_name",
            "change_effective_date": "parser_effective_date",
            "date_precision": "parser_date_precision",
            "change_evidence_tier": "evidence_tier",
            "change_evidence_url": "source_url",
        }
    )


def score_events(predicted_events: pd.DataFrame, event_ground_truth: pd.DataFrame):
    denominator = len(event_ground_truth)
    if denominator != 6:
        raise ValueError("FROZEN_EVENT_DENOMINATOR_MUST_BE_SIX")
    pred = predicted_events.copy()
    gt = event_ground_truth.copy()
    if (
        "event_id" in gt
        and "event_id" in pred
        and set(gt.event_id.astype(str)) == set(pred.event_id.astype(str))
    ):
        merged = gt.merge(pred, on="event_id", how="left", suffixes=("_review", "_parser"))
    elif (
        "firm_key" in gt
        and "firm_key" in pred
        and "review_effective_date" in gt
        and "parser_effective_date" in pred
    ):
        gt = gt.copy()
        pred = pred.copy()
        gt["_event_year"] = (
            gt.review_effective_date.fillna("").astype(str).str[:4].replace({"nan": ""})
        )
        pred["_event_year"] = (
            pred.parser_effective_date.fillna("")
            .astype(str)
            .str[:4]
            .replace({"nan": "", "None": ""})
        )
        if "year" in pred:
            fallback_years = (
                pd.to_numeric(pred["year"], errors="coerce")
                .astype("Int64")
                .astype(str)
                .replace("<NA>", "")
            )
            pred.loc[pred._event_year.eq(""), "_event_year"] = fallback_years.loc[
                pred._event_year.eq("")
            ]
        merged = gt.merge(
            pred, on=["firm_key", "_event_year"], how="left", suffixes=("_review", "_parser")
        )
    else:
        join = (
            ["firm_key"]
            if "firm_key" in gt and "firm_key" in pred
            else [col for col in ("firm_key", "year") if col in gt and col in pred]
        )
        merged = gt.merge(
            pred, on=join or ["event_id"], how="left", suffixes=("_review", "_parser")
        )

    def correct(pred_col: str, gt_col: str) -> int:
        pcol = pred_col if pred_col in merged else pred_col + "_parser"
        gcol = gt_col if gt_col in merged else gt_col + "_review"
        if pcol not in merged or gcol not in merged:
            return 0
        return int(
            merged[pcol]
            .fillna("")
            .astype(str)
            .str.strip()
            .eq(merged[gcol].fillna("").astype(str).str.strip())
            .sum()
        )

    old = correct("parser_previous_legal_name", "review_previous_legal_name")
    new = correct("parser_new_legal_name", "review_new_legal_name")
    date = correct("parser_effective_date", "review_effective_date")
    precision = correct("parser_date_precision", "review_date_precision")
    previous_col = (
        "parser_previous_legal_name_parser"
        if "parser_previous_legal_name_parser" in merged
        else "parser_previous_legal_name"
    )
    new_col = (
        "parser_new_legal_name_parser"
        if "parser_new_legal_name_parser" in merged
        else "parser_new_legal_name"
    )
    unresolved = (
        int(merged[[c for c in (previous_col, new_col) if c in merged]].isna().any(axis=1).sum())
        if previous_col in merged and new_col in merged
        else denominator
    )
    return {
        "event_denominator": denominator,
        "event_old_correct": old,
        "event_new_correct": new,
        "event_date_correct": date,
        "event_date_precision_correct": precision,
        "event_old_accuracy": old / denominator,
        "event_new_accuracy": new / denominator,
        "event_date_accuracy": date / denominator,
        "event_date_precision_accuracy": precision / denominator,
        "unresolved_event_count": unresolved,
    }


def verify_ground_truth_fingerprints(
    row_gt: pd.DataFrame,
    event_gt: pd.DataFrame,
    evidence_gt: pd.DataFrame,
    binding: dict[str, object],
):
    observed = {
        "row_ground_truth_fingerprint": _fingerprint(row_gt),
        "event_ground_truth_fingerprint": _fingerprint(event_gt),
        "evidence_state_ground_truth_fingerprint": _fingerprint(evidence_gt),
    }
    for key, value in observed.items():
        if str(binding.get(key, "")).lower() != value.lower():
            raise ValueError("FROZEN_GT_FINGERPRINT_MISMATCH")
    return observed
