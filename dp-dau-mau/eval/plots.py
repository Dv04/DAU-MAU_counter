# ruff: noqa: B008
"""Plot evaluation outputs for reporting."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import typer

app = typer.Typer(help="Render evaluation plots from results.json")


@app.command()
def main(
    input: Path = typer.Option(
        Path("{{DATA_DIR}}/experiments/{{EXPERIMENT_ID}}/results.json"),
        help="Results JSON produced by evaluate.py",
    ),
    out: Path = typer.Option(
        Path("{{DATA_DIR}}/plots/{{EXPERIMENT_ID}}"), help="Directory for output figures"
    ),
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with input.open("r", encoding="utf-8") as fp:
        records = json.load(fp)

    grouped: dict[str, list[dict]] = {}
    for record in records:
        grouped.setdefault(record["sketch"], []).append(record)

    for sketch, entries in grouped.items():
        epsilons = [entry["epsilon"] for entry in entries]
        dau_error = [
            abs(entry["dau"]["estimate"] - entry["dau"].get("exact_value", 0.0))
            for entry in entries
        ]
        mau_error = [
            abs(entry["mau"]["estimate"] - entry["mau"].get("exact_value", 0.0))
            for entry in entries
        ]

        plt.figure(figsize=(6, 4))
        plt.plot(epsilons, dau_error, marker="o", label="DAU error")
        plt.plot(epsilons, mau_error, marker="s", label="MAU error")
        plt.xlabel("Epsilon")
        plt.ylabel("Absolute Error")
        plt.title(f"Error vs Epsilon ({sketch})")
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        out_path = out / f"error_vs_epsilon_{sketch}.png"
        plt.savefig(out_path)
        plt.close()


if __name__ == "__main__":
    app()
