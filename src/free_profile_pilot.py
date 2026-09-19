from __future__ import annotations

import hashlib
import time

import akshare as ak
import pandas as pd

PILOT_COUNTS = {"SSE": 8, "SZSE": 8, "BSE": 4}
PILOT_CUTOFF = pd.Timestamp("2022-01-01")

PROVINCE_NAMES = {
    "北京市": "北京市",
    "天津市": "天津市",
    "河北省": "河北省",
    "山西省": "山西省",
    "内蒙古自治区": "内蒙古自治区",
    "辽宁省": "辽宁省",
    "吉林省": "吉林省",
    "黑龙江省": "黑龙江省",
    "上海市": "上海市",
    "江苏省": "江苏省",
    "浙江省": "浙江省",
    "安徽省": "安徽省",
    "福建省": "福建省",
    "江西省": "江西省",
    "山东省": "山东省",
    "河南省": "河南省",
    "湖北省": "湖北省",
    "湖南省": "湖南省",
    "广东省": "广东省",
    "广西壮族自治区": "广西壮族自治区",
    "海南省": "海南省",
    "重庆市": "重庆市",
    "四川省": "四川省",
    "贵州省": "贵州省",
    "云南省": "云南省",
    "西藏自治区": "西藏自治区",
    "陕西省": "陕西省",
    "甘肃省": "甘肃省",
    "青海省": "青海省",
    "宁夏回族自治区": "宁夏回族自治区",
    "新疆维吾尔自治区": "新疆维吾尔自治区",
}


def normalize_stock_code(value: object) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    if not text.isdigit():
        raise ValueError(f"invalid stock code: {value!r}")
    return text.zfill(6)


def _standardize_listing_frame(frame: pd.DataFrame, exchange: str) -> pd.DataFrame:
    def first_column(names: tuple[str, ...]) -> pd.Series:
        for name in names:
            if name in frame.columns:
                return frame[name]
        return pd.Series(pd.NA, index=frame.index)

    result = pd.DataFrame(
        {
            "stock_code": first_column(("证券代码", "A股代码")),
            "stock_name": first_column(("证券简称", "A股简称")),
            "company_name": first_column(("公司全称", "证券全称")),
            "listing_date": first_column(("上市日期", "A股上市日期")),
        }
    )
    result["stock_code"] = result["stock_code"].map(normalize_stock_code)
    result["exchange"] = exchange
    result["listing_date"] = pd.to_datetime(result["listing_date"], errors="coerce")
    return result[["stock_code", "stock_name", "company_name", "exchange", "listing_date"]]


def _fetch_exchange_listings() -> dict[str, pd.DataFrame]:
    sse = pd.concat(
        [
            ak.stock_info_sh_name_code(symbol="主板A股"),
            ak.stock_info_sh_name_code(symbol="科创板"),
        ],
        ignore_index=True,
    )
    return {
        "SSE": _standardize_listing_frame(sse, "SSE"),
        "SZSE": _standardize_listing_frame(
            ak.stock_info_sz_name_code(symbol="A股列表"), "SZSE"
        ),
        "BSE": _standardize_listing_frame(ak.stock_info_bj_name_code(), "BSE"),
    }


def stable_pick(
    frame: pd.DataFrame,
    exchange: str,
    n: int,
    seed: str = "20260919",
) -> pd.DataFrame:
    candidates = frame.loc[frame["exchange"].eq(exchange)].copy()
    candidates = candidates.loc[candidates["listing_date"].le(PILOT_CUTOFF)].copy()
    candidates = candidates.drop_duplicates(subset=["stock_code"])
    if len(candidates) < n:
        raise ValueError(f"not enough {exchange} listings before {PILOT_CUTOFF.date()}")
    candidates["_stable_key"] = candidates["stock_code"].map(
        lambda code: hashlib.sha256(f"{seed}|{exchange}|{code}".encode()).hexdigest()
    )
    selected = candidates.sort_values(["_stable_key", "stock_code"]).head(n).copy()
    selected["pilot_rank"] = range(1, n + 1)
    return selected.drop(columns="_stable_key").reset_index(drop=True)


def build_pilot_universe() -> pd.DataFrame:
    listings = _fetch_exchange_listings()
    selected = [
        stable_pick(listings[exchange], exchange, n) for exchange, n in PILOT_COUNTS.items()
    ]
    result = pd.concat(selected, ignore_index=True)
    result = result.sort_values(["exchange", "pilot_rank"]).reset_index(drop=True)
    return result[["stock_code", "stock_name", "exchange", "listing_date", "pilot_rank"]]


def extract_province_from_address(address: object) -> str | None:
    if address is None or pd.isna(address):
        return None
    text = str(address).strip()
    if "（上海）" in text or "(上海)" in text:
        return "上海市"
    for name in sorted(PROVINCE_NAMES, key=len, reverse=True):
        if name in text:
            return name
    return None


def _call_profile(stock_code: str) -> pd.DataFrame:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            return ak.stock_profile_cninfo(symbol=stock_code)
        except Exception as exc:  # network libraries expose different exception classes
            last_error = exc
            message = str(exc).lower()
            if any(token in message for token in ("403", "429", "captcha", "verification")):
                break
            if attempt < 2 and any(
                token in message
                for token in ("timeout", "connection", "reset", "500", "502", "503", "504")
            ):
                time.sleep(1.0)
                continue
            break
    if last_error is not None:
        raise last_error
    return pd.DataFrame()


def fetch_profile_record(exchange: str, stock_code: str) -> dict[str, object]:
    stock_code = normalize_stock_code(stock_code)
    base: dict[str, object] = {
        "stock_code": stock_code,
        "exchange": exchange,
        "profile_success": False,
        "company_name": None,
        "former_names": None,
        "industry_name": None,
        "listing_date": None,
        "registered_address": None,
        "province": None,
        "province_source": "registered_address_static",
        "profile_source": "AKShare.stock_profile_cninfo",
        "profile_error": None,
    }
    try:
        frame = _call_profile(stock_code)
        if frame.empty:
            base["profile_error"] = (
                "cninfo_profile_unavailable_for_bse" if exchange == "BSE" else "empty_profile"
            )
            return base
        row = frame.iloc[0]
        address = row.get("注册地址")
        base.update(
            {
                "profile_success": True,
                "company_name": row.get("公司名称"),
                "former_names": row.get("曾用简称"),
                "industry_name": row.get("所属行业"),
                "listing_date": row.get("上市日期"),
                "registered_address": address,
                "province": extract_province_from_address(address),
            }
        )
    except Exception as exc:
        base["profile_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
    return base


def run_profile_pilot(pilot: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for index, row in pilot.iterrows():
        rows.append(fetch_profile_record(row["exchange"], row["stock_code"]))
        if index < len(pilot) - 1:
            time.sleep(1.0)
    return pd.DataFrame(rows)
