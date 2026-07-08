#!/usr/bin/env python3
"""Two empirical/analytical strengtheners for the PoPETs 2027.2 revision response.

Run from dp-dau-mau/ with the project's venv:

    .venv/bin/python experiments/strengtheners.py

Everything here is seeded (default seed 20260708) and deterministic given a
seed. Nothing in this file is imported by, or changes the behaviour of, the
shipped application code under src/. It only *reads* the shipped sketch and
DP-mechanism implementations to drive controlled experiments against them.

STRENGTHENER 1 -- history-independence exhibit
    Empirically tests the paper's Definition ("History-Independent
    Deletion"): for backend state built by ingesting D then removing user u,
    is the result identically distributed to state built from D \\ {u}
    directly? Tested against every backend that actually exists and is
    importable in this checkout:
      - SetSketch  ("set")  -- the exact backend that ships and is tested.
      - KMVSketch  ("kmv")  -- the approximate bottom-k backend that ships
        and is tested.
      - RoaringSketch       -- an UNTRACKED / never-committed / unregistered
        snapshot (experiments/orphaned_roaring_impl_snapshot.py) that the
        paper's prose describes as "the" evaluation backend. Tested here
        only because the task specifically asked for it and the file
        happens to exist on disk; its orphan status is reported honestly.
    Theta is NOT implemented anywhere in this repository (committed or
    otherwise), so it cannot be tested; this is reported as N/A, not
    fabricated.

STRENGTHENER 2 -- tree-aggregation vs. per-release composition
    Part A (empirical): a from-scratch, seeded Monte-Carlo simulation of the
    classical Chan-Song-Shi / Dwork-Naor-Pitassi-Rothblum binary-tree
    ("hierarchical") continual-release mechanism, using the repo's actual
    Laplace sampler (dp_core.dp_mechanisms.sample_laplace) as the noise
    primitive, applied to a synthetic ADDITIVE daily counter (new-user
    arrivals) -- the natural class of query tree-aggregation targets. This
    is NOT literally DAU/MAU (a non-additive distinct-count/union query that
    does not decompose through a summation tree), and that substitution is
    disclosed prominently in STRENGTHENERS_RESULTS.md.
    Part B (analytical, using the repo's real epsilon/delta/sensitivity
    constants and its actual PrivacyAccountant RDP-composition code): the
    literal DAU (Laplace) and MAU (Gaussian) per-release mechanisms, exactly
    as shipped, compared against a tree-aggregated variant at a matched
    total privacy budget over a 365-release horizon. Clearly labeled
    analytical-not-empirical per the task's fallback allowance.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
EXPERIMENTS_ROOT = Path(__file__).resolve().parent
for p in (SRC_ROOT, EXPERIMENTS_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from dp_core.config import DPSettings  # noqa: E402
from dp_core.dp_mechanisms import sample_laplace  # noqa: E402
from dp_core.privacy_accountant import PrivacyAccountant  # noqa: E402
from dp_core.sketches.base import SketchConfig  # noqa: E402
from dp_core.sketches.kmv_impl import KMVSketch  # noqa: E402
from dp_core.sketches.set_impl import SetSketch  # noqa: E402

try:
    from orphaned_roaring_impl_snapshot import RoaringSketch  # noqa: E402

    ROARING_IMPORT_ERROR: str | None = None
except Exception as exc:  # pragma: no cover - environment dependent
    RoaringSketch = None  # type: ignore[assignment]
    ROARING_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

DEFAULT_SEED = 20260708


# ---------------------------------------------------------------------------
# Strengthener 1: history-independence exhibit
# ---------------------------------------------------------------------------


def _random_key(rng: random.Random) -> bytes:
    return rng.getrandbits(128).to_bytes(16, "big")


def _canonical_state(sketch: Any, backend: str) -> tuple:
    """Return a hashable, order-independent snapshot of a sketch's retained
    state, using only each backend's own public/testing-helper accessors."""
    if backend == "set":
        return tuple(sorted(sketch.keys()))
    if backend == "kmv":
        return tuple(sorted(sketch._hashes))  # noqa: SLF001 - test introspection
    if backend == "roaring":
        return tuple(sorted(sketch.keys_as_ints()))
    raise ValueError(backend)


