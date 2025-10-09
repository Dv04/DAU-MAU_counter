PYTHON ?= python
UVICORN ?= uvicorn
PACKAGE = dp_core
SERVICE_APP = service.app:app
DATA_DIR ?= {{DATA_DIR}}
EXPERIMENT_ID ?= {{EXPERIMENT_ID}}

.PHONY: setup fmt lint test run eval plots backup-ledger placeholder-check precommit install-dev

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
	pytest --cov=$(PACKAGE) --cov=service --maxfail=1

run:
	$(UVICORN) $(SERVICE_APP) --reload --host 0.0.0.0 --port 8000

eval:
	$(PYTHON) eval/evaluate.py --out $(DATA_DIR)/experiments/$(EXPERIMENT_ID)

plots:
	$(PYTHON) eval/plots.py --input $(DATA_DIR)/experiments/$(EXPERIMENT_ID) --out $(DATA_DIR)/plots/$(EXPERIMENT_ID)

placeholder-check:
	$(PYTHON) tools/check_placeholders.py --root . --manifest Placeholders.md

backup-ledger:
	@mkdir -p $(DATA_DIR)/backups
	@cp $(DATA_DIR)/ledgers/ledger.sqlite $(DATA_DIR)/backups/ledger-$$(date +%Y%m%d).sqlite
