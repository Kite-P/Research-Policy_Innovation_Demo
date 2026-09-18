from pathlib import Path

import pandas as pd
import pytest

from src.chapter3_analysis import WEBB_SUPPORT, _fit
from src.chapter3_robustness import build_lagged_policy

ROOT = Path(__file__).parents[1]


def _panel() -> pd.DataFrame:
    rows = []
    for province, values in {"甲": [0.1, 0.2, 0.3], "乙": [0.4, 0.5, 0.6]}.items():
        for firm in (f"{province}1", f"{province}2"):
            for year, policy in zip((2020, 2021, 2022), values):
                rows.append(
                    {
                        "stock_code": firm,
                        "province": province,
                        "year": year,
                        "policy_continuity_tfidf": policy,
                        "patent_total_ln": policy + 1,
                        "size_ln": 1.0,
                        "leverage": 0.2,
                        "roa": 0.1,
                        "cash_ratio": 0.3,
                        "employee_ln": 2.0,
                    }
                )
    return pd.DataFrame(rows)


def test_lag_is_joined_from_unique_province_year_not_firm_rows():
    panel = _panel()
    lagged = build_lagged_policy(panel, "policy_continuity_tfidf")
    assert len(lagged) == len(panel) == 12
    for province, first, second in (("甲", 0.1, 0.2), ("乙", 0.4, 0.5)):
        subset = lagged[lagged.province == province]
        assert subset.loc[subset.year == 2020, "policy_lag"].isna().all()
        assert subset.loc[subset.year == 2021, "policy_lag"].eq(first).all()
        assert subset.loc[subset.year == 2022, "policy_lag"].eq(second).all()


def test_fit_reports_exact_model_regressors():
    panel = _panel()
    model0 = _fit(panel, "patent_total_ln", controls=False)
    primary = _fit(panel, "patent_total_ln", controls=True)
    assert model0["regressor_names"] == ["policy_continuity_tfidf"]
    assert primary["regressor_names"] == [
        "policy_continuity_tfidf",
        "size_ln",
        "leverage",
        "roa",
        "cash_ratio",
        "employee_ln",
    ]


def test_webb_support_has_six_distinct_points():
    assert WEBB_SUPPORT.tolist() == pytest.approx(
        [-(1.5**0.5), -1.0, -(0.5**0.5), 0.5**0.5, 1.0, 1.5**0.5]
    )


@pytest.mark.parametrize("filename", [
    "stata/08_policy_baseline.do",
    "stata/09_policy_timing_robustness.do",
    "stata/10_policy_measurement_robustness.do",
])
def test_each_formal_stata_model_has_year_fixed_effect(filename):
    text = (ROOT / filename).read_text(encoding="utf-8")
    commands = [
        line.strip().lower()
        for line in text.splitlines()
        if "xtreg" in line.lower() and not line.lstrip().startswith("*")
    ]
    assert commands
    assert all("i.year" in command for command in commands), commands


def test_crosscheck_comparator_is_strict():
    from src.chapter3_stata_crosscheck import compare_point_estimates

    left = pd.DataFrame([{"model": "BASE_PRIMARY", "beta": 1.0, "N": 10}])
    right = pd.DataFrame([{"model": "BASE_PRIMARY", "beta": 1.0 + 1e-8, "N": 10}])
    assert compare_point_estimates(left, right, tolerance=1e-7).passed.all()
    assert not compare_point_estimates(left.assign(N=9), right).passed.all()
