"""HTTP routes for the FastAPI service."""

from __future__ import annotations

import datetime as dt
import time
from collections import defaultdict
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse

from dp_core.pipeline import EventRecord, PipelineManager

from . import auth
from .api_schemas import BudgetResponse, EventIngestionRequest, HealthResponse, MetricResponse

router = APIRouter()


def get_pipeline(request: Request) -> PipelineManager:
    return request.app.state.pipeline  # type: ignore[attr-defined]


def get_config(request: Request):
    return request.app.state.config  # type: ignore[attr-defined]


@dataclass
class RouteStats:
    count: int = 0
    durations_ms: list[float] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.durations_ms is None:
            self.durations_ms = []

    def record(self, duration_ms: float) -> None:
        self.count += 1
        self.durations_ms.append(duration_ms)
        if len(self.durations_ms) > 1024:
            self.durations_ms.pop(0)

    def percentile(self, percentile: float) -> float:
        if not self.durations_ms:
            return 0.0
        data = sorted(self.durations_ms)
        index = min(len(data) - 1, max(0, int(round(percentile / 100 * (len(data) - 1)))))
        return data[index]


REQUEST_STATS: dict[str, RouteStats] = defaultdict(RouteStats)


def record_metrics(route: str, duration_ms: float) -> None:
    REQUEST_STATS[route].record(duration_ms)


@router.post("/event", status_code=status.HTTP_202_ACCEPTED)
async def post_event(
    payload: EventIngestionRequest,
    request: Request,
    pipeline: PipelineManager = Depends(get_pipeline),
    _: None = Depends(auth.require_api_key),
) -> Response:
    start = time.perf_counter()
    try:
        events = payload.events or []
        pipeline.ingest_batch(
            EventRecord(
                user_id=evt.user_id,
                op=evt.op,
                day=evt.day,
                metadata=evt.metadata,
            )
            for evt in events
        )
        response = JSONResponse({"ingested": len(events)}, status_code=status.HTTP_202_ACCEPTED)
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        record_metrics("/event", duration_ms)
    return response


@router.get("/dau/{day}", response_model=MetricResponse)
async def get_dau(
    day: dt.date,
    request: Request,
    pipeline: PipelineManager = Depends(get_pipeline),
    _: None = Depends(auth.require_api_key),
) -> MetricResponse:
    start = time.perf_counter()
    try:
        result = pipeline.get_daily_release(day)
        result["version"] = request.app.state.config.storage.experiment_id  # type: ignore[attr-defined]
        return MetricResponse(**result)
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        record_metrics("/dau", duration_ms)


@router.get("/mau", response_model=MetricResponse)
async def get_mau(
    end: dt.date,
    request: Request,
    window: int | None = None,
    pipeline: PipelineManager = Depends(get_pipeline),
    _: None = Depends(auth.require_api_key),
) -> MetricResponse:
    start = time.perf_counter()
    try:
        result = pipeline.get_mau_release(end, window)
        result["version"] = request.app.state.config.storage.experiment_id  # type: ignore[attr-defined]
        return MetricResponse(**result)
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        record_metrics("/mau", duration_ms)


@router.get("/metrics")
async def get_metrics() -> PlainTextResponse:
    lines: list[str] = []
    for route, stats in REQUEST_STATS.items():
        lines.append(f'dp_requests_total{{route="{route}"}} {stats.count}')
        lines.append(f'dp_request_latency_ms_p50{{route="{route}"}} {stats.percentile(50):.3f}')
        lines.append(f'dp_request_latency_ms_p99{{route="{route}"}} {stats.percentile(99):.3f}')
    text = "\n".join(lines) + "\n"
    return PlainTextResponse(text)


@router.get("/healthz", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@router.get("/budget/{metric}", response_model=BudgetResponse)
async def get_budget(
    metric: str,
    day: dt.date,
    pipeline: PipelineManager = Depends(get_pipeline),
    _: None = Depends(auth.require_api_key),
) -> BudgetResponse:
    start = time.perf_counter()
    try:
        metric_normalized = metric.lower()
        if metric_normalized not in {"dau", "mau"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="metric must be 'dau' or 'mau'"
            )
        summary = pipeline.get_budget_summary(metric_normalized, day)
        return BudgetResponse(**summary)
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        record_metrics("/budget", duration_ms)
