PYTHON ?= python
UVICORN ?= uvicorn
SERVICE_APP = service.app:app
DATA_DIR ?= {{DATA_DIR}}
EXPERIMENT_ID ?= {{EXPERIMENT_ID}}
LOAD_HOST ?= http://127.0.0.1:8000
LOAD_USERS ?= 500
LOAD_SPAWN ?= 100
LOAD_RUNTIME ?= 2m
COVERAGE_THRESHOLD ?= {{COVERAGE_THRESHOLD}}
TEST_DATA_DIR := $(strip $(shell python - <<'PY'\nimport tempfile\npath = tempfile.mkdtemp(prefix=\"dpdau-test-\")\nprint(path)\nPY\n))
BUDGET_SNAPSHOT := $(TEST_DATA_DIR)/reports/budget-snapshot.json

.PHONY: setup fmt lint test run eval plots backup-ledger placeholder-check precommit install-dev load-test smoke

setup: install-dev precommit placeholder-check
	@mkdir -p $(DATA_DIR)/ledgers $(DATA_DIR)/streams $(DATA_DIR)/plots/$(EXPERIMENT_ID) $(DATA_DIR)/experiments/$(EXPERIMENT_ID)

install-dev:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

precommit:
	pre-commit install

fmt:
	black src cli tests eval
	ruff check --select I src cli tests eval --fix

lint:
	ruff check src cli tests eval
	mypy src cli tests

test: placeholder-check
	DATA_DIR=$(TEST_DATA_DIR) pytest --cov=src --cov-report=term --cov-report=xml --cov-fail-under=$(COVERAGE_THRESHOLD) --maxfail=1
	DATA_DIR=$(TEST_DATA_DIR) $(PYTHON) tools/export_budget_report.py --out $(BUDGET_SNAPSHOT) --sample-days 3 --daily-users 64
	@echo "Budget snapshot: $(BUDGET_SNAPSHOT)"

run:
	PYTHONPATH=src $(UVICORN) --app-dir src $(SERVICE_APP) --reload --host 0.0.0.0 --port 8000

eval:
	$(PYTHON) eval/evaluate.py --out $(DATA_DIR)/experiments/$(EXPERIMENT_ID)

plots:
	$(PYTHON) eval/plots.py --input $(DATA_DIR)/experiments/$(EXPERIMENT_ID) --out $(DATA_DIR)/plots/$(EXPERIMENT_ID)

placeholder-check:
	$(PYTHON) tools/check_placeholders.py --root . --manifest Placeholders.md

backup-ledger:
	@mkdir -p $(DATA_DIR)/backups
	@cp $(DATA_DIR)/ledgers/ledger.sqlite $(DATA_DIR)/backups/ledger-$$(date +%Y%m%d).sqlite

load-test:
	LOCUST_LOCUSTFILE=load/locustfile.py locust --headless --host $(LOAD_HOST) --users $(LOAD_USERS) --spawn-rate $(LOAD_SPAWN) --run-time $(LOAD_RUNTIME)

smoke:
	bash scripts/smoke.sh
