from __future__ import annotations

import pandas as pd
import pytest

from scripts.audit_entity_key_reconciliation import compare_key_sets


def test_compare_key_sets_rejects_any_unverified_firm_key_change() -> None:
    old = {"SSE:600555:1999-01-18", "SSE:600555:2001-03-28", "SSE:600999:2000-01-01"}
    new = {"SSE:600555:2001-03-28", "SSE:600999:2000-01-01"}
    verified = {"SSE:600555:1999-01-18"}

    result = compare_key_sets(old, new, verified)

    assert result == {
        "removed": ["SSE:600555:1999-01-18"],
        "added": [],
        "exact_verified_removal": True,
    }
    with pytest.raises(ValueError, match="UNVERIFIED_KEY_DIFFERENCE"):
        compare_key_sets(old, new - {"SSE:600999:2000-01-01"}, verified)


def test_alias_diff_has_only_11_removed_firm_years() -> None:
    alias_years = {
        "SSE:600190:1998-05-19": range(2020, 2026),
        "SSE:600555:1999-01-18": range(2020, 2023),
        "SSE:600614:1992-07-28": range(2020, 2022),
    }
    alias_rows = [(key, year) for key, years in alias_years.items() for year in years]
    stable_rows = [("SSE:600999:2000-01-01", 2020)]
    old = pd.DataFrame(
        {
            "firm_key": [key for key, _ in alias_rows + stable_rows],
            "year": [year for _, year in alias_rows + stable_rows],
        }
    )
    new = old.loc[~old.firm_key.isin(alias_years)].copy()

    result = compare_key_sets(
        set(zip(old.firm_key, old.year)),
        set(zip(new.firm_key, new.year)),
        set(alias_rows),
    )

    assert len(result["removed"]) == 11
    assert result["added"] == []
    assert {key for key, _ in result["removed"]} == set(alias_years)
