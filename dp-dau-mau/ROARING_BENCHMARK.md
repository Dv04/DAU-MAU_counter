# Roaring Bitmap backend — measured benchmarks

All numbers below are **measured on this branch** (`popets-strengtheners`), not
copied from the paper. Where a measured value differs from the paper's current
claim, the difference is stated explicitly; the paper should be updated to
match these measurements, never the other way around.

## Environment

- Machine: Apple Silicon (macOS, `darwin`), same class as the paper's "Apple M1, 16GB".
- Python 3.13.13, fresh venv from `requirements.txt` + `pyroaring` 1.1.0 (CRoaring bindings).
- Backend under test: `RoaringSketch` (`src/dp_core/sketches/roaring_impl.py`) —
  keys hashed with personalized BLAKE2b to **64 bits** and stored in a
  `pyroaring.BitMap64`. This is an *exact* backend (no truncation collisions;
  see the module docstring for why 64-bit and not the orphaned draft's 32-bit).
- Ingest path: `PartitionedLogManager` per-day append-only **binary log**
  (`src/dp_core/storage/`), buffered writes — now the pipeline's committed
  ingest path, replacing the previous per-event SQLite `INSERT`+`commit`.
- Reproduce:
  ```
  .venv/bin/python eval/benchmark_roaring.py pipeline \
      --user-counts 10000 100000 1000000 --sketch roaring --out roaring.json
  .venv/bin/python eval/benchmark_roaring.py memory \
      --active-per-day 2000 20000 200000 --days 30 --out memory.json
  ```
- Methodology: N users, 30 days, 20% daily-active rate (≈ `0.2 * 30 * N`
  events — the paper's stated workload). Query latency is p50/p99 over 50
  repeated samples after one warm-up call. Peak RSS is whole-process
  `getrusage(RUSAGE_SELF).ru_maxrss` (bytes on macOS), so it **includes the
  in-process synthetic event list**, not just backend state.

## MAU union optimization: profiling, what was tried, what landed

The exact MAU query was profiled with `cProfile` on the real pipeline
(`PipelineManager.get_mau_release` → `WindowManager.get_mau`,
`src/dp_core/windows.py`). At 200k users / 40k active/day, 10 repeated MAU
calls (300 total day-unions) showed:

```
   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
      300    2.717    0.009    2.717    0.009 roaring_impl.py:68(union)
```

**97.5% of wall time was the Python for-loop in `get_mau`** doing 30
sequential `union.union(snapshot.sketch)` calls
(`RoaringSketch.union` → `self._bitmap |= other._bitmap`), confirming the
suspected hot path. Everything else (snapshot cache lookups, DP release,
budget accounting, SQLite erasure-log reads) was negligible (<3%).

Three fixes were tried, in the order the task specified, each measured
against the same 200k-user / 40k-active/day fixture (real hashed keys from
the pipeline, not synthetic uniform ints, since the paper's keys are BLAKE2b
digests):

| Optimization tried | Measured vs. current loop `\|=` | Kept? |
|---|---|---|
| (a) `pyroaring.BitMap64.union(*bitmaps)` (native N-ary union) | **349.9 ms vs 297.0 ms — ~18% *slower*** | No |
| (a) pairwise tree-merge (`\|`, new bitmaps each level) | **489.7 ms — ~65% slower** | No |
| (a) pairwise tree-merge (in-place `\|=`, copied leaves) | **566.7 ms — ~91% slower** | No |
| (a) sequential loop, smallest-bitmap-first ordering | **336.6 ms — ~13% slower** | No |
| (c) serialization/copy overhead in the hot path | none found — the union writes directly into a freshly-created `BitMap64`, no extra copy/serialize round-trip | N/A |
| (b) memoized window-union cache, keyed by a monotonic per-day version fingerprint | **repeat query of the same window: ~0.6 ms vs ~297 ms — exact cache hit** | **Yes** |

**Why (a) doesn't help here:** keys are BLAKE2b digests hashed uniformly
over the full 64-bit space (by design — see `roaring_impl.py`'s docstring on
why 64-bit and not 32-bit truncation). Uniformly-random 64-bit values give
each day's ~40k-200k entries almost no shared high-order bits, so a
`BitMap64`'s top-level structure degenerates toward many small/singleton
containers rather than a few large, run-compressible ones. In that regime,
pyroaring's native multi-way union (which does more bookkeeping to merge
many inputs in one pass) and pairwise tree merges (which allocate/copy
intermediate bitmaps at every level) both do *more* total work than simply
accumulating in place — so the original sequential `|=` loop was already the
fastest option found. This is a measured, honest negative result, not an
assumption.

**What landed — option (b):** `WindowManager` (`src/dp_core/windows.py`) now
memoizes the union for a given `(end_day, window_days)`, fingerprinted by
each involved day's monotonically-increasing `version` (bumped only when
`_build_snapshot` rebuilds that day, e.g. after an erasure marks it dirty).
If no day in the window has changed since the union was last computed, the
cached union is returned as-is — this is not an approximation, it is
*exactly* the same object that a full recomputation of unchanged inputs
would produce. Any change to any day inside the window (new ingest,
erasure/retroactive deletion) changes that day's version and transparently
invalidates the cache, forcing an exact recomputation. This was verified
independently of the existing test suite: a manual script erased a user via
the real `ingest_event`/`replay_deletions()` production path (no test-only
`snapshots.clear()` shortcut) and confirmed the MAU estimate correctly
dropped from 2 to 1 on the very next query.

