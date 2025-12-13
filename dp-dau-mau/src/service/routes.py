"""HTTP routes for the FastAPI service."""

from __future__ import annotations

import datetime as dt
from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse

from dp_core.pipeline import BudgetExceededError, EventRecord, PipelineManager

from . import auth
from .api_schemas import BudgetResponse, EventIngestionRequest, HealthResponse, MetricResponse
from .metrics import METRICS

router = APIRouter()


def get_pipeline(request: Request) -> PipelineManager:
    return cast(PipelineManager, request.app.state.pipeline)


def _budget_error_response(pipeline: PipelineManager, exc: BudgetExceededError) -> JSONResponse:
    metric = exc.metric
    cap = pipeline.budgets.dau if metric == "dau" else pipeline.budgets.mau
    delta = 0.0 if metric == "dau" else pipeline.config.dp.delta
    snapshot = pipeline.accountant.budget_snapshot(
        metric,
        exc.day,
        cap,
        delta,
        pipeline.config.dp.rdp_orders,
        pipeline.config.dp.advanced_delta,
    )
    year = exc.day.year
    month = exc.day.month
    if month == 12:
        next_reset = dt.date(year + 1, 1, 1)
    else:
        next_reset = dt.date(year, month + 1, 1)
    content = {
        "error": "budget_exhausted",
        "metric": metric,
        "period": snapshot.period,
        "epsilon_spent": snapshot.epsilon_spent,
        "epsilon_cap": snapshot.epsilon_cap,
        "epsilon_remaining": snapshot.epsilon_remaining,
        "next_reset": next_reset.isoformat(),
        "budget": snapshot.as_dict(),
    }
    return JSONResponse(status_code=status.HTTP_429_TOO_MANY_REQUESTS, content=content)


@router.post("/event", status_code=status.HTTP_202_ACCEPTED)
async def post_event(
    payload: EventIngestionRequest,
    request: Request,
    pipeline: PipelineManager = Depends(get_pipeline),  # noqa: B008
    _: None = Depends(auth.require_api_key),  # noqa: B008
) -> JSONResponse:
    events = payload.events or []
    pipeline.ingest_batch(
        EventRecord(
            user_id=evt.user_id,
            op=cast(Literal["+", "-"], evt.op),
            day=evt.day,
            metadata=evt.metadata,
        )
        for evt in events
    )
    return JSONResponse({"ingested": len(events)}, status_code=status.HTTP_202_ACCEPTED)


@router.get("/dau/{day}", response_model=MetricResponse)
async def get_dau(
    day: dt.date,
    request: Request,
    pipeline: PipelineManager = Depends(get_pipeline),  # noqa: B008
    _: None = Depends(auth.require_api_key),  # noqa: B008
) -> MetricResponse | JSONResponse:
    try:
        result = pipeline.get_daily_release(day)
    except BudgetExceededError as exc:
        return _budget_error_response(pipeline, exc)
    result["version"] = request.app.state.config.storage.experiment_id  # type: ignore[attr-defined]
    return MetricResponse(**result)


@router.get("/mau", response_model=MetricResponse)
async def get_mau(
    end: dt.date,
    request: Request,
    window: int | None = None,
    pipeline: PipelineManager = Depends(get_pipeline),  # noqa: B008
    _: None = Depends(auth.require_api_key),  # noqa: B008
) -> MetricResponse | JSONResponse:
    try:
        result = pipeline.get_mau_release(end, window)
    except BudgetExceededError as exc:
        return _budget_error_response(pipeline, exc)
    result["version"] = request.app.state.config.storage.experiment_id  # type: ignore[attr-defined]
    return MetricResponse(**result)


@router.get("/metrics")
async def get_metrics() -> PlainTextResponse:
    return PlainTextResponse(METRICS.render())


@router.get("/healthz", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@router.get("/budget/{metric}", response_model=BudgetResponse)
async def get_budget(
    metric: str,
    day: dt.date,
    pipeline: PipelineManager = Depends(get_pipeline),  # noqa: B008
    _: None = Depends(auth.require_api_key),  # noqa: B008
) -> BudgetResponse:
    metric_normalized = metric.lower()
    if metric_normalized not in {"dau", "mau"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="metric must be 'dau' or 'mau'"
        )
    summary = pipeline.get_budget_summary(metric_normalized, day)
    return BudgetResponse(**summary)
