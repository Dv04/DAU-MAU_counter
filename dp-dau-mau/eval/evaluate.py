# ruff: noqa: B008
"""Evaluation harness for sketch accuracy and DP noise."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import typer

from dp_core import config as config_module
from dp_core.pipeline import EventRecord, PipelineManager

DEFAULT_EVENTS = Path("{{DATA_DIR}}/streams/sim.jsonl")

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


def build_config(sketch_impl: str, epsilon: float) -> config_module.AppConfig:
    cfg = config_module.AppConfig.from_env()
    cfg = cfg.model_copy(deep=True)
    cfg.sketch.impl = sketch_impl
    cfg.dp.epsilon_dau = epsilon
    cfg.dp.epsilon_mau = max(cfg.dp.epsilon_mau, epsilon)
    return cfg


@app.command()
def main(
    events: Path = typer.Option(DEFAULT_EVENTS, help="Input events JSONL"),
    sketches: list[str] = typer.Option(["set"], help="Sketch implementations to evaluate"),
    epsilons: list[float] = typer.Option([0.3, 0.5], help="Epsilon values to sweep"),
    out: Path = typer.Option(
        Path("{{DATA_DIR}}/experiments/{{EXPERIMENT_ID}}/results.json"), help="Output results path"
    ),
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    events_data = load_events(events)
    results: list[dict] = []

    for sketch in sketches:
        for epsilon in epsilons:
            config = build_config(sketch, epsilon)
            pipeline = PipelineManager(config=config)
            pipeline.ingest_batch(events_data)
            last_day = max(record.day for record in events_data)
            dau = pipeline.get_daily_release(last_day)
            mau = pipeline.get_mau_release(last_day)
            results.append(
                {
                    "sketch": sketch,
                    "epsilon": epsilon,
                    "dau": dau,
                    "mau": mau,
                }
            )

    with out.open("w", encoding="utf-8") as fp:
        json.dump(results, fp, indent=2)


if __name__ == "__main__":
    app()