This targets the realistic "same MAU window queried repeatedly" access
pattern (e.g. a dashboard polling "MAU as of today" many times before the
day rolls over) — it does **not** make a genuinely new/never-seen window
(e.g. today's window, asked for the first time) faster; that query still
pays the full union cost, honestly reported below as "fresh" latency.

## Headline: Roaring backend at 1M users (fast binary-log ingest)

| Metric | Measured (Roaring, exact 64-bit) | Paper's current claim | Verdict |
|---|---|---|---|
| Ingest throughput | **107,817 events/s** (unchanged by this work) | 115,000 events/s | **≈ MATCH** (within ~6%) |
| DAU query p50 / p99 | 6.64 ms / 14.66 ms (unchanged) | 2.4 ms (median) / 3.9 ms (p99) | DIFFER (higher, same order) |
| MAU query, cold first-ever call | **14,942 ms** (30 uncached day-sketch rebuilds + union) | — | new measurement, not previously isolated |
| MAU query, fresh (uncached) p50 / p99 | 2,690 ms / **4,474 ms** (union-compute floor; day sketches warm, window never cached) | 202 ms (p99) | **DIFFER (≈22× slower)** |
| MAU query, cached (repeat same window) p50 / p99 | **0.57 ms / 1.45 ms** — exact, same bits as a fresh recompute | 202 ms (p99) | **BEATS** the paper's claim, for this access pattern, exactly |
| Peak RSS @ 1M | **1,554 MB** | ~1,150 MB (1.15 GB) | DIFFER (~1.35× higher) |

The honest split: a **genuinely new** MAU window (never queried before) still
costs multi-seconds at 1M users — an exact 64-bit Roaring union of 30 daily
bitmaps (each ~200k random 64-bit values → sparse, mostly-singleton
containers) is intrinsically heavier than the paper's 202 ms, which was
produced by the orphaned draft's *32-bit-truncated* `pyroaring.BitMap` (dense
containers, fast SIMD OR — but lossy, ~116 colliding user-pairs at 1M). What
changed is that **repeat queries of the same window are now free and exact**
(memoized union, see above) — a real, common production pattern, but not the
same claim as "every MAU query takes 202 ms."

## Roaring backend — scaling (fast binary-log ingest)

Before (measured on this branch prior to the window-union cache — every call,
including repeats of the same window, recomputed the union from scratch):

| Users | Events | Ingest (s) | Throughput | DAU p50 | DAU p99 | MAU p50 | MAU p99 | Peak RSS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 10,000 | 60,000 | 0.52 | 114,427/s | 0.41 ms | 0.54 ms | 14.7 ms | 17.3 ms | 70.9 MB |
| 100,000 | 600,000 | 5.31 | 113,035/s | 0.70 ms | 0.94 ms | 137.4 ms | 146.0 ms | 286.9 MB |
| **1,000,000** | **6,000,000** | **55.65** | **107,817/s** | **6.64 ms** | **14.66 ms** | **2,821 ms** | **3,423 ms** | **1,636 MB** |

After (this work — memoized window-union cache in `WindowManager.get_mau`;
`mau fresh` = union-compute floor with the cache force-cleared every sample,
i.e. what a genuinely new window still costs; `mau cached` = repeat query of
the *same* window, the realistic dashboard-polling case):

