# Next Steps

## Immediate
- Update CI workflow (GitHub Actions or similar) to archive both `coverage.xml` and `{{DATA_DIR}}/reports/budget-snapshot.json` produced by `make test`.
- Spot-check `/budget/{metric}` responses and the generated snapshot file to confirm Rényi curves match expectations for the current month.
- Capture CLI smoke run: `dpdau generate-synthetic --days 14 ...` followed by `dpdau ingest` to ensure the CSV/JSONL loaders behave in your environment; keep resulting dataset under `{{DATA_DIR}}/streams/`.

## Short Term Enhancements
- Add CI task to fail if `SERVICE_API_KEY` remains unset in integration environments; document secret provisioning in the runbook.
- Publish `/metrics` to your Prometheus stack and pin dashboards for `app_requests_total`/`app_request_latency_seconds` with pager thresholds.
- Extend observability by storing the last N `/budget` responses in `{{DATA_DIR}}/reports/` during smoke tests for historical comparison.

## Longer Term
- Prototype Theta and HLL++ sketches by adding optional extras (`pip install .[theta]`, `[hllpp]`) and gating tests accordingly.
- Extend the ledger to support Postgres by honoring `{{SERVICE_DATABASE_URL}}` and layering SQLAlchemy migrations via Alembic.
- Build a minimal gRPC facade (see HANDOFF.md) to validate transport-agnostic pipeline usage.
- Integrate a tree aggregation mechanism (handout section) for continual release with improved privacy amplification.
- Investigate tighter accountant techniques (e.g., privacy loss distributions) if the advanced composition bounds prove too loose for production SLOs.

## Operational Follow-ups
- Create `docs/runbook.md` capturing salt rotation procedures, DP budget reset process, and failure recovery steps; link from HANDOFF.
- Schedule load tests once the benchmark harness exists; target 10–50k events/sec as specified.
- Establish alerting: populate `service/auth.py` with actual email/SMS hooks using `{{ADMIN_EMAIL}}`.
