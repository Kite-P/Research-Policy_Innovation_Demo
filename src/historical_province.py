from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from datetime import date

import pandas as pd

HISTORICAL_STATUSES = {
    "historical_confirmed",
    "historical_inferred",
    "static_fallback_only",
    "missing",
}

PROVINCE_ALIASES = {
    "北京": "北京市", "京": "北京市", "天津": "天津市", "津": "天津市",
    "上海": "上海市", "沪": "上海市", "重庆": "重庆市", "渝": "重庆市",
    "河北": "河北省", "冀": "河北省", "山西": "山西省", "晋": "山西省",
    "内蒙古": "内蒙古自治区", "蒙": "内蒙古自治区", "辽宁": "辽宁省", "辽": "辽宁省",
    "吉林": "吉林省", "吉": "吉林省", "黑龙江": "黑龙江省", "黑": "黑龙江省",
    "江苏": "江苏省", "苏": "江苏省", "浙江": "浙江省", "浙": "浙江省",
    "安徽": "安徽省", "皖": "安徽省", "福建": "福建省", "闽": "福建省",
    "江西": "江西省", "赣": "江西省", "山东": "山东省", "鲁": "山东省",
    "河南": "河南省", "豫": "河南省", "湖北": "湖北省", "鄂": "湖北省",
    "湖南": "湖南省", "湘": "湖南省", "广东": "广东省", "粤": "广东省",
    "广西": "广西壮族自治区", "桂": "广西壮族自治区", "海南": "海南省", "琼": "海南省",
    "四川": "四川省", "川": "四川省", "贵州": "贵州省", "黔": "贵州省",
    "云南": "云南省", "滇": "云南省", "西藏": "西藏自治区", "藏": "西藏自治区",
    "陕西": "陕西省", "陕": "陕西省", "甘肃": "甘肃省", "甘": "甘肃省", "陇": "甘肃省",
    "青海": "青海省", "青": "青海省", "宁夏": "宁夏回族自治区", "宁": "宁夏回族自治区",
    "新疆": "新疆维吾尔自治区", "新": "新疆维吾尔自治区", "台湾": "台湾省",
    "香港": "香港特别行政区", "澳门": "澳门特别行政区",
}

# Explicit prefecture-level city mapping; unmapped cities intentionally remain missing.
CITY_TO_PROVINCE = {
    "石家庄市": "河北省", "唐山市": "河北省", "秦皇岛市": "河北省", "邯郸市": "河北省",
    "邢台市": "河北省", "保定市": "河北省", "张家口市": "河北省", "承德市": "河北省",
    "沧州市": "河北省", "廊坊市": "河北省", "衡水市": "河北省",
    "太原市": "山西省", "大同市": "山西省", "长治市": "山西省", "晋城市": "山西省",
    "呼和浩特市": "内蒙古自治区", "包头市": "内蒙古自治区", "鄂尔多斯市": "内蒙古自治区",
    "沈阳市": "辽宁省", "大连市": "辽宁省", "鞍山市": "辽宁省", "锦州市": "辽宁省",
    "长春市": "吉林省", "吉林市": "吉林省", "哈尔滨市": "黑龙江省", "大庆市": "黑龙江省",
    "南京市": "江苏省", "无锡市": "江苏省", "徐州市": "江苏省", "常州市": "江苏省",
    "苏州市": "江苏省", "南通市": "江苏省", "连云港市": "江苏省", "淮安市": "江苏省",
    "盐城市": "江苏省", "扬州市": "江苏省", "镇江市": "江苏省", "泰州市": "江苏省",
    "宿迁市": "江苏省", "杭州市": "浙江省", "宁波市": "浙江省", "温州市": "浙江省",
    "嘉兴市": "浙江省", "湖州市": "浙江省", "绍兴市": "浙江省", "金华市": "浙江省",
    "衢州市": "浙江省", "舟山市": "浙江省", "台州市": "浙江省", "丽水市": "浙江省",
    "合肥市": "安徽省", "芜湖市": "安徽省", "蚌埠市": "安徽省", "福州市": "福建省",
    "厦门市": "福建省", "泉州市": "福建省", "南昌市": "江西省", "九江市": "江西省",
    "济南市": "山东省", "青岛市": "山东省", "淄博市": "山东省", "烟台市": "山东省",
    "潍坊市": "山东省", "济宁市": "山东省", "临沂市": "山东省", "郑州市": "河南省",
    "洛阳市": "河南省", "武汉市": "湖北省", "宜昌市": "湖北省", "襄阳市": "湖北省",
    "长沙市": "湖南省", "株洲市": "湖南省", "湘潭市": "湖南省", "广州市": "广东省",
    "深圳市": "广东省", "珠海市": "广东省", "佛山市": "广东省", "东莞市": "广东省",
    "中山市": "广东省", "惠州市": "广东省", "江门市": "广东省", "南宁市": "广西壮族自治区",
    "海口市": "海南省", "湛江市": "广东省", "成都市": "四川省",
    "绵阳市": "四川省", "宜宾市": "四川省", "龙岩市": "福建省",
    "贵阳市": "贵州省", "昆明市": "云南省", "拉萨市": "西藏自治区", "西安市": "陕西省",
    "兰州市": "甘肃省", "西宁市": "青海省", "银川市": "宁夏回族自治区",
    "乌鲁木齐市": "新疆维吾尔自治区",
}


