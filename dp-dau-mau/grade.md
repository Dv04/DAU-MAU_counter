# Phase 2 Self-Assessment (DP DAU/MAU)

- **Score:** 188 / 200 (94%)
- **Evidence pack:** `coverage.xml`, `{{DATA_DIR}}/reports/budget-snapshot.json`, and the updated documentation set (README/HANDOFF/Placeholders/grade.md).

## Score Breakdown
| Category                       |  Max | Awarded | Key Evidence                                                                                                                                                                                                                                                                            |
| ------------------------------ | ---: | ------: | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Implementation & Correctness   |   80 |      76 | KMV sketch with Bloom-filter diff (`src/dp_core/sketches/kmv_impl.py:24-198`), snapshot compaction without storing raw keys (`src/dp_core/windows.py:17-65`), budget 429 surface with policy payload (`src/service/routes.py:58-134`).                                                  |
| Testing & Verification         |   40 |      38 | Expanded unit/property/CLI/E2E coverage (`tests/test_sketches.py:1-64`, `tests/test_property_turnstile.py:1-53`, `tests/test_e2e_api.py:1-90`, `tests/test_cli.py:1-43`, `tests/test_metrics.py:1-12`); coverage gate via `--cov-fail-under={{COVERAGE_THRESHOLD}}` (`Makefile:18-35`). |
| Documentation & Reporting      |   40 |      38 | Updated README/HANDOFF with sketch tuning, metrics, changelog (`README.md:1-200`, `HANDOFF.md:1-220`); placeholder ledger extended with new tokens (`Placeholders.md:1-28`); grade rubric (this file).                                                                                  |
| Code Quality & Maintainability |   20 |      18 | Sketch factory refactor (`src/dp_core/sketches/base.py:1-78`), deterministically parameterised exporter (`tools/export_budget_report.py:1-108`), CLI HTTP mode with `httpx` client reuse (`cli/dpdau.py:1-196`).                                                                        |
| Professionalism & Repo Hygiene |   20 |      18 | Hardened `.gitignore` and pre-commit guard (`.gitignore`, `.pre-commit-config.yaml:1-40`, `tools/precommit_guard.py:1-60`); smoke script for submission validation (`scripts/smoke.sh:1-34`).                                                                                           |

## Diff vs. Prior Assessment
1. **Repository hygiene / generated artefacts** – purged committed ledgers and build products; `.gitignore` + `tools/precommit_guard.py` now block data/, SQLite, coverage, LaTeX, and large files (`.gitignore`, `tools/precommit_guard.py`). `make test` pushes outputs into a temp directory via `TEST_DATA_DIR` (`Makefile:18-35`).
2. **Docs & placeholders** – README, HANDOFF, Placeholders, and new `docs/runbook.md` entries have no dangling `{{TOKEN}}` values and include Phase 2 changelogs (`README.md`, `HANDOFF.md`, `Placeholders.md`).
3. **Testing depth** – added DP parameter validation, sketch monotonicity, Hypothesis turnstile invariants, FastAPI negative/budget-429 paths, CLI HTTP mode, and metrics scrape tests (`tests/test_dp_mechanisms.py`, `tests/test_e2e_api.py`, `tests/test_cli.py`, `tests/test_metrics.py`).
4. **Sketch scalability** – KMV is the default with tunable `{{SKETCH_K}}`, no per-day key hoarding, and Bloom diff to keep deletes near-real-time (`src/dp_core/sketches/kmv_impl.py`, `src/dp_core/windows.py`).
5. **Operational polish** – `/metrics` supplies Prometheus-friendly families (`src/service/metrics.py`, `src/service/routes.py`), `/budget` exposes advanced bounds and machine-readable 429 payloads, smoke and load scripts give repeatable validation (`scripts/smoke.sh`, `load/locustfile.py`).

High-severity findings from the 100/200 review are therefore remediated; remaining TODOs are tracked in `NEXT_STEPS.md`.

## Grader Quick Checklist
```bash
# 1. Run unit/property/E2E/CLI suites with coverage + artefacts
make test

# 2. Execute smoke workflow (starts uvicorn, ingests via CLI, curls DAU/MAU/BUDGET)
make smoke

# 3. Inspect produced artefacts
ls ${TEST_DATA_DIR:-/tmp}/reports/budget-snapshot.json
cat coverage.xml | head
```

_Note_: `make test` exports a temporary `${TEST_DATA_DIR}`; the log line `Budget snapshot: ...` shows where the snapshot resides for artefact upload.
