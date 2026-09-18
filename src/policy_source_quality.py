"""Apply auditable manual source tiers and manifest provenance fields."""

from __future__ import annotations

import io
import subprocess
from argparse import ArgumentParser
from pathlib import Path

import pandas as pd

TIER_LABELS = {
    1: "direct_provincial_official",
    2: "other_government_official",
    3: "official_or_state_media_reprint",
    4: "other_complete_reprint",
}

TIER_1_IDS = {
    *(f"beijing_{year}" for year in range(2019, 2026)),
    *(f"shanghai_{year}" for year in range(2019, 2025)),
    *(f"jiangsu_{year}" for year in range(2019, 2026)),
    "sichuan_2019",
    *(f"hubei_{year}" for year in (2023, 2024, 2025)),
    *(f"guangdong_{year}" for year in (2019, 2020, 2021, 2022, 2023, 2025)),
}
TIER_2_IDS = {
    "zhejiang_2020",
    "zhejiang_2024",
    "zhejiang_2025",
    "hubei_2019",
    "hubei_2021",
    *(f"sichuan_{year}" for year in range(2020, 2026)),
}
TIER_3_IDS = {"shanghai_2025", "hubei_2020", "zhejiang_2022", "guangdong_2024"}
TIER_4_IDS = {"zhejiang_2019", "zhejiang_2021", "zhejiang_2023", "hubei_2022"}

CANONICAL_REPLACEMENTS: dict[str, dict[str, str]] = {}


def classify_source(policy_id: str, source_url: str) -> tuple[int, str, str]:
    if policy_id in TIER_1_IDS:
        reason = "省级人民政府、人大或正式政府公报直接发布完整报告正文或附件。"
        return 1, TIER_LABELS[1], reason
    if policy_id in TIER_2_IDS:
        reason = "政府部门、下级政府、政府管理机构或正式公共机构完整转载同一报告。"
        return 2, TIER_LABELS[2], reason
    if policy_id in TIER_3_IDS:
        reason = "经来源页面核对为党媒、国家/省级官方媒体或官方公共媒体完整转载。"
        return 3, TIER_LABELS[3], reason
    if policy_id in TIER_4_IDS:
        reason = "可核对为同年度完整报告转载，但当前页面不属于政府机关或正式官方媒体一级来源。"
        return 4, TIER_LABELS[4], reason
    raise ValueError(f"unclassified policy source: {policy_id} {source_url}")


def enrich_manifest(manifest: pd.DataFrame) -> pd.DataFrame:
    result = manifest.copy()
    for policy_id, replacement in CANONICAL_REPLACEMENTS.items():
        mask = result["policy_id"].eq(policy_id)
        for column, value in replacement.items():
            if column != "reason":
                result.loc[mask, column] = value
        result.loc[mask, "notes"] = replacement["reason"]
    tiers = result.apply(
        lambda row: classify_source(str(row["policy_id"]), str(row["source_url"])), axis=1
    )
    result["source_tier"] = [item[0] for item in tiers]
    result["source_tier_label"] = [item[1] for item in tiers]
    result["source_tier_reason"] = [item[2] for item in tiers]
    result["source_tier_verified"] = 1
    history = result["notes"].fillna("").astype(str).str.findall(r"fetch_error=\w+")
    existing_history = result.get(
        "retrieval_history_note", pd.Series("", index=result.index)
    ).fillna("").astype(str)
    result["retrieval_history_note"] = [
        ";".join(dict.fromkeys([item for item in [*old.split(";"), *new] if item]))
        for old, new in zip(existing_history, history)
    ]
    result["notes"] = (
        result["notes"].fillna("").astype(str)
        .str.replace(r"(?:^|\s*)fetch_error=\w+", "", regex=True)
        .str.strip(" ;")
        .replace("", pd.NA)
    )
    return result


def update_manifest(path: str | Path) -> pd.DataFrame:
    manifest_path = Path(path)
    manifest = pd.read_csv(manifest_path, dtype=str, keep_default_na=False)
    try:
        old_csv = subprocess.run(
            ["git", "show", f"HEAD:{manifest_path.as_posix()}"],
            check=True,
            capture_output=True,
        ).stdout.decode("utf-8-sig")
        old_manifest = pd.read_csv(io.StringIO(old_csv), dtype=str, keep_default_na=False)
        old_notes = old_manifest.set_index("policy_id")["notes"].to_dict()
        recovered = manifest["policy_id"].map(old_notes).fillna("").str.findall(
            r"fetch_error=\w+"
        )
        manifest["retrieval_history_note"] = [
            ";".join(
                dict.fromkeys(
                    [item for item in [*str(current).split(";"), *values] if item]
                )
            )
            for current, values in zip(
                manifest.get("retrieval_history_note", pd.Series("", index=manifest.index)),
                recovered,
            )
        ]
    except (OSError, subprocess.CalledProcessError, KeyError, pd.errors.ParserError):
        pass
    result = enrich_manifest(manifest)
    result.to_csv(manifest_path, index=False, encoding="utf-8-sig")
    return result


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="metadata/policy_source_manifest.csv")
    args = parser.parse_args()
    update_manifest(args.manifest)
