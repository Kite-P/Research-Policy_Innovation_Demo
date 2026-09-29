"""Legacy filename retained for compatibility; implementation lives in 20260929."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_cninfo_legal_name_recovery_20260929 as _canonical  # noqa: E402


def main() -> int:
    """Delegate all CLI behavior, including Full authorization, to canonical code."""
    return _canonical.main()


if __name__ == "__main__":
    raise SystemExit(main())
