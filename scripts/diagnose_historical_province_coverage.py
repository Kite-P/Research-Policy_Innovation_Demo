from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "historical_province"
sys.path.insert(0, str(ROOT))

def _records_by_key() -> dict[tuple[str, int], dict[str, object]]:
    records: dict[tuple[str, int], dict[str, object]] = {}
    for path in (RESULTS / "cache").glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for record in payload.get("records", []):
            key = (str(record.get("firm_key", "")), int(record.get("source_report_year", -1)))
            records[key] = record
    return records


def classify(row: pd.Series, source: dict[str, object] | None) -> str:
    status = row["province_status"]
    if bool(row.get("province_conflict", False)):
        return "same_tier_conflict"
    if status in {"historical_confirmed", "historical_inferred"}:
        return "resolved_historical"
    if source is None:
        return "source_record_missing"
    reason = str(source.get("missing_reason") or "")
    if reason == "annual_report_not_found":
        return "annual_report_not_found"
    if reason == "registered_address_field_not_found":
        return "report_found_address_field_not_found"
    if reason == "unresolved_temporal_semantics":
        raw = source.get("province_raw")
        from src.historical_province import province_from_address

        if raw and province_from_address(raw):
            return "unresolved_temporal_semantics"
        if raw:
            return "report_found_address_unparseable"
        history = source.get("registered_address_history_raw")
        if history:
            return "historical_event_missing_effective_date"
        return "unresolved_temporal_semantics"
    if status == "static_fallback_only":
        return "current_profile_only"
    if source.get("extraction_method") in {
        "pdftotext_empty", "pdf_text_too_short", "pdf_decode_error"
    }:
        return "pdf_text_extraction_problem"
    return "other"


def main() -> None:
    panel = pd.read_csv(RESULTS / "full_panel_audit.csv", low_memory=False)
    source_records = _records_by_key()
    panel["year"] = pd.to_numeric(panel["year"], errors="raise").astype(int)
    panel["recent_ipo"] = pd.to_datetime(panel["market_listing_date"], errors="coerce").ge(
        pd.Timestamp("2020-01-01")
    )
    panel["source_failure_reason"] = [
        classify(row, source_records.get((str(row.firm_key), int(row.year))))
        for row in panel.itertuples(index=False)
        for row in [pd.Series(row._asdict())]
    ]
    panel["current_or_delisted"] = panel["current_status"].fillna("unknown")
    output_columns = [
        "firm_key", "exchange", "current_or_delisted", "year", "recent_ipo",
        "province_status", "province_conflict", "province_missing_reason",
        "source_failure_reason", "province_source_year", "source_type",
        "extraction_method", "source_url_or_id",
    ]
    panel[output_columns].to_csv(
        RESULTS / "coverage_failure_decomposition.csv", index=False, encoding="utf-8-sig"
    )
    summary = panel.groupby(
        ["exchange", "current_or_delisted", "year", "recent_ipo", "source_failure_reason"],
        dropna=False,
    ).agg(firms=("firm_key", "nunique"), firm_years=("firm_key", "size")).reset_index()
    summary.to_csv(
        RESULTS / "coverage_failure_decomposition_summary.csv", index=False, encoding="utf-8-sig"
    )
    unresolved = (panel.source_failure_reason != "resolved_historical").sum()
    print(f"rows={len(panel)} unresolved={unresolved}")
    counts = summary.groupby("source_failure_reason").firm_years.sum()
    print(counts.sort_values(ascending=False).to_string())


if __name__ == "__main__":
    main()
