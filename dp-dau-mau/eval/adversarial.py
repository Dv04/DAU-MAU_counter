# ruff: noqa: B008
"""Adversarial workload generator that stresses deletion handling."""

from __future__ import annotations

import datetime as dt
import json
import random
from pathlib import Path

import typer

app = typer.Typer(help="Generate adversarial churn workloads.")


@app.command()
def main(
    users: int = typer.Option(500, help="Number of toggling users"),
    window: int = typer.Option(30, help="Window size", show_default="{{MAU_WINDOW_DAYS}}"),
    flips: int = typer.Option(2, help="Max flips per user", show_default="{{W_BOUND}}"),
    seed: int = typer.Option(20251009, help="Random seed", show_default="{{DEFAULT_SEED}}"),
    out: Path = typer.Option(
        Path("{{DATA_DIR}}/streams/adversarial.jsonl"), help="Output JSONL path"
    ),
) -> None:
    rng = random.Random(seed)
    out.parent.mkdir(parents=True, exist_ok=True)
    start_day = dt.datetime.now(tz=dt.UTC).date() - dt.timedelta(days=window)
    with out.open("w", encoding="utf-8") as fp:
        for user_idx in range(users):
            user_id = f"adv-{user_idx}"
            for flip_idx in range(flips):
                offset = rng.randint(0, max(window - 1, 0))
                event_day = start_day + dt.timedelta(days=offset)
                event = {
                    "user_id": user_id,
                    "op": "+" if flip_idx % 2 == 0 else "-",
                    "day": event_day.isoformat(),
                    "metadata": {
                        "source": "adversarial",
                        "flip": flip_idx,
                        "window": window,
                        "offset": offset,
                    },
                }
                fp.write(json.dumps(event) + "\n")


if __name__ == "__main__":
    app()
