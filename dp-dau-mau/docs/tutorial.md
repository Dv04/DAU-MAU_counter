# DP-DAU/MAU Tutorial

Complete guide to using every feature of the DP-accurate DAU/MAU Counter.

---

## Table of Contents
1. [Setup](#1-setup)
2. [Running the Server](#2-running-the-server)
3. [CLI Commands](#3-cli-commands)
4. [API Endpoints](#4-api-endpoints)
5. [Testing](#5-testing)
6. [Evaluation](#6-evaluation)
7. [CI/CD Tools](#7-cicd-tools-new)
8. [Docker](#8-docker)
9. [Maintenance](#9-maintenance)

---

## 1. Setup

### Create Virtual Environment
```bash
cd dp-dau-mau
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# or: .venv\Scripts\activate  # Windows
```

### Install Dependencies
```bash
# Basic installation
pip install -r requirements.txt

# With development tools
pip install -e ".[dev]"

# With optional sketch backends
pip install -e ".[theta]"   # Apache DataSketches Theta
pip install -e ".[hllpp]"   # HyperLogLog++
pip install -e ".[load]"    # Locust load testing
```

### Configure Environment Variables
```bash
# Required
export DATA_DIR="$PWD/data"
export SERVICE_API_KEY="your-secret-key"

# Privacy parameters (with defaults)
export EPSILON_DAU=0.3
export EPSILON_MAU=0.5
export DELTA=1e-6
export ADVANCED_DELTA=1e-7
export MAU_WINDOW_DAYS=30

# Budget caps
export DAU_BUDGET_TOTAL=3.0
export MAU_BUDGET_TOTAL=3.5

# Sketch configuration
export SKETCH_IMPL=kmv  # kmv, set, or theta
export SKETCH_K=4096

# RDP orders for composition
export RDP_ORDERS="2,4,8,16,32"
```

---

## 2. Running the Server

### Development Server (with auto-reload)
```bash
make run
# or manually:
PYTHONPATH=src uvicorn --app-dir src service.app:app --reload --host 0.0.0.0 --port 8000
```

### Production Server
```bash
uvicorn --app-dir src service.app:app --host 0.0.0.0 --port 8000 --workers 4
```

### Access Points
- API: http://127.0.0.1:8000
- Health: http://127.0.0.1:8000/healthz
- OpenAPI Docs: http://127.0.0.1:8000/docs
- Metrics: http://127.0.0.1:8000/metrics

---

## 3. CLI Commands

### Generate Synthetic Data
```bash
# Basic generation (7 days, 100 users)
python -m cli.dpdau generate-synthetic

# Custom parameters
python -m cli.dpdau generate-synthetic \
  --days 14 \
  --users 200 \
  --p-active 0.2 \
  --delete-rate 0.1 \
  --seed 12345 \
  --out data/streams/custom.jsonl

# With specific start date
python -m cli.dpdau generate-synthetic \
  --days 30 \
  --start 2025-01-01 \
  --out data/streams/january.jsonl
```

### Ingest Events
```bash
# Local ingestion (direct to pipeline)
python -m cli.dpdau ingest --from data/streams/synthetic_14d.jsonl

# Remote ingestion (via API)
python -m cli.dpdau ingest \
  --from data/streams/synthetic_14d.jsonl \
  --host http://127.0.0.1:8000 \
  --api-key your-secret-key

# With format hint
python -m cli.dpdau ingest --from data.csv --format csv
```

### Query DAU (Daily Active Users)
```bash
# Local query
python -m cli.dpdau dau --day 2025-10-01

# Remote query
python -m cli.dpdau dau \
  --day 2025-10-01 \
  --host http://127.0.0.1:8000 \
  --api-key your-secret-key
```

### Query MAU (Monthly Active Users)
```bash
# Local query with default 30-day window
python -m cli.dpdau mau --end 2025-10-31

# Custom window
python -m cli.dpdau mau --end 2025-10-31 --window 7

# Remote query
python -m cli.dpdau mau \
  --end 2025-10-31 \
  --window 30 \
  --host http://127.0.0.1:8000 \
  --api-key your-secret-key
```

### Manage Deletions
```bash
# Process pending erasure requests
python -m cli.dpdau flush-deletes
```

### Reset Privacy Budget
```bash
# Reset DAU budget for a month
python -m cli.dpdau reset-budget dau 2025-10

# Reset MAU budget
python -m cli.dpdau reset-budget mau 2025-10
```

### Rotate Hash Salt
```bash
# Generate new salt with effective date
python -m cli.dpdau rotate-salt 2025-11-01 --rotation-days 30
```

---

## 4. API Endpoints

### Health Check
```bash
curl http://127.0.0.1:8000/healthz
```

### Ingest Events
```bash
# Single event
curl -X POST http://127.0.0.1:8000/event \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-key" \
  -d '{
    "events": [
      {"user_id": "user-001", "op": "+", "day": "2025-10-01"}
    ]
  }'

# Batch events
curl -X POST http://127.0.0.1:8000/event \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-key" \
  -d '{
    "events": [
      {"user_id": "user-001", "op": "+", "day": "2025-10-01"},
      {"user_id": "user-002", "op": "+", "day": "2025-10-01"},
      {"user_id": "user-001", "op": "-", "day": "2025-10-02", "metadata": {"reason": "gdpr"}}
    ]
  }'
```

### Query DAU
```bash
curl "http://127.0.0.1:8000/dau/2025-10-01" \
  -H "X-API-Key: your-secret-key"
```

### Query MAU
```bash
# Default 30-day window
curl "http://127.0.0.1:8000/mau?end=2025-10-31" \
  -H "X-API-Key: your-secret-key"

# Custom window
curl "http://127.0.0.1:8000/mau?end=2025-10-31&window=7" \
  -H "X-API-Key: your-secret-key"
```

### Check Privacy Budget
```bash
curl "http://127.0.0.1:8000/budget/dau?day=2025-10-01" \
  -H "X-API-Key: your-secret-key"

curl "http://127.0.0.1:8000/budget/mau?day=2025-10-31" \
  -H "X-API-Key: your-secret-key"
```

### Prometheus Metrics
```bash
curl http://127.0.0.1:8000/metrics
```

---

## 5. Testing

### Run All Tests
```bash
make test
# or:
pytest
```

### Run with Coverage
```bash
pytest --cov=dp_core --cov=service --cov-report=html
open htmlcov/index.html
```

### Run Specific Test Files
```bash
pytest tests/test_pipeline.py -v
pytest tests/test_sketches.py -v
pytest tests/test_dp_mechanisms.py -v
pytest tests/test_e2e_api.py -v
pytest tests/test_e2e_service.py -v
```

### Run Property Tests
```bash
pytest tests/test_property_turnstile.py -v
```

### Smoke Test
```bash
make smoke
# or:
./scripts/smoke.sh
```

---

## 6. Evaluation

> **Note**: Evaluation scripts require PYTHONPATH to be set. Use `make eval` for automatic setup.

### Run Accuracy Evaluation
```bash
# Via Makefile (recommended)
make eval

# Direct invocation (must set PYTHONPATH)
PYTHONPATH=src python eval/evaluate.py

# Custom sweep
PYTHONPATH=src python eval/evaluate.py \
  --events data/streams/synthetic_14d.jsonl \
  --sketches set kmv \
  --epsilons 0.1 0.3 0.5 1.0 \
  --out data/experiments/sweep/results.json
```

### Generate Synthetic Workloads
```bash
# Simulate realistic traffic
python eval/simulate.py \
  --users 5000 \
  --days 45 \
  --p-active 0.18 \
  --delete-rate 0.02 \
  --out data/streams/simulation.jsonl

# Adversarial churn workload
python eval/adversarial.py \
  --users 200 \
  --window 30 \
  --flips 10 \
  --out data/streams/adversarial.jsonl
```

### Generate Plots
```bash
make plots
# or:
PYTHONPATH=src python eval/plots.py
```

### Jupyter Notebook
```bash
jupyter notebook eval/notebooks/evaluation.ipynb
```

---

## 7. CI/CD Tools (NEW)

### Check CLI Version
```bash
python -m cli.dpdau --version
# Output: dpdau version 0.1.0
```

### Show Makefile Help
```bash
make help
# Displays all available targets with descriptions
```

### CI Configuration Guard
```bash
# Check if required environment variables are set
python tools/ci_config_guard.py

# In CI pipeline
make ci-guard
```

### Post-Deployment Verification
```bash
make verify-deploy
# Runs smoke.sh for end-to-end validation
```

---

## 8. Docker

### Build Image
```bash
cd dp-dau-mau
docker build -t dp-dau-mau -f docker/Dockerfile .
```

### Run Container
```bash
docker run -d \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -e SERVICE_API_KEY=your-secret-key \
  dp-dau-mau

# Test it
curl http://localhost:8000/healthz
```

### Docker Compose
```bash
cd docker
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

---

## 9. Maintenance

### Code Formatting
```bash
make fmt
# or:
black src tests cli
ruff check --fix src tests cli
```

### Linting
```bash
make lint
# or:
ruff check src tests cli
mypy src
```

### Backup Ledger
```bash
make backup-ledger
# Creates: data/backups/ledger-YYYYMMDD.sqlite
```

### Export Budget Report
```bash
python tools/export_budget_report.py \
  --sample-days 3 \
  --daily-users 100
# Output: data/reports/budget-snapshot.json
```

### Check Placeholders
```bash
python tools/check_placeholders.py
```

### Load Testing
```bash
# Install locust
pip install -e ".[load]"

# Run load test
SERVICE_API_KEY=your-key make load-test \
  LOAD_USERS=2000 \
  LOAD_SPAWN=500 \
  LOAD_RUNTIME=5m \
  LOAD_HOST=http://127.0.0.1:8000
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Start server | `make run` |
| Run tests | `make test` |
| Format code | `make fmt` |
| Lint code | `make lint` |
| Smoke test | `make smoke` |
| Generate data | `python -m cli.dpdau generate-synthetic --days 14 --users 200` |
| Query DAU | `python -m cli.dpdau dau --day 2025-10-01` |
| Query MAU | `python -m cli.dpdau mau --end 2025-10-31` |
| Check budget | `curl "http://localhost:8000/budget/dau?day=2025-10-01"` |

---

## Troubleshooting

### Import Errors
```bash
# Ensure PYTHONPATH includes src
export PYTHONPATH=$PWD/src:$PYTHONPATH
```

### Budget Exhausted (HTTP 429)
```bash
# Check current budget
curl "http://localhost:8000/budget/dau?day=$(date +%Y-%m-%d)" -H "X-API-Key: $SERVICE_API_KEY"

# Reset if needed (requires approval)
python -m cli.dpdau reset-budget dau $(date +%Y-%m)
```

### Theta Sketch Unavailable
```bash
# Install optional dependency
pip install datasketches
export SKETCH_IMPL=theta
```

### API Authentication Failed (unauthorized)
The server reads `SERVICE_API_KEY` at **startup time**. If you set the key after starting the server, you must restart:
```bash
# 1. Stop the running server (Ctrl+C in the make run terminal)
# 2. Export the key
export SERVICE_API_KEY="your-secret-key"
# 3. Restart
make run
```

Then use the same key in your requests:
```bash
python -m cli.dpdau ingest --from data.jsonl --host http://127.0.0.1:8000 --api-key your-secret-key
```

### Eval/Plots Fail with BudgetExceededError
Previous runs may have exhausted the privacy budget. Solutions:
```bash
# Option 1: Reset budget for the month
python -m cli.dpdau reset-budget dau $(date +%Y-%m)
python -m cli.dpdau reset-budget mau $(date +%Y-%m)

# Option 2: Use make eval (uses fresh temp directory)
make eval

# Option 3: Clear ledger data
rm -rf data/ledgers/*.sqlite
```
