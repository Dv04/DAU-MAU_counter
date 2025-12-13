# DP-accurate DAU/MAU Counter Under Deletions

A differential-privacy aware turnstile streaming pipeline that reports distinct **Daily Active Users (DAU)** and rolling 30-day **Monthly Active Users (MAU)**, while honoring user deletion requests (GDPR/CCPA compliant).

## Features

- **Differential Privacy**: Laplace noise for DAU (δ=0), Gaussian for MAU (δ>0)
- **Deletion Support**: Turnstile stream with `+`/`-` operations and erasure replay
- **Privacy Accounting**: RDP-based composition with monthly budget caps
- **Sketch Abstraction**: Pluggable backends (KMV, exact set, Theta)
- **Pseudonymization**: HMAC-SHA256 with rotating salts
- **REST API**: FastAPI service with Prometheus metrics

## Quickstart

```bash
# 1. Setup environment
cd dp-dau-mau
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure environment variables
export DATA_DIR="$PWD/data" \
       SERVICE_HOST="http://127.0.0.1:8000" \
       SERVICE_API_KEY="changeme-super-secret" \
       EPSILON_DAU=0.3 EPSILON_MAU=0.5 DELTA=1e-6

# 3. Generate synthetic data
python -m cli.dpdau generate-synthetic --days 14 --users 200

# 4. Start the API
make run

# 5. Query DAU/MAU
python -m cli.dpdau dau --day 2025-10-01
python -m cli.dpdau mau --end 2025-10-31 --window 30
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client Layer                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │  dpdau CLI   │  │  HTTP/curl   │  │  Locust Load Test    │   │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘   │
└─────────│─────────────────│─────────────────────│───────────────┘
          │                 │                     │
          ▼                 ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Service                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │  routes.py   │  │   auth.py    │  │     metrics.py       │   │
│  │  /event      │  │  X-API-Key   │  │  Prometheus export   │   │
│  │  /dau/{day}  │  └──────────────┘  └──────────────────────┘   │
│  │  /mau        │                                                │
│  │  /budget     │                                                │
│  └──────┬───────┘                                                │
└─────────│───────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                        DP Core Engine                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │  pipeline.py │  │dp_mechanisms │  │ privacy_accountant   │   │
│  │  Orchestrator│  │Laplace/Gauss │  │ RDP composition      │   │
│  └──────┬───────┘  └──────────────┘  └──────────────────────┘   │
│         │                                                        │
│  ┌──────▼───────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │  ledger.py   │  │  windows.py  │  │     hashing.py       │   │
│  │  SQLite WAL  │  │ Rolling MAU  │  │ HMAC-SHA256 + salt   │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Sketch Backends                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │  kmv_impl    │  │  set_impl    │  │    theta_impl        │   │
│  │  (default)   │  │  (testing)   │  │ (DataSketches opt.)  │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Repository Layout

```
dp-dau-mau/
├── src/
│   ├── dp_core/           # Core DP logic
│   │   ├── pipeline.py    # Ingestion & release orchestrator
│   │   ├── dp_mechanisms.py   # Laplace/Gaussian noise
│   │   ├── privacy_accountant.py  # Budget tracking
│   │   ├── ledger.py      # SQLite activity/erasure log
│   │   ├── hashing.py     # Pseudonymization
│   │   ├── windows.py     # Rolling window logic
│   │   └── sketches/      # KMV, Set, Theta backends
│   └── service/           # FastAPI REST service
│       ├── app.py         # Application entry
│       ├── routes.py      # API endpoints
│       ├── auth.py        # API key auth
│       └── metrics.py     # Prometheus export
├── cli/
│   └── dpdau.py           # Typer CLI
├── eval/                  # Evaluation & benchmarks
├── tests/                 # Pytest suite
├── docker/                # Containerization
└── docs/                  # Additional documentation
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `dpdau ingest --from <path>` | Ingest events from JSONL/CSV |
| `dpdau dau --day YYYY-MM-DD` | Query daily active users |
| `dpdau mau --end YYYY-MM-DD` | Query monthly active users |
| `dpdau generate-synthetic` | Generate test workloads |
| `dpdau flush-deletes` | Process pending erasures |
| `dpdau reset-budget <metric> <month>` | Reset privacy budget |
| `dpdau rotate-salt --effective YYYY-MM-DD` | Generate new hash salt |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/event` | POST | Ingest batch of events |
| `/dau/{day}` | GET | Get DAU with DP noise |
| `/mau?end=YYYY-MM-DD&window=30` | GET | Get MAU with DP noise |
| `/budget/{metric}?day=YYYY-MM-DD` | GET | Check budget status |
| `/metrics` | GET | Prometheus metrics |
| `/healthz` | GET | Health check |

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `EPSILON_DAU` | 0.3 | Privacy budget per DAU release |
| `EPSILON_MAU` | 0.5 | Privacy budget per MAU release |
| `DELTA` | 1e-6 | Delta parameter for Gaussian |
| `MAU_WINDOW_DAYS` | 30 | Rolling window size |
| `SKETCH_IMPL` | kmv | Sketch backend (kmv/set/theta) |
| `DAU_BUDGET_TOTAL` | 3.0 | Monthly DAU budget cap |
| `MAU_BUDGET_TOTAL` | 3.5 | Monthly MAU budget cap |
| `SERVICE_API_KEY` | - | API authentication key |

## Privacy Model

- **Item-level DP**: Protects each user's entire activity trace
- **Sensitivity**: Bounded by flippancy parameter `W_BOUND`
- **Composition**: RDP (Rényi DP) with fallback to naive summation
- **Budget Exhaustion**: Returns HTTP 429 when monthly cap exceeded

## Development

```bash
make setup    # Install hooks, create directories
make fmt      # Format with black + ruff
make lint     # Run ruff + mypy
make test     # Run pytest with coverage
make run      # Start uvicorn dev server
make eval     # Run evaluation workloads
```

## Testing

```bash
# Run all tests
make test

# Run specific test file
pytest tests/test_pipeline.py -v

# Run with coverage
pytest --cov=dp_core --cov=service
```

## Docker

```bash
cd docker
docker-compose up --build
```

## References

- [Differential Privacy (Dwork et al., 2006)](https://www.microsoft.com/en-us/research/publication/calibrating-noise-to-sensitivity-in-private-data-analysis/)
- [Flippancy in Turnstile Streams (NeurIPS 2023)](https://arxiv.org/abs/2306.06723)
- [Apache DataSketches](https://datasketches.apache.org/)

## License

See [LICENSE](LICENSE) file.
