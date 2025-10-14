# DP DAU/MAU Operational Runbook

_Last updated: 2025-10-13_

This runbook captures the minimum steps for triaging incidents, rotating secrets, and validating the DP accountant for the DAU/MAU proof-of-concept.

## Contact & Access
- Primary on-call: `{{ADMIN_EMAIL}}`
- Repository: `dp-dau-mau`
- Service entrypoint: `make run` (wraps `uvicorn --app-dir src service.app:app`)
- Credentials: export `SERVICE_API_KEY={{SERVICE_API_KEY}}` before starting the service; store the real key in the secrets manager.

## 1. Alert Intake
| Alert | Trigger | First Response |
| --- | --- | --- |
| High 5xx rate | ≥10 increments of `app_requests_5xx_total` within 5 minutes | Check `/metrics` and application logs for stack traces; verify DB health. |
| Latency regression | `/metrics` histogram shows `/event` bucket `le="1"` saturation or `/mau` p99 drift >1s | Inspect `/metrics`, confirm worker CPU usage, consider throttling ingestion. |
| Privacy budget exhaustion | `/dau`/`/mau` returns HTTP 429 or `budget_remaining == 0` | Review monthly spend via `/budget/{metric}?day=YYYY-MM-DD`; notify stakeholders before resetting. |

All alerts must be acknowledged in the incident channel within 15 minutes.

## 2. Quick Triage Checklist
1. Confirm the service is reachable:
   ```bash
   curl http://127.0.0.1:8000/healthz -H "X-API-Key: $SERVICE_API_KEY"
   ```
2. Inspect recent metrics (focus on `app_requests_total`, `app_requests_5xx_total`, latency buckets):
   ```bash
   curl http://127.0.0.1:8000/metrics
   ```
3. Capture a privacy snapshot (for incident timeline):
   ```bash
   curl "http://127.0.0.1:8000/budget/mau?day=$(date +%Y-%m-%d)" \
        -H "X-API-Key: $SERVICE_API_KEY" \
        | jq '.' > /tmp/budget-$(date +%s).json
   ```
4. If deletes are backlogged, run:
   ```bash
   dpdau flush-deletes
   ```

## 3. Handling Common Issues
### 3.1 Elevated 5xx Responses
- Review Uvicorn logs for stack traces.
- Restart the service after investigating if it is wedged:
  ```bash
  pkill -f "uvicorn.*service.app" || true
  SERVICE_API_KEY={{SERVICE_API_KEY}} make run
  ```
- If SQLite is corrupted, restore from the most recent backup:
  ```bash
  latest=$(ls {{DATA_DIR}}/backups/ledger-*.sqlite | tail -n1)
  cp "$latest" {{DATA_DIR}}/ledgers/ledger.sqlite
  ```
- Document root cause and mitigation in the incident report.

### 3.2 Privacy Budget Exhaustion
- Confirm budget:
  ```bash
  curl "http://127.0.0.1:8000/budget/dau?day=YYYY-MM-DD" -H "X-API-Key: $SERVICE_API_KEY" | jq .
  ```
- If the month legitimately ended, record approval and reset:
  ```bash
  dpdau reset-budget dau YYYY-MM
  dpdau reset-budget mau YYYY-MM
  ```
- Avoid resetting twice without product sign-off; log the decision in the incident doc.

### 3.3 Stale Deletes / MAU Drift
- Run the synthetic smoke test to ensure the rebuild path is healthy:
  ```bash
  dpdau generate-synthetic --days 14 --daily-users 200 --delete-rate 0.1 \
      --out {{DATA_DIR}}/streams/smoke.jsonl
  dpdau ingest --from {{DATA_DIR}}/streams/smoke.jsonl
  curl "http://127.0.0.1:8000/mau?end=$(date +%Y-%m-%d)" -H "X-API-Key: $SERVICE_API_KEY"
  ```
- If MAU does not drop after deletes, inspect `{{DATA_DIR}}/ledgers/ledger.sqlite` and reopen the incident as Sev-1.

## 4. Maintenance Procedures
### 4.1 Salt Rotation
1. Run the helper to generate a new secret:
   ```bash
   dpdau rotate-salt 2025-11-01 --rotation-days {{HASH_SALT_ROTATION_DAYS}}
   ```
2. Store the printed `HASH_SALT_SECRET` in secrets manager, update `.env` (never commit).
3. Schedule rollout in the incident log; coordinate with downstream consumers.

### 4.2 Scheduled Backups
- Nightly cron should execute `make backup-ledger`. Verify the latest copy:
  ```bash
  ls -l {{DATA_DIR}}/backups/ledger-*.sqlite
  ```
- Check backup integrity monthly by opening the file with `sqlite3`.

### 4.3 Budget Snapshot Archiving
- `make test` writes `{{DATA_DIR}}/reports/budget-snapshot.json`. Ensure CI uploads it with `coverage.xml`.
- For manual exports:
  ```bash
  python tools/export_budget_report.py --sample-days 3 --daily-users 100
  ```

## 5. Change Management
- Before deploying major changes, run:
  ```bash
  pip install -r requirements.txt
  python -m pytest
  make fmt lint
  ```
- Attach `budget-snapshot.json`, pytest output, and curl examples to the change ticket.

## 6. Escalation
- If privacy guarantees are compromised (e.g., ledger tampering), immediately notify legal and security leads.
- For extended outages (>30 min), escalate to Eng Lead and record updates every 15 min until resolved.

## 7. Post-Incident Checklist
- Root cause documented and reviewed.
- Runbook updated with any new remediation steps.
- Budget snapshot and metrics archived with the incident timeline.
- Regression tests added if a bug contributed to the outage.
