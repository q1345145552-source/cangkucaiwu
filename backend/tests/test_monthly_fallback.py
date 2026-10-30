"""Offline monthly routing checks; no database or application startup."""
from datetime import date
from types import SimpleNamespace

import pytest

from app.services.monthly_payroll import use_new_monthly


@pytest.mark.parametrize("mode,fixed_days,start,end,resignation,expected", [
    (None, None, date(2026, 10, 1), date(2026, 10, 31), False, False),
    ("actual", None, date(2026, 10, 1), date(2026, 10, 31), False, True),
    ("fixed", 26, date(2026, 10, 1), date(2026, 10, 31), False, True),
    ("fixed", None, date(2026, 10, 1), date(2026, 10, 31), False, False),
    ("actual", None, date(2026, 10, 15), date(2026, 10, 31), False, False),
    ("actual", None, date(2026, 10, 1), date(2026, 10, 31), True, False),
    ("fixed", 0, date(2026, 10, 1), date(2026, 10, 31), False, False),
    ("fixed", -1, date(2026, 10, 1), date(2026, 10, 31), False, False),
    ("actual", None, date(2026, 10, 1), date(2026, 10, 15), False, False),
    ("actual", None, date(2026, 10, 1), date(2026, 11, 30), False, False),
    ("actual", None, date(2028, 2, 1), date(2028, 2, 29), False, True),
    ("unknown", None, date(2026, 10, 1), date(2026, 10, 31), False, False),
])
def test_use_new_monthly(mode, fixed_days, start, end, resignation, expected):
    template = SimpleNamespace(monthly_deduction_mode=mode, monthly_fixed_days=fixed_days)
    actual = use_new_monthly(template, start, end, resignation)
    print(f"mode={mode}, fixed_days={fixed_days}, {start}..{end}, resignation={resignation}: {actual}")
    assert actual is expected
