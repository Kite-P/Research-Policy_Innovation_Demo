from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests

from .free_profile_pilot import extract_province_from_address

PROFILE_ENDPOINT = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
PROFILE_REPORT = "RPT_F10_BASIC_ORGINFO"
PROFILE_SOURCE = "EastMoney F10 RPT_F10_BASIC_ORGINFO"
EXPECTED_PROFILE_FIELDS = {
    "ORG_NAME",
    "FORMERNAME",
    "INDUSTRYCSRC1",
    "EM2016",
    "REG_ADDRESS",
    "PROVINCE",
    "LISTING_DATE",
    "ORG_CODE",
    "SECUCODE",
}


class SourceBlocked(RuntimeError):
    """Raised when the public source indicates access must stop."""


def to_eastmoney_secucode(exchange: str, stock_code: object) -> str:
    suffix = {"SSE": "SH", "SZSE": "SZ", "BSE": "BJ"}.get(str(exchange).upper())
    if suffix is None:
        raise ValueError(f"unsupported exchange: {exchange!r}")
    text = str(stock_code).strip()
    if text.endswith(".0"):
        text = text[:-2]
    if not text.isdigit():
        raise ValueError(f"invalid stock code: {stock_code!r}")
    return f"{text.zfill(6)}.{suffix}"


