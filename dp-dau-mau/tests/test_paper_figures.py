"""Checks for the paper-figure generator: it must read the committed numbers."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("matplotlib")

SCRIPT = Path(__file__).resolve().parent.parent / "eval" / "make_paper_figures.py"


@pytest.fixture(scope="module")
def figs():
    spec = importlib.util.spec_from_file_location("make_paper_figures", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_after_table_matches_committed_benchmark(figs) -> None:
    table = figs._parse_after_table()
    assert set(table) == {10_000, 100_000, 1_000_000}
    one_m = table[1_000_000]
    assert one_m["mau_fresh_p50"] == pytest.approx(2690.0)
    assert one_m["mau_fresh_p99"] == pytest.approx(4474.0)
    assert one_m["mau_cached_p50"] == pytest.approx(0.57)
    assert one_m["mau_cached_p99"] == pytest.approx(1.45)


def test_budget_curves_use_accountant_rdp(figs) -> None:
    ks, naive, rdp = figs.budget_curves()
    assert naive[29] == pytest.approx(15.0)
    assert rdp[29] == pytest.approx(3.04, abs=0.01)
    assert naive[364] == pytest.approx(182.5)
    assert rdp[364] == pytest.approx(11.1, abs=0.05)
    # RDP conversion is looser than naive for a single release, tighter from k=2 on.
    assert rdp[0] > naive[0]
    assert all(r < n for r, n in zip(rdp[1:], naive[1:], strict=True))
    assert ks[0] == 1 and ks[-1] == 365
