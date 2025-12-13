# Operational Handoff: DP-accurate DAU/MAU Counter

**Authors:** Dev Sanghvi, Lazeen Manasia  
**Last Updated:** December 2025

---

## System Overview

A differential-privacy aware turnstile streaming pipeline that reports distinct Daily Active Users (DAU) and rolling 30-day Monthly Active Users (MAU), while honoring user deletion requests (GDPR/CCPA compliant).

## System Components

| Component | Path | Purpose |
|-----------|------|---------|
| **FastAPI Service** | `src/service/app.py` | REST API exposing ingestion/query endpoints |
| **Pipeline Core** | `src/dp_core/pipeline.py` | Orchestrates hashing, sketches, erasure replay, DP release |
| **Sketch Implementations** | `src/dp_core/sketches/` | KMV (default), set (exact), theta (optional) |
| **Ledger** | `src/dp_core/ledger.py` | SQLite-backed activity/erasure tracking |
| **Privacy Accountant** | `src/dp_core/privacy_accountant.py` | ε/δ budget tracking with RDP composition |
| **CLI** | `cli/dpdau.py` | Command-line interface for all operations |

## Quick Reference

```bash
# Start server (set API key BEFORE starting!)
export SERVICE_API_KEY="your-secret-key"
make run

# Run tests
make test

# Show all commands
make help

# Check CLI version
python -m cli.dpdau --version

# Generate data & query
python -m cli.dpdau generate-synthetic --days 14 --users 200
python -m cli.dpdau dau --day 2025-10-01
```

> **Important**: The server reads `SERVICE_API_KEY` at startup. If you change it, you must restart the server.

## Data Flow

1. `/event` receives JSON events → normalized to `EventRecord`
2. `PipelineManager.ingest_event` hashes `user_id` with day-specific salt
3. Activity logged to SQLite; deletions (`op == "-"`) populate erasure ledger
4. On release: `WindowManager` materializes sketches, rebuilds dirty days
5. DP noise applied with seeded RNG; results persisted to release history

## Privacy Budgeting

| Metric | Mechanism | ε | δ | Sensitivity |
|--------|-----------|---|---|-------------|
| DAU | Laplace | `EPSILON_DAU` (0.3) | 0 | `W_BOUND` |
| MAU | Gaussian | `EPSILON_MAU` (0.5) | `DELTA` (1e-6) | `W_BOUND` |

**Budget exhaustion**: Returns HTTP 429 with structured payload. Reset via:
```bash
python -m cli.dpdau reset-budget dau 2025-10
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_DIR` | `data` | Root directory for artifacts |
| `EPSILON_DAU` | 0.3 | DAU privacy budget |
| `EPSILON_MAU` | 0.5 | MAU privacy budget |
| `DELTA` | 1e-6 | Gaussian δ parameter |
| `SKETCH_IMPL` | kmv | Sketch backend |
| `SERVICE_API_KEY` | - | API authentication |

## Changelog

### December 2025 - Critical Correctness Fixes

**Bug Fixes:**
1. ✅ **MAU Identity** - Fixed hash function to use epoch-stable salts (not per-day). Same user now hashes to same key within rotation epoch → MAU counts unique users correctly.
2. ✅ **Retroactive Deletion** - Deletions now write tombstone events for all affected historical days → DAU/MAU decrease when user is erased.
3. ✅ **HLL++ Backend** - Wired HLL++ as a selectable sketch implementation (`SKETCH_IMPL=hllpp`).

**Modified Files:**
- `src/dp_core/hashing.py` - Removed `day.isoformat()` from salt derivation
- `src/dp_core/pipeline.py` - Added tombstone insertion on deletion, registered HLL++
- `src/dp_core/ledger.py` - Added `record_activity_batch()` for efficient tombstone insertion
- `src/dp_core/config.py` - Added `hllpp` to allowed sketch implementations

**New Tests:**
- `tests/test_correctness_fixes.py` - 6 regression tests for MAU identity, hash stability, and retroactive deletion

> [!IMPORTANT]
> **Breaking Change**: Hash algorithm changed. Clear existing ledger data: `rm -rf data/ledgers/*.sqlite`

> [!IMPORTANT]
> For MAU correctness: `HASH_SALT_ROTATION_DAYS >= MAU_WINDOW_DAYS` is required.

### December 2025 - Quick Wins & Documentation

**Quick Wins Implemented:**
1. ✅ Added `make help` target - displays all Makefile commands with descriptions
2. ✅ Added `--version` / `-V` flag to CLI - prints `dpdau version 0.1.0`
3. ✅ Enhanced pre-commit guard - now blocks unresolved `{{PLACEHOLDER}}` tokens
4. ✅ Fixed `{{PAPER_DATE}}` placeholder in `paper/paper.tex` → "December 2025"
5. ✅ Updated authors in `pyproject.toml` → "Dev Sanghvi, Lazeen Manasia"

**Critical Priority Implemented:**
1. ✅ **Deployment Verification** - Added `make verify-deploy` that runs smoke.sh post-rollout
2. ✅ **CI Configuration Guard** - Created `tools/ci_config_guard.py` to fail CI if SERVICE_API_KEY is unset/placeholder
3. ✅ **Rate Limiting** - Added sliding window rate limiter (600 req/min) for `/event` endpoint
4. ✅ **Alerting Hooks** - Enhanced `auth.py` with security event logging and webhook/email stubs

**New Makefile Targets:**
```bash
make ci-guard      # Run CI configuration checks
make verify-deploy # Run post-deployment smoke test
make help          # Show all available commands
```

**New Files Created:**
- `docs/tutorial.md` - Comprehensive usage guide
- `src/service/rate_limit.py` - Rate limiting middleware
- `tools/ci_config_guard.py` - CI environment validation

**Files Modified:**
- `Makefile` - Added help, ci-guard, verify-deploy targets
- `cli/dpdau.py` - Added version callback
- `tools/precommit_guard.py` - Added placeholder checking
- `src/service/app.py` - Integrated rate limiting middleware
- `src/service/auth.py` - Added alerting hooks
- `paper/paper.tex` - Fixed date placeholder
- `pyproject.toml` - Updated authors

**Documentation Created:**
- `docs/tutorial.md` - Comprehensive usage guide with all commands
- Updated `README.md` - Complete project documentation
- `walkthrough.md` - Project architecture walkthrough

### October 2025 - Phase 2

- Middleware-driven Prometheus metrics (`app_requests_total`, `app_requests_5xx_total`)
- RDP-backed privacy accountant with best ε selection
- API key enforcement with OpenAPI documentation
- E2E FastAPI test suite
- HTTP-based `tools/export_budget_report.py`

## Maintenance Procedures

### Salt Rotation
```bash
python -m cli.dpdau rotate-salt 2025-12-01 --rotation-days 30
# Update HASH_SALT_SECRET in secrets manager
```

### Backup Ledger
```bash
make backup-ledger
# Creates: data/backups/ledger-YYYYMMDD.sqlite
```

### Load Testing
```bash
pip install -e ".[load]"
SERVICE_API_KEY=your-key make load-test LOAD_USERS=2000
```

## Known Gaps & TODOs

See `task.md` artifact for comprehensive improvement list organized by priority.

**Critical:**
- [ ] Integrate smoke.sh into deployment pipeline
- [ ] Add CI guard for unset SERVICE_API_KEY
- [ ] Implement alerting hooks in auth.py

**High Priority:**
- [ ] Streaming ingestion via Kafka
- [ ] Postgres support with Alembic migrations
- [ ] Tree aggregation for privacy amplification
