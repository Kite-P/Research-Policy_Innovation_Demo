from __future__ import annotations

import os
import shutil
from pathlib import Path

import pandas as pd

try:
    from src.free_employee_pilot import run_employee_pilot
    from src.free_financial_pilot import run_financial_pilot
    from src.free_patent_pilot import build_patent_freshness_query, build_patent_schema_query
    from src.free_profile_pilot import build_pilot_universe, run_profile_pilot
except ModuleNotFoundError:
    from free_employee_pilot import run_employee_pilot
    from free_financial_pilot import run_financial_pilot
    from free_patent_pilot import build_patent_freshness_query, build_patent_schema_query
    from free_profile_pilot import build_pilot_universe, run_profile_pilot

ROOT = Path(__file__).parents[1]
OUTPUT_DIR = ROOT / "results" / "free_source_pilot"
CACHE_DIR = OUTPUT_DIR / "cache"


def _write(frame: pd.DataFrame, name: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUTPUT_DIR / name, index=False, encoding="utf-8-sig")


def _run_profile(pilot: pd.DataFrame) -> pd.DataFrame:
    cache_path = CACHE_DIR / "profile_pilot.csv"
    if cache_path.exists() and not os.environ.get("FREE_SOURCE_FORCE_REFRESH"):
        return pd.read_csv(cache_path, dtype={"stock_code": str})
    result = run_profile_pilot(pilot)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(cache_path, index=False, encoding="utf-8-sig")
    return result


def _run_financial(pilot: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    result_path = CACHE_DIR / "financial_pilot.csv"
    inventory_path = CACHE_DIR / "financial_schema_inventory.csv"
    if (
        result_path.exists()
        and inventory_path.exists()
        and not os.environ.get("FREE_SOURCE_FORCE_REFRESH")
    ):
        return (
            pd.read_csv(result_path, dtype={"stock_code": str}),
            pd.read_csv(inventory_path),
        )
    result, inventory = run_financial_pilot(pilot)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(result_path, index=False, encoding="utf-8-sig")
    inventory.to_csv(inventory_path, index=False, encoding="utf-8-sig")
    return result, inventory


def _run_employee(pilot: pd.DataFrame) -> pd.DataFrame:
    cache_path = CACHE_DIR / "employee_pilot.csv"
    if cache_path.exists() and not os.environ.get("FREE_SOURCE_FORCE_REFRESH"):
        return pd.read_csv(cache_path, dtype={"stock_code": str})
    result = run_employee_pilot(pilot)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(cache_path, index=False, encoding="utf-8-sig")
    return result


def _definition_audit(financial: pd.DataFrame) -> pd.DataFrame:
    audit = financial[
        [
            "stock_code",
            "exchange",
            "year",
            "revenue",
            "operating_income_narrow",
            "net_profit",
            "consolidated_net_profit_audit",
        ]
    ].copy()
    audit["revenue_pair_equal"] = (
        audit["revenue"].notna()
        & audit["operating_income_narrow"].notna()
        & audit["revenue"].eq(audit["operating_income_narrow"])
    )
    audit["netprofit_pair_equal"] = (
        audit["net_profit"].notna()
        & audit["consolidated_net_profit_audit"].notna()
        & audit["net_profit"].eq(audit["consolidated_net_profit_audit"])
    )
    return audit


def _bigquery_environment() -> dict[str, object]:
    bq = shutil.which("bq")
    gcloud = shutil.which("gcloud")
    return {
        "bq_installed": bool(bq),
        "gcloud_installed": bool(gcloud),
        "authenticated": False,
        "patent_bigquery_status": "GOOGLE_AUTH_REQUIRED" if not bq else "AUTH_CHECK_PENDING",
        "billing_enabled_by_task": False,
        "actual_query_executed": False,
        "maximum_bytes_billed": 10_000_000_000,
        "schema_query_available": bool(bq),
        "freshness_query": build_patent_freshness_query(),
        "schema_query": build_patent_schema_query(),
    }


def _profile_summary(profile: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for exchange, group in profile.groupby("exchange", dropna=False):
        total = len(group)
        rows.extend(
            {
                "exchange": exchange,
                "metric": metric,
                "value": float(group[column].notna().mean()) if total else 0.0,
                "n": int(group[column].notna().sum()),
                "denominator": total,
            }
            for metric, column in (
                ("profile_success", "profile_success"),
                ("company_name", "company_name"),
                ("industry", "industry_name"),
                ("registered_address", "registered_address"),
                ("province", "province"),
                ("former_names", "former_names"),
            )
        )
    return pd.DataFrame(rows)


def _financial_summary(financial: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for exchange, group in financial.groupby("exchange", dropna=False):
        fields = [
            "financial_success",
            "total_assets",
            "total_liabilities",
            "cash",
            "revenue",
            "net_profit",
            "rd_expense",
            "employees",
        ]
        for field in fields:
            if field == "financial_success":
                coverage = group[field].eq(True).mean() if len(group) else 0.0
            else:
                coverage = group[field].notna().mean() if len(group) else 0.0
            rows.append(
                {
                    "exchange": exchange,
                    "field": field,
                    "coverage": float(coverage),
                    "n": int(group[field].notna().sum()),
                    "denominator": len(group),
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pilot = build_pilot_universe()
    _write(pilot, "pilot_universe.csv")
    profile = _run_profile(pilot)
    profile_output = profile.merge(
        pilot[["stock_code", "stock_name"]],
        on="stock_code",
        how="left",
    )
    _write(profile_output, "profile_pilot.csv")
    _write(_profile_summary(profile), "profile_summary.csv")
    financial, inventory = _run_financial(pilot)
    _write(financial, "financial_pilot.csv")
    _write(inventory, "financial_schema_inventory.csv")
    _write(financial, "financial_pilot_resolved.csv")
    _write(_financial_summary(financial), "financial_summary.csv")
    _write(_definition_audit(financial), "financial_definition_audit.csv")
    employee = _run_employee(pilot)
    _write(employee, "employee_pilot.csv")
    patent_environment = _bigquery_environment()
    pd.DataFrame([patent_environment]).drop(columns=["freshness_query", "schema_query"]).to_csv(
        OUTPUT_DIR / "patent_environment.csv", index=False, encoding="utf-8-sig"
    )
    (OUTPUT_DIR / "patent_schema_query.sql").write_text(
        patent_environment["schema_query"], encoding="utf-8"
    )
    (OUTPUT_DIR / "patent_freshness_query.sql").write_text(
        patent_environment["freshness_query"], encoding="utf-8"
    )
    print(f"pilot_universe={len(pilot)}")
    print(f"profile_rows={len(profile)}")
    print(f"financial_rows={len(financial)}")
    print(f"patent_bigquery_status={patent_environment['patent_bigquery_status']}")


if __name__ == "__main__":
    main()
