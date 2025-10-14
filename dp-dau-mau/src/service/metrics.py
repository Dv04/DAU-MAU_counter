"""Simple Prometheus-style metrics registry for the FastAPI service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Tuple


DEFAULT_BUCKETS: Tuple[float, ...] = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0)


@dataclass
class MetricsRegistry:
    buckets: Tuple[float, ...] = DEFAULT_BUCKETS
    request_totals: Dict[tuple[str, str, int], int] = field(default_factory=dict)
    requests_5xx: Dict[tuple[str, str], int] = field(default_factory=dict)
    latency_buckets: Dict[tuple[str, str, float], int] = field(default_factory=dict)
    latency_sum: Dict[tuple[str, str], float] = field(default_factory=dict)
    latency_count: Dict[tuple[str, str], int] = field(default_factory=dict)

    def observe(self, method: str, handler: str, status: int, duration_seconds: float) -> None:
        key = (handler, method, status)
        self.request_totals[key] = self.request_totals.get(key, 0) + 1
        pair = (handler, method)
        self.latency_sum[pair] = self.latency_sum.get(pair, 0.0) + duration_seconds
        self.latency_count[pair] = self.latency_count.get(pair, 0) + 1
        if 500 <= status < 600:
            self.requests_5xx[pair] = self.requests_5xx.get(pair, 0) + 1
        for bucket in self.buckets:
            if duration_seconds <= bucket:
                bucket_key = (handler, method, bucket)
                self.latency_buckets[bucket_key] = self.latency_buckets.get(bucket_key, 0) + 1

    def _render_requests_total(self) -> Iterable[str]:
        for (handler, method, status), count in sorted(self.request_totals.items()):
            yield (
                f'app_requests_total{{handler="{handler}",method="{method}",status="{status}"}} {count}'
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
                f'app_request_latency_seconds_bucket{{handler="{handler}",method="{method}",le="+Inf"}} {count}'
            )
            total = self.latency_sum.get((handler, method), 0.0)
            yield (
                f'app_request_latency_seconds_sum{{handler="{handler}",method="{method}"}} {total}'
            )
            yield (
                f'app_request_latency_seconds_count{{handler="{handler}",method="{method}"}} {count}'
            )

    def render(self) -> str:
        lines = list(self._render_requests_total())
        lines.extend(self._render_requests_5xx())
        lines.extend(self._render_latency())
        return "\n".join(lines) + ("\n" if lines else "")


METRICS = MetricsRegistry()
