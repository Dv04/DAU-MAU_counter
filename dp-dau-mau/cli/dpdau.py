# ruff: noqa: B008
"""Command-line helpers for the DP DAU/MAU pipeline."""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import random
from collections.abc import Iterable
from pathlib import Path

import httpx
import typer

from dp_core import config as config_module
from dp_core.hashing import generate_random_secret
from dp_core.pipeline import EventRecord, PipelineManager

app = typer.Typer(help="Manage the DP-aware DAU/MAU proof-of-concept.")

HTTP_TIMEOUT = 30.0


def _load_jsonl(path: Path) -> Iterable[EventRecord]:
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            payload = json.loads(line)
            yield EventRecord(
                user_id=payload["user_id"],
                op=payload["op"],
                day=dt.date.fromisoformat(payload["day"]),
                metadata=payload.get("metadata", {}),
            )


def _load_csv(path: Path) -> Iterable[EventRecord]:
    with path.open("r", encoding="utf-8", newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            meta_payload: dict[str, object] = {}
            for key, value in row.items():
                if value in (None, ""):
                    continue
                if key.startswith("metadata."):
                    meta_payload[key.removeprefix("metadata.")] = value
            yield EventRecord(
                user_id=row["user_id"],
                op=row["op"],
                day=dt.date.fromisoformat(row["day"]),
                metadata=meta_payload,
            )


def _load_events(path: Path) -> Iterable[EventRecord]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _load_csv(path)
    return _load_jsonl(path)


def _pipeline() -> PipelineManager:
    return PipelineManager(config=config_module.AppConfig.from_env())


def _normalize_host(host: str) -> str:
    return host.rstrip("/")


def _resolve_api_key(provided: str | None) -> str | None:
    return provided or os.environ.get("SERVICE_API_KEY")


def _api_headers(api_key: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def _event_payload(event: EventRecord) -> dict[str, object]:
    return {
        "user_id": event.user_id,
        "op": event.op,
        "day": event.day.isoformat(),
        "metadata": event.metadata,
    }


@app.command()
def ingest(
    from_path: Path = typer.Argument(Path("{{EXAMPLE_DATASET_PATH}}"), help="Path to events JSONL"),
    host: str | None = typer.Option(None, "--host", help="Service base URL (e.g., http://127.0.0.1:8000)"),
    api_key: str | None = typer.Option(None, "--api-key", help="X-API-Key for service authentication"),
) -> None:
    """Ingest a batch of events from disk."""

    events = list(_load_events(from_path))
    if host:
        base_url = _normalize_host(host)
        key = _resolve_api_key(api_key)
        payload = {"events": [_event_payload(evt) for evt in events]}
        with httpx.Client(base_url=base_url, headers=_api_headers(key), timeout=HTTP_TIMEOUT) as client:
            response = client.post("/event", json=payload)
        if response.status_code >= 400:
            typer.echo(f"Failed to ingest events: {response.text}", err=True)
            raise typer.Exit(code=1)
        typer.echo(f"Ingested {len(payload['events'])} events via {base_url}/event")
        return

    pipeline = _pipeline()
    pipeline.ingest_batch(events)
    typer.echo(f"Ingested events from {from_path}")


@app.command()
def dau(
    day: dt.date = typer.Argument(..., help="Day to query (YYYY-MM-DD)"),
    host: str | None = typer.Option(None, "--host", help="Service base URL"),
    api_key: str | None = typer.Option(None, "--api-key", help="X-API-Key header"),
) -> None:
    if host:
        base_url = _normalize_host(host)
        key = _resolve_api_key(api_key)
        with httpx.Client(base_url=base_url, headers=_api_headers(key), timeout=HTTP_TIMEOUT) as client:
            response = client.get(f"/dau/{day.isoformat()}")
        if response.status_code >= 400:
            typer.echo(f"Request failed: {response.text}", err=True)
            raise typer.Exit(code=1)
        typer.echo(json.dumps(response.json(), indent=2))
        return

    pipeline = _pipeline()
    result = pipeline.get_daily_release(day)
    typer.echo(json.dumps(result, indent=2))


@app.command()
def mau(
    end: dt.date = typer.Argument(..., help="Window end day (YYYY-MM-DD)"),
    window: int = typer.Option(None, help="Window size in days"),
    host: str | None = typer.Option(None, "--host", help="Service base URL"),
    api_key: str | None = typer.Option(None, "--api-key", help="X-API-Key header"),
) -> None:
    if host:
        base_url = _normalize_host(host)
        key = _resolve_api_key(api_key)
        params = {"end": end.isoformat()}
        if window is not None:
            params["window"] = window
        with httpx.Client(base_url=base_url, headers=_api_headers(key), timeout=HTTP_TIMEOUT) as client:
            response = client.get("/mau", params=params)
        if response.status_code >= 400:
            typer.echo(f"Request failed: {response.text}", err=True)
            raise typer.Exit(code=1)
        typer.echo(json.dumps(response.json(), indent=2))
        return

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


@app.command(name="generate-synthetic")
def generate_synthetic(
    out: Path = typer.Option(
        Path("{{EXAMPLE_DATASET_PATH}}"), "--out", "-o", help="Destination JSONL path"
    ),
    days: int = typer.Option(30, "--days", "-d", min=1, help="Number of days to generate"),
    daily_users: int = typer.Option(
        500, "--daily-users", "-n", min=1, help="Approximate users per day"
    ),
    delete_rate: float = typer.Option(
        0.1, "--delete-rate", min=0.0, max=1.0, help="Fraction of users triggering deletes"
    ),
    seed: int = typer.Option(20251009, "--seed", help="Random seed"),
    start: dt.date | None = typer.Option(
        None, "--start", help="Start day (default: today - days + 1)"
    ),
) -> None:
    """Generate a synthetic workload with deletes and saves it as JSONL."""

    rng = random.Random(seed)
    if start is None:
        start = dt.date.today() - dt.timedelta(days=days - 1)
    events: list[EventRecord] = []
    activity: dict[str, list[str]] = {}
    user_pool = [f"user-{i:06d}" for i in range(daily_users * 2)]
    for offset in range(days):
        day = start + dt.timedelta(days=offset)
        day_str = day.isoformat()
        active_users = rng.sample(user_pool, k=daily_users)
        for user in active_users:
            metadata = {"source": "synthetic", "day_offset": offset}
            events.append(EventRecord(user_id=user, op="+", day=day, metadata=metadata))
            activity.setdefault(user, []).append(day_str)
        deletable = [user for user, seen_days in activity.items() if seen_days]
        deletes = (
            rng.sample(
                deletable,
                k=int(round(delete_rate * len(deletable))),
            )
            if deletable
            else []
        )
        for user in deletes:
            days_for_user = activity.get(user, [])
            if not days_for_user:
                continue
            metadata = {"source": "synthetic", "days": days_for_user.copy()}
            events.append(EventRecord(user_id=user, op="-", day=day, metadata=metadata))
            activity[user].clear()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fp:
        for event in events:
            payload = {
                "user_id": event.user_id,
                "op": event.op,
                "day": event.day.isoformat(),
                "metadata": event.metadata,
            }
            fp.write(json.dumps(payload) + "\n")
    typer.echo(
        f"Wrote {len(events)} events covering {days} days to {out} "
        f"(delete rate ≈ {delete_rate:.2%}, seed={seed})."
    )


if __name__ == "__main__":
    app()
