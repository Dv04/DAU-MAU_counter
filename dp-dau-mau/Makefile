SHELL := /bin/bash
PYTHON ?= python
ifdef VIRTUAL_ENV
PYTHON := $(VIRTUAL_ENV)/bin/python
else ifeq ($(wildcard ./.env/bin/python),./.env/bin/python)
PYTHON := ./.env/bin/python
endif
UVICORN ?= uvicorn
SERVICE_APP = service.app:app
DATA_DIR ?= {{DATA_DIR}}
EXPERIMENT_ID ?= {{EXPERIMENT_ID}}
EVAL_DATASET ?= $(DATA_DIR)/streams/eval_synthetic.jsonl
MPLCONFIGDIR ?= $(DATA_DIR)/.mpl
XDG_CACHE_HOME ?= $(DATA_DIR)/.cache
EPSILONS ?= 0.3 0.5
EVAL_SKETCHES ?= set
LOAD_HOST ?= http://127.0.0.1:8000
LOAD_USERS ?= 500
LOAD_SPAWN ?= 100
LOAD_RUNTIME ?= 2m
COVERAGE_THRESHOLD ?= {{COVERAGE_THRESHOLD}}
export PYTHONPATH := src
export DATA_DIR
export EXPERIMENT_ID
export MPLCONFIGDIR
export XDG_CACHE_HOME

ifeq ($(COVERAGE_THRESHOLD),{{COVERAGE_THRESHOLD}})
COVERAGE_THRESHOLD := 70
endif

ifeq ($(DATA_DIR),{{DATA_DIR}})
DATA_DIR := data
endif

ifeq ($(EXPERIMENT_ID),{{EXPERIMENT_ID}})
EXPERIMENT_ID := dev
endif
TEST_DATA_DIR := $(strip $(shell python -c 'import tempfile; print(tempfile.mkdtemp(prefix="dpdau-test-"))'))
BUDGET_SNAPSHOT := $(TEST_DATA_DIR)/reports/budget-snapshot.json
EVAL_EPSILONS := $(foreach eps,$(EPSILONS),--epsilons $(eps))
EVAL_SKETCH_ARGS := $(foreach sk,$(EVAL_SKETCHES),--sketches $(sk))

.PHONY: setup fmt lint test run eval plots backup-ledger placeholder-check precommit install-dev load-test smoke help verify-deploy ci-guard

setup: install-dev precommit placeholder-check
	@mkdir -p $(DATA_DIR)/ledgers $(DATA_DIR)/streams $(DATA_DIR)/plots/$(EXPERIMENT_ID) $(DATA_DIR)/experiments/$(EXPERIMENT_ID)

ci-guard:
	$(PYTHON) tools/ci_config_guard.py

verify-deploy:
	@echo "Running post-deployment verification..."
	bash scripts/smoke.sh
	@echo "✅ Deployment verification passed"

install-dev:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

precommit:
	pre-commit install

fmt:
	black src cli tests eval
	ruff check --select I src cli tests eval --fix

$(EVAL_DATASET):
	$(PYTHON) -m cli.dpdau generate-synthetic --days 30 --users 500 --p-active 0.3 --delete-rate 0.1 --out $(notdir $(EVAL_DATASET))

lint:
	$(PYTHON) -m ruff check src cli tests eval
	$(PYTHON) -m mypy -p dp_core -p service
	$(PYTHON) -m mypy cli tests

test: placeholder-check
	DATA_DIR=$(TEST_DATA_DIR) $(PYTHON) -m pytest --cov=src --cov-report=term --cov-report=xml --cov-fail-under=$(COVERAGE_THRESHOLD) --maxfail=1
	DATA_DIR=$(TEST_DATA_DIR) $(PYTHON) tools/export_budget_report.py --out $(BUDGET_SNAPSHOT) --sample-days 3 --daily-users 64
	@echo "Budget snapshot: $(BUDGET_SNAPSHOT)"

run:
	PYTHONPATH=src $(UVICORN) --app-dir src $(SERVICE_APP) --reload --host 0.0.0.0 --port 8000

eval: $(EVAL_DATASET)
	@echo "Running evaluation with fresh budget in temp directory..."
	DATA_DIR=$(TEST_DATA_DIR) $(PYTHON) eval/evaluate.py --events $(EVAL_DATASET) $(EVAL_SKETCH_ARGS) $(EVAL_EPSILONS) --out $(DATA_DIR)/experiments/$(EXPERIMENT_ID)

plots: eval
	@mkdir -p $(MPLCONFIGDIR)
	@mkdir -p $(XDG_CACHE_HOME)/fontconfig
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

help:
	@echo "DP-DAU/MAU Makefile Commands"
	@echo "============================"
	@echo ""
	@echo "Setup & Installation:"
	@echo "  make setup          - Install dev deps, hooks, create directories"
	@echo "  make install-dev    - Install Python dependencies"
	@echo "  make precommit      - Install pre-commit hooks"
	@echo ""
	@echo "Development:"
	@echo "  make run            - Start FastAPI dev server (port 8000)"
	@echo "  make fmt            - Format code with black + ruff"
	@echo "  make lint           - Run ruff and mypy checks"
	@echo ""
	@echo "Testing:"
	@echo "  make test           - Run pytest with coverage"
	@echo "  make smoke          - Run end-to-end smoke test"
	@echo "  make load-test      - Run Locust load test"
	@echo ""
	@echo "Evaluation:"
	@echo "  make eval           - Run accuracy evaluation"
	@echo "  make plots          - Generate evaluation plots"
	@echo ""
	@echo "Maintenance:"
	@echo "  make backup-ledger  - Backup SQLite ledger"
	@echo "  make placeholder-check - Verify placeholder consistency"
	@echo ""
	@echo "Variables:"
	@echo "  DATA_DIR=$(DATA_DIR)"
	@echo "  EXPERIMENT_ID=$(EXPERIMENT_ID)"
	@echo "  COVERAGE_THRESHOLD=$(COVERAGE_THRESHOLD)"

