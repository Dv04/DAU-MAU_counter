import datetime as dt
from pathlib import Path

import pytest

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


def test_budget_snapshot_reports_rdp(tmp_path: Path) -> None:
    accountant = PrivacyAccountant(tmp_path / "acct.sqlite")
    day = dt.date(2025, 10, 10)
    accountant.record_release("mau", day, 0.5, 1e-6, "gaussian", 7)
    accountant.log_rdp("mau", day, order=2.0, rdp_value=0.25)
    snapshot = accountant.budget_snapshot(
        "mau", day, cap=1.0, delta=1e-6, orders=[2.0, 4.0], advanced_delta=1e-7
    )
    assert snapshot.metric == "mau"
    assert snapshot.period == "2025-10"
    assert snapshot.rdp_curve[2.0] == 0.25
    best_eps = snapshot.best_rdp_epsilon
    assert best_eps is not None and best_eps > 0.0
    assert snapshot.advanced_epsilon is not None and snapshot.advanced_epsilon > 0.0
    assert snapshot.advanced_delta is not None and snapshot.advanced_delta > 0.0
    assert snapshot.release_count == 1
    assert snapshot.rdp_orders == (2.0, 4.0)
    assert snapshot.as_dict()["policy"]["delta"] == pytest.approx(1e-6)


def test_accountant_spent_epsilon_and_count(tmp_path: Path) -> None:
    accountant = PrivacyAccountant(tmp_path / "acct.sqlite")
    day = dt.date(2025, 9, 1)
    for idx in range(3):
        accountant.record_release("dau", day, 0.2, 0.0, "laplace", idx)
    assert accountant.get_spent_epsilon("dau", day) == pytest.approx(0.6)
    assert accountant.monthly_release_count("dau", day) == 3
