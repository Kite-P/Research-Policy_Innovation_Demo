import pandas as pd

from scripts.run_financial_pilot import select_pilot_universe_years


def test_pilot_year_filter_keeps_only_2020_to_2025():
    universe = pd.DataFrame(
        {
            "firm_key": ["SSE:1:2000"] * 3,
            "year": [2019, 2020, 2025],
        }
    )
    result = select_pilot_universe_years(universe)
    assert result["year"].tolist() == [2020, 2025]