def _build_sketch(backend: str, cfg: SketchConfig, keys: list[bytes]) -> Any:
    if backend == "set":
        s = SetSketch(cfg)
    elif backend == "kmv":
        s = KMVSketch(cfg)
    elif backend == "roaring":
        s = RoaringSketch(cfg)
    else:
        raise ValueError(backend)
    for k in keys:
        s.add(k)
    return s


def _singleton(backend: str, cfg: SketchConfig, key: bytes) -> Any:
    return _build_sketch(backend, cfg, [key])


@dataclass
class HITrialResult:
    backend: str
    regime: str
    n_total: int
    k: int
    state_match: bool
    estimate_a: float
    estimate_b: float
    estimate_match: bool
    abs_estimate_diff: float


def run_history_independence_trial(
    backend: str, n_total: int, k: int, rng: random.Random
) -> HITrialResult:
    cfg = SketchConfig(k=k, use_bloom_for_diff=False, bloom_fp_rate=0.01)
    keys = [_random_key(rng) for _ in range(n_total)]
    u = rng.choice(keys)

    order_a = keys[:]
    rng.shuffle(order_a)
    sketch_full = _build_sketch(backend, cfg, order_a)
    sketch_after_delete = sketch_full.a_not_b(_singleton(backend, cfg, u))

    d_minus_u = [key for key in keys if key != u]
    order_b = d_minus_u[:]
    rng.shuffle(order_b)
    sketch_direct = _build_sketch(backend, cfg, order_b)

    state_a = _canonical_state(sketch_after_delete, backend)
    state_b = _canonical_state(sketch_direct, backend)
    est_a = sketch_after_delete.estimate()
    est_b = sketch_direct.estimate()
    regime = "n<=k (no truncation possible)" if n_total <= k else "n>k (truncation occurred)"
    return HITrialResult(
        backend=backend,
        regime=regime,
        n_total=n_total,
        k=k,
        state_match=(state_a == state_b),
        estimate_a=est_a,
        estimate_b=est_b,
        estimate_match=(est_a == est_b),
        abs_estimate_diff=abs(est_a - est_b),
    )


