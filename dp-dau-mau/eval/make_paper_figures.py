#!/usr/bin/env python3
"""Regenerate the four paper figures from committed results and committed code.

Every plotted number is read from a file in this repository or computed by
committed code; nothing is typed in by hand.

Outputs (paper/figs/):
  error_vs_epsilon_set.png   <- eval/results/error_vs_epsilon_10k_results.json
                                (exact `set` backend, N=10,000, 5 seeds; copied
                                verbatim from results_dense_fixed.json, commit
                                095001e on branch wip-dec2025-snapshot)
  budget_consumption.png     <- dp_core.privacy_accountant.PrivacyAccountant
                                (_best_from_curve, the same RDP-to-(eps,delta)
                                conversion the pipeline uses) with the shipped
                                DPSettings defaults (MAU: eps=0.5, delta=1e-6)
  scalability_linear.png     <- eval/results/pipeline_roaring_fast.json
  query_latency.png          <- DAU p50/p99 and MAU fresh p50/p99 for 10k and
                                100k users from pipeline_roaring_fast.json; MAU
                                fresh at 1M and all MAU cached values from the
                                "After" table of ROARING_BENCHMARK.md (these are
                                the values printed in the paper's Table
                                "Measured Scalability"); DAU at 1M from JSON.

Usage (from dp-dau-mau/):  python eval/make_paper_figures.py
Requires matplotlib and the repo requirements (pyroaring etc., because
importing dp_core pulls in the sketch backends).
"""

from __future__ import annotations

import json
import math
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from dp_core.config import DPSettings  # noqa: E402
from dp_core.privacy_accountant import PrivacyAccountant  # noqa: E402

RESULTS = REPO_ROOT / "eval" / "results"
FIGS = REPO_ROOT.parent / "paper" / "figs"
DPI = 200


def _load(name: str):
    with (RESULTS / name).open() as fp:
        return json.load(fp)


# --------------------------------------------------------------------------
# Figure: relative error vs epsilon
# --------------------------------------------------------------------------
def fig_error_vs_epsilon() -> None:
    data = _load("error_vs_epsilon_10k_results.json")
    by_eps: dict[float, dict[str, list[float]]] = defaultdict(lambda: {"dau": [], "mau": []})
    for entry in data:
        for metric in ("dau", "mau"):
            res = entry[metric]
            err = abs(res["estimate"] - res["exact_value"]) / max(res["exact_value"], 1) * 100.0
            by_eps[entry["epsilon"]][metric].append(err)
    eps = sorted(by_eps)
    dau = [statistics.mean(by_eps[e]["dau"]) for e in eps]
    mau = [statistics.mean(by_eps[e]["mau"]) for e in eps]

    fig, ax = plt.subplots(figsize=(6.0, 3.8))
    ax.plot(eps, dau, "o-", lw=2, label="DAU (Laplace)")
    ax.plot(eps, mau, "s-", lw=2, label="MAU (Gaussian)")
    ax.axhline(0.5, color="r", ls="--", label="0.5% threshold")
    ax.set_xlabel(r"Privacy parameter $\varepsilon$")
    ax.set_ylabel("Relative error (%), mean of 5 seeds")
    ax.set_title("Relative error vs. $\\varepsilon$ (N = 10,000, exact backend)")
    ax.grid(True, ls="--", alpha=0.5)
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGS / "error_vs_epsilon_set.png", dpi=DPI)
    plt.close(fig)


# --------------------------------------------------------------------------
# Figure: budget consumption (naive vs RDP) from the committed accountant
# --------------------------------------------------------------------------
def budget_curves(horizon: int = 365) -> tuple[list[int], list[float], list[float]]:
    """Naive and RDP-composed cumulative epsilon for k = 1..horizon MAU releases."""
    dp = DPSettings()
    eps, delta, orders = dp.epsilon_mau, dp.delta, list(dp.rdp_orders)
    sensitivity = float(min(dp.w_bound, 1))
    sigma = math.sqrt(2.0 * math.log(1.25 / delta)) * sensitivity / eps
    ks = list(range(1, horizon + 1))
    naive = [k * eps for k in ks]
    rdp = []
    for k in ks:
        curve = {a: k * a * sensitivity**2 / (2.0 * sigma**2) for a in orders}
        best, _ = PrivacyAccountant._best_from_curve(delta, curve)  # noqa: SLF001
        assert best is not None
        rdp.append(best)
    return ks, naive, rdp


def fig_budget() -> dict[str, float]:
    ks, naive, rdp = budget_curves()

    fig, ax = plt.subplots(figsize=(6.0, 3.8))
    ax.plot(ks, naive, "-", lw=2, color="#2196F3", label=r"Naive summation ($k\varepsilon$)")
    ax.plot(ks, rdp, "-", lw=2, color="#4CAF50", label=r"RDP composition ($\delta=10^{-6}$)")
    ax.axvline(30, color="gray", ls=":", lw=1)
    ax.annotate(
        f"k=30: {naive[29]:.1f} vs {rdp[29]:.2f}",
        (30, rdp[29]),
        xytext=(45, 45),
        textcoords="offset points",
        fontsize=8,
        arrowprops={"arrowstyle": "-", "color": "gray"},
    )
    ax.set_xlabel("Number of MAU releases $k$ (one per day)")
    ax.set_ylabel(r"Cumulative $\varepsilon$")
    ax.set_title(r"MAU budget consumption ($\varepsilon=0.5$ per release)")
    ax.grid(True, ls="--", alpha=0.5)
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(FIGS / "budget_consumption.png", dpi=DPI)
    plt.close(fig)
    return {
        "k30_naive": naive[29],
        "k30_rdp": rdp[29],
        "k365_naive": naive[364],
        "k365_rdp": rdp[364],
    }


