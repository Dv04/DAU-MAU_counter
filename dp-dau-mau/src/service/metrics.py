"""Prometheus metrics helpers and middleware for the FastAPI service."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

DEFAULT_BUCKETS: tuple[float, ...] = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0)


@dataclass
class MetricsRegistry:
    buckets: tuple[float, ...] = DEFAULT_BUCKETS
    request_totals: dict[tuple[str, str, int], int] = field(default_factory=dict)
    requests_5xx: dict[tuple[str, str], int] = field(default_factory=dict)
    latency_buckets: dict[tuple[str, str, float], int] = field(default_factory=dict)
    latency_sum: dict[tuple[str, str], float] = field(default_factory=dict)
    latency_count: dict[tuple[str, str], int] = field(default_factory=dict)

    def observe(self, method: str, handler: str, status: int, duration_seconds: float) -> None:
        key = (handler, method, status)
        self.request_totals[key] = self.request_totals.get(key, 0) + 1
        pair = (handler, method)
        self.requests_5xx.setdefault(pair, 0)
        self.latency_sum[pair] = self.latency_sum.get(pair, 0.0) + duration_seconds
        self.latency_count[pair] = self.latency_count.get(pair, 0) + 1
        if 500 <= status < 600:
            self.requests_5xx[pair] = self.requests_5xx.get(pair, 0) + 1
        for bucket in self.buckets:
            if duration_seconds <= bucket:
                bucket_key = (handler, method, bucket)
                self.latency_buckets[bucket_key] = self.latency_buckets.get(bucket_key, 0) + 1

    def _render_requests_total(self) -> Iterable[str]:
        for (handler, method, status_code), count in sorted(self.request_totals.items()):
            yield (
                f'app_requests_total{{handler="{handler}",method="{method}",'
                f'status="{status_code}"}} {count}'
            )

    def _render_requests_5xx(self) -> Iterable[str]:
        for (handler, method), count in sorted(self.requests_5xx.items()):
            yield f'app_requests_5xx_total{{handler="{handler}",method="{method}"}} {count}'

    def _render_latency(self) -> Iterable[str]:
        for handler, method in sorted(self.latency_count):
            count = self.latency_count.get((handler, method), 0)
            for bucket in self.buckets:
                bucket_count = self.latency_buckets.get((handler, method, bucket), 0)
                yield (
                    f'app_request_latency_seconds_bucket{{handler="{handler}",method="{method}",'
                    f'le="{bucket}"}} {bucket_count}'
                )
            # +Inf bucket equals total count
            yield (
                f'app_request_latency_seconds_bucket{{handler="{handler}",method="{method}",'
                f'le="+Inf"}} {count}'
            )
            total = self.latency_sum.get((handler, method), 0.0)
            yield (
                f'app_request_latency_seconds_sum{{handler="{handler}",method="{method}"}} {total}'
            )
            yield (
                f'app_request_latency_seconds_count{{handler="{handler}",method="{method}"}} '
                f"{count}"
            )

    def render(self) -> str:
        lines = list(self._render_requests_total())
        lines.extend(self._render_requests_5xx())
        lines.extend(self._render_latency())
        return "\n".join(lines) + ("\n" if lines else "")


METRICS = MetricsRegistry()


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record per-request metrics against :class:`MetricsRegistry`."""

    def __init__(self, app: ASGIApp, registry: MetricsRegistry | None = None) -> None:
        super().__init__(app)
        self._registry = registry or METRICS

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        handler = getattr(request.scope.get("route"), "path", request.url.path)
        method = request.method.upper()
        start = time.perf_counter()
        status_code: int
        response: Response
        try:
            response = await call_next(request)
            status_code = response.status_code
        except HTTPException as exc:
            status_code = exc.status_code
            duration = time.perf_counter() - start
            self._registry.observe(method, handler, status_code, duration)
            raise
        except Exception:
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            duration = time.perf_counter() - start
            self._registry.observe(method, handler, status_code, duration)
            raise
        duration = time.perf_counter() - start
        self._registry.observe(method, handler, status_code, duration)
        return response
