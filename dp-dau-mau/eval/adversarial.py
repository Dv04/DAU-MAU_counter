"""Adversarial workload generator that stresses deletion handling."""

from __future__ import annotations

import json
import random
import datetime as dt
from pathlib import Path

import typer

app = typer.Typer(help="Generate adversarial churn workloads.")


@app.command()
def main(
    users: int = typer.Option(500, help="Number of toggling users"),
    window: int = typer.Option(30, help="Window size", show_default="{{MAU_WINDOW_DAYS}}"),
    flips: int = typer.Option(2, help="Max flips per user", show_default="{{W_BOUND}}"),
    seed: int = typer.Option(20251009, help="Random seed", show_default="{{DEFAULT_SEED}}"),
    out: Path = typer.Option(Path("{{DATA_DIR}}/streams/adversarial.jsonl"), help="Output JSONL path"),
) -> None:
    rng = random.Random(seed)
    out.parent.mkdir(parents=True, exist_ok=True)
    start_day = dt.date.today() - dt.timedelta(days=window)
    with out.open("w", encoding="utf-8") as fp:
        for user_idx in range(users):
            user_id = f"adv-{user_idx}"
            day = start_day
            for flip_idx in range(flips):
                event = {
                    "user_id": user_id,
                    "op": "+" if flip_idx % 2 == 0 else "-",
                    "day": (day + dt.timedelta(days=flip_idx % window)).isoformat(),
                    "metadata": {"source": "adversarial", "flip": flip_idx},
                }
                fp.write(json.dumps(event) + "\n")


if __name__ == "__main__":
    app()
