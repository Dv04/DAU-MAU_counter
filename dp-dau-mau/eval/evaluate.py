# ruff: noqa: B008
"""Evaluation harness for sketch accuracy and DP noise."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import sys
sys.path.append("src")
import typer

from dp_core import config as config_module
from dp_core.pipeline import EventRecord, PipelineManager


def _default_events() -> Path:
    cfg = config_module.AppConfig.from_env()
    return cfg.storage.example_dataset_path


DEFAULT_EVENTS = _default_events()

app = typer.Typer(help="Run accuracy and budget evaluations.")


def load_events(path: Path) -> list[EventRecord]:
    records: list[EventRecord] = []
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            payload = json.loads(line)
            records.append(
                EventRecord(
                    user_id=payload["user_id"],
                    op=payload["op"],
                    day=dt.date.fromisoformat(payload["day"]),
                    metadata=payload.get("metadata", {}),
                )
            )
    return records


def build_config(sketch_impl: str, epsilon: float, seed: int) -> config_module.AppConfig:
    cfg = config_module.AppConfig.from_env()
    cfg = cfg.model_copy(deep=True)
    cfg.sketch.impl = sketch_impl
    cfg.dp.epsilon_dau = epsilon
    cfg.dp.epsilon_mau = max(cfg.dp.epsilon_mau, epsilon)
    cfg.dp.default_seed = seed
    return cfg


@app.command()
def main(
    events: Path = typer.Option(DEFAULT_EVENTS, help="Input events JSONL"),
    sketches: list[str] = typer.Option(["set"], help="Sketch implementations to evaluate"),
    epsilons: list[float] = typer.Option([0.3, 0.5], help="Epsilon values to sweep"),
    num_seeds: int = typer.Option(1, help="Number of random seeds to evaluate per config"),
    out: Path = typer.Option(
        Path("{{DATA_DIR}}/experiments/{{EXPERIMENT_ID}}/results.json"), help="Output results path"
    ),
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    events_data = load_events(events)
    results: list[dict] = []

    for sketch in sketches:
        # Optimization: Ingest once per sketch implementation
        # This reduces runtime from Hours to Minutes for large N
        print(f"Ingesting data for sketch={sketch}...")
        base_cfg = build_config(sketch, 1.0, 42)
        pipeline = PipelineManager(config=base_cfg)
        pipeline.ingest_batch(events_data)
        
        last_day = max(record.day for record in events_data)
        print("Ingestion complete. Starting epsilon sweep...")

        for epsilon in epsilons:
            for seed in range(num_seeds):
                current_seed = 20251009 + seed
                
                # Hot-swap config for query
                pipeline.config.dp.epsilon_dau = epsilon
                pipeline.config.dp.epsilon_mau = epsilon
                pipeline.config.dp.default_seed = current_seed
                
                # Reset accountant limits for this query to ensure release is allowed
                # (Since we reuse pipeline, budget might be consumed)
                # Actually, RDP/Budget logic tracks cumulative consumption.
                # For evaluation, we want stateless queries (fresh budget each time).
                # We can reset the accountant or just mock the budget check?
                # PipelineManager has reset_budget method, but it resets month.
                # Or we can just disable budget checking in config?
                # Best way: Reset accountant database or use ephemeral accountant.
                
                # Hack: Reset the underlying accountant's history for the metric/day
                # or just force release independent of budget.
                # The _release method raises BudgetExceededError.
                # Let's bypass checks by increasing budget in config temporarily to infinite?
                pipeline.config.dp.dau_budget_total = 999999.0
                pipeline.config.dp.mau_budget_total = 999999.0
                # And reset the specific day's usage in accountant?
                # Actually, standard usage accumulates.
                # If we query 100 times, we burn 100x budget.
                # The accountant is persistent (sqlite).
                # We should use an in-memory accountant for evaluation!
                # Or delete the file.
                
                # Let's re-initialize accountant with :memory: path if possible.
                # PipelineManager constructor allows injection.
                # But we already constructed it.
                # Let's swap the accountant.
                from dp_core.privacy_accountant import PrivacyAccountant
                pipeline.accountant = PrivacyAccountant(Path(":memory:"))
                pipeline.budgets.dau = 999999.0
                pipeline.budgets.mau = 999999.0

                dau = pipeline.get_daily_release(last_day)
                mau = pipeline.get_mau_release(last_day)
                results.append(
                    {
                        "sketch": sketch,
                        "epsilon": epsilon,
                        "seed": current_seed,
                        "dau": dau,
                        "mau": mau,
                    }
                )

    with out.open("w", encoding="utf-8") as fp:
        json.dump(results, fp, indent=2)


if __name__ == "__main__":
    app()
