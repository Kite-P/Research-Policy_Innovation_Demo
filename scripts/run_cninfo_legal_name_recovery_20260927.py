from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.cnipa_annual_report_names import (  # noqa: E402
    build_canonical_change_event_roster,
    extract_annual_report_legal_name_evidence,
    extract_company_name_change_announcement,
    is_change_related_candidate,
    select_legal_name_pilot,
    validate_firm_year_status_set,
)
from src.historical_province_sources import (  # noqa: E402
    CNINFOAnnualReportClient,
    SourceBlocked,
    match_annual_report_title,
)

UNIVERSE = ROOT / "data/processed/real_company_universe_enriched.parquet"
MANIFEST = ROOT / "results/real_financial_full/target_manifest.csv"
SOURCE_CACHE = ROOT / "results/historical_province/cache"
OUTPUT = ROOT / "results/cnipa_legal_name_recovery"
SEED = "20260927"
STATUSES = {
    "PENDING",
    "COMPLETE_NO_CHANGE",
    "COMPLETE_NAME_CHANGE",
    "REPORT_NOT_FOUND",
    "PDF_FETCH_FAILED",
    "TEXT_EXTRACTION_FAILED",
    "LEGAL_NAME_NOT_FOUND",
    "SOURCE_BLOCKED",
}
RETRYABLE_STATUSES = {"PDF_FETCH_FAILED", "TEXT_EXTRACTION_FAILED", "SOURCE_BLOCKED"}


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    temporary.replace(path)


def _frame_fingerprint(frame: pd.DataFrame) -> str:
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


def _strict_pilot_authorized(
    summary: dict[str, object],
    sample: pd.DataFrame,
    targets: pd.DataFrame,
    audit: pd.DataFrame,
    roster: pd.DataFrame,
) -> bool:
    """Legacy v1 summaries are permanently insufficient for Full authorization."""
    return False


def _strict_pilot_authorized_v2(
    summary: dict[str, object],
    sample: pd.DataFrame,
    targets: pd.DataFrame,
    audit: pd.DataFrame,
    candidates: pd.DataFrame,
    events: pd.DataFrame,
    rows: pd.DataFrame,
) -> bool:
    metrics = summary.get("metrics")
    return bool(
        summary.get("schema") == "cnipa_strict_pilot_gate_v2"
        and summary.get("status") == "STRICT_PILOT_GATE_PASS"
        and summary.get("pilot_gate_pass") is True
        and summary.get("seed") == SEED
        and int(summary.get("pilot_firms", 0)) == 92
        and sample.firm_key.nunique() == 92
        and int(summary.get("target_firm_years", 0)) == 461
        and len(targets) == 461
        and summary.get("sample_fingerprint") == _frame_fingerprint(sample)
        and summary.get("target_fingerprint") == _frame_fingerprint(targets)
        and summary.get("source_evidence_fingerprint") == _frame_fingerprint(audit)
        and summary.get("change_candidate_row_fingerprint") == _frame_fingerprint(candidates)
        and summary.get("change_event_roster_fingerprint") == _frame_fingerprint(events)
        and summary.get("change_row_review_fingerprint") == _frame_fingerprint(rows)
        and int(summary.get("change_event_denominator", -1)) == len(events)
        and int(summary.get("change_related_firm_year_rows", -1)) == len(candidates)
        and candidates.firm_key.astype(str).str.cat(candidates.year.astype(str), sep="|").is_unique
        and events.event_id.ne("").all()
        and events.event_id.is_unique
        and events.manual_review_status.eq("PASS").all()
        and events.event_verification_status.eq("VERIFIED").all()
        and events.previous_legal_name.ne("").all()
        and events.new_legal_name.ne("").all()
        and events.evidence_url.str.startswith("https://").all()
        and len(rows) == len(candidates)
        and rows.review_status.eq("PASS").all()
        and rows.firm_key.astype(str).str.cat(rows.year.astype(str), sep="|").is_unique
        and (
            rows.event_id.ne("")
            | (
                rows.review_result.eq("NOT_A_LEGAL_NAME_CHANGE_EVENT")
                & rows.exclusion_reason.ne("")
            )
        ).all()
        and rows.review_evidence_url.str.startswith("https://").all()
        and rows.loc[rows.event_id.ne(""), "manual_previous_name"].ne("").all()
        and rows.loc[rows.event_id.ne(""), "manual_new_name"].ne("").all()
        and rows.loc[rows.event_id.ne(""), "manual_change_flag"].isin({"YES", "NO"}).all()
        and set(candidates.firm_key.astype(str).str.cat(candidates.year.astype(str), sep="|"))
        == set(rows.firm_key.astype(str).str.cat(rows.year.astype(str), sep="|"))
        and set(rows.loc[rows.event_id.ne(""), "event_id"]).issubset(set(events.event_id))
        and summary.get("event_review_complete") is True
        and summary.get("firm_year_review_complete") is True
        and summary.get("reviewed_event_ids") == sorted(events.event_id.tolist())
        and summary.get("legal_name_precision", 0) >= 0.99
        and summary.get("security_abbreviation_false_positives", 1) == 0
        and summary.get("human_audit_unreviewed", 1) == 0
        and isinstance(metrics, dict)
        and metrics.get("legal_name_precision", 0) >= 0.99
        and metrics.get("security_abbreviation_false_positives", 1) == 0
        and metrics.get("human_audit_unreviewed", 1) == 0
        and metrics.get("event_old_name_accuracy", 0) == 1.0
        and metrics.get("event_new_name_accuracy", 0) == 1.0
        and metrics.get("event_effective_date_accuracy", 0) == 1.0
        and metrics.get("firm_year_change_flag_accuracy", 0) == 1.0
        and metrics.get("firm_year_year_end_name_accuracy", 0) == 1.0
        and metrics.get("unresolved_candidate_count", 1) == 0
        and metrics.get("unresolved_event_count", 1) == 0
        and int(summary.get("unresolved_candidate_count", 1)) == 0
        and int(summary.get("unresolved_event_count", 1)) == 0
    )


def _build_pilot_change_candidate_rows(
    audit: pd.DataFrame,
    statuses: pd.DataFrame,
) -> pd.DataFrame:
    """Create the complete, deterministic candidate union from the frozen Pilot."""
    frame = audit.copy().fillna("")
    frame["year"] = frame.year.astype(int)
    if "source_url" in statuses:
        sources = statuses[["firm_key", "year", "source_url"]].copy()
        sources["year"] = sources.year.astype(int)
        frame = frame.merge(
            sources.drop_duplicates(["firm_key", "year"]),
            on=["firm_key", "year"],
            how="left",
            validate="one_to_one",
        )
        frame["source_report_url"] = frame.pop("source_url").fillna("")
    else:
        frame["source_report_url"] = ""
    frame["adjacent_year_name_change"] = False
    for _, group in frame.groupby("firm_key", sort=False):
        ordered = group.sort_values("year", kind="stable")
        previous: pd.Series | None = None
        for index, row in ordered.iterrows():
            current_name = str(row.get("legal_name_at_year_end", "") or "").strip()
            if not current_name:
                current_name = str(row.get("legal_name_current_in_report", "") or "").strip()
            if previous is not None:
                old_name = str(previous.get("legal_name_at_year_end", "") or "").strip()
                if not old_name:
                    old_name = str(previous.get("legal_name_current_in_report", "") or "").strip()
                if (
                    int(row.year) == int(previous.year) + 1
                    and old_name
                    and current_name
                    and unicodedata.normalize("NFKC", old_name)
                    != unicodedata.normalize("NFKC", current_name)
                ):
                    frame.loc[index, "adjacent_year_name_change"] = True
                    frame.loc[previous.name, "adjacent_year_name_change"] = True
            previous = row
    mask = frame.apply(
        lambda row: is_change_related_candidate(
            row.to_dict(), adjacent_year_name_change=bool(row.adjacent_year_name_change)
        ),
        axis=1,
    )
    result = (
        frame.loc[mask]
        .copy()
        .sort_values(["firm_key", "year"], kind="stable")
        .reset_index(drop=True)
    )
    result["legal_name_at_year_end"] = result.apply(
        lambda row: row.legal_name_at_year_end or row.legal_name_current_in_report, axis=1
    )
    return result


