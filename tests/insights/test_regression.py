import pytest

from src.insights.regression import compare_answer


@pytest.mark.parametrize(
    ("actual", "expected", "refused", "passed"),
    [
        ("No weather", "Refuse: outside scope", True, True),
        ("No weather", "Refuse: outside scope", False, False),
        ("rate\n35.1", "rate\n35.1", False, True),
        ("rate\n35.2", "rate\n35.1", False, False),
        ("The programme lasts 3 months and payment is reduced 50%.", "3 months; payment reduced by 50%.", False, True),
        ("The programme lasts 6 months.", "3 months; payment reduced by 50%.", False, False),
    ],
)
def test_compare_answer(actual: str, expected: str, refused: bool, passed: bool) -> None:
    assert compare_answer(actual, expected, refused)[0] is passed
