from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.historical_province import build_historical_province_target  # noqa: E402
from src.historical_province_sources import (  # noqa: E402
    CACHE_FORMAT_VERSION,
    CNINFOAnnualReportClient,
    SourceBlocked,
)

UNIVERSE = ROOT / "data" / "processed" / "real_company_universe_enriched.parquet"
OUTPUT = ROOT / "results" / "historical_province"
REFRESH_REASONS = {"annual_report_not_found", "registered_address_field_not_found"}


def run() -> int:
    target = build_historical_province_target(pd.read_parquet(UNIVERSE))
    firms = target.sort_values("firm_key").drop_duplicates("firm_key")
    cache_dir = OUTPUT / "cache"
    refresh_by_firm: dict[str, set[int]] = {}
    for cache_path in sorted(cache_dir.glob("*.json")):
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        if cache.get("cache_format_version") == CACHE_FORMAT_VERSION:
            continue
        for record in cache.get("records", []):
            if record.get("missing_reason") in REFRESH_REASONS:
                refresh_by_firm.setdefault(str(record["firm_key"]), set()).add(
                    int(record["source_report_year"])
                )

    refresh_by_firm = {
        firm_key: years
        for firm_key, years in refresh_by_firm.items()
        if firm_key in set(firms.firm_key)
    }
    client = CNINFOAnnualReportClient(cache_dir, request_spacing=1.0)
    complete = 0
    title_audit = []
    for firm_key, years_to_refresh in sorted(refresh_by_firm.items()):
        firm_rows = firms.loc[firms.firm_key.eq(firm_key)]
        firm = firm_rows.iloc[0].to_dict()
        legal_years = sorted(
            target.loc[target.firm_key.eq(firm_key), "year"].astype(int).tolist()
        )
        try:
            client.fetch_firm_reports(
                firm,
                years=legal_years,
                refresh_years=years_to_refresh,
            )
        except SourceBlocked as exc:
            print(f"SOURCE_BLOCKED firm_key={firm_key} reason={exc}", flush=True)
            return 2
        title_audit.extend(client.last_annual_report_query_audit)
        complete += 1
        if complete % 25 == 0 or complete == len(refresh_by_firm):
            print(
                f"PROGRESS affected_firms={complete}/{len(refresh_by_firm)} "
                f"refreshed_years={sum(map(len, refresh_by_firm.values()))}",
                flush=True,
            )
    audit_frame = pd.DataFrame(title_audit).drop_duplicates()
    if len(audit_frame):
        audit_frame = audit_frame.loc[audit_frame.report_year.ge(2020)]
    audit_frame.to_csv(
        OUTPUT / "title_matcher_query_audit.csv", index=False, encoding="utf-8-sig"
    )
    print(
        f"TARGETED_FAILURE_REFRESH_COMPLETE affected_firms={len(refresh_by_firm)} "
        f"affected_years={sum(map(len, refresh_by_firm.values()))}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
