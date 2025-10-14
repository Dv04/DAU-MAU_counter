# Operational Handoff: DP-accurate DAU/MAU Counter

## System Components
- **FastAPI Service (`src/service/app.py`)**: exposes ingestion and query endpoints, thin wrapper over `PipelineManager`.
- **Pipeline Core (`src/dp_core/pipeline.py`)**: orchestrates hashing, sketch updates, erasure replay, DP release, and ledger persistence.
- **Sketch Implementations (`src/dp_core/sketches/`)**: `kmv_impl` for bottom-k distinct counting (default), `set_impl` for exact counting, and `theta_impl` gated on Apache DataSketches – all import guarded.
- **Ledger (`src/dp_core/ledger.py`)**: SQLite-backed tables for activity, erasures, and DP budgets located at `{{DATA_DIR}}/ledgers/ledger.sqlite`.
- **Privacy Accountant (`src/dp_core/privacy_accountant.py`)**: tracks ε/δ spend, aggregates Rényi orders {{RDP_ORDERS}}, and enforces hard caps {{DAU_BUDGET_TOTAL}}/{{MAU_BUDGET_TOTAL}}.
- **Evaluation Suite (`eval/`)**: synthetic generators, adversarial workloads, benchmarking utilities, plots, and notebook.
- **CLI (`cli/dpdau.py`)**: direct ingest/query interface for batch experimentation.

## Code Map
| Path | Purpose |
| --- | --- |
| `src/dp_core/hashing.py` | HMAC-SHA256 salting & rotation helpers referencing `{{HASH_SALT_SECRET}}` and `{{HASH_SALT_ROTATION_DAYS}}`. |
| `src/dp_core/windows.py` | Rolling DAU/MAU union logic, rebuild scheduling, difference helpers. |
| `src/dp_core/dp_mechanisms.py` | Laplace/Gaussian noise, CI calculations, seeded RNG via `{{DEFAULT_SEED}}`. |
| `src/service/routes.py` | REST handlers, request validation, CI + budget metadata in responses. |
| `eval/evaluate.py` | Accuracy/latency harness; stores results under `{{DATA_DIR}}/experiments/{{EXPERIMENT_ID}}/`. |
| `docker/` | Local containerization; mount `{{DATA_DIR}}` volume. |

## Data Flow & Erasure Replay
1. `/event` receives JSON (single or batch). Each record normalized to `EventRecord`.
2. `PipelineManager.ingest_event` hashes `user_id` using the day-specific salt bucket.
3. Activity table stores `(user_key, day, op)` for auditing; erasure requests (`op == "-"`) populate erasure ledger.
4. On release, `WindowManager` materializes day sketches; dirty days (due to deletes) trigger rebuild from persisted events.
5. DP release noise drawn with seeded RNG; results persisted to release history.

**Replay deletes**: `PipelineManager.replay_deletions()` iterates erasure ledger rows flagged `pending=1`, removes user keys from affected sketches, recomputes unions, and marks rows complete. Schedule this before each release cycle or on-demand via CLI `dpdau flush-deletes`.

## Privacy Budgeting Rules
- Daily releases per metric cost `epsilon_metric` ({{EPSILON_DAU}}, {{EPSILON_MAU}}).
- `PrivacyAccountant.budget_snapshot(metric, day, cap, delta, {{RDP_ORDERS}}, {{ADVANCED_DELTA}})` returns naive spend, remaining headroom, best Rényi-derived `(ε,δ)`, and an advanced-composition bound `(ε_adv, δ_total)`.
- `/budget/{metric}?day=YYYY-MM-DD` surfaces the same snapshot for operators; CLI commands `dpdau dau` / `dpdau mau` embed the budget block for quick checks.
- Use `PipelineManager.reset_budget` (exposed via `dpdau reset-budget`) to wipe a monthly ledger after approvals; log manual overrides in your ops runbook.

## Sketch Tuning
- Default deployment uses KMV (`{{SKETCH_IMPL}}=kmv`). Increase `{{SKETCH_K}}` to reduce variance at the cost of memory (~8 bytes per retained hash). Values ≥2048 are recommended for production traffic.
- `{{USE_BLOOM_FOR_DIFF}}` controls whether A\B uses a Bloom filter; adjust `{{BLOOM_FP_RATE}}` if deletions exhibit bias. Disable Bloom (`false`) for deterministic debugging.
- Switch to `{{SKETCH_IMPL}}=set` for exact replay tests or tightly regulated workloads; Theta remains available when Apache DataSketches is installed.

## Salt Rotation
- Secrets stored in `.env` as `HASH_SALT_SECRET={{HASH_SALT_SECRET}}`.
- `SaltManager` derives per-day salts via HKDF on `(day || rotation_epoch)`.
- Rotate by running `python cli/dpdau.py rotate-salt --effective 2025-11-01 --secret {{HASH_SALT_SECRET}} --rotation-days {{HASH_SALT_ROTATION_DAYS}}`.
- Document rotation event in `docs/runbook.md` (create if missing) including hash of new salt store; never commit secrets.

## Recovery & Incident Response
- All ingested events recorded in `activity_log` table; rebuild entire state via `dpdau rebuild --start 2025-09-01 --end 2025-10-31`.
- If ledger corrupted, restore from snapshot `{{DATA_DIR}}/backups/ledger-YYYYMMDD.sqlite` (see Makefile `make backup-ledger`).
- Budget overspend triggers HTTP 429 with `budget_remaining=0`; resume after monthly reset via `dpdau reset-budget --month 2025-11`.
- Ensure deletes are re-applied after restore by replaying `erasure_log` with `pending=1`.

