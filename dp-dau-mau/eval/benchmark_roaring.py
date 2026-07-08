#!/usr/bin/env python3
"""Scalability + memory benchmark for the Roaring Bitmap sketch backend.

This re-derives the paper's claimed evaluation numbers (115k events/sec
ingest, 202ms MAU p99, 1.15GB peak RSS at 1M users) against the *real*,
now-registered RoaringSketch backend (src/dp_core/sketches/roaring_impl.py),
instead of the never-committed, unregistered 32-bit-truncated draft that
originally produced those numbers.

Two measurements:

1. End-to-end pipeline benchmark (`pipeline` command): generates a synthetic
   event stream (N users, 30 days, 20% daily-active rate -- the paper's
   stated methodology, giving ~0.2*30*N events), ingests it through the real
   PipelineManager (which persists to a SQLite-backed ledger), and measures:
     - ingest throughput (events/sec)
     - DAU / MAU query latency p50 and p99 over repeated samples (not a
       single call, unlike the original draft script)
     - whole-process peak RSS (resource.getrusage, bytes on macOS)

2. Sketch-only memory comparison (`memory` command): isolates the
   set-vs-roaring compression story from ledger/SQLite overhead by directly
   building `active_users_per_day` day-sketches with each backend (bypassing
   the pipeline entirely) and measuring both serialized bytes and retained
   process RSS delta.

Usage:
    .venv/bin/python eval/benchmark_roaring.py pipeline \
        --user-counts 10000 100000 1000000 --sketch roaring --out out.json
    .venv/bin/python eval/benchmark_roaring.py memory \
        --active-per-day 2000 20000 200000 --days 30 --out mem.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import gc
import json
import random
import resource
import shutil
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

DAILY_ACTIVE_RATE = 0.2
NUM_DAYS = 30
NUM_QUERY_SAMPLES = 50


def get_peak_rss_mb() -> float:
    """Peak resident set size in MB. macOS reports ru_maxrss in bytes."""
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return usage / (1024 * 1024)
    return usage / 1024  # Linux reports KB


def generate_events(n_users: int, days: int, seed: int) -> list:
    from dp_core.pipeline import EventRecord

    rng = random.Random(seed)
    base_date = dt.date(2023, 1, 1)
    user_ids = list(range(n_users))
    active_count = int(n_users * DAILY_ACTIVE_RATE)
    events = []
    for day_offset in range(days):
        day = base_date + dt.timedelta(days=day_offset)
        active_users = rng.sample(user_ids, active_count)
        for uid in active_users:
            events.append(EventRecord(user_id=str(uid), op="+", day=day, metadata={}))
    return events


def run_pipeline_benchmark(user_counts: list[int], sketch: str, seed: int) -> list[dict]:
    import os
    import uuid

    from dp_core import config as config_module
    from dp_core.pipeline import PipelineManager

    results = []
    for n in user_counts:
        print(f"[pipeline] N={n} sketch={sketch} ...", flush=True)
        data_dir = Path(f"/tmp/dpdau-bench-{sketch}-{n}-{uuid.uuid4().hex[:8]}")
        shutil.rmtree(data_dir, ignore_errors=True)

        os.environ["DATA_DIR"] = str(data_dir)
        os.environ["SKETCH_IMPL"] = sketch
        os.environ["DAU_BUDGET_TOTAL"] = "1e9"
        os.environ["MAU_BUDGET_TOTAL"] = "1e9"
        os.environ["HASH_SALT_ROTATION_DAYS"] = "30"
        os.environ["MAU_WINDOW_DAYS"] = str(NUM_DAYS)

        t0 = time.time()
        events = generate_events(n, NUM_DAYS, seed)
        gen_time = time.time() - t0
        print(f"  generated {len(events)} events in {gen_time:.2f}s", flush=True)

        cfg = config_module.AppConfig.from_env()
        pipeline = PipelineManager(config=cfg)

        gc.collect()
        t0 = time.time()
        pipeline.ingest_batch(events)
        ingest_time = time.time() - t0
        events_per_sec = len(events) / ingest_time if ingest_time > 0 else float("inf")
        peak_rss_after_ingest_mb = get_peak_rss_mb()
        print(
            f"  ingest: {ingest_time:.2f}s ({events_per_sec:.0f} events/sec), "
            f"peak_rss={peak_rss_after_ingest_mb:.1f}MB",
            flush=True,
        )

        last_day = dt.date(2023, 1, 1) + dt.timedelta(days=NUM_DAYS - 1)

        # Warm the snapshot cache once (first call pays the rebuild cost);
        # then sample repeated calls for a real latency distribution.
        pipeline.get_daily_release(last_day)
        dau_samples_ms = []
        for _ in range(NUM_QUERY_SAMPLES):
            t0 = time.perf_counter()
            pipeline.get_daily_release(last_day)
            dau_samples_ms.append((time.perf_counter() - t0) * 1000)

        # The very first-ever MAU query for this window: no per-day sketch is
        # cached yet (all NUM_DAYS must be built from the activity log) *and*
        # the (end_day, window_days) union cache is empty. This is the
        # absolute worst-case single-shot cold latency.
        t0 = time.perf_counter()
        pipeline.get_mau_release(last_day, NUM_DAYS)
        mau_cold_first_query_ms = (time.perf_counter() - t0) * 1000

        # "Fresh" MAU latency: day-level sketches are warm (already built by
        # the call above / by ingest), but the window-union memoization
        # cache (see WindowManager.get_mau) is force-cleared before every
        # sample -- i.e. this measures the honest per-query union-compute
        # cost as if this exact (end_day, window_days) had never been asked
        # for before. This is the number that matters for a *new* MAU query
        # (a window nobody has asked for yet, e.g. a new end_day rolling in).
        mau_fresh_samples_ms = []
        for _ in range(NUM_QUERY_SAMPLES):
            pipeline.window_manager._mau_cache.clear()
            t0 = time.perf_counter()
            pipeline.get_mau_release(last_day, NUM_DAYS)
            mau_fresh_samples_ms.append((time.perf_counter() - t0) * 1000)

        # "Cached" MAU latency: repeat queries of the *same* (end_day,
        # window_days) -- e.g. a dashboard re-polling "MAU as of today"
        # before the day rolls over. The union cache (memoized by a
        # monotonic per-day version fingerprint -- see WindowManager.get_mau)
        # makes these O(1) and byte-identical to the fresh computation.
        pipeline.get_mau_release(last_day, NUM_DAYS)
        mau_cached_samples_ms = []
        for _ in range(NUM_QUERY_SAMPLES):
            t0 = time.perf_counter()
            pipeline.get_mau_release(last_day, NUM_DAYS)
            mau_cached_samples_ms.append((time.perf_counter() - t0) * 1000)

        peak_rss_final_mb = get_peak_rss_mb()

        def pctl(samples: list[float], p: float) -> float:
            return statistics.quantiles(samples, n=100, method="inclusive")[int(p) - 1]

        result = {
            "sketch": sketch,
            "users": n,
            "num_events": len(events),
            "ingest_time_sec": ingest_time,
            "events_per_sec": events_per_sec,
            "dau_latency_p50_ms": statistics.median(dau_samples_ms),
            "dau_latency_p99_ms": pctl(dau_samples_ms, 99),
            "mau_cold_first_query_ms": mau_cold_first_query_ms,
            "mau_fresh_latency_p50_ms": statistics.median(mau_fresh_samples_ms),
            "mau_fresh_latency_p99_ms": pctl(mau_fresh_samples_ms, 99),
            "mau_cached_latency_p50_ms": statistics.median(mau_cached_samples_ms),
            "mau_cached_latency_p99_ms": pctl(mau_cached_samples_ms, 99),
            # Back-compat keys: keep pointing at the "fresh" (uncached, worst
            # case per-window) numbers so anything reading the old field
            # names gets the honest floor, not the cache-inflated one.
            "mau_latency_p50_ms": statistics.median(mau_fresh_samples_ms),
            "mau_latency_p99_ms": pctl(mau_fresh_samples_ms, 99),
            "peak_rss_after_ingest_mb": peak_rss_after_ingest_mb,
            "peak_rss_final_mb": peak_rss_final_mb,
        }
        print(f"  result: {json.dumps(result, indent=2)}", flush=True)
        results.append(result)

        del pipeline
        del events
        gc.collect()
        shutil.rmtree(data_dir, ignore_errors=True)

    return results


def _build_day_sketches_and_report(backend_name: str, n_active: int, days: int, seed: int) -> dict:
    """Worker body: build `days` day-sketches with one backend, hold them all
    in memory, and report serialized size + this (fresh, isolated) process's
    peak RSS. Must run in its own subprocess -- ru_maxrss is a monotonic
    high-water mark since process start, so before/after diffing within one
    long-lived process silently ratchets upward across trials and cannot be
    trusted for A/B comparison.
    """
    from dp_core.config import AppConfig
    from dp_core.hashing import hash_user_id
    from dp_core.sketches.base import SketchConfig
    from dp_core.sketches.roaring_impl import RoaringSketch
    from dp_core.sketches.set_impl import SetSketch

    backend_cls = {"set": SetSketch, "roaring": RoaringSketch}[backend_name]
    cfg = SketchConfig(k=4096, use_bloom_for_diff=False, bloom_fp_rate=0.01)
    app_cfg = AppConfig.from_env()
    rng = random.Random(seed)
    base_date = dt.date(2023, 1, 1)

    sketches = []
    for day_offset in range(days):
        day = base_date + dt.timedelta(days=day_offset)
        sk = backend_cls(cfg)
        for _ in range(n_active):
            key = hash_user_id(f"user-{rng.randrange(10**9)}-{day_offset}", day, app_cfg)
            sk.add(key)
        sk.compact()
        sketches.append(sk)

    total_serialized = sum(len(sk.serialize()) for sk in sketches)
    gc.collect()
    return {
        "backend": backend_name,
        "active_per_day": n_active,
        "days": days,
        "total_users_across_days": n_active * days,
        "total_serialized_bytes": total_serialized,
        "bytes_per_user": total_serialized / (n_active * days),
        "process_peak_rss_mb": get_peak_rss_mb(),
    }


def run_memory_comparison(active_per_day: list[int], days: int, seed: int) -> list[dict]:
    """Direct sketch-only memory comparison, bypassing the pipeline/SQLite.

    Runs each (backend, active_per_day) combination in its own subprocess so
    peak RSS reflects only that backend's retained sketches, not whatever
    ran before it in this process. Reports both serialized bytes (backend's
    own compact on-disk form) and the isolated process's peak RSS -- the two
    numbers a "why Roaring" table needs.
    """
    import subprocess

    results = []
    for n_active in active_per_day:
        for backend_name in ("set", "roaring"):
            print(
                f"[memory] backend={backend_name} active_per_day={n_active} days={days} ...",
                flush=True,
            )
            proc = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "memory-worker",
                    "--backend",
                    backend_name,
                    "--active-per-day",
                    str(n_active),
                    "--days",
                    str(days),
                    "--seed",
                    str(seed),
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=True,
            )
            result = json.loads(proc.stdout.strip().splitlines()[-1])
            print(f"  {json.dumps(result, indent=2)}", flush=True)
            results.append(result)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    p1 = sub.add_parser("pipeline", help="End-to-end pipeline ingest+query benchmark")
    p1.add_argument("--user-counts", type=int, nargs="+", default=[10000, 100000])
    p1.add_argument("--sketch", type=str, default="roaring")
    p1.add_argument("--seed", type=int, default=20260708)
    p1.add_argument("--out", type=Path, default=Path("benchmark_roaring_pipeline.json"))

    p2 = sub.add_parser("memory", help="Sketch-only set-vs-roaring memory comparison")
    p2.add_argument("--active-per-day", type=int, nargs="+", default=[2000, 20000])
    p2.add_argument("--days", type=int, default=30)
    p2.add_argument("--seed", type=int, default=20260708)
    p2.add_argument("--out", type=Path, default=Path("benchmark_roaring_memory.json"))

    p3 = sub.add_parser("memory-worker", help=argparse.SUPPRESS)
    p3.add_argument("--backend", type=str, required=True, choices=["set", "roaring"])
    p3.add_argument("--active-per-day", type=int, required=True)
    p3.add_argument("--days", type=int, required=True)
    p3.add_argument("--seed", type=int, required=True)

    args = parser.parse_args()

    if args.mode == "pipeline":
        results = run_pipeline_benchmark(args.user_counts, args.sketch, args.seed)
    elif args.mode == "memory":
        results = run_memory_comparison(args.active_per_day, args.days, args.seed)
    else:  # memory-worker
        result = _build_day_sketches_and_report(
            args.backend, args.active_per_day, args.days, args.seed
        )
        print(json.dumps(result))
        return

    args.out.write_text(json.dumps(results, indent=2))
    print(f"Wrote {args.out}", flush=True)


if __name__ == "__main__":
    main()
