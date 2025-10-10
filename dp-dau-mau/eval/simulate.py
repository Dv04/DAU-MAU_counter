# ruff: noqa: B008
"""Synthetic workload generator for DAU/MAU evaluation."""

from __future__ import annotations

import datetime as dt
import json
import random
from pathlib import Path

import typer

app = typer.Typer(help="Generate synthetic event streams for the DP DAU/MAU pipeline.")


@app.command()
def main(
    users: int = typer.Option(10000, help="Number of unique users", show_default="{{N_USERS}}"),
    days: int = typer.Option(60, help="Number of days to simulate"),
    p_active: float = typer.Option(
        0.2, help="Daily active probability", show_default="{{P_ACTIVE}}"
    ),
    delete_rate: float = typer.Option(
        0.05, help="Probability of delete events", show_default="{{DELETE_RATE}}"
    ),
    seed: int = typer.Option(20251009, help="Random seed", show_default="{{DEFAULT_SEED}}"),
    out: Path = typer.Option(Path("{{DATA_DIR}}/streams/sim.jsonl"), help="Output JSONL path"),
) -> None:
    """Emit a JSONL file containing turnstile events."""

    rng = random.Random(seed)
    out.parent.mkdir(parents=True, exist_ok=True)
    start_day = dt.datetime.now(tz=dt.UTC).date() - dt.timedelta(days=days)
    with out.open("w", encoding="utf-8") as fp:
        for day_offset in range(days):
            day = start_day + dt.timedelta(days=day_offset)
            active = [u for u in range(users) if rng.random() < p_active]
            for user_idx in active:
                event = {
                    "user_id": f"user-{user_idx}",
                    "op": "+",
                    "day": day.isoformat(),
                    "metadata": {"source": "sim", "seed": seed},
                }
                fp.write(json.dumps(event) + "\n")
                if rng.random() < delete_rate:
                    delete_event = {
                        "user_id": event["user_id"],
                        "op": "-",
                        "day": day.isoformat(),
                        "metadata": {"reason": "simulated_delete", "source": "sim"},
                    }
                    fp.write(json.dumps(delete_event) + "\n")


if __name__ == "__main__":
    app()
