# Operational Handoff: DP-accurate DAU/MAU Counter

## System Components
- **FastAPI Service (`src/service/app.py`)**: exposes ingestion and query endpoints, thin wrapper over `PipelineManager`.
- **Pipeline Core (`src/dp_core/pipeline.py`)**: orchestrates hashing, sketch updates, erasure replay, DP release, and ledger persistence.
- **Sketch Implementations (`src/dp_core/sketches/`)**: `set_impl` for exact counting; optional `theta_impl`/`hllpp_impl` for approximations – import guarded.
- **Ledger (`src/dp_core/ledger.py`)**: SQLite-backed tables for activity, erasures, and DP budgets located at `{{DATA_DIR}}/ledgers/ledger.sqlite`.
- **Privacy Accountant (`src/dp_core/privacy_accountant.py`)**: tracks ε/δ spend, enforces hard caps {{DAU_BUDGET_TOTAL}}/{{MAU_BUDGET_TOTAL}}.
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
- `LedgerAccountant.can_release(metric, epsilon)` checks both per-metric monthly cap and optional global budget.
- Use `PipelineManager.force_release(..., override=True)` only for backfills; log manual approvals in `ledger.manual_overrides`.
- RDP hook: `privacy_accountant.log_rdp(metric, order, epsilon)` is a stub – extend to integrate with advanced accountants.

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

## Test Dataset Generation
- Baseline synthetic set: `python eval/simulate.py --users 5000 --days 45 --p-active 0.18 --delete-rate 0.02 --seed {{DEFAULT_SEED}} --out {{DATA_DIR}}/streams/smoke.jsonl`.
- Adversarial churn: `python eval/adversarial.py --users 200 --window {{MAU_WINDOW_DAYS}} --flips {{W_BOUND}} --out {{DATA_DIR}}/streams/adversarial.jsonl`.
- Store metadata in `{{DATA_DIR}}/streams/README.md` (auto-generated stub).

## Security & Configuration Tips
- API key authentication optional; enable by setting `SERVICE_API_KEY={{API_KEY}}`.
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
- [ ] Implement full RDP accountant and advanced composition support.
- [ ] Optimize HLL++ rebuild by caching bucketed per-day hashes.
- [ ] Add streaming ingestion benchmark harness (locust / vegeta).
- [ ] Harden notebook reproducibility with papermill automation.
- [ ] Flesh out alerting integration in `service/auth.py`.
