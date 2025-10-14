"""HTTP routes for the FastAPI service."""

from __future__ import annotations

import datetime as dt
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse

from dp_core.pipeline import BudgetExceededError, EventRecord, PipelineManager

from . import auth
from .api_schemas import BudgetResponse, EventIngestionRequest, HealthResponse, MetricResponse
from .metrics import METRICS

router = APIRouter()


def get_pipeline(request: Request) -> PipelineManager:
    return request.app.state.pipeline  # type: ignore[attr-defined]


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
    pipeline: PipelineManager = Depends(get_pipeline),
    _: None = Depends(auth.require_api_key),
) -> Response:
    start = time.perf_counter()
    status_code = status.HTTP_202_ACCEPTED
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
        return response
    except HTTPException as exc:
        status_code = exc.status_code
        raise
    except Exception:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        raise
    finally:
        duration = time.perf_counter() - start
        METRICS.observe("POST", "/event", status_code, duration)


@router.get("/dau/{day}", response_model=MetricResponse)
async def get_dau(
    day: dt.date,
    request: Request,
    pipeline: PipelineManager = Depends(get_pipeline),
    _: None = Depends(auth.require_api_key),
) -> MetricResponse:
    start = time.perf_counter()
    status_code = status.HTTP_200_OK
    response: Response
    try:
        result = pipeline.get_daily_release(day)
        result["version"] = request.app.state.config.storage.experiment_id  # type: ignore[attr-defined]
        response = MetricResponse(**result)
    except BudgetExceededError as exc:
        response = _budget_error_response(pipeline, exc)
        status_code = response.status_code
    except Exception:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        raise
    finally:
        duration = time.perf_counter() - start
        METRICS.observe("GET", "/dau", status_code, duration)
    return response


@router.get("/mau", response_model=MetricResponse)
async def get_mau(
    end: dt.date,
    request: Request,
    window: int | None = None,
    pipeline: PipelineManager = Depends(get_pipeline),
    _: None = Depends(auth.require_api_key),
) -> MetricResponse:
    start = time.perf_counter()
    status_code = status.HTTP_200_OK
    response: Response
    try:
        result = pipeline.get_mau_release(end, window)
        result["version"] = request.app.state.config.storage.experiment_id  # type: ignore[attr-defined]
        response = MetricResponse(**result)
    except BudgetExceededError as exc:
        response = _budget_error_response(pipeline, exc)
        status_code = response.status_code
    except Exception:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        raise
    finally:
        duration = time.perf_counter() - start
        METRICS.observe("GET", "/mau", status_code, duration)
    return response


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
    pipeline: PipelineManager = Depends(get_pipeline),
    _: None = Depends(auth.require_api_key),
) -> BudgetResponse:
    start = time.perf_counter()
    status_code = status.HTTP_200_OK
    try:
        metric_normalized = metric.lower()
        if metric_normalized not in {"dau", "mau"}:
            status_code = status.HTTP_400_BAD_REQUEST
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="metric must be 'dau' or 'mau'"
            )
        summary = pipeline.get_budget_summary(metric_normalized, day)
        response = BudgetResponse(**summary)
    except HTTPException:
        raise
    except Exception:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        raise
    finally:
        duration = time.perf_counter() - start
        METRICS.observe("GET", "/budget", status_code, duration)
    return response
