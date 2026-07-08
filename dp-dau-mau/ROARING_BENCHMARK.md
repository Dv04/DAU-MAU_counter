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

## Headline: Roaring backend at 1M users (fast binary-log ingest)

| Metric | Measured (Roaring, exact 64-bit) | Paper's current claim | Verdict |
|---|---|---|---|
| Ingest throughput | **107,817 events/s** | 115,000 events/s | **≈ MATCH** (within ~6%) |
| DAU query p50 / p99 | 6.64 ms / 14.66 ms | 2.4 ms (median) / 3.9 ms (p99) | DIFFER (higher, same order) |
| MAU query p50 / p99 | 2,821 ms / **3,423 ms** | 202 ms (p99) | **DIFFER (≈17× slower)** |
| Peak RSS @ 1M | **1,636 MB** | ~1,150 MB (1.15 GB) | DIFFER (~1.4× higher) |

The single big discrepancy is **MAU latency**: an exact 64-bit Roaring union of
30 daily bitmaps (each ~200k random 64-bit values → sparse, mostly array
containers) is far heavier than the paper's 202 ms, which was produced by the
orphaned draft's *32-bit-truncated* `pyroaring.BitMap` (dense containers, fast
SIMD OR — but lossy, ~116 colliding user-pairs at 1M). Exactness costs MAU
latency; see "MATCH/DIFFER" below.

## Roaring backend — scaling (fast binary-log ingest)

| Users | Events | Ingest (s) | Throughput | DAU p50 | DAU p99 | MAU p50 | MAU p99 | Peak RSS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 10,000 | 60,000 | 0.52 | 114,427/s | 0.41 ms | 0.54 ms | 14.7 ms | 17.3 ms | 70.9 MB |
| 100,000 | 600,000 | 5.31 | 113,035/s | 0.70 ms | 0.94 ms | 137.4 ms | 146.0 ms | 286.9 MB |
| **1,000,000** | **6,000,000** | **55.65** | **107,817/s** | **6.64 ms** | **14.66 ms** | **2,821 ms** | **3,423 ms** | **1,636 MB** |

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
| MAU p50 / p99 | 778 / 1,396 ms | 2,821 / 3,423 ms |
| Peak RSS | 2,082 MB | 1,636 MB |

Honest nuance: the Python `set` backend is actually **faster on queries** (its
union is a C-level hash-set union; Roaring's 64-bit sparse-container union is
heavier), but uses **~27% more RAM**. Roaring's advantage is memory, not query
speed, at this exact-backend/64-bit configuration.

## MATCH / DIFFER vs the paper's current claims

Paper currently claims (abstract + Table `tab:performance` + Section Performance):
**115k events/s ingest, 202 ms MAU p99, ~1.15 GB @ 1M, 42× ingest / 223× MAU.**

| # | Paper claim | Measured (this branch) | Verdict |
|---|---|---|---|
| 1 | 115,000 events/s ingest | 107,817/s @ 1M (114,427/s @ 10k) | **≈ MATCH** — reproducible with the binary-log engine; within ~6%. Suggest updating to "≈108k events/s at 1M". |
| 2 | 202 ms MAU query (p99) | **3,423 ms @ 1M** (p99); 2,821 ms p50 | **DIFFER — ~17× slower.** The 202 ms figure is not reproducible with an *exact* backend; it reflects 32-bit truncation. Even the `set` backend is 1,396 ms. Update the claim or re-scope it (e.g. cache the MAU union, or state it for the lossy 32-bit variant explicitly). |
| 3 | ~1.15 GB @ 1M | 1,636 MB (1.6 GB) whole-process incl. event list | **DIFFER — ~1.4× higher.** Note: the *previous SQLite path* measured 1,216 MB (≈1.15 GB), so the paper's figure matches the OLD path, not the fast one. Sketch-only Roaring state for 6M user-days is only 126 MB serialized / 526 MB RSS. |
| 4a | 42× ingest (naive 2,700/s → 115,600/s) | fast 107,817/s ÷ old SQLite 9,176/s = **11.75×**; ÷ a 2,700/s naive baseline would be ~40× | **PARTIAL** — the ~40× vs a 2,700/s "naive Python" holds if that baseline is taken as given, but this branch did not re-measure a 2,700/s naive loop; the measured, in-repo speedup (SQLite→binary-log) is 11.75×. |
| 4b | 223× MAU (naive 45.2 s → 0.202 s) | not reproducible: measured MAU p99 is 3.42 s, not 0.202 s | **DIFFER** — with 3.42 s exact MAU, a 45.2 s naive baseline would be only ~13×, not 223×. The 223× depends on the unreproducible 202 ms. |

### Bottom line for the paper
- **Ingest throughput and the Roaring memory-compression story are real and reproducible** (≈108k events/s; Roaring 22 vs set 35 bytes/user).
- **MAU latency (202 ms) and the 223× MAU speedup are NOT reproducible with an exact 64-bit Roaring backend** — they came from lossy 32-bit truncation. Recommend the paper either (a) report the true exact-backend MAU latency (~3.4 s at 1M, unoptimized), (b) add MAU-union caching and re-measure, or (c) explicitly scope the 202 ms to the approximate 32-bit variant.
- **The 1.15 GB memory figure matches the OLD SQLite path, not the fast one** (which is ~1.6 GB whole-process); the clean per-backend Roaring state is far smaller (126 MB serialized for 6M user-days).
