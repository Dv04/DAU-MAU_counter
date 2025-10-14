#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="$(mktemp -d)"
export DATA_DIR
export EXPERIMENT_ID="smoke-run"
export SERVICE_API_KEY="smoke-key"
export SKETCH_IMPL="kmv"
export SKETCH_K="256"
export USE_BLOOM_FOR_DIFF="true"
export BLOOM_FP_RATE="0.01"
export EPSILON_DAU="0.3"
export EPSILON_MAU="0.5"
export DELTA="1e-6"

HOST="http://127.0.0.1:8001"
START_DAY="2025-10-01"
END_DAY="2025-10-07"

python -m uvicorn --app-dir src service.app:app --host 127.0.0.1 --port 8001 --log-level error &
UVICORN_PID=$!
trap 'kill "${UVICORN_PID}" >/dev/null 2>&1 || true; rm -rf "${DATA_DIR}"' EXIT

for _ in {1..30}; do
    if curl -sf "${HOST}/healthz" >/dev/null; then
        break
    fi
    sleep 1
done

if ! curl -sf "${HOST}/healthz" >/dev/null; then
    echo "Failed to start service for smoke test" >&2
    exit 1
fi

DATASET="$(mktemp).jsonl"
python -m cli.dpdau generate-synthetic --out "${DATASET}" --days 7 --daily-users 10 --seed 42 --start "${START_DAY}"
python -m cli.dpdau ingest "${DATASET}" --host "${HOST}" --api-key "${SERVICE_API_KEY}"
python -m cli.dpdau mau "${END_DAY}" --host "${HOST}" --api-key "${SERVICE_API_KEY}" >/dev/null

curl -sf "${HOST}/dau/${END_DAY}" -H "X-API-Key: ${SERVICE_API_KEY}" >/dev/null
curl -sf "${HOST}/budget/dau?day=${END_DAY}" -H "X-API-Key: ${SERVICE_API_KEY}" >/dev/null

echo "Smoke test completed successfully."