def normalize_province(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = re.sub(r"\s+", "", str(value)).strip("，,。；;\t")
    if not text:
        return None
    if text in PROVINCE_ALIASES:
        return PROVINCE_ALIASES[text]
    for alias, normalized in sorted(PROVINCE_ALIASES.items(), key=lambda item: -len(item[0])):
        if text.startswith(alias) and alias in {"内蒙古", "广西", "西藏", "宁夏", "新疆"}:
            return normalized
    if text.endswith(("省", "市", "自治区", "特别行政区")):
        return text
    return None


def province_from_address(address: object) -> str | None:
    if address is None or pd.isna(address):
        return None
    text = re.sub(r"\s+", "", str(address)).lstrip("“”‘’\"'")
    text = re.sub(r"^中国", "", text).lstrip("（(")
    for name, province in sorted(PROVINCE_ALIASES.items(), key=lambda item: -len(item[0])):
        if text.startswith(name):
            return province
    for city, province in sorted(CITY_TO_PROVINCE.items(), key=lambda item: -len(item[0])):
        if city in text[:24]:
            return province
    return None


def build_historical_province_target(universe: pd.DataFrame) -> pd.DataFrame:
    required = {"firm_key", "exchange", "year"}
    missing = required.difference(universe.columns)
    if missing:
        raise ValueError(f"missing universe columns: {sorted(missing)}")
    frame = universe.loc[
        universe["exchange"].isin(["SSE", "SZSE"])
        & universe["year"].between(2020, 2025)
    ].copy()
    if "is_financial_industry" in frame:
        frame = frame.loc[~frame["is_financial_industry"].fillna(True)]
    if "industry_known" in frame:
        frame = frame.loc[frame["industry_known"].fillna(False)]
    if frame.duplicated(["firm_key", "year"]).any():
        raise ValueError("duplicate source firm-year keys")
    frame["year"] = frame["year"].astype(int)
    for column in (
        "stock_code_current", "company_name_legal", "market_listing_date", "listing_date",
        "delisting_date", "industry_csrc", "registered_address", "province_profile",
    ):
        if column not in frame:
            frame[column] = pd.NA
    frame["province_historical"] = pd.NA
    frame["province_status"] = "missing"
    frame["province_source_tier"] = pd.NA
    frame["province_source_name"] = pd.NA
    frame["province_source_year"] = pd.NA
    frame["province_effective_date"] = pd.NaT
    frame["province_static_current"] = frame["province_profile"].map(normalize_province)
    frame["province_static_agrees"] = pd.NA
    frame["province_conflict"] = False
    frame["province_missing_reason"] = "source_not_yet_resolved"
    return frame.sort_values(["exchange", "firm_key", "year"]).reset_index(drop=True)


def _stable_rank(seed: str, stratum: str, firm_key: str) -> str:
    return hashlib.sha256(f"{seed}|{stratum}|{firm_key}".encode("utf-8")).hexdigest()


def select_historical_province_pilot(
    firms: pd.DataFrame,
    seed: str = "20260925",
) -> pd.DataFrame:
    frame = firms.drop_duplicates("firm_key").copy()
    if "current_status" not in frame:
        frame["current_status"] = frame["delisting_date"].isna().map(
            {True: "current", False: "delisted"}
        )
    listing = pd.to_datetime(frame["market_listing_date"], errors="coerce")
    recent = listing.ge(pd.Timestamp("2020-01-01"))
    current = frame["current_status"].eq("current")
    delisted = frame["current_status"].eq("delisted")
    sse = frame["exchange"].eq("SSE")
    szse = frame["exchange"].eq("SZSE")
    masks = {
        "SSE_current": sse & current & ~recent,
        "SZSE_current": szse & current & ~recent,
        "SSE_delisted": sse & delisted,
        "SZSE_delisted": szse & delisted,
        "SSE_recent_IPO": sse & current & recent,
        "SZSE_recent_IPO": szse & current & recent,
    }
    quotas = {
        "SSE_current": 25, "SZSE_current": 25, "SSE_delisted": 10,
        "SZSE_delisted": 10, "SSE_recent_IPO": 5, "SZSE_recent_IPO": 5,
    }
    selected = []
    for stratum, mask in masks.items():
        candidates = frame.loc[mask].copy()
        candidates["_rank"] = candidates["firm_key"].astype(str).map(
            lambda key: _stable_rank(seed, stratum, key)
        )
        chosen = (
            candidates.sort_values(["_rank", "firm_key"])
            .head(quotas[stratum])
            .drop(columns="_rank")
        )
        chosen["pilot_stratum"] = stratum
        chosen["pilot_target_firms"] = quotas[stratum]
        chosen["pilot_actual_firms"] = len(chosen)
        selected.append(chosen)
    if not selected:
        return frame.iloc[0:0].assign(pilot_stratum=pd.Series(dtype=str))
    result = pd.concat(selected, ignore_index=True)
    if result["firm_key"].duplicated().any():
        raise ValueError("pilot strata overlap; duplicate firms selected")
    return result.sort_values(["pilot_stratum", "firm_key"]).reset_index(drop=True)


def assign_historical_province_chunks(
    firms: pd.DataFrame, chunk_size: int = 100
) -> dict[str, list[str]]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    if firms["firm_key"].duplicated().any():
        raise ValueError("firm manifest must contain unique firm_key values")
    keys = sorted(firms["firm_key"].astype(str))
    return {
        f"province_{index // chunk_size + 1:03d}": keys[index : index + chunk_size]
        for index in range(0, len(keys), chunk_size)
    }


def classify_static_profile(province: object, year: int) -> dict[str, object]:
    normalized = normalize_province(province)
    return {
        "year": int(year),
        "province_historical": None,
        "province_static_current": normalized,
        "historical_status": "static_fallback_only" if normalized else "missing",
    }


def infer_province_for_year(
    events: Iterable[Mapping[str, object]], year: int
) -> dict[str, object]:
    year_end = date(int(year), 12, 31)
    usable = []
    for event in events:
        effective = event.get("effective_date")
        if effective is None or pd.isna(effective):
            continue
        try:
            effective_date = pd.Timestamp(effective).date()
        except (TypeError, ValueError):
            continue
        old_province = normalize_province(event.get("old_province"))
        new_province = normalize_province(event.get("new_province"))
        if old_province and new_province:
            usable.append((effective_date, old_province, new_province))
    if not usable:
        return {"province": None, "historical_status": "missing", "effective_date": None}
    usable.sort(key=lambda row: row[0])
    before_year_end = [row for row in usable if row[0] <= year_end]
    if before_year_end:
        effective_date, _, province = before_year_end[-1]
    else:
        effective_date, province, _ = usable[0]
    return {
        "province": province,
        "historical_status": "historical_inferred",
        "effective_date": effective_date.isoformat(),
    }


TIER_ORDER = {"H1": 0, "H2": 1, "H3": 2, "S": 3}


def choose_preferred_candidate(
    candidates: Iterable[Mapping[str, object]],
) -> tuple[dict[str, object] | None, bool]:
    records = [dict(item) for item in candidates if item.get("province")]
    provinces = {str(item["province"]) for item in records}
    conflict = len(provinces) > 1
    if not records:
        return None, conflict
    best_tier = min(TIER_ORDER.get(str(item.get("source_tier")), 99) for item in records)
    top = [
        item
        for item in records
        if TIER_ORDER.get(str(item.get("source_tier")), 99) == best_tier
    ]
    if len({str(item["province"]) for item in top}) > 1:
        return None, True
    return top[0], conflict


def resolve_historical_province_panel(
    target: pd.DataFrame,
    source_records: Iterable[Mapping[str, object]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Join source candidates to every legal key; never remove missing firm-years."""
    from .historical_province_sources import parse_address_change_events

    panel = target.copy().reset_index(drop=True)
    if "province_static_current" not in panel:
        static_source = panel["province_profile"] if "province_profile" in panel else pd.Series(
            None, index=panel.index
        )
        panel["province_static_current"] = static_source.map(normalize_province)
    if "current_status" not in panel:
        if "delisting_date" in panel:
            panel["current_status"] = panel["delisting_date"].isna().map(
                {True: "current", False: "delisted"}
            )
        else:
            panel["current_status"] = "current"
    if "pilot_stratum" not in panel:
        panel["pilot_stratum"] = pd.NA
    if panel.duplicated(["firm_key", "year"]).any():
        raise ValueError("target has duplicate firm-year keys")
    records = [dict(row) for row in source_records]
    by_firm: dict[str, list[dict[str, object]]] = {}
    for record in records:
        by_firm.setdefault(str(record.get("firm_key")), []).append(record)
    for firm_key, group in by_firm.items():
        if firm_key not in set(panel["firm_key"].astype(str)):
            raise ValueError(f"source record outside target firm set: {firm_key}")

    out_rows = []
    conflict_rows = []
    for row in panel.to_dict("records"):
        firm_key = str(row["firm_key"])
        year = int(row["year"])
        firm_records = by_firm.get(firm_key, [])
        year_records = [
            record
            for record in firm_records
            if int(record.get("source_report_year", -1)) == year
            and record.get("source_url_or_id")
        ]
        candidates = []
        for record in year_records:
            province = province_from_address(record.get("province_raw"))
            if province:
                candidates.append(
                    {
                        "province": province,
                        "source_tier": str(record.get("source_tier") or "H1"),
                        "source_id": record.get("source_url_or_id"),
                        "source_record": record,
                    }
                )

        events = []
        for record in firm_records:
            history = record.get("registered_address_history_raw")
            for event in parse_address_change_events(str(history) if history else None):
                old_address = event["old_address"]
                new_address = event["new_address"]
                if new_address in {"现址", "现地址", "新址"}:
                    new_address = str(record.get("province_raw") or new_address)
                old_province = province_from_address(old_address)
                new_province = province_from_address(new_address)
                if old_province and new_province:
                    events.append(
                        {
                            "old_province": old_province,
                            "new_province": new_province,
                            "old_address": old_address,
                            "new_address": new_address,
                            "effective_date": event["effective_date"],
                            "source_url_or_id": record.get("source_url_or_id"),
                            "source_report_year": record.get("source_report_year"),
                            "source_record": record,
                        }
                    )

        inferred = infer_province_for_year(events, year) if events else None
        matching_future_events = [
            event for event in events if str(event["effective_date"])[:4] > str(year)
        ]
        preferred, conflict = choose_preferred_candidate(candidates)
        temporal_adjusted = False
        selected = None
        status = "missing"
        source_tier = None
        source_name = None
        source_year = None
        effective_date = None
        missing_reason = "annual_report_or_dated_event_not_found"
        selected_record = None
        source_effective_date = None
        registered_address_raw = None
        source_url_or_id = None
        source_report_date = None
        extraction_method = None
        inference_rule = None
        source_type = None

        if inferred and inferred["province"]:
            selected = inferred["province"]
            status = "historical_inferred"
            effective_date = inferred["effective_date"]
            if preferred and preferred["province"] != selected:
                if matching_future_events:
                    temporal_adjusted = True
                    conflict = False
                else:
                    conflict = True
                    selected = None
                    status = "missing"
                    missing_reason = "unresolved_source_conflict"
            source_event = next(
                (
                    event
                    for event in events
                    if event["effective_date"] == effective_date
                    and (
                        event["old_province"] == selected
                        or event["new_province"] == selected
                    )
                ),
                None,
            )
            if source_event:
                source_tier = "H2"
                source_name = "CNINFO dated registered-address history"
                source_year = source_event["source_report_year"]
                selected_record = source_event["source_record"]
                source_effective_date = effective_date
                registered_address_raw = (
                    source_event["old_address"]
                    if source_event["old_province"] == selected
                    else source_event["new_address"]
                )
                source_url_or_id = source_event["source_url_or_id"]
                source_report_date = selected_record.get("source_report_date")
                extraction_method = "dated_address_change_text"
                source_type = "official_address_change_event"
                inference_rule = "effective_date_on_or_before_firm_year_end"
        elif preferred:
            selected = preferred["province"]
            source_record = preferred["source_record"]
            selected_record = source_record
            status = "historical_confirmed"
            source_tier = preferred["source_tier"]
            source_name = str(source_record.get("source_name") or "CNINFO official annual report")
            source_year = int(source_record["source_report_year"])
            registered_address_raw = source_record.get("province_raw")
            source_url_or_id = source_record.get("source_url_or_id")
            source_report_date = source_record.get("source_report_date")
            extraction_method = source_record.get("extraction_method")
            source_type = source_record.get("source_type")
            inference_rule = "year_specific_annual_report_snapshot"
            missing_reason = None
        elif conflict:
            missing_reason = "unresolved_source_conflict"

        if selected is None:
            static_value = normalize_province(row.get("province_static_current"))
            if static_value:
                status = "static_fallback_only"
                missing_reason = "historical_source_not_verified"

        row["province_historical"] = selected
        row["province_status"] = status
        row["province_source_tier"] = source_tier
        row["province_source_name"] = source_name
        row["province_source_year"] = source_year
        row["province_effective_date"] = effective_date
        row["source_effective_date"] = source_effective_date
        row["province_raw"] = (
            selected_record.get("province_raw") if selected_record else None
        )
        row["province_normalized"] = selected
        row["registered_address_raw"] = registered_address_raw
        row["source_type"] = source_type
        row["source_url_or_id"] = source_url_or_id
        row["source_report_date"] = source_report_date
        row["extraction_method"] = extraction_method
        row["fallback_level"] = "S" if status == "static_fallback_only" else None
        row["evidence_quality"] = source_tier
        row["inference_rule"] = inference_rule
        row["province_static_current"] = normalize_province(row.get("province_static_current"))
        row["province_static_agrees"] = (
            selected == row["province_static_current"] if selected else pd.NA
        )
        row["province_conflict"] = bool(conflict)
        row["province_missing_reason"] = missing_reason
        row["province_source_temporal_adjusted"] = bool(temporal_adjusted)
        out_rows.append(row)
        if conflict:
            for candidate in candidates:
                candidate_record = candidate["source_record"]
                conflict_rows.append(
                    {
                        "firm_key": firm_key,
                        "year": year,
                        "candidate_province": candidate["province"],
                        "source_tier": candidate["source_tier"],
                        "source_url_or_id": candidate["source_id"],
                        "source_report_year": candidate_record.get("source_report_year"),
                        "preferred_candidate": (
                            candidate["source_id"] == (preferred or {}).get("source_id")
                        ),
                        "conflict_flag": True,
                    }
                )
    result = pd.DataFrame(out_rows)
    conflicts = pd.DataFrame(conflict_rows)
    if len(result) != len(target) or set(zip(result.firm_key, result.year)) != set(
        zip(target.firm_key, target.year)
    ):
        raise ValueError("historical province panel does not preserve the target key set")
    return result, conflicts


def summarize_historical_province_coverage(panel: pd.DataFrame) -> pd.DataFrame:
    frame = panel.copy()
    frame["is_historical"] = frame["province_status"].isin(
        {"historical_confirmed", "historical_inferred"}
    )
    rows = []
    groups = {
        "all": pd.Series(True, index=frame.index),
        "SSE_current": frame["exchange"].eq("SSE") & frame["current_status"].eq("current"),
        "SZSE_current": frame["exchange"].eq("SZSE") & frame["current_status"].eq("current"),
        "SSE_delisted": frame["exchange"].eq("SSE") & frame["current_status"].eq("delisted"),
        "SZSE_delisted": frame["exchange"].eq("SZSE") & frame["current_status"].eq("delisted"),
    }
    if "market_listing_date" in frame:
        recent = pd.to_datetime(frame["market_listing_date"], errors="coerce").ge(
            pd.Timestamp("2020-01-01")
        )
        for exchange in ("SSE", "SZSE"):
            groups[f"{exchange}_recent_IPO"] = (
                frame["exchange"].eq(exchange)
                & frame["current_status"].eq("current")
                & recent
            )
    elif "pilot_stratum" in frame and frame["pilot_stratum"].notna().any():
        for stratum in ("SSE_recent_IPO", "SZSE_recent_IPO"):
            groups[stratum] = frame["pilot_stratum"].eq(stratum)
    for stratum, mask in groups.items():
        group = frame.loc[mask]
        denominator = len(group)
        counts = group["province_status"].value_counts()
        rows.append(
            {
                "stratum": stratum,
                "firms": int(group["firm_key"].nunique()),
                "firm_years": denominator,
                "historical_confirmed": int(counts.get("historical_confirmed", 0)),
                "historical_inferred": int(counts.get("historical_inferred", 0)),
                "confirmed_plus_inferred": int(group["is_historical"].sum()),
                "historical_coverage": float(group["is_historical"].mean()) if denominator else 0.0,
                "static_fallback_only": int(counts.get("static_fallback_only", 0)),
                "missing": int(counts.get("missing", 0)),
                "conflicts": int(group["province_conflict"].sum()),
                "conflict_rate": float(group["province_conflict"].mean()) if denominator else 0.0,
            }
        )
    return pd.DataFrame(rows)


def build_policy_geography_coverage(
    panel: pd.DataFrame, policy_provinces: Iterable[str]
) -> pd.DataFrame:
    accepted = {normalize_province(value) for value in policy_provinces}
    accepted.discard(None)
    historical = panel.loc[
        panel["province_status"].isin({"historical_confirmed", "historical_inferred"})
        & panel["province_historical"].notna()
    ]
    rows = historical.groupby("province_historical", dropna=True).agg(
        firms=("firm_key", "nunique"), firm_years=("year", "size")
    )
    result = rows.reset_index().rename(columns={"province_historical": "province"})
    result["existing_policy_corpus_available"] = result["province"].isin(accepted)
    result["primary_historical_firm_years"] = result["firm_years"]
    return result.sort_values("province").reset_index(drop=True)


def evaluate_historical_province_pilot_gate(
    panel: pd.DataFrame,
    change_cases_verified: int,
) -> tuple[str, dict[str, object]]:
    coverage = summarize_historical_province_coverage(panel)
    indexed = coverage.set_index("stratum")
    current_sse = float(indexed.loc["SSE_current", "historical_coverage"])
    current_szse = float(indexed.loc["SZSE_current", "historical_coverage"])
    duplicates = int(panel.duplicated(["firm_key", "year"]).sum())
    illegal_mask = ~panel["exchange"].isin(["SSE", "SZSE"]) | ~panel["year"].between(
        2020, 2025
    )
    illegal = int(illegal_mask.sum())
    conflict_rate = float(panel["province_conflict"].mean()) if len(panel) else 0.0
    gate = {
        "SSE_current_coverage": current_sse,
        "SZSE_current_coverage": current_szse,
        "duplicate_keys": duplicates,
        "illegal_firm_years": illegal,
        "unresolved_conflict_rate": conflict_rate,
        "change_cases_verified": int(change_cases_verified),
        "source_semantics_verified": int(change_cases_verified) >= 5,
        "post_period_snapshot_adjustments": int(
            panel.get(
                "province_source_temporal_adjusted", pd.Series(False, index=panel.index)
            ).sum()
        ),
    }
    passed = (
        current_sse >= 0.90
        and current_szse >= 0.90
        and duplicates == 0
        and illegal == 0
        and gate["source_semantics_verified"]
        and conflict_rate <= 0.01
    )
    return (
        "HISTORICAL_PROVINCE_PILOT_PASS" if passed else "HISTORICAL_PROVINCE_SOURCE_NEEDS_FIX",
        gate,
    )
