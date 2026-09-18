import pandas as pd

from src.chapter3_stata_crosscheck import compare_point_estimates, validate_wcb_coherence


def test_point_estimate_comparator_checks_model_beta_and_n():
    left = pd.DataFrame([{"model": "A", "beta": 1.0, "N": 10}])
    right = pd.DataFrame([{"model": "A", "beta": 1.0 + 1e-8, "N": 10}])
    result = compare_point_estimates(left, right)
    assert result.passed.tolist() == [True]

    assert not compare_point_estimates(left.assign(N=9), right).passed.all()


def test_wcb_coherence_flags_ci_containing_zero():
    result = validate_wcb_coherence(
        pd.DataFrame(
            [
                {"model": "A", "wcb_p": 0.01, "wcb_ci_low": 1.0, "wcb_ci_high": 2.0},
                {"model": "B", "wcb_p": 0.20, "wcb_ci_low": -1.0, "wcb_ci_high": 2.0},
            ]
        )
    )
    assert result.coherent.all()