- `make test` automatically drops `{{DATA_DIR}}/reports/budget-snapshot.json` (via `tools/export_budget_report.py`) for CI uploads; attach alongside `coverage.xml` so reviewers can inspect ε spend per build.
- Monitor `/metrics` (`app_requests_total`, `app_requests_5xx_total`, `app_request_latency_seconds_*`) plus FastAPI status codes. Fire a Sev-2 alert when there are ≥10 `app_requests_5xx_total` increments in 5 minutes or when the `/event` P99 bucket exceeds 1 s for 15 minutes.
- During incidents, capture both the Prometheus scrape and `curl /budget/{metric}?day=YYYY-MM-DD` outputs to validate budget headroom before re-running backfills.

## Test Dataset Generation
- Baseline synthetic set: `python eval/simulate.py --users 5000 --days 45 --p-active 0.18 --delete-rate 0.02 --seed {{DEFAULT_SEED}} --out {{DATA_DIR}}/streams/smoke.jsonl`.
- Adversarial churn: `python eval/adversarial.py --users 200 --window {{MAU_WINDOW_DAYS}} --flips {{W_BOUND}} --out {{DATA_DIR}}/streams/adversarial.jsonl`.
- Quick smoke dataset: `dpdau generate-synthetic --days 14 --daily-users 200 --delete-rate 0.15 --out {{DATA_DIR}}/streams/smoke.jsonl`.
- Store metadata in `{{DATA_DIR}}/streams/README.md` (auto-generated stub).

## Load Testing
- Locust harness lives in `load/locustfile.py`; install extras via `pip install .[load]`.
- Run `SERVICE_API_KEY={{SERVICE_API_KEY}} make load-test LOAD_USERS=2000 LOAD_SPAWN=500 LOAD_RUNTIME=5m` to simulate 10–50k events/sec.
- Collect Locust CSV/HTML artifacts (pass `--csv`/`--html` flags via `LOCUST_OPTS`) and correlate with `/metrics` for latency regression analysis.
- For quick confidence checks, execute `make smoke` which spins up a temporary Uvicorn instance, generates a 7-day synthetic workload, ingests it via the CLI, and validates DAU/MAU/BUDGET responses.

## Security & Configuration Tips
- API key authentication optional; enable by setting `SERVICE_API_KEY={{SERVICE_API_KEY}}`.
- Admin alerts routed via `{{ADMIN_EMAIL}}` (use SMTP integration stub `service/auth.py`).
- SQLite connections operate with WAL mode; ensure `{{DATA_DIR}}` disk encrypted.
- Disable approximate sketches in regulated contexts by setting `{{SKETCH_IMPL}}=set`.

## Extending to gRPC / Theta Sketches
- Swap FastAPI with gRPC by generating protobuf in `proto/` (stub path). Reuse pipeline service layer; only transport changes.
- Theta sketch: install `datasketches` and set `{{SKETCH_IMPL}}=theta`. Ensure CI marks tests with `@pytest.mark.requires_theta`. `theta_impl.py` already handles module detection; update README instructions.

## Postgres & Kafka Migration Path
- Replace SQLite ledger with Postgres by parameterizing DSN via `DATABASE_URL={{SERVICE_DATABASE_URL}}`.
- Ingestion pipeline can subscribe to Kafka topic `{{KAFKA_TOPIC}}`; adapt `cli/dpdau.py ingest-stream`.
- Ensure schema migrations managed via Alembic (scaffold under `db/`).

## Tree Aggregation Roadmap
- Implement binary tree aggregator in `dp_mechanisms.py` using buffered releases, maintaining node sums per day.
- Update accountant to split budget across nodes; note manual tuning required.
- Document state snapshot strategy in `docs/tree-aggregation.md`.

## Known Gaps & TODOs
- [ ] Introduce advanced composition or moments accountant to complement the fixed {{RDP_ORDERS}} set.
- [ ] Optimize HLL++ rebuild by caching bucketed per-day hashes.
- [ ] Add streaming ingestion benchmark harness (locust / vegeta).
- [ ] Harden notebook reproducibility with papermill automation.
- [ ] Flesh out alerting integration in `service/auth.py`.

## Changelog
- **Phase 2 (October 2025)**
  - Default sketch switched to KMV with configurable `{{SKETCH_K}}`, `{{USE_BLOOM_FOR_DIFF}}`, and `{{BLOOM_FP_RATE}}`; exact set remains for deterministic ops.
  - Budget snapshot now returns advanced composition bounds and 429 responses expose machine-readable exhaustion payloads.
  - `/metrics` exports `app_requests_total`, `app_requests_5xx_total`, and latency histograms for Prometheus; smoke and load-test automation added.
  - CLI supports `--host`/`--api-key` for exercising the running API; CI enforces coverage via {{COVERAGE_THRESHOLD}} and uploads budget artefacts.

## Recent Changes & Operational Notes
- `make run` now invokes `uvicorn --app-dir src` so that `service.app` imports cleanly under the reloader. Always launch from the repository root and keep the process running in its own terminal tab.
- All configuration values (privacy budgets, sketch choice, data paths) have defaults. Only export overrides when needed; README includes a single copy-and-paste command for convenience.
- The placeholder auditor ignores `.env/` virtualenv contents to prevent third-party packages from polluting the ledger.
- Differential privacy release seeds are masked to 63 bits before persisting to SQLite to avoid integer overflow errors.
