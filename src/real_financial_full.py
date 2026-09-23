from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .build_real_financial_panel import (
    CORE_FIELDS,
    SourceBlocked,
    _empty_financial_rows,
    construct_variables,
    fetch_company_with_fallback,
    financial_cache_path,
)
from .real_financial_gate import add_industry_flags

REQUIRED_CACHE_FIELDS = {
    "exchange",
    "firm_key",
    "stock_code_current",
    "year",
    "financial_query_code",
    *CORE_FIELDS,
    "rd_expense",
    "financial_success",
    "failure_reason",
}
PHASE_A = "sse_szse_nonfinancial"
PHASE_B = "bse_nonfinancial_pending_mapping"
EXCLUDED = "excluded_financial"


def universe_fingerprint(universe: pd.DataFrame) -> str:
    pairs = universe[["firm_key", "year"]].drop_duplicates().copy()
    values = pairs.assign(year=pairs["year"].astype(int)).sort_values(["firm_key", "year"])
    payload = "\n".join(f"{row.firm_key}|{row.year}" for row in values.itertuples())
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_full_financial_target(universe: pd.DataFrame) -> pd.DataFrame:
    enriched = add_industry_flags(universe) if "industry_known" not in universe else universe.copy()
    firm_columns = [
        "firm_key",
        "exchange",
        "stock_code_current",
        "company_name_legal",
        "market_listing_date",
        "listing_date",
        "delisting_date",
        "industry_csrc",
        "industry_known",
        "is_financial_industry",
        "bse_mapping_status",
    ]
    available = [column for column in firm_columns if column in enriched.columns]
    firms = enriched.sort_values(["exchange", "firm_key"]).drop_duplicates("firm_key")[available]
    counts = enriched.groupby("firm_key", sort=False)["year"].agg(
        valid_year_min="min", valid_year_max="max", valid_firm_year_count="count"
    )
    result = firms.merge(counts, left_on="firm_key", right_index=True, validate="one_to_one")
    nonfinancial = result["industry_known"] & ~result["is_financial_industry"].fillna(False)
    is_bse = result["exchange"].eq("BSE")
    is_sse_szse = result["exchange"].isin(["SSE", "SZSE"])
    result["current_status"] = (
        result["delisting_date"].isna().map({True: "current", False: "delisted"})
    )
    result["fetch_phase"] = EXCLUDED
    result.loc[is_sse_szse & nonfinancial, "fetch_phase"] = PHASE_A
    result.loc[is_bse & nonfinancial, "fetch_phase"] = PHASE_B
    result["fetch_scope"] = result["fetch_phase"].map(
        {PHASE_A: "fetch", PHASE_B: "fetch_pending_mapping", EXCLUDED: EXCLUDED}
    )
    result["formal_ready"] = result["fetch_phase"].eq(PHASE_A)
    result["bse_mapping_status"] = result.get("bse_mapping_status", "not_applicable")
    result.loc[is_bse & nonfinancial, "bse_mapping_status"] = "BSE_MAPPING_REQUIRED"
    result = result.sort_values(["fetch_phase", "exchange", "firm_key"]).reset_index(drop=True)
    return result


