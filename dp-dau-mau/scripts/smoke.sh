#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${DATA_DIR:-$(mktemp -d)}"
export DATA_DIR
export EXPERIMENT_ID="smoke-run"
export SERVICE_API_KEY="smoke-key"
export SKETCH_IMPL="kmv"
export SKETCH_K="256"
export USE_BLOOM_FOR_DIFF="true"
export BLOOM_FP_RATE="0.01"
export EPSILON_DAU="0.5"
export EPSILON_MAU="0.8"
export DELTA="1e-6"
export MAU_WINDOW_DAYS="30"

HOST="http://127.0.0.1:8001"
export SERVICE_HOST="${HOST}"
export SMOKE_HOST="${HOST}"

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

DATASET="${DATA_DIR}/streams/smoke.jsonl"
python -m cli.dpdau generate-synthetic \
  --days 7 \
  --users 32 \
  --p-active 0.4 \
  --delete-rate 0.2 \
  --seed 42 \
  --out "${DATASET}"

python -m cli.dpdau ingest \
  --from "${DATASET}" \
  --format jsonl \
  --host "${HOST}" \
  --api-key "${SERVICE_API_KEY}"

python - <<'PY'
import datetime as dt
import json
import os
import sys

import httpx

host = os.environ["SMOKE_HOST"]
api_key = os.environ["SERVICE_API_KEY"]
headers = {"X-API-Key": api_key}

today = dt.date.today()
yesterday = today - dt.timedelta(days=1)
window_days = int(os.environ.get("MAU_WINDOW_DAYS", "30"))

required_fields = [
    "day",
    "estimate",
    "lower_95",
    "upper_95",
    "epsilon_used",
    "delta",
    "mechanism",
    "sketch_impl",
    "budget_remaining",
    "version",
    "budget",
]

with httpx.Client(base_url=host, headers=headers, timeout=10.0) as client:
    dau_resp = client.get(f"/dau/{yesterday.isoformat()}")
    dau_resp.raise_for_status()
    dau = dau_resp.json()
    if any(key not in dau for key in required_fields):
        print("DAU response missing required keys", file=sys.stderr)
        sys.exit(1)

    mau_resp = client.get(
        "/mau", params={"end": today.isoformat(), "window": window_days}
    )
    mau_resp.raise_for_status()
    mau = mau_resp.json()
    if any(key not in mau for key in required_fields):
        print("MAU response missing required keys", file=sys.stderr)
        sys.exit(1)

    budget_resp = client.get(
        f"/budget/mau", params={"day": today.isoformat()}
    )
    budget_resp.raise_for_status()
    budget = budget_resp.json()
    for key in ("epsilon_spent", "epsilon_remaining", "policy", "rdp_orders", "release_count"):
        if key not in budget:
            print("Budget response missing key", key, file=sys.stderr)
            sys.exit(1)

print(
    "Smoke OK: dau={d:.1f} mau={m:.1f} epsilon_spent={eps:.2f}".format(
        d=dau["estimate"], m=mau["estimate"], eps=budget["epsilon_spent"]
    )
)
PY
