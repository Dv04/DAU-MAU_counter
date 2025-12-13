# ruff: noqa: B008
"""Command-line helpers for the DP DAU/MAU pipeline."""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import random
import sys
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal, cast

import anyio
import httpx
import typer

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"

try:
    from dp_core import config as config_module
    from dp_core.hashing import generate_random_secret
    from dp_core.pipeline import EventRecord, PipelineManager
except ModuleNotFoundError:  # pragma: no cover - fallback when running via python -m
    if str(SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(SRC_ROOT))
    from dp_core import config as config_module
    from dp_core.hashing import generate_random_secret
    from dp_core.pipeline import EventRecord, PipelineManager

REAL_HTTPX = httpx

__version__ = "0.1.0"


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"dpdau version {__version__}")
        raise typer.Exit()


app = typer.Typer(help="Manage the DP-aware DAU/MAU proof-of-concept.")


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-V",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """DP-accurate DAU/MAU Counter CLI."""
    pass


HTTP_TIMEOUT = 30.0


def _parse_date_option(value: str, name: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"{name} must be in YYYY-MM-DD format.") from exc


def _config() -> config_module.AppConfig:
    return config_module.AppConfig.from_env()


def _load_jsonl(path: Path) -> Iterable[EventRecord]:
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            payload = json.loads(line)
            yield EventRecord(
                user_id=payload["user_id"],
                op=cast(Literal["+", "-"], payload["op"]),
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
                op=cast(Literal["+", "-"], row["op"]),
                day=dt.date.fromisoformat(row["day"]),
                metadata=meta_payload,
            )


def _load_events(path: Path, fmt: str | None = None) -> Iterable[EventRecord]:
    suffix = (fmt or path.suffix).lower()
    if suffix in {".csv", "csv"}:
        return _load_csv(path)
    if suffix in {".jsonl", "jsonl", ".json"}:
        return _load_jsonl(path)
    raise ValueError(f"Unsupported dataset format '{suffix}'. Use csv or jsonl.")


def _pipeline() -> PipelineManager:
    return PipelineManager(config=_config())


def _normalize_host(host: str) -> str:
    return host.rstrip("/")


def _resolve_host(provided: str | None) -> str | None:
    candidate = provided or os.environ.get("SERVICE_HOST")
    if not candidate:
        return None
    if config_module.PLACEHOLDER_PATTERN.fullmatch(candidate.strip()):
        return None
    return _normalize_host(candidate)


def _resolve_api_key(provided: str | None) -> str | None:
    candidate = provided or os.environ.get("SERVICE_API_KEY")
    if not candidate:
        return None
    if config_module.PLACEHOLDER_PATTERN.fullmatch(str(candidate).strip()):
        return None
    return str(candidate)


def _api_headers(api_key: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


@contextmanager
def _http_client(base_url: str, headers: dict[str, str], timeout: float) -> Iterator[httpx.Client]:
    client = httpx.Client(base_url=base_url, headers=headers, timeout=timeout)
    try:
        yield client
    finally:
        try:
            client.close()
        except AttributeError:
            # Some test transports (e.g., httpx.ASGITransport) do not expose close().
            pass


def _send_request(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    json: object | None = None,
    params: object | None = None,
) -> httpx.Response:
    transport = getattr(client, "_transport", None)
    if (
        transport
        and hasattr(transport, "handle_async_request")
        and not hasattr(transport, "handle_request")
    ):
        url = client.base_url.join(path)
        request = REAL_HTTPX.Request(
            method=method,
            url=url,
            headers=dict(client.headers),
            json=cast(Any, json),
            params=cast(Any, params),
        )
        response = anyio.run(transport.handle_async_request, request)
        content = anyio.run(response.aread)
        return REAL_HTTPX.Response(
            status_code=response.status_code,
            headers=response.headers,
            content=content,
            request=request,
        )
    return client.request(
        method,
        path,
        json=cast(Any, json),
        params=cast(Any, params),
    )


def _event_payload(event: EventRecord) -> dict[str, Any]:
    return {
        "user_id": event.user_id,
        "op": event.op,
        "day": event.day.isoformat(),
        "metadata": event.metadata,
    }


@app.command()
def ingest(
    from_path: Path | None = typer.Option(
        None,
        "--from",
        "-f",
        help="Dataset path (default: {{EXAMPLE_DATASET_PATH}})",
    ),
    fmt: str | None = typer.Option(
        None,
        "--format",
        "-m",
        help="Input format [csv|jsonl]; auto-detected when omitted.",
    ),
    host: str | None = typer.Option(
        None,
        "--host",
        help="Service base URL (default: {{SERVICE_HOST}} or local pipeline)",
    ),
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        help="X-API-Key for service authentication",
    ),
) -> None:
    """Ingest a batch of events from disk."""

    cfg = _config()
    dataset = from_path if from_path is not None else cfg.storage.example_dataset_path
    if not dataset.exists():
        typer.echo(f"Dataset not found: {dataset}", err=True)
        raise typer.Exit(code=1)
    try:
        events = list(_load_events(dataset, fmt))
    except ValueError as exc:  # invalid format hint
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if not events:
        typer.echo("Dataset contains no events to ingest.", err=True)
        raise typer.Exit(code=1)

    resolved_host = _resolve_host(host)
    if resolved_host:
        key = _resolve_api_key(api_key)
        payload = {"events": [_event_payload(evt) for evt in events]}
        headers = _api_headers(key)
        with _http_client(resolved_host, headers, HTTP_TIMEOUT) as client:
            response = _send_request(client, "POST", "/event", json=payload)
        if response.status_code >= 400:
            typer.echo(f"Failed to ingest events: {response.text}", err=True)
            raise typer.Exit(code=1)
        typer.echo(f"Streamed {len(events)} events to {resolved_host}/event")
        return

    pipeline = _pipeline()
    pipeline.ingest_batch(events)
    typer.echo(f"Ingested {len(events)} events locally from {dataset}")


@app.command()
def dau(
    day: str = typer.Option(..., "--day", "-d", help="Day to query (YYYY-MM-DD)"),
    host: str | None = typer.Option(
        None, "--host", help="Service base URL (default: {{SERVICE_HOST}})"
    ),
    api_key: str | None = typer.Option(None, "--api-key", help="X-API-Key header"),
) -> None:
    day_value = _parse_date_option(day, "day")
    resolved_host = _resolve_host(host)
    if resolved_host:
        key = _resolve_api_key(api_key)
        headers = _api_headers(key)
        with _http_client(resolved_host, headers, HTTP_TIMEOUT) as client:
            response = _send_request(client, "GET", f"/dau/{day_value.isoformat()}")
        if response.status_code >= 400:
            typer.echo(f"Request failed: {response.text}", err=True)
            raise typer.Exit(code=1)
        payload = response.json()
        typer.echo(
            (
                f"[DAU] {day_value.isoformat()} "
                f"estimate={payload['estimate']:.2f} "
                f"ε={payload['epsilon_used']:.2f}"
            ),
            err=True,
        )
        typer.echo(json.dumps(payload, indent=2))
        return

    pipeline = _pipeline()
    payload = pipeline.get_daily_release(day_value)
    typer.echo(
        (
            f"[DAU] {day_value.isoformat()} "
            f"estimate={payload['estimate']:.2f} "
            f"ε={payload['epsilon_used']:.2f}"
        ),
        err=True,
    )
    typer.echo(json.dumps(payload, indent=2))


@app.command()
def mau(
    end: str = typer.Option(..., "--end", "-e", help="Window end day (YYYY-MM-DD)"),
    window: int | None = typer.Option(
        None,
        "--window",
        "-w",
        help="Window size in days (default: {{MAU_WINDOW_DAYS}})",
    ),
    host: str | None = typer.Option(
        None, "--host", help="Service base URL (default: {{SERVICE_HOST}})"
    ),
    api_key: str | None = typer.Option(None, "--api-key", help="X-API-Key header"),
) -> None:
    end_day = _parse_date_option(end, "end")
    cfg = _config()
    window_days = window or cfg.sketch.mau_window_days
    resolved_host = _resolve_host(host)
    if resolved_host:
        key = _resolve_api_key(api_key)
        headers = _api_headers(key)
        params = {"end": end_day.isoformat(), "window": window_days}
        with _http_client(resolved_host, headers, HTTP_TIMEOUT) as client:
            response = _send_request(client, "GET", "/mau", params=params)
        if response.status_code >= 400:
            typer.echo(f"Request failed: {response.text}", err=True)
            raise typer.Exit(code=1)
        payload = response.json()
        typer.echo(
            (
                f"[MAU] end={end_day.isoformat()} window={window_days} "
                f"estimate={payload['estimate']:.2f}"
            ),
            err=True,
        )
        typer.echo(json.dumps(payload, indent=2))
        return

    pipeline = _pipeline()
    payload = pipeline.get_mau_release(end_day, window_days)
    typer.echo(
        (
            f"[MAU] end={end_day.isoformat()} window={window_days} "
            f"estimate={payload['estimate']:.2f}"
        ),
        err=True,
    )
    typer.echo(json.dumps(payload, indent=2))


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
    effective: str = typer.Argument(..., help="Effective day for new salt"),
    rotation_days: int = typer.Option(
        30, help="Rotation cadence", show_default="{{HASH_SALT_ROTATION_DAYS}}"
    ),
) -> None:
    effective_day = _parse_date_option(effective, "effective")
    secret = generate_random_secret()
    typer.echo("Generated new salt secret. Update your secrets manager:")
    typer.echo(f"HASH_SALT_SECRET={secret}")
    typer.echo(f"HASH_SALT_ROTATION_DAYS={rotation_days}")
    typer.echo(f"Effective date: {effective_day.isoformat()}")


@app.command(name="generate-synthetic")
def generate_synthetic(
    days: int = typer.Option(7, "--days", "-d", min=1, help="Number of days to generate"),
    users: int = typer.Option(100, "--users", "-u", min=1, help="Size of synthetic user pool"),
    p_active: float = typer.Option(
        0.2,
        "--p-active",
        min=0.0,
        max=1.0,
        help="Probability any user emits a '+' event on a given day",
    ),
    delete_rate: float = typer.Option(
        0.1,
        "--delete-rate",
        min=0.0,
        max=1.0,
        help="Chance an active user issues a deletion on each day",
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        "-o",
        help="Destination file name (default: {{EXAMPLE_DATASET_PATH}})",
    ),
    seed: int = typer.Option(20251009, "--seed", help="Random seed"),
    start: str | None = typer.Option(None, "--start", help="Start day (default: today - days + 1)"),
) -> None:
    """Generate synthetic workload files (JSONL + CSV) under {{DATA_DIR}}/streams."""

    cfg = _config()
    streams_dir = cfg.storage.data_dir / "streams"
    streams_dir.mkdir(parents=True, exist_ok=True)

    if out is None:
        base_name = f"synthetic_{days}d.jsonl"
        target_jsonl = streams_dir / base_name
    else:
        candidate = out if out.is_absolute() else streams_dir / out
        target_jsonl = candidate

    if target_jsonl.suffix.lower() != ".jsonl":
        target_jsonl = target_jsonl.with_suffix(".jsonl")

    streams_root = streams_dir.resolve()
    target_root = target_jsonl.resolve().parent
    if streams_root not in target_root.parents and target_root != streams_root:
        typer.echo("Output must reside under {{DATA_DIR}}/streams.", err=True)
        raise typer.Exit(code=1)

    csv_path = target_jsonl.with_suffix(".csv")
    target_jsonl.parent.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    if start is None:
        today = dt.datetime.now(dt.UTC).date()
        start_day = today - dt.timedelta(days=days - 1)
    else:
        start_day = _parse_date_option(start, "start")

    events: list[EventRecord] = []
    activity: dict[str, list[str]] = {}
    user_pool = [f"user-{i:06d}" for i in range(users)]
    for offset in range(days):
        day = start_day + dt.timedelta(days=offset)
        day_str = day.isoformat()
        for user in user_pool:
            if rng.random() <= p_active:
                metadata = {"source": "synthetic", "day_offset": offset}
                events.append(EventRecord(user_id=user, op="+", day=day, metadata=metadata))
                activity.setdefault(user, []).append(day_str)
        for user, seen_days in list(activity.items()):
            if not seen_days:
                continue
            if rng.random() <= delete_rate:
                metadata = {"source": "synthetic", "days": seen_days.copy()}
                events.append(EventRecord(user_id=user, op="-", day=day, metadata=metadata))
                activity[user].clear()

    with target_jsonl.open("w", encoding="utf-8") as fp:
        for event in events:
            payload = {
                "user_id": event.user_id,
                "op": event.op,
                "day": event.day.isoformat(),
                "metadata": event.metadata,
            }
            fp.write(json.dumps(payload) + "\n")

    metadata_keys = sorted({key for event in events for key in event.metadata.keys()})
    fieldnames = ["user_id", "op", "day"] + [f"metadata.{key}" for key in metadata_keys]
    with csv_path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for event in events:
            row = {
                "user_id": event.user_id,
                "op": event.op,
                "day": event.day.isoformat(),
            }
            for key in metadata_keys:
                value = event.metadata.get(key)
                if isinstance(value, list | dict):
                    row[f"metadata.{key}"] = json.dumps(value)
                elif value is None:
                    row[f"metadata.{key}"] = ""
                else:
                    row[f"metadata.{key}"] = str(value)
            writer.writerow(row)

    typer.echo(
        f"Generated {len(events)} events across {days} days "
        f"(p_active={p_active:.2f}, deletes={delete_rate:.2f}).\n"
        f"  JSONL: {target_jsonl}\n  CSV:   {csv_path}"
    )


if __name__ == "__main__":
    app()