| Users | Ingest (s) | Throughput | DAU p50 | DAU p99 | MAU cold (1st ever) | MAU fresh p50 | MAU fresh p99 | MAU cached p50 | MAU cached p99 | Peak RSS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10,000 | 0.50 | 119,055/s | 0.46 ms | 0.70 ms | 109.8 ms | 14.30 ms | 17.60 ms | **0.57 ms** | **0.79 ms** | 70.8 MB |
| 100,000 | 5.65 | 106,107/s | 0.75 ms | 2.04 ms | 1,119.9 ms | 132.44 ms | 155.04 ms | **0.56 ms** | **1.07 ms** | 267.9 MB |
| **1,000,000** | **56.14** | **106,883/s** | **11.88 ms** | **18.92 ms** | **14,942 ms** | **2,690 ms** | **4,474 ms** | **0.57 ms** | **1.45 ms** | 1,553.5 MB |

Reading this honestly: the "fresh" column at each scale is statistically the
same as the "before" column (within run-to-run noise) — confirming the raw
union-compute cost did **not** get algorithmically faster (per the (a)/(c)
findings above, no faster exact algorithm was found for this workload). The
"cached" column is the genuine, exact win: **~25× faster at 10k, ~237× at
100k, ~4,700× at 1M** (p50, cached vs. fresh) — the gain grows with scale
because the fresh/uncached cost itself grows with scale while the cache hit
stays flat (a fingerprint-tuple comparison plus returning an existing
object). It is the *same computation, skipped* when nothing in the window
changed, not an approximation.

## Committed baseline BEFORE the fast log (SQLite ledger, for reference)

Same Roaring backend, but with the previously-committed per-event SQLite ingest
path (one `INSERT`+`commit` per event). This is the "as-committed before this
work" number and shows the binary log is the entire throughput story:

| Users | Ingest throughput | DAU p99 | MAU p99 | Peak RSS |
|---|---:|---:|---:|---:|
| 10,000 | 8,431/s | 0.49 ms | 15.8 ms | 59.1 MB |
| 100,000 | 8,003/s | 0.86 ms | 195.1 ms | 167.7 MB |
| 1,000,000 | 9,176/s | 35.4 ms | 3,995 ms | 1,215.6 MB |

**Binary log vs SQLite at 1M: 107,817/s vs 9,176/s — a ~11.75× ingest speedup**,
purely from replacing per-event commits with buffered append-only logging. (The
Roaring sketch is identical in both; the storage layer is the only change.)

## Set vs Roaring — why Roaring (memory compression)

Sketch-only comparison (bypasses the pipeline/log entirely): build `days`
day-sketches of `active_per_day` freshly-hashed users each, in an isolated
subprocess per (backend, size), reporting serialized bytes and process peak RSS.

| Users (active/day × 30d) | Backend | Serialized total | Bytes/user | Process peak RSS |
|---|---|---:|---:|---:|
| 60,000 | set | 2,100,720 B (2.00 MB) | 35.01 | 51.9 MB |
| 60,000 | roaring | 1,320,240 B (1.26 MB) | 22.00 | 50.4 MB |
| 600,000 | set | 21,002,870 B (20.0 MB) | 35.00 | 152.2 MB |
| 600,000 | roaring | 13,200,004 B (12.6 MB) | 22.00 | 116.6 MB |
| **6,000,000** | **set** | **210,006,705 B (200 MB)** | **35.00** | **784.9 MB** |
| **6,000,000** | **roaring** | **131,984,406 B (126 MB)** | **22.00** | **526.5 MB** |

- Serialized state: Roaring is **~1.59× smaller** (22.0 vs 35.0 bytes/user), stable across scale.
- Process RSS at 6M user-days: Roaring **526 MB vs set 785 MB (~33% less RAM)**.
- At the full-pipeline 1M level this also shows up: Roaring peak RSS **1,636 MB
  vs the exact `set` backend's 2,082 MB** (same fast-log ingest path).

This is the concrete "why Roaring": exact counting at materially lower memory
than a plain Python `set`.

## Set backend at 1M (fast log, for the memory/latency contrast)

| Metric | set | roaring |
|---|---:|---:|
| Ingest throughput | 108,779/s | 107,817/s |
| DAU p50 / p99 | 0.33 / 0.58 ms | 6.64 / 14.66 ms |
| MAU p50 / p99 (pre-cache / "fresh") | 778 / 1,396 ms | 2,821 / 3,423 ms |
| Peak RSS | 2,082 MB | 1,636 MB |

