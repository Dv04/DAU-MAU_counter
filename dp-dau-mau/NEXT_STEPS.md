# Next Steps

## Immediate
- Exercise the MAU endpoint with multiple days of synthetic data (`eval/simulate.py`) to confirm delete handling and rolling windows behave as expected.
- Add end-to-end tests that ingest a small stream via the FastAPI test client and assert DAU/MAU responses include the documented keys.
- Wire `SERVICE_API_KEY` into the curl examples once a real key management scheme is chosen; update README accordingly.

## Short Term Enhancements
- Implement CLI commands for loading CSV/JSONL batches directly from `{{DATA_DIR}}/streams/` and querying MAU windows.
- Flesh out `privacy_accountant.log_rdp` with a basic Rényi accountant and expose remaining budget in the API.
- Add coverage reporting to CI artifacts (currently only generated locally).
- Introduce a Prometheus counter for failed requests and HTTP status breakdown.

## Longer Term
- Prototype Theta and HLL++ sketches by adding optional extras (`pip install .[theta]`, `[hllpp]`) and gating tests accordingly.
- Extend the ledger to support Postgres by honoring `{{SERVICE_DATABASE_URL}}` and layering SQLAlchemy migrations via Alembic.
- Build a minimal gRPC facade (see HANDOFF.md) to validate transport-agnostic pipeline usage.
- Integrate a tree aggregation mechanism (handout section) for continual release with improved privacy amplification.

## Operational Follow-ups
- Create `docs/runbook.md` capturing salt rotation procedures, DP budget reset process, and failure recovery steps; link from HANDOFF.
- Schedule load tests once the benchmark harness exists; target 10–50k events/sec as specified.
- Establish alerting: populate `service/auth.py` with actual email/SMS hooks using `{{ADMIN_EMAIL}}`.
