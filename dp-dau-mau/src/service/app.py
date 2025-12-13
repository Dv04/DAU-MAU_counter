"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import FastAPI, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.requests import Request

from dp_core.config import AppConfig
from dp_core.pipeline import PipelineManager

from . import openapi_overrides
from .metrics import MetricsMiddleware
from .rate_limit import RateLimitConfig, RateLimiter, RateLimitMiddleware
from .routes import router


def _normalize_detail(detail: object) -> tuple[str, str]:
    if isinstance(detail, dict):
        error = str(detail.get("error", "unknown_error"))
        hint = str(detail.get("hint", detail.get("detail", "")))
        return error, hint
    return "request_failed", str(detail)


def _validation_hint(errors: Iterable[dict[str, object]]) -> str:
    messages = []
    for err in errors:
        loc_value = err.get("loc", [])
        if isinstance(loc_value, Iterable) and not isinstance(loc_value, (str, bytes)):
            loc = ".".join(str(part) for part in loc_value)
        else:
            loc = str(loc_value)
        msg = str(err.get("msg", "invalid value"))
        messages.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(messages) or "invalid request body"


def create_app() -> FastAPI:
    config = AppConfig.from_env()
    app = FastAPI(
        title="DP-accurate DAU/MAU Counter",
        description="Proof-of-concept FastAPI service for differentially private DAU/MAU metrics.",
        version=config.storage.experiment_id,
        openapi_url="/openapi.json",
        contact={"name": "DP Duty", "email": config.security.admin_email or "dp-admin@example.com"},
    )
    app.state.config = config
    app.state.pipeline = PipelineManager(config=config)
    app.add_middleware(MetricsMiddleware)

    # Add rate limiting middleware for /event endpoint
    rate_limit_config = RateLimitConfig(
        requests_per_minute=600,  # 10 req/s average
        burst_size=100,
        enabled=True,
    )
    app.add_middleware(
        RateLimitMiddleware,
        limiter=RateLimiter(rate_limit_config),
        protected_paths={"/event"},
    )

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(
        request: Request,
        exc: RequestValidationError,  # noqa: ARG001
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "invalid_request", "hint": _validation_hint(exc.errors())},
        )

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(
        request: Request,
        exc: HTTPException,  # noqa: ARG001
    ) -> JSONResponse:
        error, hint = _normalize_detail(exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": error, "hint": hint},
            headers=exc.headers,
        )

    openapi_overrides.apply(app)
    app.include_router(router)
    return app


app = create_app()