# --------------------------------------------------------------------------
# Figures: scalability and latency
# --------------------------------------------------------------------------
def _parse_after_table() -> dict[int, dict[str, float]]:
    """Parse the 'After' scaling table of ROARING_BENCHMARK.md (MAU cold/fresh/cached)."""
    text = (REPO_ROOT / "ROARING_BENCHMARK.md").read_text()
    marker = "| Users | Ingest (s) | Throughput | DAU p50 |"
    start = text.index(marker)
    rows: dict[int, dict[str, float]] = {}
    for line in text[start:].splitlines()[2:]:
        if not line.startswith("|"):
            break
        cells = [re.sub(r"[*,]|\s*(ms|MB|/s)\b", "", c).strip() for c in line.strip("|").split("|")]
        users = int(cells[0])
        rows[users] = {
            "mau_fresh_p50": float(cells[6]),
            "mau_fresh_p99": float(cells[7]),
            "mau_cached_p50": float(cells[8]),
            "mau_cached_p99": float(cells[9]),
        }
    return rows


def fig_scalability() -> list[tuple[int, float]]:
    rows = _load("pipeline_roaring_fast.json")
    users = [r["users"] for r in rows]
    t = [r["ingest_time_sec"] for r in rows]
    ideal = [t[0] * u / users[0] for u in users]
    fig, ax = plt.subplots(figsize=(6.0, 3.8))
    ax.plot(users, t, "o-", lw=2, ms=8, color="#2ecc71", label="Measured ingest time")
    ax.plot(users, ideal, "--", lw=1.5, color="#95a5a6", label=r"Ideal $O(N)$ from 10K point")
    for u, v in zip(users, t, strict=True):
        ax.annotate(f"{v:.2f} s", (u, v), textcoords="offset points", xytext=(0, 9), ha="center")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xticks(users)
    ax.set_xticklabels([f"{u // 1000}K" if u < 1_000_000 else "1M" for u in users])
    ax.set_xlabel("Number of users")
    ax.set_ylabel("Ingestion time (s)")
    ax.set_title("Ingestion scalability (30 days, 20% daily activity)")
    ax.grid(True, ls="--", alpha=0.4)
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(FIGS / "scalability_linear.png", dpi=DPI)
    plt.close(fig)
    return list(zip(users, t, strict=True))


def fig_latency() -> dict[int, dict[str, float]]:
    rows = {r["users"]: r for r in _load("pipeline_roaring_fast.json")}
    after = _parse_after_table()
    users = sorted(rows)
    # Same provenance as the paper's Table "Measured Scalability": JSON for
    # 10k/100k MAU fresh, the ROARING_BENCHMARK.md "After" row for 1M fresh,
    # and the "After" table for every cached value.
    fresh_p50, fresh_p99 = [], []
    for u in users:
        if u == 1_000_000:
            fresh_p50.append(after[u]["mau_fresh_p50"])
            fresh_p99.append(after[u]["mau_fresh_p99"])
        else:
            fresh_p50.append(rows[u]["mau_latency_p50_ms"])
            fresh_p99.append(rows[u]["mau_latency_p99_ms"])
    series = {
        "DAU": (
            [rows[u]["dau_latency_p50_ms"] for u in users],
            [rows[u]["dau_latency_p99_ms"] for u in users],
            "#3498db",
        ),
        "MAU, fresh window": (fresh_p50, fresh_p99, "#e74c3c"),
        "MAU, cached repeat": (
            [after[u]["mau_cached_p50"] for u in users],
            [after[u]["mau_cached_p99"] for u in users],
            "#8e44ad",
        ),
    }
    fig, ax = plt.subplots(figsize=(6.0, 3.8))
    for label, (p50, p99, color) in series.items():
        ax.plot(users, p50, "o-", lw=2, color=color, label=f"{label} p50")
        ax.plot(users, p99, "x--", lw=1, color=color, alpha=0.7, label=f"{label} p99")
    ax.axhline(1000, color="gray", ls="--", alpha=0.5)
    ax.annotate("1 s", (users[0], 1000), textcoords="offset points", xytext=(2, 3), fontsize=8)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xticks(users)
    ax.set_xticklabels([f"{u // 1000}K" if u < 1_000_000 else "1M" for u in users])
    ax.set_xlabel("Number of users")
    ax.set_ylabel("Query latency (ms)")
    ax.set_title("Query latency vs. user population")
    ax.grid(True, ls="--", alpha=0.4)
    ax.legend(fontsize=7, loc="center left", bbox_to_anchor=(1.01, 0.5))
    fig.tight_layout()
    fig.savefig(FIGS / "query_latency.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    return after


def main() -> None:
    FIGS.mkdir(parents=True, exist_ok=True)
    fig_error_vs_epsilon()
    budget = fig_budget()
    scal = fig_scalability()
    after = fig_latency()
    print("budget:", budget)
    print("ingest:", scal)
    print("after-table:", after)
    print("wrote figures to", FIGS)


if __name__ == "__main__":
    main()
