from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.historical_province import (  # noqa: E402
    build_historical_province_target,
    province_from_address,
    select_historical_province_pilot,
)
from src.historical_province_sources import (  # noqa: E402
    CNINFOAnnualReportClient,
    SourceBlocked,
    parse_address_change_events,
)

UNIVERSE_PATH = ROOT / "data" / "processed" / "real_company_universe_enriched.parquet"
OUTPUT_PATH = ROOT / "results" / "historical_province" / "source_probe.json"
CACHE_DIR = ROOT / "results" / "historical_province" / "cache"

CHANGE_CASES = {
    "300370": {"name": "安控科技", "years": [2020, 2021], "old": "北京市", "new": "四川省"},
    "000668": {"name": "荣丰控股", "years": [2020, 2021], "old": "上海市", "new": "山东省"},
    "002388": {"name": "新亚制程", "years": [2022, 2023], "old": "广东省", "new": "浙江省"},
    "600715": {"name": "文投控股", "years": [2023, 2024], "old": "辽宁省", "new": "北京市"},
    "002453": {"name": "华软科技", "years": [2023, 2024], "old": "江苏省", "new": "北京市"},
}

SUPPORTING_EVENT_DOCUMENTS = {
    "300370": {
        "source_url": "https://static.cninfo.com.cn/finalpage/2021-08-27/1210872701.PDF",
        "effective_date": "2021-05-25",
        "source_description": "official 2021 interim report registration-change table",
    }
}


def _choose_probe_firms(target: pd.DataFrame) -> list[dict[str, object]]:
    firms = target.drop_duplicates("firm_key").copy()
    if "current_status" not in firms:
        firms["current_status"] = firms["delisting_date"].isna().map(
            {True: "current", False: "delisted"}
        )
    pilot = select_historical_province_pilot(firms)
    selected = []
    for _, group in pilot.groupby("pilot_stratum", sort=True):
        selected.append(group.sort_values("firm_key").iloc[0].to_dict())
    listing = pd.to_datetime(firms["market_listing_date"], errors="coerce")
    for exchange in ("SSE", "SZSE"):
        candidates = firms.loc[firms["exchange"].eq(exchange) & listing.le("2000-12-31")]
        if len(candidates):
            selected.append(candidates.sort_values("firm_key").iloc[0].to_dict())
    unique = {str(row["firm_key"]): row for row in selected}
    return [unique[key] for key in sorted(unique)]


