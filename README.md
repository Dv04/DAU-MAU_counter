# DP-DAU/MAU Counter

**Differentially Private Daily/Monthly Active User Counter with GDPR Deletion Support**

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Test Coverage](https://img.shields.io/badge/coverage-82%25-brightgreen.svg)](tests/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## Overview

A privacy-preserving analytics system that computes DAU (Daily Active Users) and MAU (Monthly Active Users) while:
- **Differential Privacy**: Formal (ε, δ)-DP guarantees with RDP composition
- **GDPR Compliance**: Tombstone-based deletion that removes users from historical aggregates
- **Streaming Efficiency**: KMV sketches for O(k) memory distinct counting

## Quick Start

```bash
cd dp-dau-mau

# Install dependencies
make install

# Run tests
make test

# Start API server
export SERVICE_API_KEY="your-secret-key"
make run

# Generate synthetic data and evaluate
make eval
```

## Project Structure

```
dp-dau-mau/
├── src/
│   ├── dp_core/          # Core DP logic
│   │   ├── pipeline.py   # Main DAU/MAU pipeline
│   │   ├── privacy_accountant.py  # RDP budget tracking
│   │   └── sketches/     # KMV, Set implementations
│   ├── service/          # FastAPI REST service
│   └── cli/              # Command-line tools
├── eval/                 # Evaluation scripts
├── tests/                # Test suite (82% coverage)
└── data/                 # Synthetic workloads

paper/                    # Research paper (ACM format)
tex/                      # Course final report
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/event` | POST | Ingest user activity event |
| `/dau/{day}` | GET | Get DP DAU estimate |
| `/mau/{day}` | GET | Get DP MAU estimate |
| `/budget` | GET | Check privacy budget status |
| `/health` | GET | Service health check |

## Key Features

### Privacy
- **User-level DP**: Sensitivity = 1 via daily coalescing
- **RDP Composition**: ~27% tighter bounds than naive composition
- **Configurable budgets**: `EPSILON_DAU=0.3`, `EPSILON_MAU=0.5`

### Deletion Support
- Tombstone-based retroactive deletion
- Dirty flag propagation for lazy rebuild
- Passes all 6 deletion correctness tests

### Performance
- 5,000 events/second ingestion
- <50ms query latency (p99)
- <100MB memory for 30-day window

## Experimental Results

| Users | ε | DAU Error | MAU Error |
|-------|---|-----------|-----------|
| 10,000 | 0.5 | 0.06% | 0.09% |
| 10,000 | 1.0 | 0.03% | 0.04% |

Without deletion support, naive systems show **6.3% error** (overcounting deleted users).

## Documents

| Document | Description |
|----------|-------------|
| [tex/main.pdf](tex/main.pdf) | Final project report (16 pages) |
| [paper/paper.pdf](paper/paper.pdf) | Research paper (5 pages ACM format) |
| [docs/tutorial.md](dp-dau-mau/docs/tutorial.md) | Detailed usage guide |

## Configuration

```bash
export EPSILON_DAU=0.3          # DAU privacy parameter
export EPSILON_MAU=0.5          # MAU privacy parameter
export DELTA=1e-6               # DP delta
export MAU_WINDOW_DAYS=30       # Rolling window size
export HASH_SALT_ROTATION_DAYS=365  # Salt epoch length
export SERVICE_API_KEY=xxx      # API authentication
```

## Authors

- Dev Sanghvi (ds221) - Rice University
- Lazeen Manasia (lm152) - Rice University

## Course

COMP 480: Probabilistic Algorithms and Data Structures  
Rice University, Fall 2025

## License

MIT
