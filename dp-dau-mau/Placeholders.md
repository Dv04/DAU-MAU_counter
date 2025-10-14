# Placeholder Ledger

Every placeholder token of the form `{{DATA_DIR}}`, `{{EPSILON_DAU}}`, etc. must be registered in this table. Update this file whenever you introduce, move, or remove a placeholder. The `Location` column references representative files/sections; keep it up to date when refactoring.

| Placeholder | Location | Description | Type | Constraints / Example | Default |
| --- | --- | --- | --- | --- | --- |
| {{DATA_DIR}} | README.md (Quickstart, Makefile), docker/, src/dp_core/config.py | Root directory for writable artifacts (ledgers, streams, plots). | path | Absolute or relative path. Example: `/tmp/dp-dau` | REQUIRED |
| {{EXPERIMENT_ID}} | README.md (plots), Makefile, eval/evaluate.py, docker/ | Label for experiment outputs and evaluation artifacts. | string | Alphanumeric with dashes. Example: `baseline-oct2025` | REQUIRED |
| {{EPSILON_DAU}} | README.md (Quickstart), src/dp_core/config.py | Privacy budget ε used for DAU releases. | float | Positive, ≤1 recommended. Example: `0.3` | 0.3 |
| {{EPSILON_MAU}} | README.md (Quickstart), src/dp_core/config.py | Privacy budget ε used for MAU releases. | float | Positive, ≤1 recommended. Example: `0.5` | 0.5 |
| {{DELTA}} | README.md (Quickstart), src/dp_core/config.py | δ parameter for Gaussian mechanism / advanced accounting. | float | 0 < δ < 1. Example: `1e-6` | 1e-6 |
| {{ADVANCED_DELTA}} | README.md (Quickstart), src/dp_core/config.py | Slack δ' used for advanced composition bounds. | float | 0 < δ' < 1. Example: `1e-7` | 1e-7 |
| {{W_BOUND}} | README.md (Core Concepts), src/dp_core/windows.py | Flippancy bound: max toggles per user per window. | int | ≥1. Example: `2` | 2 |
| {{HASH_SALT_ROTATION_DAYS}} | HANDOFF.md (Salt Rotation), src/dp_core/hashing.py | Duration between hash salt rotations. | int | ≥1. Example: `30` | 30 |
| {{HASH_SALT_SECRET}} | HANDOFF.md (Salt Rotation), src/dp_core/hashing.py | Root secret for HMAC-based hashing. | secret | 32+ byte base64 string. Example: `b64:...` | REQUIRED |
| {{MAU_WINDOW_DAYS}} | README.md (API), src/dp_core/config.py | Window size (days) used for MAU computation. | int | ≥1. Example: `30` | 30 |
| {{SERVICE_API_KEY}} | README.md (Quickstart/API), src/dp_core/config.py, src/service/auth.py | API key required in `X-API-Key` header when enabled. | secret | Non-empty string. Example: `changeme-super-secret` | REQUIRED |
| {{ADMIN_EMAIL}} | HANDOFF.md (Security), src/service/auth.py, src/service/openapi_overrides.py | Contact for alerting and admin notifications. | string | Valid email. Example: `dp-admin@example.com` | REQUIRED |
| {{DEFAULT_SEED}} | HANDOFF.md (Test Dataset), src/dp_core/config.py | Default RNG seed for reproducibility. | int | 0 ≤ seed < 2^32. Example: `20251009` | 20251009 |
| {{EXAMPLE_DATASET_PATH}} | README.md (CLI), cli/dpdau.py | Example dataset path for CLI ingest. | path | JSONL/CSV path. Example: `data/example.jsonl` | REQUIRED |
| {{HLL_REBUILD_DAYS_BUFFER}} | HANDOFF.md (Known Gaps), src/dp_core/sketches/hllpp_impl.py | Extra days to cache during HLL++ rebuilds. | int | ≥0. Example: `7` | 3 |
| {{SKETCH_IMPL}} | README.md, src/dp_core/config.py | Active sketch backend selection (`kmv`, `set`, `theta`). | string | Must be one of allowed values. | kmv |
| {{SKETCH_K}} | README.md (Sketch Tuning), src/dp_core/config.py | Bottom-k parameter for KMV sketch. | int | ≥64 recommended. Example: `4096` | 4096 |
| {{USE_BLOOM_FOR_DIFF}} | README.md (Sketch Tuning), src/dp_core/config.py | Whether KMV diff uses Bloom filter to filter B before A	extbackslash B. | bool | `true` / `false`. | true |
| {{BLOOM_FP_RATE}} | README.md (Sketch Tuning), src/dp_core/config.py | Target false-positive rate for the Bloom filter when diffing. | float | 0 < p < 1. Example: `0.01` | 0.01 |
| {{DAU_BUDGET_TOTAL}} | HANDOFF.md (Budgeting), src/dp_core/privacy_accountant.py | Monthly ε budget cap for DAU. | float | >0. Example: `3.0` | 3.0 |
| {{MAU_BUDGET_TOTAL}} | HANDOFF.md (Budgeting), src/dp_core/privacy_accountant.py | Monthly ε budget cap for MAU. | float | >0. Example: `3.5` | 3.5 |
| {{RDP_ORDERS}} | README.md (Privacy Accounting), src/dp_core/config.py | Comma-separated Rényi orders tracked by the accountant. | list | Orders > 1. Example: `2,4,8,16` | 2,4,8,16,32 |
| {{N_USERS}} | README.md (Evaluation), eval/simulate.py | Synthetic workload total users. | int | ≥1. Example: `10000` | 10000 |
| {{P_ACTIVE}} | README.md (Evaluation), eval/simulate.py | Daily activity probability. | float | 0 ≤ p ≤ 1. Example: `0.2` | 0.2 |
| {{DELETE_RATE}} | README.md (Evaluation), eval/simulate.py | Per-event delete probability. | float | 0 ≤ p ≤ 1. Example: `0.05` | 0.05 |
| {{TIMEZONE}} | README.md (Event JSON), src/dp_core/config.py | Canonical timezone for day boundaries. | string | IANA TZ name. Example: `UTC` | UTC |
| {{SERVICE_DATABASE_URL}} | HANDOFF.md (Postgres Migration), src/dp_core/config.py | Database connection string when migrating off SQLite. | string | DSN format. Example: `postgresql://user:pass@host/db` | REQUIRED |
| {{KAFKA_TOPIC}} | HANDOFF.md (Postgres & Kafka), src/dp_core/config.py | Upstream Kafka topic for streaming ingest. | string | Kafka topic name. Example: `dp-dau-events` | REQUIRED |
| {{COVERAGE_THRESHOLD}} | README.md (Testing), Makefile | Minimum coverage percentage enforced in CI. | float | 0 < threshold ≤ 100. Example: `70` | 70 |