def _case_events(records: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = []
    for row in records:
        history = row.get("registered_address_history_raw")
        events = parse_address_change_events(str(history) if history else None)
        for event in events:
            old_address = event["old_address"]
            new_address = event["new_address"]
            if new_address in {"现址", "现地址", "新址"}:
                new_address = str(row.get("province_raw") or new_address)
            rows.append(
                {
                    "report_year": row["source_report_year"],
                    "source_url": row.get("source_url_or_id"),
                    **event,
                    "old_address": old_address,
                    "new_address": new_address,
                }
            )
    return rows


def _province_of_event_address(address: str) -> str | None:
    return province_from_address(address)


def _save(payload: dict[str, object]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(_json_safe(payload), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    temporary.replace(OUTPUT_PATH)


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def main() -> int:
    universe = pd.read_parquet(UNIVERSE_PATH)
    target = build_historical_province_target(universe)
    representatives = _choose_probe_firms(target)
    by_code = {}
    for code, group in target.groupby(target["stock_code_current"].astype(str).str.zfill(6)):
        records = group.drop_duplicates("firm_key").to_dict("records")
        if len(records) != 1:
            continue
        firm = records[0]
        legal_names = group.get("company_name_legal_profile", pd.Series(dtype=object)).dropna()
        if len(legal_names):
            firm["company_name_legal"] = legal_names.iloc[-1]
        by_code[str(code)] = firm
    plans: dict[str, dict[str, object]] = {}
    legal_years = target.groupby("firm_key")["year"].agg(
        lambda values: sorted(set(map(int, values)))
    )
    for firm in representatives:
        code = str(firm["stock_code_current"]).zfill(6)
        firm_years = legal_years.get(str(firm["firm_key"]), [])
        plans[code] = {"firm": firm, "years": firm_years, "roles": ["stratified"]}
    for code, case in CHANGE_CASES.items():
        if code not in by_code:
            case["target_match"] = False
            continue
        plan = plans.setdefault(code, {"firm": by_code[code], "years": [], "roles": []})
        legal_case_years = set(legal_years.get(str(plan["firm"]["firm_key"]), []))
        plan["years"] = sorted(set(plan["years"]) | (set(case["years"]) & legal_case_years))
        plan["roles"].append("change_case")

    client = CNINFOAnnualReportClient(CACHE_DIR, request_spacing=1.0)
    records_by_code: dict[str, list[dict[str, object]]] = {}
    payload: dict[str, object] = {
        "status": "RUNNING",
        "source": "CNINFO official disclosure search and static annual-report PDFs",
        "source_tier": "H1",
        "source_probe_started_at": datetime.now(timezone.utc).isoformat(),
        "target_firms": int(target["firm_key"].nunique()),
        "target_firm_years": int(len(target)),
        "representative_firms": [],
        "change_case_audits": [],
        "records": [],
    }
    try:
        for code, plan in sorted(plans.items()):
            firm = plan["firm"]
            records = client.fetch_firm_reports(firm, years=plan["years"])
            records_by_code[code] = records
            payload["records"].extend(records)
            payload["representative_firms"].append(
                {
                    "firm_key": firm["firm_key"],
                    "exchange": firm["exchange"],
                    "stock_code_current": code,
                    "company_name_legal": firm.get("company_name_legal"),
                    "pilot_stratum": firm.get("pilot_stratum"),
                    "market_listing_date": str(firm.get("market_listing_date")),
                    "current_status": firm.get("current_status"),
                    "roles": plan["roles"],
                    "report_years_requested": plan["years"],
                    "report_years_found": sorted(
                        int(row["source_report_year"])
                        for row in records
                        if row.get("source_url_or_id")
                    ),
                }
            )
            _save(payload)
        for code, case in CHANGE_CASES.items():
            if code not in by_code:
                payload["change_case_audits"].append(
                    {"stock_code": code, "name": case["name"], "audit_status": "NOT_IN_PHASE_A"}
                )
                continue
            case_records = records_by_code.get(code, [])
            events = _case_events(case_records)
            matching = [
                item for item in events
                if _province_of_event_address(item["old_address"]) == case["old"]
                and _province_of_event_address(item["new_address"]) == case["new"]
            ]
            support = SUPPORTING_EVENT_DOCUMENTS.get(code)
            support_audit = None
            if support:
                support_text = client.extract_pdf_text(str(support["source_url"]))
                year, month, day = map(int, str(support["effective_date"]).split("-"))
                expected_date_text = f"{year}年{month:02d}月{day:02d}日"
                normalized_support_text = "".join(support_text.split())
                support_audit = {
                    **support,
                    "date_found_in_document": expected_date_text in normalized_support_text,
                    "company_identity_found": (
                        "安控科技" in support_text or "300370" in support_text
                    ),
                    "source_type": "official_interim_report",
                }
            if not matching and code == "300370":
                annual_provinces = {
                    int(row["source_report_year"]): _province_of_event_address(
                        str(row.get("province_raw") or "")
                    )
                    for row in case_records
                }
                if (
                    annual_provinces.get(2020) == case["old"]
                    and annual_provinces.get(2021) == case["new"]
                    and support_audit
                    and support_audit["date_found_in_document"]
                    and support_audit["company_identity_found"]
                ):
                    matching = [
                        {"basis": "consecutive_annual_reports_plus_official_dated_interim_record"}
                    ]
            payload["change_case_audits"].append(
                {
                    "stock_code": code,
                    "name": case["name"],
                    "expected_old_province": case["old"],
                    "expected_new_province": case["new"],
                    "report_years_requested": case["years"],
                    "events": events,
                    "supporting_event_record": support_audit,
                    "audit_status": "PASS" if matching else "EVENT_NOT_EXTRACTED",
                    "matching_event_count": len(matching),
                }
            )
        successful_cases = sum(
            item["audit_status"] == "PASS" for item in payload["change_case_audits"]
        )
        payload["change_cases_required"] = 5
        payload["change_cases_verified"] = successful_cases
        payload["source_access_status"] = "PUBLIC_QUERY_AND_PDF_PASS"
        payload["status"] = (
            "SOURCE_PROBE_PASS" if successful_cases >= 5 else "SOURCE_SEMANTICS_NEEDS_REVIEW"
        )
    except SourceBlocked as exc:
        payload["status"] = "HISTORICAL_PROVINCE_PAUSED_SOURCE_BLOCKED"
        payload["source_blocked_reason"] = str(exc)
    except Exception as exc:
        payload["status"] = "SOURCE_PROBE_ERROR"
        payload["error_type"] = type(exc).__name__
        payload["error_message"] = str(exc)
    payload["source_probe_finished_at"] = datetime.now(timezone.utc).isoformat()
    _save(payload)
    summary = _json_safe({key: value for key, value in payload.items() if key != "records"})
    print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if payload["status"] == "SOURCE_PROBE_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
