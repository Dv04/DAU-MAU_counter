import datetime as dt
from pathlib import Path

from dp_core.privacy_accountant import PrivacyAccountant


def test_privacy_accountant_tracks_budget(tmp_path: Path) -> None:
    accountant = PrivacyAccountant(tmp_path / "acct.sqlite")
    day = dt.date(2025, 10, 9)
    assert accountant.can_release("dau", 0.3, day, 1.0)
    accountant.record_release("dau", day, 0.3, 0.0, "laplace", 1)
    remaining = accountant.remaining_budget("dau", day, 1.0)
    assert 0.6 <= remaining <= 0.7
    accountant.reset_month("dau", day.strftime("%Y-%m"))
    assert accountant.remaining_budget("dau", day, 1.0) == 1.0
