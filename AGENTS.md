# Repository Guidelines

## Project Structure & Module Organization
All project assets live under `dp-dau-mau/`. Core pipeline logic resides in `src/dp_core/` (hashing, sketches, DP mechanisms, pipeline). The FastAPI surface is in `src/service/`, while the Typer CLI sits in `cli/dpdau.py`. Synthetic workloads and plots live in `eval/`, and notebooks under `eval/notebooks/`. Tests mirror package layout in `tests/`. Generated artifacts (ledgers, experiment outputs, plots) must land inside `{{DATA_DIR}}` and stay out of Git. Keep this map current whenever new modules or directories appear.

## Build, Test, and Development Commands
Activate a Python 3.13 virtualenv and install dependencies with `pip install -r requirements.txt`. Run `make setup` once to install hooks and create `{{DATA_DIR}}` scaffolding. Format code via `make fmt` (`black` + `ruff`). Use `make lint` for `ruff` and `mypy`, and `make test` for pytest, coverage, and placeholder checks. Launch the API locally with `make run` (uvicorn reload) and generate evaluation sweeps through `make eval` / `make plots`. Document new commands in the README and this guide as they are added.

## Coding Style & Naming Conventions
Write typed Python 3.13 with a 100-char soft wrap. Modules and functions use `snake_case`; classes follow CapWords. Public FastAPI handlers stay in `routes.py` and return Pydantic response models. Keep placeholder tokens explicit (e.g., `{{DATA_DIR}}`) in config, docs, and sample commands, and register each in `Placeholders.md`. Run `black`, `ruff`, and `mypy` before opening any PR to ensure consistent style.

## Testing Guidelines
Unit tests belong in `tests/`, mirroring their target modules (`tests/test_pipeline.py` exercises `src/dp_core/pipeline.py`, etc.). Prefer pytest fixtures in `tests/conftest.py` for shared environment setup (temp `{{DATA_DIR}}`, seeded secrets). Aim for ≥90% line coverage on DP mechanisms, ledger/accountant code, and windowing logic; track via `pytest --cov=dp_core --cov=service`. Add property tests with Hypothesis for churn/deletion scenarios as they emerge. Every bug fix needs a regression case capturing the failing stream.

## Commit & Pull Request Guidelines
Use imperative present-tense subjects (`Add HLL rebuild cache`). Group unrelated work across separate commits. Reference issues with `(#id)` where relevant. PR descriptions must outline intent, link to documentation updates (README/HANDOFF/Placeholders), and list validation commands (lint, tests, placeholder check). Include JSON or curl snippets when API behaviour changes, and point reviewers to updated plots if evaluation outputs shift.

## Environment & Configuration Tips
Never check secrets into Git. Store runtime values (e.g., `HASH_SALT_SECRET`, `{{API_KEY}}`) in your shell or `.env`. Whenever you introduce a new placeholder, update `Placeholders.md` and run `make placeholder-check`. Keep sample configs (`docker/docker-compose.yml`, README Quickstart) aligned with the latest defaults. For SQLite artefacts, mount `{{DATA_DIR}}` when running inside containers so ledgers persist between restarts.
