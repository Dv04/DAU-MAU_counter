# ruff: noqa: B008
"""Command-line helpers for the DP DAU/MAU pipeline."""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterable
from pathlib import Path

import typer

from dp_core import config as config_module
from dp_core.hashing import generate_random_secret
from dp_core.pipeline import EventRecord, PipelineManager

app = typer.Typer(help="Manage the DP-aware DAU/MAU proof-of-concept.")


def _load_events(path: Path) -> Iterable[EventRecord]:
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            payload = json.loads(line)
            yield EventRecord(
                user_id=payload["user_id"],
                op=payload["op"],
                day=dt.date.fromisoformat(payload["day"]),
                metadata=payload.get("metadata", {}),
            )


def _pipeline() -> PipelineManager:
    return PipelineManager(config=config_module.AppConfig.from_env())


@app.command()
def ingest(
    from_path: Path = typer.Argument(Path("{{EXAMPLE_DATASET_PATH}}"), help="Path to events JSONL"),
) -> None:
    """Ingest a batch of events from disk."""

    pipeline = _pipeline()
    pipeline.ingest_batch(_load_events(from_path))
    typer.echo(f"Ingested events from {from_path}")


@app.command()
def dau(day: dt.date = typer.Argument(..., help="Day to query (YYYY-MM-DD)")) -> None:
    pipeline = _pipeline()
    result = pipeline.get_daily_release(day)
    typer.echo(json.dumps(result, indent=2))


@app.command()
def mau(
    end: dt.date = typer.Argument(..., help="Window end day (YYYY-MM-DD)"),
    window: int = typer.Option(None, help="Window size in days"),
) -> None:
    pipeline = _pipeline()
    result = pipeline.get_mau_release(end, window)
    typer.echo(json.dumps(result, indent=2))


@app.command(name="flush-deletes")
def flush_deletes() -> None:
    pipeline = _pipeline()
    pipeline.replay_deletions()
    typer.echo("Queued deletions marked for rebuild.")


@app.command(name="reset-budget")
def reset_budget(
    metric: str = typer.Argument(..., help="Metric to reset (dau|mau)"),
    month: str = typer.Argument(..., help="Month in YYYY-MM format"),
) -> None:
    pipeline = _pipeline()
    if metric not in {"dau", "mau"}:
        raise typer.BadParameter("Metric must be 'dau' or 'mau'.")
    pipeline.reset_budget(metric, month)
    typer.echo(f"Reset budget for {metric} during {month}.")


@app.command(name="rotate-salt")
def rotate_salt(
    effective: dt.date = typer.Argument(..., help="Effective day for new salt"),
    rotation_days: int = typer.Option(
        30, help="Rotation cadence", show_default="{{HASH_SALT_ROTATION_DAYS}}"
    ),
) -> None:
    secret = generate_random_secret()
    typer.echo("Generated new salt secret. Update your secrets manager:")
    typer.echo(f"HASH_SALT_SECRET={secret}")
    typer.echo(f"HASH_SALT_ROTATION_DAYS={rotation_days}")
    typer.echo(f"Effective date: {effective.isoformat()}")


if __name__ == "__main__":
    app()