def assign_chunks(manifest: pd.DataFrame, chunk_size: int = 100) -> pd.DataFrame:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    result = (
        manifest.sort_values(["fetch_phase", "exchange", "firm_key"]).reset_index(drop=True).copy()
    )
    result["chunk_id"] = ""
    result["chunk_position"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
    eligible = result.index[result["fetch_phase"].eq(PHASE_A)].tolist()
    for position, index in enumerate(eligible):
        chunk_number = position // chunk_size + 1
        result.at[index, "chunk_id"] = f"SSE-SZSE-A-{chunk_number:04d}"
        result.at[index, "chunk_position"] = position % chunk_size + 1
    return result


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def cache_is_valid(path: Path, firm_key: str, valid_years: tuple[int, ...]) -> bool:
    if not path.exists():
        return False
    try:
        frame = pd.read_parquet(path)
    except Exception:
        return False
    if not REQUIRED_CACHE_FIELDS.issubset(frame.columns):
        return False
    keys = set(zip(frame["firm_key"].astype(str), frame["year"].astype(int)))
    expected = set(zip([firm_key] * len(valid_years), valid_years))
    return keys == expected and len(frame) == len(expected)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _initial_state(fingerprint: str, phase: str, target_firms: int) -> dict[str, object]:
    now = _now()
    return {
        "universe_fingerprint": fingerprint,
        "phase": phase,
        "started_at": now,
        "updated_at": now,
        "target_firms": target_firms,
        "completed_firms": 0,
        "successful_firms": 0,
        "failed_firms": 0,
        "cached_firms": 0,
        "blocked": False,
        "last_firm_key": "",
        "completed_chunks": [],
    }


def _valid_years(universe: pd.DataFrame, firm_key: str) -> tuple[int, ...]:
    return tuple(sorted(universe.loc[universe["firm_key"].eq(firm_key), "year"].astype(int)))


def _status_row(
    firm, chunk_id: str, status: str, frame: pd.DataFrame, cache_used: bool
) -> dict[str, object]:
    success = frame.get("financial_success", pd.Series(False, index=frame.index)).fillna(False)
    reasons = frame.get("failure_reason", pd.Series("", index=frame.index)).fillna("")
    return {
        "firm_key": firm.firm_key,
        "exchange": firm.exchange,
        "current_status": firm.current_status,
        "chunk_id": chunk_id,
        "status": status,
        "valid_firm_years": int(len(frame)),
        "complete_firm_years": int(success.sum()),
        "failed_firm_years": int((~success).sum()),
        "cache_used": bool(cache_used),
        "financial_query_code": ";".join(
            sorted(
                frame.get("financial_query_code", pd.Series(dtype=str))
                .dropna()
                .astype(str)
                .unique()
            )
        ),
        "failure_reason": ";".join(sorted(set(";".join(reasons.astype(str)).split(";")) - {""})),
    }


def run_full_fetch(
    universe: pd.DataFrame,
    manifest: pd.DataFrame,
    cache_dir: Path,
    chunk_id: str,
    *,
    spacing: float = 1.0,
    max_firms: int | None = None,
    state_path: Path | None = None,
    expected_fingerprint: str | None = None,
) -> pd.DataFrame:
    if spacing < 1.0:
        raise ValueError("request spacing must be at least 1.0 second")
    if "chunk_id" not in manifest.columns:
        manifest = assign_chunks(manifest)
    selected = manifest.loc[manifest["formal_ready"]].copy()
    if chunk_id != "__MAX__":
        selected = selected.loc[selected["chunk_id"].eq(chunk_id)]
    selected = selected.sort_values(["chunk_position", "firm_key"])
    if max_firms is not None:
        selected = selected.head(max_firms)
    fingerprint = universe_fingerprint(universe)
    if expected_fingerprint is not None and expected_fingerprint != fingerprint:
        raise ValueError("UNIVERSE_FINGERPRINT_MISMATCH")
    if state_path and state_path.exists():
        previous_state = json.loads(state_path.read_text(encoding="utf-8"))
        if previous_state.get("universe_fingerprint") != fingerprint:
            raise ValueError("UNIVERSE_FINGERPRINT_MISMATCH")
        state = _initial_state(fingerprint, PHASE_A, int(len(selected)))
        state["completed_chunks"] = previous_state.get("completed_chunks", [])
    else:
        state = _initial_state(fingerprint, PHASE_A, int(len(selected)))
    cache_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for firm in selected.itertuples(index=False):
        years = _valid_years(universe, firm.firm_key)
        path = financial_cache_path(cache_dir, firm.firm_key)
        cache_valid = cache_is_valid(path, firm.firm_key, years)
        stale = path.exists() and not cache_valid
        if cache_valid:
            frame = pd.read_parquet(path)
            status = "CACHE_HIT"
        else:
            try:
                frame = fetch_company_with_fallback(
                    firm.exchange,
                    firm.stock_code_current,
                    [str(firm.stock_code_current).zfill(6)],
                    firm.firm_key,
                    years,
                )
            except SourceBlocked:
                state.update(
                    {"blocked": True, "updated_at": _now(), "last_firm_key": firm.firm_key}
                )
                if state_path:
                    atomic_write_json(state_path, state)
                raise
            except Exception as exc:
                frame = _empty_financial_rows(
                    firm.exchange,
                    firm.stock_code_current,
                    firm.firm_key,
                    years,
                    f"{type(exc).__name__}: {str(exc)[:160]}",
                )
            frame.to_parquet(path, index=False)
            success = frame["financial_success"].fillna(False)
            status = (
                "STALE_CACHE_REFETCHED"
                if stale
                else (
                    "COMPLETE"
                    if bool(success.all())
                    else "PARTIAL"
                    if bool(success.any())
                    else "QUERY_FAILED"
                )
            )
        rows.append(
            _status_row(firm, getattr(firm, "chunk_id", chunk_id), status, frame, cache_valid)
        )
        state["completed_firms"] = int(state.get("completed_firms", 0)) + 1
        state["successful_firms"] = int(
            sum(row["status"] in {"COMPLETE", "CACHE_HIT", "STALE_CACHE_REFETCHED"} for row in rows)
        )
        state["failed_firms"] = int(
            sum(row["status"] in {"QUERY_FAILED", "PARTIAL"} for row in rows)
        )
        state["cached_firms"] = int(sum(row["cache_used"] for row in rows))
        state.update({"updated_at": _now(), "last_firm_key": firm.firm_key})
        if state_path:
            atomic_write_json(state_path, state)
        if len(rows) % 10 == 0 or len(rows) == len(selected):
            print(
                f"[{len(rows)}/{len(selected)}] success={state['successful_firms']} "
                f"failed={state['failed_firms']} cache={state['cached_firms']}"
            )
        if len(rows) < len(selected):
            time.sleep(spacing)
    if state_path and len(rows) == len(selected):
        completed = {row["chunk_id"] for row in rows}
        state["completed_chunks"] = sorted(set(state.get("completed_chunks", [])) | completed)
        state["updated_at"] = _now()
        atomic_write_json(state_path, state)
    return pd.DataFrame(rows)


def assemble_full_financial_panel(
    universe: pd.DataFrame, cache_dir: Path, manifest: pd.DataFrame
) -> pd.DataFrame:
    target = manifest.loc[manifest["formal_ready"], ["firm_key", "exchange", "stock_code_current"]]
    metadata = [
        column
        for column in (
            "firm_key",
            "year",
            "exchange",
            "stock_code_current",
            "listing_date",
            "market_listing_date",
            "delisting_date",
        )
        if column in universe.columns
    ]
    skeleton = (
        universe.loc[universe["firm_key"].isin(target["firm_key"]), metadata]
        .drop_duplicates(["firm_key", "year"])
        .copy()
    )
    actual = []
    for firm_key in target["firm_key"]:
        years = _valid_years(skeleton, firm_key)
        path = financial_cache_path(cache_dir, firm_key)
        if cache_is_valid(path, firm_key, years):
            actual.append(pd.read_parquet(path))
    if actual:
        data = pd.concat(actual, ignore_index=True)
        financial_columns = [
            column for column in data.columns if column not in set(metadata) - {"firm_key", "year"}
        ]
        panel = skeleton.merge(data[financial_columns], on=["firm_key", "year"], how="left")
    else:
        panel = skeleton.copy()
        for column in (*CORE_FIELDS, "rd_expense"):
            panel[column] = float("nan")
        panel["financial_query_code"] = ""
        panel["failure_reason"] = ""
        panel["financial_success"] = False
    return construct_variables(panel)