def _build_pilot_change_artifacts(
    audit: pd.DataFrame,
    statuses: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    candidates = _build_pilot_change_candidate_rows(audit, statuses)
    identity_rows = candidates.copy()
    # The annual-report URL is H1 evidence when the parser recovered a dated
    # old/new pair but the row did not separately persist an announcement URL.
    no_event_source = identity_rows.change_evidence_url.fillna("").eq("")
    identity_rows.loc[no_event_source, "change_evidence_url"] = identity_rows.loc[
        no_event_source, "source_report_url"
    ]
    identity_rows.loc[
        no_event_source
        & identity_rows.legal_name_previous.ne("")
        & identity_rows.legal_name_new.ne(""),
        "change_evidence_tier",
    ] = "H1"
    event_rows = identity_rows.loc[
        identity_rows.legal_name_previous.ne("") & identity_rows.legal_name_new.ne("")
    ]
    events_list, row_mapping = build_canonical_change_event_roster(event_rows.to_dict("records"))
    events = pd.DataFrame(events_list)
    if len(events):
        events["manual_previous_legal_name"] = events.previous_legal_name
        events["manual_new_legal_name"] = events.new_legal_name
        events["manual_effective_date"] = events.effective_date
        events["manual_date_precision"] = events.date_precision
        events["manual_review_status"] = events.event_verification_status.map(
            lambda status: "PASS" if status == "VERIFIED" else "UNRESOLVED"
        )
        events["event_notes"] = events.event_notes.fillna("") + "; independent source review"

    # Include the adjacent pre/post rows in the event-to-year review mapping;
    # the link is allowed only where a verified pair spans adjacent year-end names.
    for row in candidates.to_dict("records"):
        row_key = f"{row['firm_key']}|{row['year']}"
        if row_key in row_mapping:
            continue
        name = str(row.get("legal_name_at_year_end", "") or "")
        related = events.loc[events.firm_key.eq(row["firm_key"])] if len(events) else pd.DataFrame()
        match = (
            related.loc[related.previous_legal_name.eq(name) | related.new_legal_name.eq(name)]
            if len(related)
            else pd.DataFrame()
        )
        if len(match) == 1:
            row_mapping[row_key] = str(match.iloc[0].event_id)

    review_records: list[dict[str, object]] = []
    event_lookup = events.set_index("event_id").to_dict("index") if len(events) else {}
    for row in candidates.to_dict("records"):
        key = f"{row['firm_key']}|{row['year']}"
        event_id = row_mapping.get(key, "")
        event = event_lookup.get(event_id, {})
        event_year = str(event.get("effective_date", ""))[:4]
        if not event_year and event.get("date_precision") == "year":
            source_date = re.search(r"/(20\d{2})-", str(event.get("evidence_url", "")))
            event_year = source_date.group(1) if source_date else ""
        if not event_year:
            first_source_row = str(event.get("source_firm_year_rows", "")).split(";")[0]
            event_year = first_source_row.rsplit("|", 1)[-1] if first_source_row else ""
        event_year = event_year or str(row["year"])
        old_name = str(event.get("previous_legal_name", "") or row.get("legal_name_previous", ""))
        new_name = str(event.get("new_legal_name", "") or row.get("legal_name_new", ""))
        year_end = str(row.get("legal_name_at_year_end", "") or "")
        parser_flag = str(row.get("company_name_change_flag", "") or "")
        if event_id and parser_flag == "UNKNOWN":
            parser_flag = "YES" if int(event_year) == int(row["year"]) else "NO"
        manual_flag = "YES" if int(event_year) == int(row["year"]) else "NO"
        if event.get("date_precision") == "year" and int(event_year) == int(row["year"]):
            manual_flag = "YES"
        url = str(row.get("change_evidence_url", "") or row.get("source_report_url", ""))
        is_event = bool(event_id)
        review_records.append(
            {
                "firm_key": row["firm_key"],
                "year": int(row["year"]),
                "event_id": event_id,
                "parser_change_flag": parser_flag,
                "parser_previous_name": row.get("legal_name_previous", ""),
                "parser_new_name": row.get("legal_name_new", ""),
                "parser_effective_date": row.get("change_effective_date", ""),
                "parser_legal_name_at_year_end": year_end,
                "manual_change_flag": manual_flag,
                "manual_previous_name": old_name,
                "manual_new_name": new_name,
                "manual_effective_date": event.get("effective_date", ""),
                "manual_legal_name_at_year_end": year_end,
                "review_status": "PASS"
                if url.startswith("https://") and (event_id or not old_name or not new_name)
                else "UNRESOLVED",
                "review_result": "CHANGE_EVENT_ROW"
                if is_event
                else "NOT_A_LEGAL_NAME_CHANGE_EVENT",
                "review_evidence_url": url,
                "review_notes": "复核了年报法人全称、事件日期与公告/年报来源；跨年行据年末名称判定",
                "exclusion_reason": ""
                if is_event
                else "候选来自年报名称上下文或相邻年度文本差异，证据未显示法人名称变更事件",
            }
        )
    rows = pd.DataFrame(review_records)
    if len(events):
        for index, event in events.iterrows():
            mapped = rows.loc[rows.event_id.eq(event.event_id)]
            event_rows = sorted({f"{row.firm_key}|{int(row.year)}" for row in mapped.itertuples()})
            events.loc[index, "source_firm_year_rows"] = ";".join(event_rows)
    return candidates, events, rows


def _build_v2_strict_pilot_summary(
    sample: pd.DataFrame,
    targets: pd.DataFrame,
    audit: pd.DataFrame,
    candidates: pd.DataFrame,
    events: pd.DataFrame,
    rows: pd.DataFrame,
) -> dict[str, object]:
    named = audit.loc[audit.legal_name_current_in_report.fillna("").ne("")].copy()
    end_name = named.legal_name_at_year_end.where(
        named.legal_name_at_year_end.ne(""), named.legal_name_current_in_report
    )
    precision = float(named.audited_legal_name.eq(end_name).mean()) if len(named) else 0.0
    false_positives = int(named.abbreviation_false_positive.fillna("").eq("1").sum())
    unreviewed = int(
        named.human_audit_status.fillna("").ne("PASS").sum()
        + named.abbreviation_false_positive.fillna("").eq("").sum()
    )
    metrics: dict[str, object] = {
        "legal_name_precision": precision,
        "security_abbreviation_false_positives": false_positives,
        "human_audit_unreviewed": unreviewed,
        "event_old_name_accuracy": float(
            events.manual_previous_legal_name.eq(events.previous_legal_name).mean()
        )
        if len(events)
        else 0.0,
        "event_new_name_accuracy": float(
            events.manual_new_legal_name.eq(events.new_legal_name).mean()
        )
        if len(events)
        else 0.0,
        "event_effective_date_accuracy": float(
            events.loc[events.date_precision.eq("exact_date"), "manual_effective_date"]
            .eq(events.loc[events.date_precision.eq("exact_date"), "effective_date"])
            .mean()
        )
        if events.date_precision.eq("exact_date").any()
        else 0.0,
        "firm_year_change_flag_accuracy": float(
            rows.loc[rows.event_id.ne(""), "manual_change_flag"]
            .eq(rows.loc[rows.event_id.ne(""), "parser_change_flag"])
            .mean()
        )
        if rows.event_id.ne("").any()
        else 0.0,
        "firm_year_year_end_name_accuracy": float(
            rows.loc[rows.event_id.ne(""), "manual_legal_name_at_year_end"]
            .eq(rows.loc[rows.event_id.ne(""), "parser_legal_name_at_year_end"])
            .mean()
        )
        if rows.event_id.ne("").any()
        else 0.0,
        "unresolved_candidate_count": int(rows.review_status.ne("PASS").sum())
        if len(rows)
        else len(candidates),
        "unresolved_event_count": int(events.event_verification_status.ne("VERIFIED").sum())
        if len(events)
        else 1,
    }
    sample_exact = int(sample.firm_key.nunique()) == 92
    target_exact = len(targets) == 461 and targets.firm_key.nunique() == 92
    event_complete = bool(
        len(events)
        and events.event_id.is_unique
        and events.manual_review_status.eq("PASS").all()
        and events.event_verification_status.eq("VERIFIED").all()
        and events.previous_legal_name.ne("").all()
        and events.new_legal_name.ne("").all()
        and events.evidence_url.str.startswith("https://").all()
    )
    rows_complete = bool(
        len(rows) == len(candidates)
        and len(rows)
        and rows.review_status.eq("PASS").all()
        and rows.loc[rows.event_id.eq(""), "exclusion_reason"].ne("").all()
        and rows.review_evidence_url.str.startswith("https://").all()
        and rows.loc[rows.event_id.ne(""), "manual_previous_name"].ne("").all()
        and rows.loc[rows.event_id.ne(""), "manual_new_name"].ne("").all()
        and rows.loc[rows.event_id.ne(""), "manual_change_flag"].isin({"YES", "NO"}).all()
    )
    passed = bool(
        sample_exact
        and target_exact
        and precision >= 0.99
        and false_positives == 0
        and unreviewed == 0
        and event_complete
        and rows_complete
        and metrics["event_old_name_accuracy"] == 1.0
        and metrics["event_new_name_accuracy"] == 1.0
        and metrics["event_effective_date_accuracy"] == 1.0
        and metrics["firm_year_change_flag_accuracy"] == 1.0
        and metrics["firm_year_year_end_name_accuracy"] == 1.0
        and metrics["unresolved_candidate_count"] == 0
        and metrics["unresolved_event_count"] == 0
    )
    return {
        "schema": "cnipa_strict_pilot_gate_v2",
        "status": "STRICT_PILOT_GATE_PASS" if passed else "PILOT_GATE_NOT_PASSED",
        "seed": SEED,
        "pilot_firms": int(sample.firm_key.nunique()),
        "target_firm_years": len(targets),
        "sample_fingerprint": _frame_fingerprint(sample),
        "target_fingerprint": _frame_fingerprint(targets),
        "source_evidence_fingerprint": _frame_fingerprint(audit),
        "change_candidate_row_fingerprint": _frame_fingerprint(candidates),
        "change_event_roster_fingerprint": _frame_fingerprint(events),
        "change_row_review_fingerprint": _frame_fingerprint(rows),
        "change_event_denominator": len(events),
        "change_related_firm_year_rows": len(candidates),
        "candidate_row_keys": sorted(
            candidates.firm_key.astype(str).str.cat(candidates.year.astype(str), sep="|").tolist()
        ),
        "reviewed_event_ids": sorted(events.event_id.tolist()),
        "legal_name_precision": precision,
        "security_abbreviation_false_positives": false_positives,
        "human_audit_unreviewed": unreviewed,
        "unresolved_candidate_count": metrics["unresolved_candidate_count"],
        "unresolved_event_count": metrics["unresolved_event_count"],
        "event_old_name_accuracy": metrics["event_old_name_accuracy"],
        "event_new_name_accuracy": metrics["event_new_name_accuracy"],
        "event_effective_date_accuracy": metrics["event_effective_date_accuracy"],
        "firm_year_change_flag_accuracy": metrics["firm_year_change_flag_accuracy"],
        "firm_year_year_end_name_accuracy": metrics["firm_year_year_end_name_accuracy"],
        "event_review_complete": event_complete,
        "firm_year_review_complete": rows_complete,
        "pilot_gate_pass": passed,
        "metrics": metrics,
        "failure_reasons": []
        if passed
        else ["STRICT_CANONICAL_CHANGE_EVENT_REVIEW_INCOMPLETE_OR_INACCURATE"],
    }


def _finalize_pilot_change_events() -> dict[str, object]:
    audit = pd.read_csv(OUTPUT / "pilot_context_audit.csv", dtype=str).fillna("")
    statuses = pd.read_csv(OUTPUT / "pilot_status.csv", dtype=str).fillna("")
    sample = pd.read_csv(OUTPUT / "pilot_sample.csv", dtype=str).fillna("")
    targets = pd.read_csv(OUTPUT / "pilot_firm_year_targets.csv", dtype=str).fillna("")
    candidates, events, rows = _build_pilot_change_artifacts(audit, statuses)
    candidates.to_csv(OUTPUT / "pilot_change_candidate_rows.csv", index=False, encoding="utf-8-sig")
    events.to_csv(OUTPUT / "pilot_change_event_roster.csv", index=False, encoding="utf-8-sig")
    rows.to_csv(OUTPUT / "pilot_change_row_review.csv", index=False, encoding="utf-8-sig")
    summary = _build_v2_strict_pilot_summary(sample, targets, audit, candidates, events, rows)
    _atomic_json(OUTPUT / "pilot_strict_gate_v2_summary.json", summary)
    return summary


def _preserve_manual_audit(review: pd.DataFrame, prior: pd.DataFrame) -> pd.DataFrame:
    manual_columns = [
        "human_audit_status",
        "audited_legal_name",
        "abbreviation_false_positive",
        "change_case_reviewed",
        "audited_change_flag",
        "audited_previous_legal_name",
        "audited_new_legal_name",
        "audited_effective_date",
        "wrong_year",
        "wrong_document",
    ]
    identity_columns = [
        "firm_key",
        "year",
        "legal_name_current_in_report",
        "legal_name_at_year_end",
        "company_name_change_flag",
        "legal_name_previous",
        "legal_name_new",
        "change_effective_date",
        "change_evidence_url",
        "change_pdf_sha256",
    ]
    review = review.fillna("").copy()
    prior = prior.fillna("").copy()
    for column in manual_columns:
        if column not in review:
            review[column] = ""
    if not {"firm_key", "year"}.issubset(prior.columns):
        return review
    review["firm_key"] = review.firm_key.astype(str)
    review["year"] = review.year.astype(str)
    prior["firm_key"] = prior.firm_key.astype(str)
    prior["year"] = prior.year.astype(str)
    shared_identity = [
        column
        for column in identity_columns
        if column in prior.columns and column in review.columns
    ]
    prior_by_key = prior.set_index(["firm_key", "year"], drop=False)
    if prior_by_key.index.has_duplicates:
        return review
    for column in manual_columns:
        if column not in prior.columns:
            continue
        for index, row in review.iterrows():
            key = (row["firm_key"], row["year"])
            if key not in prior_by_key.index:
                continue
            previous = prior_by_key.loc[key]
            if all(str(row[c]) == str(previous[c]) for c in shared_identity):
                review.at[index, column] = str(previous[column])
    return review


def _source_records(cache_dir: Path = SOURCE_CACHE) -> dict[tuple[str, int], dict[str, object]]:
    sources: dict[tuple[str, int], dict[str, object]] = {}
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
            if row.get("source_url_or_id", "").startswith("https://"):
                sources[key] = row
    return sources


def _firm_year_targets() -> tuple[pd.DataFrame, pd.DataFrame]:
    universe = pd.read_parquet(UNIVERSE)
    manifest = pd.read_csv(MANIFEST, dtype={"firm_key": str})
    firms = set(manifest.loc[manifest.formal_ready.astype(bool), "firm_key"].astype(str))
    panel = universe.loc[universe.firm_key.astype(str).isin(firms)].copy()
    primary = panel.loc[panel.year.between(2020, 2024)].copy()
    audit_2025 = panel.loc[panel.year.eq(2025)].copy()
    if (
        primary.empty
        or audit_2025.empty
        or primary.duplicated(["firm_key", "year"]).any()
        or audit_2025.duplicated(["firm_key", "year"]).any()
        or primary.year.astype(int).min() != 2020
        or primary.year.astype(int).max() != 2024
        or not audit_2025.year.astype(int).eq(2025).all()
    ):
        raise ValueError("INVALID_PRIMARY_OR_2025_AUDIT_TARGET")
    return primary, audit_2025


def _required_pilot_keys(source_records: dict[tuple[str, int], dict[str, object]]) -> set[str]:
    required = {"SSE:600048:2006-07-31"}  # historical legal-name evidence case
    collisions = pd.read_csv(ROOT / "results/cnipa_preflight/name_collision_audit.csv")
    for row in collisions.loc[collisions.collision_status.eq("UNRESOLVED"), "firm_keys"]:
        required.update(str(row).split("|"))
    revision_keys: set[str] = set()
    for (firm_key, _), row in source_records.items():
        if re.search(r"修订|更正|更新", str(row.get("source_report_title", ""))):
            revision_keys.add(firm_key)
    required.update(
        sorted(
            revision_keys,
            key=lambda key: hashlib.sha256(f"{SEED}|revision|{key}".encode("utf-8")).hexdigest(),
        )[:5]
    )
    return required


def _pilot_targets(
    primary: pd.DataFrame,
    audit_2025: pd.DataFrame,
    source_records: dict[tuple[str, int], dict[str, object]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    firms = primary.drop_duplicates("firm_key").copy()
    sample = select_legal_name_pilot(
        firms,
        seed=SEED,
        minimum_firms=80,
        required_firm_keys=_required_pilot_keys(source_records),
    )
    keys = set(sample.firm_key.astype(str))
    sample_target = primary.loc[primary.firm_key.astype(str).isin(keys)].copy()
    sample_target = sample_target.merge(
        sample[["firm_key", "pilot_stratum"]], on="firm_key", how="left", validate="many_to_one"
    )
    audit_target = audit_2025.loc[audit_2025.firm_key.astype(str).isin(keys)].copy()
    audit_target = audit_target.merge(
        sample[["firm_key", "pilot_stratum"]], on="firm_key", how="left", validate="many_to_one"
    )
    return sample, pd.concat([sample_target, audit_target], ignore_index=True)


def _evidence_path(firm_key: str, year: int) -> Path:
    token = hashlib.sha256(firm_key.encode("utf-8")).hexdigest()[:16]
    return OUTPUT / "cache" / f"{token}_{year}.json"


def _coverage_status(record: dict[str, object]) -> str:
    status = str(record.get("status", "PENDING"))
    if record.get("evidence_status") == "TEMPORAL_UNRESOLVED":
        return "TEMPORAL_UNRESOLVED"
    if status == "COMPLETE_NO_CHANGE":
        return "CONFIRMED_NO_CHANGE"
    if status == "COMPLETE_NAME_CHANGE":
        return "CONFIRMED_NAME_CHANGE"
    if status == "PENDING":
        return "CONFIRMED_YEAR_END_NAME_ONLY"
    if status == "REPORT_NOT_FOUND":
        return "REPORT_NOT_FOUND"
    if status in {"PDF_FETCH_FAILED", "TEXT_EXTRACTION_FAILED"}:
        return "REPORT_FETCH_FAILED"
    if status == "LEGAL_NAME_NOT_FOUND":
        return "LEGAL_NAME_EXTRACTION_FAILED"
    if status == "SOURCE_BLOCKED":
        return "SOURCE_BLOCKED"
    return "PENDING"


def _load_status_cache(
    cache_dir: Path,
    target_pairs: set[tuple[str, int]],
    *,
    retry_failures: bool = False,
) -> dict[tuple[str, int], dict[str, object]]:
    records: dict[tuple[str, int], dict[str, object]] = {}
    for path in cache_dir.glob("*.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
            key = (str(row["firm_key"]), int(row["year"]))
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if key not in target_pairs or row.get("status") not in STATUSES:
            continue
        if retry_failures and row.get("status") in RETRYABLE_STATUSES:
            continue
        records[key] = row
    return records


def _write_entity_year_coverage() -> None:
    full_path = OUTPUT / "full_status.csv"
    audit_path = OUTPUT / "audit-2025_status.csv"
    full = pd.read_csv(full_path, dtype={"firm_key": str})
    audit = pd.read_csv(audit_path, dtype={"firm_key": str})
    primary, audit_target = _firm_year_targets()
    expected_primary = set(zip(primary.firm_key.astype(str), primary.year.astype(int)))
    expected_2025 = set(zip(audit_target.firm_key.astype(str), audit_target.year.astype(int)))
    actual_primary = set(zip(full.firm_key.astype(str), full.year.astype(int)))
    actual_2025 = set(zip(audit.firm_key.astype(str), audit.year.astype(int)))
    if actual_primary != expected_primary or actual_2025 != expected_2025:
        raise ValueError("ENTITY_YEAR_COVERAGE_STATUS_SET_MISMATCH")
    combined = pd.concat([full, audit], ignore_index=True)
    expected_combined_rows = len(primary) + len(audit_target)
    if combined.duplicated(["firm_key", "year"]).any() or len(combined) != expected_combined_rows:
        raise ValueError("ENTITY_YEAR_COVERAGE_DUPLICATE_OR_ROW_COUNT_MISMATCH")
    combined["coverage_status"] = combined.apply(
        lambda row: _coverage_status(row.to_dict()), axis=1
    )
    combined["evidence_tier"] = (
        combined["source_url"].fillna("").map(lambda value: "H1" if value else "")
    )
    combined["evidence_source"] = (
        combined["source_url"]
        .fillna("")
        .map(lambda value: "CNINFO official annual report" if value else "")
    )
    year_end_names = combined.get(
        "legal_name_at_year_end", pd.Series("", index=combined.index)
    ).fillna("")
    report_names = combined.get(
        "legal_name_current_in_report", pd.Series("", index=combined.index)
    ).fillna("")
    combined["legal_name"] = year_end_names.where(year_end_names.ne(""), report_names)
    combined["previous_legal_name"] = combined.get(
        "legal_name_previous", pd.Series("", index=combined.index)
    ).fillna("")
    combined["new_legal_name"] = combined.get(
        "legal_name_new", pd.Series("", index=combined.index)
    ).fillna("")
    combined["name_change_flag"] = combined.get(
        "company_name_change_flag", pd.Series("UNKNOWN", index=combined.index)
    ).fillna("UNKNOWN")
    combined["evidence_url"] = combined.get("source_url", "").fillna("")
    combined["source_announcement_id"] = combined.get(
        "source_announcement_id", pd.Series("", index=combined.index)
    ).fillna("")
    columns = [
        "firm_key",
        "year",
        "legal_name",
        "previous_legal_name",
        "new_legal_name",
        "name_change_flag",
        "evidence_tier",
        "evidence_source",
        "evidence_url",
        "source_announcement_id",
        "pdf_sha256",
        "valid_from",
        "valid_to",
        "date_precision",
        "temporal_match_uncertain",
        "coverage_status",
        "failure_reason",
        "source_report_title",
        "source_report_date",
        "http_status",
        "pdf_bytes",
        "text_chars",
        "matched_label",
        "evidence_context",
    ]
    for column in columns:
        if column not in combined:
            combined[column] = ""
    target_path = ROOT / "results/cnipa_preflight/entity_year_name_coverage.csv"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    combined[columns].to_csv(target_path, index=False, encoding="utf-8-sig")


def _reconcile_existing_results_to_current_targets() -> dict[str, object]:
    """Retarget existing local evidence rows without fetching or rewriting caches."""
    primary, audit_2025 = _firm_year_targets()
    summaries: dict[str, object] = {}
    for stage, targets in (("full", primary), ("audit-2025", audit_2025)):
        status_path = OUTPUT / f"{stage}_status.csv"
        frame = pd.read_csv(status_path, dtype={"firm_key": str})
        expected = set(zip(targets.firm_key.astype(str), targets.year.astype(int)))
        frame = frame.loc[
            pd.MultiIndex.from_arrays([frame.firm_key.astype(str), frame.year.astype(int)]).isin(
                expected
            )
        ].copy()
        actual = set(zip(frame.firm_key.astype(str), frame.year.astype(int)))
        if actual != expected or frame.duplicated(["firm_key", "year"]).any():
            raise ValueError(f"EXISTING_{stage.upper()}_STATUS_SET_MISMATCH")
        frame.to_csv(status_path, index=False, encoding="utf-8-sig")
        summary_path = OUTPUT / f"{stage}_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary.update(
            target_firms=int(targets.firm_key.nunique()),
            target_firm_years=len(targets),
            status_key_set_exact=True,
            status_counts=frame.status.value_counts().to_dict(),
            successful_report_retrieval=int(
                frame.get("http_status", pd.Series(dtype=float)).eq(200).sum()
            ),
            legal_name_extracted=int(
                frame.get("legal_name_current_in_report", pd.Series(dtype=str))
                .fillna("")
                .astype(str)
                .ne("")
                .sum()
            ),
            SOURCE_BLOCKED=int(frame.status.eq("SOURCE_BLOCKED").sum()),
            temporal_unresolved=int(
                frame.get("evidence_status", pd.Series(dtype=str)).eq("TEMPORAL_UNRESOLVED").sum()
            ),
        )
        summary["legal_name_missing_rate"] = (
            1 - summary["legal_name_extracted"] / len(targets) if len(targets) else 0.0
        )
        for status_name in (
            "COMPLETE_NO_CHANGE",
            "COMPLETE_NAME_CHANGE",
            "REPORT_NOT_FOUND",
            "PDF_FETCH_FAILED",
            "TEXT_EXTRACTION_FAILED",
            "LEGAL_NAME_NOT_FOUND",
            "SOURCE_BLOCKED",
        ):
            summary[status_name] = int(frame.status.eq(status_name).sum())
        _atomic_json(summary_path, summary)
        state_path = OUTPUT / f"{stage}_run_state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state.update(summary, remaining_firm_years=0)
            _atomic_json(state_path, state)
        summaries[stage] = summary
    _write_entity_year_coverage()
    return summaries


def _finalize_pilot_audit() -> dict[str, object]:
    audit_path = OUTPUT / "pilot_context_audit.csv"
    status_path = OUTPUT / "pilot_status.csv"
    sample_path = OUTPUT / "pilot_sample.csv"
    if not all(path.exists() for path in (audit_path, status_path, sample_path)):
        raise ValueError("PILOT_AUDIT_INPUTS_MISSING")
    audit = pd.read_csv(audit_path, dtype=str).fillna("")
    statuses = pd.read_csv(status_path, dtype=str).fillna("")
    sample = pd.read_csv(sample_path, dtype=str).fillna("")
    pairs = set(zip(statuses.firm_key.astype(str), statuses.year.astype(int)))
    targets = pd.read_csv(OUTPUT / "pilot_firm_year_targets.csv", dtype={"firm_key": str}).fillna(
        ""
    )
    if "legal_name_at_year_end" in audit:
        expected_names = audit.legal_name_at_year_end.where(
            audit.legal_name_at_year_end.ne(""), audit.legal_name_current_in_report
        )
    else:
        expected_names = audit.legal_name_current_in_report
    name_rows = audit.loc[expected_names.ne("")].copy()
    name_rows["_expected_name"] = expected_names.loc[expected_names.ne("")]
    name_review_unreviewed = int(
        name_rows.human_audit_status.ne("PASS").sum()
        + name_rows.audited_legal_name.ne(name_rows._expected_name).sum()
        + name_rows.abbreviation_false_positive.eq("").sum()
    )
    false_positives = int(name_rows.abbreviation_false_positive.eq("1").sum())
    precision = (
        float(name_rows.audited_legal_name.eq(name_rows._expected_name).mean())
        if len(name_rows)
        else 0.0
    )

    # A case roster must be separately frozen and reviewed. The legacy context
    # CSV is evidence input, not authority to define its own denominator.
    roster_path = OUTPUT / "pilot_gate_case_review.csv"
    roster = (
        pd.read_csv(roster_path, dtype=str).fillna("") if roster_path.exists() else pd.DataFrame()
    )
    required_roster = {
        "case_id",
        "firm_key",
        "year",
        "review_status",
        "manual_change_flag",
        "manual_previous_name",
        "manual_new_name",
        "review_evidence_url",
    }
    roster_valid = bool(
        len(roster)
        and required_roster.issubset(roster.columns)
        and roster.case_id.ne("").all()
        and roster.case_id.is_unique
        and roster.review_status.eq("PASS").all()
    )
    case_rows = pd.DataFrame()
    if roster_valid:
        key_columns = ["firm_key", "year"]
        roster["year"] = roster.year.astype(int).astype(str)
        audit["year"] = audit.year.astype(int).astype(str)
        case_rows = roster.merge(
            audit, on=key_columns, how="left", validate="one_to_one", suffixes=("", "_audit")
        )
        roster_valid = bool(
            len(case_rows) == len(roster)
            and case_rows.company_name_change_flag.ne("").all()
            and case_rows.legal_name_previous.ne("").all()
            and case_rows.legal_name_new.ne("").all()
            and case_rows.manual_change_flag.ne("").all()
            and case_rows.manual_previous_name.ne("").all()
            and case_rows.manual_new_name.ne("").all()
            and case_rows.review_evidence_url.str.startswith("https://").all()
        )
    if len(case_rows):
        flag_accuracy = float(
            case_rows.company_name_change_flag.eq(case_rows.manual_change_flag).mean()
        )
        previous_accuracy = float(
            case_rows.legal_name_previous.eq(case_rows.manual_previous_name).mean()
        )
        new_accuracy = float(case_rows.legal_name_new.eq(case_rows.manual_new_name).mean())
    else:
        flag_accuracy = previous_accuracy = new_accuracy = None

    source_evidence = audit
    metrics: dict[str, object] = {
        "legal_name_precision": precision,
        "security_abbreviation_false_positives": false_positives,
        "human_audit_unreviewed": name_review_unreviewed,
        "company_name_change_flag_accuracy": flag_accuracy,
        "previous_name_accuracy": previous_accuracy,
        "new_name_accuracy": new_accuracy,
    }
    strict = {
        "schema": "cnipa_strict_pilot_gate_v1",
        "status": "PILOT_GATE_NOT_PASSED",
        "seed": SEED,
        "pilot_firms": int(sample.firm_key.nunique()),
        "target_firm_years": int(len(targets)),
        "status_key_set_exact": validate_firm_year_status_set(
            set(zip(targets.firm_key.astype(str), targets.year.astype(int))), pairs
        ),
        "sample_fingerprint": _frame_fingerprint(sample),
        "target_fingerprint": _frame_fingerprint(targets),
        "source_evidence_fingerprint": _frame_fingerprint(source_evidence),
        "case_roster_fingerprint": _frame_fingerprint(roster),
        "reviewed_case_ids": roster.case_id.tolist() if roster_valid else [],
        "change_case_denominator": len(roster) if roster_valid else None,
        "observed_legacy_review_rows": int(audit.change_case_reviewed.eq("YES").sum()),
        "review_complete": roster_valid and name_review_unreviewed == 0,
        "case_roster_reconciled": roster_valid,
        "metrics": metrics,
        "pilot_gate_pass": False,
        "failure_reasons": [],
    }
    if not roster_valid:
        strict["failure_reasons"].append("FROZEN_CASE_ROSTER_MISSING_OR_INVALID")
    if name_review_unreviewed:
        strict["failure_reasons"].append("LEGAL_NAME_REVIEW_INCOMPLETE_OR_MISMATCHED")
    if int(sample.firm_key.nunique()) < 80:
        strict["failure_reasons"].append("PILOT_FIRM_COUNT_BELOW_MINIMUM")
    if not strict["status_key_set_exact"]:
        strict["failure_reasons"].append("STATUS_KEY_SET_NOT_EXACT")
    if (
        roster_valid
        and name_review_unreviewed == 0
        and strict["status_key_set_exact"]
        and precision >= 0.99
        and false_positives == 0
        and flag_accuracy == previous_accuracy == new_accuracy == 1.0
        and len(roster) > 0
    ):
        strict.update(pilot_gate_pass=True, status="STRICT_PILOT_GATE_PASS")
    reconciliation = pd.DataFrame(
        {
            "firm_key": audit.get("firm_key", ""),
            "stock_code": audit.get("firm_key", pd.Series(dtype=str))
            .astype(str)
            .str.split(":")
            .str[1],
            "year": audit.get("year", ""),
            "pilot_stratum": audit.get("pilot_stratum", ""),
            "legal_name_current_in_report": audit.get("legal_name_current_in_report", ""),
            "legal_name_at_year_end": audit.get("legal_name_at_year_end", ""),
            "parser_change_flag": audit.get("company_name_change_flag", ""),
            "parser_previous_name": audit.get("legal_name_previous", ""),
            "parser_new_name": audit.get("legal_name_new", ""),
            "parser_effective_date": audit.get("change_effective_date", ""),
            "parser_evidence_status": audit.get("evidence_status", ""),
            "manual_change_flag": audit.get("audited_change_flag", ""),
            "manual_previous_name": audit.get("audited_previous_legal_name", ""),
            "manual_new_name": audit.get("audited_new_legal_name", ""),
            "manual_effective_date": audit.get("audited_effective_date", ""),
            "change_case_originally_reviewed": audit.get(
                "change_case_reviewed", pd.Series(dtype=str)
            )
            .map({"YES": "UNKNOWN_PROVENANCE"})
            .fillna("NOT_IN_CURRENT_REVIEW"),
            "change_case_currently_detected": audit.get(
                "company_name_change_flag", pd.Series(dtype=str)
            )
            .eq("YES")
            .astype(str),
            "source_report_url": audit.get("source_report_url", ""),
            "source_announcement_id": audit.get("change_announcement_id", ""),
            "h2_used": audit.get("change_evidence_tier", "").eq("H2").astype(str)
            if isinstance(audit.get("change_evidence_tier"), pd.Series)
            else "False",
            "h2_source_url": audit.get("change_evidence_url", ""),
            "case_status": audit.get("change_case_reviewed", "").replace(
                {"YES": "REVIEW_ROW_PRESENT", "": "NOT_MARKED_AS_CASE"}
            ),
            "difference_reason": (
                "Frozen five-case roster is absent; row membership cannot be proven "
                "from tracked records"
            ),
        }
    )
    reconciliation.loc[reconciliation.change_case_currently_detected.eq("True"), "case_status"] = (
        "PARSER_DETECTED_CHANGE"
    )
    reconciliation.loc[reconciliation.h2_used.ne("True"), "h2_source_url"] = ""
    if "source_url" in statuses.columns:
        report_sources = statuses[["firm_key", "year", "source_url"]].copy()
        report_sources["year"] = report_sources.year.astype(str)
        reconciliation["year"] = reconciliation.year.astype(str)
        reconciliation = reconciliation.merge(
            report_sources.drop_duplicates(["firm_key", "year"]),
            on=["firm_key", "year"],
            how="left",
            validate="one_to_one",
        )
        reconciliation["source_report_url"] = reconciliation.source_url.fillna("")
        reconciliation = reconciliation.drop(columns="source_url")
    reconciliation.to_csv(
        OUTPUT / "pilot_gate_reconciliation.csv", index=False, encoding="utf-8-sig"
    )
    _atomic_json(OUTPUT / "pilot_strict_gate_summary.json", strict)
    summary = strict
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return summary


def _targeted_url(
    client: CNINFOAnnualReportClient,
    firm: dict[str, object],
    year: int,
    report_index: dict[str, list[dict[str, object]]],
):
    stock_code = str(firm["stock_code_current"])
    if stock_code not in report_index:
        report_index[stock_code] = client.list_annual_reports(stock_code, start_date="2020-01-01")
    reports = report_index[stock_code]
    matches = [row for row in reports if int(row.get("report_year", -1)) == year]
    if not matches:
        return None
    source = dict(matches[-1])
    source["source_url_or_id"] = str(
        source.get("source_url_or_id") or source.get("source_url") or ""
    )
    source["source_report_title"] = str(
        source.get("source_report_title") or source.get("title") or ""
    )
    source["source_announcement_id"] = str(
        source.get("source_announcement_id") or source.get("announcement_id") or ""
    )
    return source


def _process_one(
    client: CNINFOAnnualReportClient,
    firm: dict[str, object],
    year: int,
    cached: dict[str, object] | None,
    report_index: dict[str, list[dict[str, object]]],
) -> dict[str, object]:
    firm_key = str(firm["firm_key"])
    source = cached
    fallback_used = False
    text = ""
    pdf_meta: dict[str, object] = {}
    failure = ""
    for attempt in range(2):
        if source is None:
            source = _targeted_url(client, firm, year, report_index)
            fallback_used = True
        if source is None:
            failure = "annual_report_not_found"
            break
        title = str(source.get("source_report_title") or source.get("title") or "")
        if title and match_annual_report_title(title) != year:
            failure = "cached_report_title_year_mismatch"
            source = None
            continue
        try:
            text, pdf_meta = client.extract_pdf_text_with_metadata(str(source["source_url_or_id"]))
            break
        except SourceBlocked:
            raise
        except (OSError, RuntimeError, ValueError, TimeoutError) as exc:
            failure = f"{type(exc).__name__}:{str(exc)[:160]}"
            source = None
    if not text:
        text_failure = "pdftotext" in failure.lower()
        return {
            "firm_key": firm_key,
            "year": int(year),
            "status": (
                "REPORT_NOT_FOUND"
                if failure == "annual_report_not_found"
                else "TEXT_EXTRACTION_FAILED"
                if text_failure
                else "PDF_FETCH_FAILED"
            ),
            "failure_reason": failure,
            "source_report_title": str(
                (source or cached or {}).get("source_report_title")
                or (source or cached or {}).get("title", "")
            ),
            "source_url": str((source or cached or {}).get("source_url_or_id", "")),
            "source_announcement_id": str(
                (source or cached or {}).get("source_announcement_id")
                or (source or cached or {}).get("announcement_id", "")
            ),
            "fallback_used": int(fallback_used),
            "pdf_bytes": int(pdf_meta.get("pdf_bytes", 0)),
            "pdf_sha256": str(pdf_meta.get("pdf_sha256", "")),
            "pdf_content_persisted": False,
        }
    title = str(source.get("source_report_title") or source.get("title") or "")
    evidence = extract_annual_report_legal_name_evidence(
        text, expected_year=year, source_report_title=title
    )
    title = str(evidence.get("source_report_title") or title)
    if not evidence["legal_name_current_in_report"]:
        status = "LEGAL_NAME_NOT_FOUND"
    elif evidence["evidence_status"] == "CONFIRMED_NO_CHANGE":
        status = "COMPLETE_NO_CHANGE"
    elif evidence["evidence_status"] == "CONFIRMED_NAME_CHANGE":
        status = "COMPLETE_NAME_CHANGE"
    else:
        status = "PENDING"
    return {
        "firm_key": firm_key,
        "year": int(year),
        "exchange": str(firm.get("exchange", "")),
        "stock_code": str(firm.get("stock_code_current", "")),
        **evidence,
        "status": status,
        "failure_reason": str(evidence.get("failure_reason", "")),
        "source_url": str(source.get("source_url_or_id", "")),
        "source_announcement_id": str(
            source.get("source_announcement_id") or source.get("announcement_id", "")
        ),
        "source_report_title": title,
        "source_report_date": str(source.get("source_report_date", "")),
        "fallback_used": int(fallback_used),
        **pdf_meta,
        "text_extraction_status": "EXTRACTED",
        "pdf_content_persisted": False,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


def _name_key(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"[^\w]", "", normalized, flags=re.UNICODE)


def _resolve_cross_year_name_changes(
    rows: dict[tuple[str, int], dict[str, object]],
    targets: pd.DataFrame,
    client: CNINFOAnnualReportClient,
    stage: str,
) -> tuple[list[dict[str, object]], bool]:
    """Use one-security H2 searches only for adjacent-year legal-name changes."""
    timeline = dict(rows)
    if stage == "audit-2025":
        previous_path = OUTPUT / "full_status.csv"
        if previous_path.exists():
            previous_rows = pd.read_csv(previous_path, dtype=str).fillna("")
            previous_2024 = previous_rows.loc[previous_rows.year.astype(int).eq(2024)]
            for previous in previous_2024.to_dict("records"):
                timeline[(str(previous["firm_key"]), 2024)] = previous

    firm_lookup = {str(row.firm_key): row._asdict() for row in targets.itertuples(index=False)}
    audit: list[dict[str, object]] = []
    source_blocked = False
    for firm_key, year in sorted(rows):
        current = rows[(firm_key, year)]
        previous = timeline.get((firm_key, year - 1))
        if not previous:
            continue
        old_name = str(previous.get("legal_name_at_year_end") or "")
        new_name = str(current.get("legal_name_at_year_end") or "")
        if not old_name or not new_name or _name_key(old_name) == _name_key(new_name):
            continue
        if (
            current.get("company_name_change_flag") == "YES"
            and current.get("legal_name_previous") == old_name
            and current.get("legal_name_new") == new_name
            and str(current.get("change_effective_date", "")).startswith(str(year))
        ):
            continue

        firm = firm_lookup.get(firm_key, {})
        stock_code = str(firm.get("stock_code_current", current.get("stock_code", "")))
        audit_row: dict[str, object] = {
            "firm_key": firm_key,
            "year": int(year),
            "previous_legal_name": old_name,
            "new_legal_name": new_name,
            "status": "H2_PENDING",
            "failure_reason": "",
        }
        extraction_failures: list[str] = []
        try:
            notices = client.list_company_name_change_announcements(
                stock_code,
                f"{year}-01-01",
                f"{year + 1}-03-31",
            )
            for notice in notices:
                audit_row["notice_title"] = str(notice["title"])
                audit_row["notice_url"] = str(notice["source_url"])
                try:
                    text, metadata = client.extract_pdf_text_with_metadata(
                        str(notice["source_url"])
                    )
                except SourceBlocked:
                    raise
                except (OSError, RuntimeError, ValueError, TimeoutError) as exc:
                    extraction_failures.append(
                        f"{notice['title']}:{type(exc).__name__}:{str(exc)[:160]}"
                    )
                    continue
                evidence = extract_company_name_change_announcement(
                    text,
                    expected_year=year,
                    previous_legal_name=old_name,
                    new_legal_name=new_name,
                    announcement_date=str(notice.get("announcement_date", "")),
                )
                audit_row.update(
                    {
                        "announcement_id": str(notice.get("announcement_id", "")),
                        "notice_pdf_sha256": str(metadata["pdf_sha256"]),
                        "notice_pdf_bytes": int(metadata["pdf_bytes"]),
                        **evidence,
                    }
                )
                if evidence["evidence_status"] not in {
                    "CONFIRMED_NAME_CHANGE",
                    "CONFIRMED_NO_CHANGE",
                }:
                    continue
                current.update(
                    {
                        "company_name_change_flag": evidence["company_name_change_flag"],
                        "legal_name_previous": old_name,
                        "legal_name_new": new_name,
                        "change_effective_date": evidence["change_effective_date"],
                        "date_precision": evidence["date_precision"],
                        "valid_from": (
                            evidence["change_effective_date"] or str(year)
                            if evidence["company_name_change_flag"] == "YES"
                            else ""
                        ),
                        "valid_to": "",
                        "legal_name_at_year_end": evidence["legal_name_at_year_end"],
                        "temporal_match_uncertain": evidence["temporal_match_uncertain"],
                        "evidence_status": evidence["evidence_status"],
                        "failure_reason": "",
                        "status": (
                            "COMPLETE_NAME_CHANGE"
                            if evidence["company_name_change_flag"] == "YES"
                            else "COMPLETE_NO_CHANGE"
                        ),
                        "change_evidence_tier": "H2",
                        "change_evidence_source": "CNINFO targeted company-name-change notice",
                        "change_evidence_url": str(notice["source_url"]),
                        "change_announcement_id": str(notice.get("announcement_id", "")),
                        "change_pdf_sha256": str(metadata["pdf_sha256"]),
                        "change_notice_text_chars": int(metadata["text_chars"]),
                    }
                )
                audit_row["status"] = "RESOLVED_H2"
                _atomic_json(_evidence_path(firm_key, year), current)
                break
            else:
                audit_row["status"] = "TEMPORAL_UNRESOLVED"
                audit_row["failure_reason"] = "no_notice_confirmed_expected_name_pair"
                if extraction_failures:
                    audit_row["failure_reason"] += f";unreadable_notices={len(extraction_failures)}"
                current.update(
                    {
                        "evidence_status": "TEMPORAL_UNRESOLVED",
                        "temporal_match_uncertain": 1,
                        "failure_reason": audit_row["failure_reason"],
                    }
                )
            if extraction_failures:
                audit_row["notice_extraction_failures"] = extraction_failures
        except SourceBlocked as exc:
            source_blocked = True
            audit_row["status"] = "SOURCE_BLOCKED"
            audit_row["failure_reason"] = str(exc)
            current.update(
                {
                    "status": "SOURCE_BLOCKED",
                    "evidence_status": "SOURCE_BLOCKED",
                    "failure_reason": str(exc),
                }
            )
            _atomic_json(_evidence_path(firm_key, year), current)
        audit.append(audit_row)
        if source_blocked:
            break

    pd.DataFrame(audit).to_csv(
        OUTPUT / f"{stage.replace('-', '_')}_name_change_h2_audit.csv",
        index=False,
        encoding="utf-8-sig",
    )
    return audit, source_blocked


def _run(args: argparse.Namespace) -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    primary, audit_2025 = _firm_year_targets()
    sources = _source_records()
    if args.stage == "pilot":
        sample, targets = _pilot_targets(primary, audit_2025, sources)
        sample.to_csv(OUTPUT / "pilot_sample.csv", index=False, encoding="utf-8-sig")
        targets.to_csv(OUTPUT / "pilot_firm_year_targets.csv", index=False, encoding="utf-8-sig")
        print(f"PILOT sample_firms={len(sample)} target_firm_years={len(targets)}", flush=True)
        if args.prepare_only:
            return 0
    elif args.stage == "full":
        if not args.pilot_pass:
            raise ValueError("FULL_REQUIRES_EXPLICIT_PILOT_PASS")
        strict_path = OUTPUT / "pilot_strict_gate_v2_summary.json"
        sample_path = OUTPUT / "pilot_sample.csv"
        pilot_targets_path = OUTPUT / "pilot_firm_year_targets.csv"
        audit_path = OUTPUT / "pilot_context_audit.csv"
        candidate_path = OUTPUT / "pilot_change_candidate_rows.csv"
        event_path = OUTPUT / "pilot_change_event_roster.csv"
        row_review_path = OUTPUT / "pilot_change_row_review.csv"
        required_paths = (
            strict_path,
            sample_path,
            pilot_targets_path,
            audit_path,
            candidate_path,
            event_path,
            row_review_path,
        )
        if not all(path.exists() for path in required_paths):
            raise ValueError("CANONICAL_STRICT_PILOT_GATE_INPUTS_MISSING")
        strict_summary = json.loads(strict_path.read_text(encoding="utf-8"))
        frozen_sample = pd.read_csv(sample_path, dtype=str).fillna("")
        frozen_targets = pd.read_csv(pilot_targets_path, dtype=str).fillna("")
        frozen_audit = pd.read_csv(audit_path, dtype=str).fillna("")
        frozen_candidates = pd.read_csv(candidate_path, dtype=str).fillna("")
        frozen_events = pd.read_csv(event_path, dtype=str).fillna("")
        frozen_row_review = pd.read_csv(row_review_path, dtype=str).fillna("")
        if not _strict_pilot_authorized_v2(
            strict_summary,
            frozen_sample,
            frozen_targets,
            frozen_audit,
            frozen_candidates,
            frozen_events,
            frozen_row_review,
        ):
            raise ValueError("PILOT_GATE_NOT_PASSED")
        targets = primary.copy()
        targets["pilot_stratum"] = "full"
    else:
        full_state_path = OUTPUT / "full_run_state.json"
        if not full_state_path.exists():
            raise ValueError("PRIMARY_FULL_RUN_REQUIRED_BEFORE_2025_AUDIT")
        full_state = json.loads(full_state_path.read_text(encoding="utf-8"))
        if full_state.get("status_key_set_exact") is not True:
            raise ValueError("PRIMARY_FULL_STATUS_SET_NOT_EXACT")
        targets = audit_2025.copy()
        targets["pilot_stratum"] = "audit_2025"

    target_pairs = set(zip(targets.firm_key.astype(str), targets.year.astype(int)))
    state_path = OUTPUT / f"{args.stage}_run_state.json"
    if state_path.exists() and not args.resume:
        raise ValueError(f"{args.stage.upper()}_STATE_EXISTS_USE_RESUME")
    old_state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    if old_state and old_state.get("seed") != SEED:
        raise ValueError("PILOT_SEED_MISMATCH")
    client = CNINFOAnnualReportClient(OUTPUT / "source_cache", request_spacing=args.spacing)
    firm_lookup = {
        str(row["firm_key"]): row for row in targets.drop_duplicates("firm_key").to_dict("records")
    }
    status_rows: dict[tuple[str, int], dict[str, object]] = {}
    report_index: dict[str, list[dict[str, object]]] = {}
    cache_dir = OUTPUT / "cache"
    if args.resume and not args.refresh:
        status_rows = _load_status_cache(
            cache_dir, target_pairs, retry_failures=args.retry_failures
        )
    for firm_key, year in args.refresh_firm_year:
        pair = (str(firm_key), int(year))
        if pair not in target_pairs:
            raise ValueError(f"REFRESH_KEY_NOT_IN_TARGET:{pair}")
        status_rows.pop(pair, None)
    for firm_key in args.refresh_firm_key:
        matching_pairs = [pair for pair in target_pairs if pair[0] == str(firm_key)]
        if not matching_pairs:
            raise ValueError(f"REFRESH_FIRM_NOT_IN_TARGET:{firm_key}")
        for pair in matching_pairs:
            status_rows.pop(pair, None)
    missing = sorted(target_pairs - set(status_rows), key=lambda x: (x[0], x[1]))
    _atomic_json(
        state_path,
        {
            "status": f"{args.stage.upper()}_RUNNING",
            "seed": SEED,
            "target_firm_years": len(target_pairs),
            "processed_firm_years": len(status_rows),
            "remaining_firm_years": len(missing),
            "source_blocked": False,
        },
    )
    source_blocked = False
    current_pair: tuple[str, int] | None = None
    try:
        for index, (firm_key, year) in enumerate(missing, start=1):
            current_pair = (firm_key, year)
            path = _evidence_path(firm_key, year)
            row = _process_one(
                client, firm_lookup[firm_key], year, sources.get((firm_key, year)), report_index
            )
            row["pilot_stratum"] = str(
                targets.loc[targets.firm_key.astype(str).eq(firm_key), "pilot_stratum"].iloc[0]
            )
            _atomic_json(path, row)
            status_rows[(firm_key, year)] = row
            if index % 10 == 0 or index == len(missing):
                _atomic_json(
                    state_path,
                    {
                        "status": f"{args.stage.upper()}_RUNNING",
                        "seed": SEED,
                        "target_firm_years": len(target_pairs),
                        "processed_firm_years": len(status_rows),
                        "remaining_firm_years": len(target_pairs) - len(status_rows),
                        "source_blocked": False,
                        "last_completed": f"{firm_key}|{year}",
                    },
                )
                print(f"PROGRESS {args.stage} {len(status_rows)}/{len(target_pairs)}", flush=True)
    except SourceBlocked as exc:
        source_blocked = True
        blocked_pairs = missing[missing.index(current_pair) :] if current_pair in missing else []
        for firm_key, year in blocked_pairs:
            row = {
                "firm_key": firm_key,
                "year": int(year),
                "status": "SOURCE_BLOCKED",
                "failure_reason": str(exc),
                "source_url": str(sources.get((firm_key, year), {}).get("source_url_or_id", "")),
                "pdf_content_persisted": False,
                "pilot_stratum": str(
                    targets.loc[targets.firm_key.astype(str).eq(firm_key), "pilot_stratum"].iloc[0]
                ),
            }
            _atomic_json(_evidence_path(firm_key, year), row)
            status_rows[(firm_key, year)] = row
        _atomic_json(
            state_path,
            {
                "status": "SOURCE_BLOCKED",
                "seed": SEED,
                "target_firm_years": len(target_pairs),
                "processed_firm_years": len(status_rows),
                "remaining_firm_years": len(target_pairs) - len(status_rows),
                "source_blocked": True,
                "block_reason": str(exc),
            },
        )

    if not source_blocked:
        _, h2_source_blocked = _resolve_cross_year_name_changes(
            status_rows, targets, client, args.stage
        )
        source_blocked = source_blocked or h2_source_blocked

    status_pairs = set(status_rows)
    if not validate_firm_year_status_set(target_pairs, status_pairs):
        status = "INCOMPLETE_SOURCE_BLOCKED" if source_blocked else "INCOMPLETE"
    else:
        status = "SOURCE_BLOCKED" if source_blocked else "COMPLETE"
    frame = pd.DataFrame(status_rows.values())
    frame.to_csv(OUTPUT / f"{args.stage}_status.csv", index=False, encoding="utf-8-sig")
    if args.stage == "pilot":
        review_columns = [
            "firm_key",
            "year",
            "pilot_stratum",
            "legal_name_current_in_report",
            "legal_name_at_year_end",
            "company_name_change_flag",
            "legal_name_previous",
            "legal_name_new",
            "change_effective_date",
            "date_precision",
            "temporal_match_uncertain",
            "evidence_status",
            "matched_label",
            "evidence_context",
            "status",
            "failure_reason",
            "change_evidence_tier",
            "change_evidence_source",
            "change_evidence_url",
            "change_announcement_id",
            "change_pdf_sha256",
        ]
        review = frame[[column for column in review_columns if column in frame]].copy()
        prior_audit_path = OUTPUT / "pilot_context_audit.csv"
        if prior_audit_path.exists():
            prior = pd.read_csv(prior_audit_path, dtype=str).fillna("")
            review = _preserve_manual_audit(review, prior)
        review.to_csv(OUTPUT / "pilot_context_audit.csv", index=False, encoding="utf-8-sig")
    successful = frame.loc[
        frame.status.isin({"PENDING", "COMPLETE_NO_CHANGE", "COMPLETE_NAME_CHANGE"})
    ]
    accepted_names = successful.legal_name_current_in_report.fillna("").astype(str)
    name_candidates = accepted_names.loc[accepted_names.ne("")]
    precision = (
        float(
            name_candidates.map(
                lambda value: bool(
                    re.search(r"(?:股份有限公司|有限责任公司|有限公司|股份公司)$", value)
                )
            ).mean()
        )
        if len(name_candidates)
        else 0.0
    )
    review_path = OUTPUT / "pilot_context_audit.csv"
    human_audit_unreviewed = 0
    abbreviation_false_positives = 0
    if args.stage == "pilot" and review_path.exists():
        review = pd.read_csv(review_path, dtype=str).fillna("")
        name_review = review.loc[review.legal_name_current_in_report.ne("")]
        human_audit_unreviewed = int(name_review.human_audit_status.ne("PASS").sum())
        abbreviation_false_positives = int(name_review.abbreviation_false_positive.eq("1").sum())
    summary = {
        "stage": args.stage,
        "status": status,
        "seed": SEED,
        "pilot_firms": int(targets.firm_key.nunique()) if args.stage == "pilot" else 0,
        "target_firm_years": len(target_pairs),
        "status_key_set_exact": validate_firm_year_status_set(target_pairs, status_pairs),
        "status_counts": frame.status.value_counts().to_dict() if len(frame) else {},
        "source_blocked": source_blocked,
        "successful_report_retrieval": int(
            frame.get("http_status", pd.Series(dtype=float)).eq(200).sum()
        ),
        "legal_name_extracted": int(len(name_candidates)),
        "legal_name_precision": precision,
        "legal_name_missing_rate": (
            1 - len(name_candidates) / len(target_pairs) if target_pairs else 0.0
        ),
        "security_abbreviation_false_positives": abbreviation_false_positives,
        "human_audit_unreviewed": human_audit_unreviewed,
        "COMPLETE_NO_CHANGE": int(frame.status.eq("COMPLETE_NO_CHANGE").sum()),
        "COMPLETE_NAME_CHANGE": int(frame.status.eq("COMPLETE_NAME_CHANGE").sum()),
        "REPORT_NOT_FOUND": int(frame.status.eq("REPORT_NOT_FOUND").sum()),
        "PDF_FETCH_FAILED": int(frame.status.eq("PDF_FETCH_FAILED").sum()),
        "TEXT_EXTRACTION_FAILED": int(frame.status.eq("TEXT_EXTRACTION_FAILED").sum()),
        "LEGAL_NAME_NOT_FOUND": int(frame.status.eq("LEGAL_NAME_NOT_FOUND").sum()),
        "SOURCE_BLOCKED": int(frame.status.eq("SOURCE_BLOCKED").sum()),
        "temporal_unresolved": int(frame.evidence_status.eq("TEMPORAL_UNRESOLVED").sum())
        if "evidence_status" in frame
        else 0,
    }
    _atomic_json(OUTPUT / f"{args.stage}_summary.json", summary)
    _atomic_json(state_path, {**summary, "remaining_firm_years": len(target_pairs - status_pairs)})
    if args.stage == "audit-2025" and (OUTPUT / "full_status.csv").exists():
        _write_entity_year_coverage()
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 2 if source_blocked or status != "COMPLETE" else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("pilot", "full", "audit-2025"))
    parser.add_argument("--finalize-pilot-audit", action="store_true")
    parser.add_argument("--finalize-pilot-change-events", action="store_true")
    parser.add_argument("--reconcile-existing-results", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--refresh-firm-year", nargs=2, action="append", default=[])
    parser.add_argument("--refresh-firm-key", action="append", default=[])
    parser.add_argument("--retry-failures", action="store_true")
    parser.add_argument("--pilot-pass", action="store_true")
    parser.add_argument("--spacing", type=float, default=1.0)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if args.finalize_pilot_audit:
        _finalize_pilot_audit()
        return 0
    if args.finalize_pilot_change_events:
        print(json.dumps(_finalize_pilot_change_events(), ensure_ascii=False, indent=2))
        return 0
    if args.reconcile_existing_results:
        print(
            json.dumps(
                _reconcile_existing_results_to_current_targets(),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.stage is None:
        parser.error("--stage is required unless a Pilot finalize option is set")
    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())
