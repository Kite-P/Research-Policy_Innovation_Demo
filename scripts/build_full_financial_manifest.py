from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.real_financial_full import (  # noqa: E402
    PHASE_A,
    PHASE_B,
    assign_chunks,
    build_full_financial_target,
    manifest_fingerprint,
    universe_fingerprint,
)

UNIVERSE = ROOT / "data" / "processed" / "real_company_universe_enriched.parquet"
OUTPUT = ROOT / "results" / "real_financial_full"


def build_manifest(universe_path: Path = UNIVERSE, output_dir: Path = OUTPUT) -> dict[str, object]:
    universe = pd.read_parquet(universe_path)
    manifest = assign_chunks(build_full_financial_target(universe), chunk_size=100)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest.to_parquet(output_dir / "target_manifest.parquet", index=False)
    manifest.to_csv(output_dir / "target_manifest.csv", index=False, encoding="utf-8-sig")
    phase_a = manifest["fetch_phase"].eq(PHASE_A)
    phase_b = manifest["fetch_phase"].eq(PHASE_B)
    summary = {
        "source_universe_rows": int(len(universe)),
        "source_universe_firms": int(universe["firm_key"].nunique()),
        "target_firms": int(manifest["formal_ready"].sum()),
        "target_firm_years": int(
            universe.loc[universe["firm_key"].isin(manifest.loc[phase_a, "firm_key"])].shape[0]
        ),
        "SSE target firms": int((phase_a & manifest["exchange"].eq("SSE")).sum()),
        "SZSE target firms": int((phase_a & manifest["exchange"].eq("SZSE")).sum()),
        "BSE pending firms": int(phase_b.sum()),
        "financial excluded firms": int(manifest["fetch_phase"].eq("excluded_financial").sum()),
        "universe fingerprint": universe_fingerprint(universe),
        "manifest fingerprint": manifest_fingerprint(manifest),
        "phase_a_chunks": int(manifest.loc[phase_a, "chunk_id"].nunique()),
    }
    (output_dir / "manifest_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    build_manifest()