def run_strengthener_1(seed: int = DEFAULT_SEED, trials_per_cell: int = 150) -> dict[str, Any]:
    rng = random.Random(seed)
    backends = ["set", "kmv"]
    if RoaringSketch is not None:
        backends.append("roaring")

    k = 16  # small k so both n<=k and n>k regimes are cheaply reachable
    n_values_small = [4, 8, 12, 16]  # <= k
    n_values_large = [24, 40, 80, 200]  # > k

    # A second, "production-scale" sanity check at the repo's real default
    # k=4096 (SketchSettings.k default) with a realistic user count, one
    # regime only (n > k, the regime that matters in production since real
    # deployments have far more than 4096 daily actives).
    prod_k = 4096
    prod_n = 20000

    rows: list[HITrialResult] = []
    for backend in backends:
        for n in n_values_small + n_values_large:
            for _ in range(trials_per_cell):
                rows.append(run_history_independence_trial(backend, n, k, rng))
        for _ in range(max(20, trials_per_cell // 5)):
            rows.append(run_history_independence_trial(backend, prod_n, prod_k, rng))

    # Aggregate by (backend, regime)
    summary: dict[tuple[str, str], dict[str, Any]] = {}
    for r in rows:
        key = (r.backend, r.regime if r.k == k else f"n>k (production k={prod_k})")
        agg = summary.setdefault(
            key,
            {
                "backend": r.backend,
                "regime": key[1],
                "n_trials": 0,
                "state_matches": 0,
                "estimate_matches": 0,
                "abs_estimate_diffs": [],
            },
        )
        agg["n_trials"] += 1
        agg["state_matches"] += int(r.state_match)
        agg["estimate_matches"] += int(r.estimate_match)
        agg["abs_estimate_diffs"].append(r.abs_estimate_diff)

    table = []
    for (backend, regime), agg in sorted(summary.items()):
        diffs = agg["abs_estimate_diffs"]
        table.append(
            {
                "backend": backend,
                "regime": regime,
                "n_trials": agg["n_trials"],
                "state_match_rate": agg["state_matches"] / agg["n_trials"],
                "estimate_match_rate": agg["estimate_matches"] / agg["n_trials"],
                "mean_abs_estimate_diff": statistics.fmean(diffs),
                "max_abs_estimate_diff": max(diffs),
            }
        )

    theta_note = (
        "Theta sketch: NOT tested. No Theta sketch implementation exists anywhere in this "
        "repository (committed or uncommitted); the paper's reference-architecture prose "
        "names it as a 'viable probabilistic backend' but no such code exists to run."
    )
    roaring_note = (
        "RoaringSketch: tested from an UNTRACKED, never-committed, unregistered code "
        f"snapshot (experiments/orphaned_roaring_impl_snapshot.py). Import status: "
        f"{'OK' if RoaringSketch is not None else 'FAILED - ' + str(ROARING_IMPORT_ERROR)}. "
        "It is not part of the shipped SketchFactory registrations and not covered by the "
        "33 shipped tests."
    )

    return {
        "seed": seed,
        "trials_per_cell": trials_per_cell,
        "small_k": k,
        "production_k": prod_k,
        "production_n": prod_n,
        "backends_tested": backends,
        "table": table,
        "notes": [theta_note, roaring_note],
    }


# ---------------------------------------------------------------------------
# Strengthener 2, Part A: empirical tree-aggregation simulation
# ---------------------------------------------------------------------------


def _tree_levels_for(t_leaves: int) -> int:
    """Number of levels (including the leaf level) in a binary tree over
    the smallest power of two >= t_leaves, i.e. ceil(log2(t_leaves)) + 1."""
    return math.ceil(math.log2(max(t_leaves, 2))) + 1


def simulate_naive_fixed_budget(
    ground_truth: list[float], epsilon_total: float, rng: random.Random
) -> list[float]:
    """T releases, each with a fresh Laplace draw at epsilon = epsilon_total / T
    (sensitivity 1) -- the classical "naive" continual-release baseline that
    spends a FIXED total budget by splitting it evenly across all releases."""
    t_count = len(ground_truth)
    eps_per_release = epsilon_total / t_count
    scale = 1.0 / eps_per_release
    prefix = 0.0
    noisy_prefixes = []
    for value in ground_truth:
        prefix += value
        noisy_prefixes.append(prefix + sample_laplace(scale, rng))
    return noisy_prefixes


def simulate_tree_aggregation(
    ground_truth: list[float], epsilon_total: float, rng: random.Random
) -> tuple[list[float], int]:
    """Binary/hierarchical mechanism (Chan-Song-Shi 2011): build a tree over
    the leaves, add one independent Laplace draw per node calibrated so that
    sequential composition across the L levels totals epsilon_total, then
    answer each prefix-sum query via its O(log T) dyadic decomposition."""
    t_count = len(ground_truth)
    levels = _tree_levels_for(t_count)
    eps_per_level = epsilon_total / levels
    scale = 1.0 / eps_per_level

    # node_true[level][index] = exact sum of the leaves that node covers
    # node_noise[level][index] = one fresh Laplace draw, cached (each node's
    # noise is added exactly once, regardless of how many queries reuse it).
    node_true: dict[tuple[int, int], float] = {}
    node_noise: dict[tuple[int, int], float] = {}

    def get_node_noisy(level: int, index: int, leaf_range: tuple[int, int]) -> float:
        key = (level, index)
        if key not in node_true:
            lo, hi = leaf_range
            node_true[key] = sum(ground_truth[lo:hi])
            node_noise[key] = sample_laplace(scale, rng)
        return node_true[key] + node_noise[key]

    noisy_prefixes = []
    for t in range(1, t_count + 1):
        # Decompose prefix [0, t) into <= levels disjoint, power-of-two
        # ALIGNED blocks by walking t's set bits from the highest level down
        # to the lowest. Peeling from the low bit instead (as one might
        # naively try) misaligns block boundaries to the tree's fixed node
        # grid; walking high-to-low keeps `start` a multiple of each chosen
        # block_size, which is required for `index = start // block_size`
        # to name a real, fixed tree node.
        total = 0.0
        start = 0
        for level in range(levels - 1, -1, -1):
            block_size = 1 << level
            if t & block_size:
                end = start + block_size
                index = start // block_size
                total += get_node_noisy(level, index, (start, end))
                start = end
        noisy_prefixes.append(total)
    return noisy_prefixes, levels


def run_strengthener_2_part_a(
    seed: int = DEFAULT_SEED, t_horizon: int = 365, n_monte_carlo: int = 400
) -> dict[str, Any]:
    """Empirical Monte-Carlo comparison on a synthetic additive daily
    counter (new-user arrivals), at a matched TOTAL privacy budget equal to
    what the shipped DAU mechanism accumulates over the same horizon under
    its actual (naive, since delta=0) composition rule: T * epsilon_dau."""
    epsilon_dau = DPSettings().epsilon_dau  # real repo default: 0.3
    epsilon_total_matched = t_horizon * epsilon_dau

    rng_truth = random.Random(seed)
    ground_truth = [float(rng_truth.randint(20, 80)) for _ in range(t_horizon)]
    true_prefixes = []
    running = 0.0
    for v in ground_truth:
        running += v
        true_prefixes.append(running)

    naive_errors: list[list[float]] = []
    tree_errors: list[list[float]] = []
    levels_used = None
    for trial in range(n_monte_carlo):
        rng = random.Random(f"{seed}:{trial}:naive")
        naive_noisy = simulate_naive_fixed_budget(ground_truth, epsilon_total_matched, rng)
        rng2 = random.Random(f"{seed}:{trial}:tree")
        tree_noisy, levels_used = simulate_tree_aggregation(
            ground_truth, epsilon_total_matched, rng2
        )
        naive_errors.append([abs(n - t) for n, t in zip(naive_noisy, true_prefixes)])
        tree_errors.append([abs(n - t) for n, t in zip(tree_noisy, true_prefixes)])

    def rmse_at(errors: list[list[float]], day_index: int) -> float:
        vals = [trial_errors[day_index] for trial_errors in errors]
        return math.sqrt(statistics.fmean(v * v for v in vals))

    checkpoints = sorted({0, t_horizon // 4, t_horizon // 2, (3 * t_horizon) // 4, t_horizon - 1})
    empirical_table = []
    for day_index in checkpoints:
        naive_rmse = rmse_at(naive_errors, day_index)
        tree_rmse = rmse_at(tree_errors, day_index)
        empirical_table.append(
            {
                "day": day_index + 1,
                "naive_fixed_budget_rmse": naive_rmse,
                "tree_aggregation_rmse": tree_rmse,
                "tree_vs_naive_ratio": tree_rmse / naive_rmse if naive_rmse > 0 else None,
            }
        )

    # Closed-form predictions for a sanity cross-check against the Monte Carlo run.
    eps_per_release = epsilon_total_matched / t_horizon
    naive_stdev_theory = math.sqrt(2.0) / eps_per_release  # per-release Laplace stdev
    eps_per_level = epsilon_total_matched / levels_used
    tree_stdev_theory_day1 = math.sqrt(1) * math.sqrt(2.0) / eps_per_level  # day 1 touches 1 node
    tree_stdev_theory_full = math.sqrt(levels_used) * math.sqrt(2.0) / eps_per_level

    return {
        "seed": seed,
        "t_horizon": t_horizon,
        "n_monte_carlo": n_monte_carlo,
        "epsilon_dau_per_release": epsilon_dau,
        "epsilon_total_matched": epsilon_total_matched,
        "tree_levels": levels_used,
        "empirical_table": empirical_table,
        "closed_form_check": {
            "naive_per_release_stdev_theory": naive_stdev_theory,
            "tree_stdev_theory_day1_touches_1_node": tree_stdev_theory_day1,
            "tree_stdev_theory_worst_case_touches_all_levels_nodes": tree_stdev_theory_full,
        },
        "disclosure": (
            "This is a synthetic ADDITIVE daily counter (new-user arrivals), not literally "
            "DAU/MAU. DAU/MAU are non-additive distinct-count (union) queries and do not "
            "decompose through a summation tree the way classical Chan-Song-Shi tree "
            "aggregation requires. This simulation validates the noise-growth formulas "
            "(naive: error grows ~linearly with the query's prefix length; tree-aggregation: "
            "error grows ~sqrt(log T)) using the repo's own Laplace sampler and its real "
            "epsilon_dau default, at a TOTAL privacy budget matched to what the shipped "
            "mechanism already accumulates over the horizon under naive/basic composition."
        ),
    }


# ---------------------------------------------------------------------------
# Strengthener 2, Part B: analytical comparison using the repo's real DP
# constants and its actual RDP-composition code (PrivacyAccountant).
# ---------------------------------------------------------------------------


def _gaussian_rdp_per_release(sigma: float, orders: list[float]) -> dict[float, float]:
    """RDP of the Gaussian mechanism at sensitivity 1: eps(alpha) = alpha / (2*sigma^2).
    This is the standard Gaussian-mechanism RDP bound; sensitivity is fixed at 1 to match
    the repo's w_bound-derived sensitivity (min(w_bound, 1) = 1 for the shipped default
    w_bound=2)."""
    return {alpha: alpha / (2.0 * sigma * sigma) for alpha in orders}


def _composed_epsilon_for_sigma(
    sigma: float, delta: float, orders: list[float], n_releases: int
) -> float:
    per_release = _gaussian_rdp_per_release(sigma, orders)
    totals = {alpha: n_releases * val for alpha, val in per_release.items()}
    best, _ = PrivacyAccountant._best_from_curve(delta, totals)  # noqa: SLF001
    assert best is not None
    return best


def _find_sigma_for_target_epsilon(
    target_epsilon: float, delta: float, orders: list[float], n_releases: int
) -> float:
    """Binary search for the per-release Gaussian sigma such that n_releases
    RDP-composed applications hit target_epsilon at the given delta."""
    lo, hi = 1e-6, 1e6
    for _ in range(200):
        mid = math.sqrt(lo * hi)
        eps = _composed_epsilon_for_sigma(mid, delta, orders, n_releases)
        if eps > target_epsilon:
            lo = mid
        else:
            hi = mid
    return hi


def run_strengthener_2_part_b(t_horizon: int = 365) -> dict[str, Any]:
    dp = DPSettings()
    orders = list(dp.rdp_orders)
    sensitivity = float(min(dp.w_bound, 1))

    # ---- DAU (Laplace, pure DP, delta = 0) -------------------------------
    # The shipped accountant's spent_budget() is a plain SUM over releases
    # (naive/basic composition) whenever delta <= 0 -- see
    # PrivacyAccountant.budget_snapshot(): using_rdp = delta > 0 and ...
    eps_dau = dp.epsilon_dau
    dau_cumulative_naive = t_horizon * eps_dau
    dau_per_release_stdev = math.sqrt(2.0) * sensitivity / eps_dau
    levels = _tree_levels_for(t_horizon)
    # Tree-aggregation budget needed to match the SAME per-release accuracy
    # the current mechanism gets "for free" (at the cost of an unbounded,
    # ever-growing cumulative epsilon as the deployment keeps running):
    #   sqrt(levels) * sqrt(2) * sensitivity / (eps_total/levels) = dau_per_release_stdev
    #   => eps_total = eps_dau * levels^1.5
    dau_tree_total_budget_matching_accuracy = eps_dau * (levels**1.5)
    # And the reverse: at the SAME total budget the current mechanism has
    # already accumulated by day 365, what per-release stdev could a tree
    # scheme guarantee, for as long as the tree has capacity (2^(levels-1)
    # days), instead of paying eps_dau again every single day forever?
    eps_per_level_matched = dau_cumulative_naive / levels
    dau_tree_stdev_at_matched_total_budget = (
        math.sqrt(levels) * math.sqrt(2.0) * sensitivity / eps_per_level_matched
    )

    # ---- MAU (Gaussian, approximate DP, delta = 1e-6) --------------------
    delta = dp.delta
    eps_mau = dp.epsilon_mau
    sigma_mau = math.sqrt(2.0 * math.log(1.25 / delta)) * sensitivity / eps_mau
    mau_cumulative_rdp_composed = _composed_epsilon_for_sigma(sigma_mau, delta, orders, t_horizon)
    mau_cumulative_naive_sum = t_horizon * eps_mau  # for reference only; NOT what the code uses
    # Tree-aggregation analogue for Gaussian: find the per-level sigma that
    # would let a `levels`-deep RDP-composed tree hit the SAME total
    # (RDP-composed) epsilon the current mechanism has accumulated by day
    # 365, then report the per-query stdev at the tree's worst case (root,
    # `levels` nodes touched) vs best case (day 1, 1 node touched).
    sigma_level_matched = _find_sigma_for_target_epsilon(
        mau_cumulative_rdp_composed, delta, orders, levels
    )
    mau_tree_stdev_worst_case = math.sqrt(levels) * sigma_level_matched
    mau_tree_stdev_best_case = sigma_level_matched

    return {
        "t_horizon": t_horizon,
        "tree_levels": levels,
        "sensitivity": sensitivity,
        "rdp_orders": orders,
        "dau": {
            "epsilon_dau_per_release": eps_dau,
            "shipped_composition_rule": "naive summation (delta=0 -> RDP path is skipped by PrivacyAccountant.budget_snapshot)",
            "cumulative_epsilon_after_365_releases": dau_cumulative_naive,
            "per_release_noise_stdev": dau_per_release_stdev,
            "tree_total_budget_to_match_same_per_release_accuracy": dau_tree_total_budget_matching_accuracy,
            "tree_per_release_stdev_at_same_cumulative_365day_budget": dau_tree_stdev_at_matched_total_budget,
        },
        "mau": {
            "epsilon_mau_per_release": eps_mau,
            "delta": delta,
            "sigma_per_release": sigma_mau,
            "shipped_composition_rule": "RDP composition via PrivacyAccountant._best_from_curve (delta>0 path)",
            "cumulative_epsilon_after_365_releases_rdp_composed": mau_cumulative_rdp_composed,
            "cumulative_epsilon_after_365_releases_if_naively_summed_for_reference_only": mau_cumulative_naive_sum,
            "tree_per_level_sigma_to_match_same_cumulative_365day_rdp_budget": sigma_level_matched,
            "tree_per_query_stdev_best_case_day1": mau_tree_stdev_best_case,
            "tree_per_query_stdev_worst_case_root": mau_tree_stdev_worst_case,
            "shipped_per_release_stdev_for_reference": sigma_mau,
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", type=Path, default=EXPERIMENTS_ROOT / "strengtheners_results.json")
    parser.add_argument("--trials-per-cell", type=int, default=150)
    parser.add_argument("--monte-carlo-trials", type=int, default=400)
    parser.add_argument("--horizon", type=int, default=365)
    args = parser.parse_args()

    print("=== Strengthener 1: history-independence exhibit ===")
    s1 = run_strengthener_1(seed=args.seed, trials_per_cell=args.trials_per_cell)
    for row in s1["table"]:
        print(
            f"  backend={row['backend']:8s} regime={row['regime']:32s} "
            f"n_trials={row['n_trials']:4d} state_match_rate={row['state_match_rate']:.4f} "
            f"estimate_match_rate={row['estimate_match_rate']:.4f} "
            f"mean_abs_diff={row['mean_abs_estimate_diff']:.4f}"
        )
    for note in s1["notes"]:
        print(f"  NOTE: {note}")

    print()
    print("=== Strengthener 2A: empirical tree-aggregation Monte Carlo ===")
    s2a = run_strengthener_2_part_a(
        seed=args.seed, t_horizon=args.horizon, n_monte_carlo=args.monte_carlo_trials
    )
    print(
        f"  T={s2a['t_horizon']} matched epsilon_total={s2a['epsilon_total_matched']:.4f} "
        f"(= T * epsilon_dau={s2a['epsilon_dau_per_release']}), tree_levels={s2a['tree_levels']}, "
        f"monte_carlo_trials={s2a['n_monte_carlo']}"
    )
    for row in s2a["empirical_table"]:
        ratio = row["tree_vs_naive_ratio"]
        print(
            f"  day={row['day']:4d} naive_rmse={row['naive_fixed_budget_rmse']:.3f} "
            f"tree_rmse={row['tree_aggregation_rmse']:.3f} "
            f"tree/naive={ratio:.4f}"
            if ratio is not None
            else ""
        )

    print()
    print("=== Strengthener 2B: analytical comparison (repo's real DP constants) ===")
    s2b = run_strengthener_2_part_b(t_horizon=args.horizon)
    print(
        f"  T={s2b['t_horizon']} tree_levels={s2b['tree_levels']} sensitivity={s2b['sensitivity']}"
    )
    print("  DAU:", json.dumps(s2b["dau"], indent=2))
    print("  MAU:", json.dumps(s2b["mau"], indent=2))

    out_payload = {
        "generated_by": "experiments/strengtheners.py",
        "seed": args.seed,
        "strengthener_1": s1,
        "strengthener_2_part_a": s2a,
        "strengthener_2_part_b": s2b,
    }
    args.out.write_text(json.dumps(out_payload, indent=2, default=str))
    print(f"\nWrote full results JSON to {args.out}")


if __name__ == "__main__":
    main()