Honest nuance: the Python `set` backend is actually **faster on a fresh
union** (its union is a C-level hash-set union; Roaring's 64-bit
sparse-container union is heavier), but uses **~27% more RAM**. Roaring's
advantage is memory, not fresh-query speed, at this exact-backend/64-bit
configuration. Not re-measured post-cache: the window-union memoization
added in this work lives in the backend-agnostic `WindowManager.get_mau`
(`src/dp_core/windows.py`), so it applies identically to the `set` backend
for repeat queries of the same window — this table's numbers were left as
originally measured (pre-cache / equivalent to "fresh") since the `set`
backend is out of scope for this MAU-latency work.

## MATCH / DIFFER vs the paper's current claims

Paper currently claims (abstract + Table `tab:performance` + Section Performance):
**115k events/s ingest, 202 ms MAU p99, ~1.15 GB @ 1M, 42× ingest / 223× MAU.**

| # | Paper claim | Measured (this branch) | Verdict |
|---|---|---|---|
| 1 | 115,000 events/s ingest | 107,817/s @ 1M (114,427/s @ 10k) | **≈ MATCH** — reproducible with the binary-log engine; within ~6%. Suggest updating to "≈108k events/s at 1M". |
| 2 | 202 ms MAU query (p99) | **fresh (never-cached window): 4,474 ms p99 / 2,690 ms p50 @ 1M**; **cached (repeat of same window): 1.45 ms p99 / 0.57 ms p50 @ 1M — exact** | **DIFFER for a fresh query (≈22× slower)**; the 202 ms figure is still not reproducible as a claim about *every* MAU query — it reflects 32-bit truncation, not caching. A window-union cache (added in this work) makes *repeat* queries of the same window exact and faster than 202 ms, but a genuinely new window still costs multi-seconds at 1M. Recommend the paper state both numbers, or scope 202 ms explicitly to the lossy 32-bit variant. |
| 3 | ~1.15 GB @ 1M | 1,553.5 MB (1.55 GB) whole-process incl. event list | **DIFFER — ~1.35× higher.** Note: the *previous SQLite path* measured 1,216 MB (≈1.15 GB), so the paper's figure matches the OLD path, not the fast one. Sketch-only Roaring state for 6M user-days is only 126 MB serialized / 526 MB RSS. |
| 4a | 42× ingest (naive 2,700/s → 115,600/s) | fast 106,883/s ÷ old SQLite 9,176/s = **~11.6×**; ÷ a 2,700/s naive baseline would be ~40× | **PARTIAL** — the ~40× vs a 2,700/s "naive Python" holds if that baseline is taken as given, but this branch did not re-measure a 2,700/s naive loop; the measured, in-repo speedup (SQLite→binary-log) is ~11.6×. |
| 4b | 223× MAU (naive 45.2 s → 0.202 s) | fresh: 45.2 s ÷ 4.47 s ≈ 10×, not 223×; **cached: 45.2 s ÷ 0.00145 s ≈ 31,200×**, but that ratio is comparing a naive *cold* computation against a *warm-cache hit*, not an apples-to-apples query cost | **DIFFER as originally stated** (the 223× depended on the unreproducible 202 ms) — but note a *cached* repeat query genuinely beats it once the window has been computed once, an option that didn't exist before this work. |

### Bottom line for the paper
- **Ingest throughput and the Roaring memory-compression story are real and reproducible** (≈107k events/s; Roaring 22 vs set 35 bytes/user).
- **MAU latency is now genuinely two numbers, both measured and both honest:** a fresh/never-seen window at 1M users costs **~2.7 s p50 / ~4.5 s p99** (this is the true exact-backend floor — profiling and three alternative union algorithms/orderings were tried and none beat the simple sequential loop for uniformly-hashed 64-bit keys, so this is not expected to get meaningfully faster without changing the key space). A **repeat** query of the same window (the realistic "MAU as of today, polled repeatedly" pattern) is memoized and now costs **~0.6 ms p50 / ~1.5 ms p99 at every scale tested (10k/100k/1M)** — exact, not approximate.
- **The paper's original 202 ms MAU / 223× claim is still not reproducible as "every MAU query costs 202 ms"** — it came from lossy 32-bit truncation. Recommend the paper report both the fresh-query floor (~2.7-4.5 s at 1M) and the cached-repeat-query number (~0.6-1.5 ms, any scale), rather than a single figure.
- **The 1.15 GB memory figure matches the OLD SQLite path, not the fast one** (which is ~1.55 GB whole-process); the clean per-backend Roaring state is far smaller (126 MB serialized for 6M user-days).