def _scalar(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text or None


def _normalize_province(value: Any) -> str | None:
    text = _scalar(value)
    if text is None:
        return None
    aliases = {
        "河北": "河北省",
        "山西": "山西省",
        "辽宁": "辽宁省",
        "吉林": "吉林省",
        "黑龙江": "黑龙江省",
        "江苏": "江苏省",
        "浙江": "浙江省",
        "安徽": "安徽省",
        "福建": "福建省",
        "江西": "江西省",
        "山东": "山东省",
        "河南": "河南省",
        "湖北": "湖北省",
        "湖南": "湖南省",
        "广东": "广东省",
        "海南": "海南省",
        "四川": "四川省",
        "贵州": "贵州省",
        "云南": "云南省",
        "陕西": "陕西省",
        "甘肃": "甘肃省",
        "青海": "青海省",
        "北京": "北京市",
        "天津": "天津市",
        "上海": "上海市",
        "重庆": "重庆市",
        "内蒙古": "内蒙古自治区",
        "广西": "广西壮族自治区",
        "西藏": "西藏自治区",
        "宁夏": "宁夏回族自治区",
        "新疆": "新疆维吾尔自治区",
    }
    if text in aliases:
        return aliases[text]
    if text.endswith(("省", "市", "自治区")):
        return text
    return aliases.get(text, text)


def normalize_profile_record(record: dict[str, Any], firm: pd.Series) -> dict[str, Any]:
    address = _scalar(record.get("REG_ADDRESS"))
    source_province = _normalize_province(record.get("PROVINCE"))
    address_province = extract_province_from_address(address)
    conflict = (
        source_province is not None
        and address_province is not None
        and source_province != address_province
    )
    legal_name = _scalar(record.get("ORG_NAME"))
    return {
        "firm_key": firm["firm_key"],
        "stock_code_current": str(firm["stock_code_current"]).zfill(6),
        "exchange": firm["exchange"],
        "company_name_legal": legal_name,
        "former_names_raw": _scalar(record.get("FORMERNAME")),
        "industry_csrc": _scalar(record.get("INDUSTRYCSRC1")),
        "industry_eastmoney": _scalar(record.get("EM2016")),
        "registered_address": address,
        "province_source_raw": source_province,
        "province_from_address": address_province,
        "province": None if conflict else (source_province or address_province),
        "province_conflict": bool(conflict),
        "source_listing_date": _scalar(record.get("LISTING_DATE")),
        "source_org_code": _scalar(record.get("ORG_CODE")),
        "profile_source": PROFILE_SOURCE,
        "profile_status": "LEGAL_NAME_MISSING" if legal_name is None else "PASS",
        "profile_error": None,
    }


def _safe_cache_name(firm_key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(firm_key))


def profile_cache_path(cache_dir: Path, firm_key: str) -> Path:
    return cache_dir / f"{_safe_cache_name(firm_key)}.json"


class EastMoneyProfileClient:
    def __init__(
        self,
        session: requests.Session | None = None,
        request_spacing: float = 0.8,
        retries: int = 2,
        timeout: float = 20.0,
    ) -> None:
        self.session = session or requests.Session()
        self.request_spacing = request_spacing
        self.retries = retries
        self.timeout = timeout
        self._last_request = 0.0

    def _wait_for_spacing(self) -> None:
        delay = self.request_spacing - (time.monotonic() - self._last_request)
        if delay > 0:
            time.sleep(delay)

    def _get_payload(self, secucode: str) -> dict[str, Any]:
        params = {
            "reportName": PROFILE_REPORT,
            "columns": "ALL",
            "pageNumber": 1,
            "pageSize": 1,
            "source": "HSF10",
            "client": "PC",
            "filter": f'(SECUCODE="{secucode}")',
        }
        for attempt in range(self.retries + 1):
            self._wait_for_spacing()
            self._last_request = time.monotonic()
            try:
                response = self.session.get(PROFILE_ENDPOINT, params=params, timeout=self.timeout)
            except (requests.Timeout, requests.ConnectionError):
                if attempt < self.retries:
                    continue
                raise
            text = response.text.lower()
            if response.status_code in {403, 429} or any(
                token in text for token in ("captcha", "verification")
            ):
                raise SourceBlocked(
                    f"EastMoney source blocked for {secucode}: HTTP {response.status_code}"
                )
            if 500 <= response.status_code <= 599 and attempt < self.retries:
                continue
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("success") is not True:
                raise ValueError(f"unexpected EastMoney response for {secucode}")
            return payload
        raise RuntimeError(f"request exhausted for {secucode}")

    def fetch_raw(self, secucode: str) -> dict[str, Any]:
        payload = self._get_payload(secucode)
        result = payload.get("result")
        if not isinstance(result, dict) or not isinstance(result.get("data"), list):
            raise ValueError("EastMoney response missing result.data")
        return payload

    def probe_schema(self, secucode: str) -> list[str]:
        payload = self.fetch_raw(secucode)
        data = payload["result"]["data"]
        return sorted(data[0].keys()) if data else []

    def fetch_record(self, firm: pd.Series) -> dict[str, Any]:
        secucode = to_eastmoney_secucode(firm["exchange"], firm["stock_code_current"])
        payload = self.fetch_raw(secucode)
        data = payload["result"]["data"]
        if not data:
            result = normalize_profile_record({}, firm)
            result["profile_status"] = "PROFILE_EMPTY"
            result["profile_error"] = "result.data is empty"
            return result
        return normalize_profile_record(data[0], firm)


def schema_probe(client: EastMoneyProfileClient, secucodes: Iterable[str]) -> dict[str, Any]:
    probes = {}
    for secucode in secucodes:
        fields = client.probe_schema(secucode)
        probes[secucode] = {
            "fields": fields,
            "expected_fields_present": sorted(EXPECTED_PROFILE_FIELDS.intersection(fields)),
        }
    return probes


def stable_pick(frame: pd.DataFrame, n: int, seed: str, stratum: str) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    candidates = frame.drop_duplicates("firm_key").copy()
    candidates["_stable_key"] = candidates["firm_key"].map(
        lambda value: hashlib.sha256(f"{seed}|{stratum}|{value}".encode()).hexdigest()
    )
    selected = (
        candidates.sort_values(["_stable_key", "firm_key"]).head(n).drop(columns="_stable_key")
    )
    selected = selected.copy()
    selected["pilot_stratum"] = stratum
    return selected.reset_index(drop=True)


def build_profile_pilot_sample(universe: pd.DataFrame, seed: str = "20260923") -> pd.DataFrame:
    data = universe.drop_duplicates("firm_key").copy()
    listing = pd.to_datetime(data["listing_date"], errors="coerce")
    current = data.loc[data["profile_status"].eq("LISTING_SOURCE_ONLY")].copy()
    delisted = data.loc[data["profile_status"].eq("DELISTED_PROFILE_UNAVAILABLE")].copy()
    recent_sse = current.loc[current["exchange"].eq("SSE") & listing.ge("2022-01-01")]
    recent_szse = current.loc[current["exchange"].eq("SZSE") & listing.ge("2022-01-01")]
    selected_recent_sse = stable_pick(recent_sse, 5, seed, "recent_ipo_sse")
    selected_recent_szse = stable_pick(recent_szse, 5, seed, "recent_ipo_szse")
    excluded = set(pd.concat([selected_recent_sse, selected_recent_szse])["firm_key"])
    current_base = current.loc[~current["firm_key"].isin(excluded)]
    bse = current_base.loc[current_base["exchange"].eq("BSE")]
    bse_transferred = bse.loc[bse["predecessor_listing_date"].notna()]
    bse_new = bse.loc[bse["predecessor_listing_date"].isna()]
    pieces = [
        stable_pick(current_base.loc[current_base["exchange"].eq("SSE")], 15, seed, "current_sse"),
        stable_pick(
            current_base.loc[current_base["exchange"].eq("SZSE")], 15, seed, "current_szse"
        ),
        stable_pick(bse_transferred, 10, seed, "bse_transferred"),
        stable_pick(bse_new, 10, seed, "bse_new"),
        stable_pick(delisted.loc[delisted["exchange"].eq("SSE")], 5, seed, "delisted_sse"),
        stable_pick(delisted.loc[delisted["exchange"].eq("SZSE")], 5, seed, "delisted_szse"),
        selected_recent_sse,
        selected_recent_szse,
    ]
    result = pd.concat(pieces, ignore_index=True)
    return result.drop_duplicates("firm_key").reset_index(drop=True)


def enrich_profiles(
    firms: pd.DataFrame,
    client: EastMoneyProfileClient,
    cache_dir: Path,
    progress_every: int = 0,
) -> pd.DataFrame:
    cache_dir.mkdir(parents=True, exist_ok=True)
    records = []
    unique = firms.drop_duplicates("firm_key").sort_values("firm_key")
    for index, (_, firm) in enumerate(unique.iterrows(), start=1):
        path = profile_cache_path(cache_dir, firm["firm_key"])
        if path.exists():
            records.append(json.loads(path.read_text(encoding="utf-8")))
            continue
        try:
            record = client.fetch_record(firm)
        except SourceBlocked:
            raise
        except Exception as exc:
            record = normalize_profile_record({}, firm)
            record["profile_status"] = "SOURCE_ERROR"
            record["profile_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        records.append(record)
        if progress_every and index % progress_every == 0:
            print(f"profile_enrichment_progress={index}/{len(unique)}", flush=True)
    return pd.DataFrame(records)


def merge_profiles(universe: pd.DataFrame, profiles: pd.DataFrame) -> pd.DataFrame:
    if profiles["firm_key"].duplicated().any():
        raise ValueError("profile records are not unique by firm_key")
    merged = universe.merge(
        profiles, on="firm_key", how="left", validate="many_to_one", suffixes=("", "_profile")
    )
    if len(merged) != len(universe):
        raise ValueError("profile merge changed universe row count")
    return merged
