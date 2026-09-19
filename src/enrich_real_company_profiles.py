from __future__ import annotations

import json
import time
from pathlib import Path

import akshare as ak
import pandas as pd

try:
    from .free_profile_pilot import extract_province_from_address
except ImportError:
    from free_profile_pilot import extract_province_from_address


def normalize_profile_response(
    frame: pd.DataFrame,
    exchange: str,
    stock_code: str,
    firm_key: str,
    delisted: bool = False,
) -> dict[str, object]:
    def scalar(value: object) -> object:
        return None if value is None or pd.isna(value) else value

    if frame.empty:
        return {
            "firm_key": firm_key,
            "exchange": exchange,
            "stock_code_current": str(stock_code).zfill(6),
            "company_name_legal": None,
            "former_names_raw": None,
            "industry_name": None,
            "registered_address": None,
            "province": None,
            "profile_source": "AKShare.stock_profile_cninfo",
            "profile_status": "DELISTED_PROFILE_UNAVAILABLE" if delisted else "UNAVAILABLE",
        }
    row = frame.iloc[0]
    legal_name = scalar(row.get("公司名称"))
    address = scalar(row.get("注册地址"))
    return {
        "firm_key": firm_key,
        "exchange": exchange,
        "stock_code_current": str(stock_code).zfill(6),
        "company_name_legal": None if pd.isna(legal_name) else str(legal_name).strip(),
        "former_names_raw": scalar(row.get("曾用简称")),
        "industry_name": scalar(row.get("所属行业")),
        "registered_address": address,
        "province": extract_province_from_address(address),
        "profile_source": "AKShare.stock_profile_cninfo",
        "profile_status": "PASS",
    }


def _cache_path(cache_dir: Path, firm_key: str) -> Path:
    safe = firm_key.replace(":", "_")
    return cache_dir / f"{safe}.json"


def fetch_profile_record(row: pd.Series) -> dict[str, object]:
    try:
        frame = ak.stock_profile_cninfo(symbol=str(row["stock_code_current"]).zfill(6))
        return normalize_profile_response(
            frame,
            row["exchange"],
            row["stock_code_current"],
            row["firm_key"],
            delisted=row.get("profile_status") == "DELISTED_PROFILE_UNAVAILABLE",
        )
    except Exception as exc:
        return {
            "firm_key": row["firm_key"],
            "exchange": row["exchange"],
            "stock_code_current": str(row["stock_code_current"]).zfill(6),
            "company_name_legal": None,
            "former_names_raw": None,
            "industry_name": None,
            "registered_address": None,
            "province": None,
            "profile_source": "AKShare.stock_profile_cninfo",
            "profile_status": "DELISTED_PROFILE_UNAVAILABLE"
            if row.get("profile_status") == "DELISTED_PROFILE_UNAVAILABLE"
            else f"ERROR:{type(exc).__name__}",
        }


def enrich_profiles(
    firms: pd.DataFrame,
    cache_dir: Path,
    request_spacing: float = 1.0,
) -> pd.DataFrame:
    cache_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    unique = firms.drop_duplicates("firm_key").sort_values(["exchange", "firm_key"])
    for index, (_, firm) in enumerate(unique.iterrows()):
        path = _cache_path(cache_dir, firm["firm_key"])
        if path.exists():
            result = json.loads(path.read_text(encoding="utf-8"))
        else:
            result = fetch_profile_record(firm)
            path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        rows.append(result)
        if index < len(unique) - 1:
            time.sleep(request_spacing)
    return pd.DataFrame(rows)


def profile_pilot_sample(current: pd.DataFrame, delisted: pd.DataFrame) -> pd.DataFrame:
    current = current.loc[current["profile_status"].eq("LISTING_SOURCE_ONLY")]
    selected = pd.concat(
        [
            current.loc[current["exchange"].eq("SSE")].head(20),
            current.loc[current["exchange"].eq("SZSE")].head(20),
            current.loc[current["exchange"].eq("BSE")].head(10),
            delisted.head(10),
        ],
        ignore_index=True,
    )
    return selected.drop_duplicates("firm_key")
