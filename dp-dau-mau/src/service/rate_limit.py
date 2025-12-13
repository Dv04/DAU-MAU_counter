"""Rate limiting middleware for the FastAPI service.

Provides configurable rate limiting to protect the /event endpoint from abuse.
Uses a simple in-memory sliding window counter.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""

    requests_per_minute: int = 600  # Default: 10 requests/second
    burst_size: int = 100  # Allow bursts up to this size
    enabled: bool = True


@dataclass
class RateLimitState:
    """Tracks request counts for rate limiting."""

    requests: list[float] = field(default_factory=list)

    def count_in_window(self, window_seconds: float = 60.0) -> int:
        """Count requests within the sliding window."""
        now = time.time()
        cutoff = now - window_seconds
        # Clean old entries
        self.requests = [t for t in self.requests if t > cutoff]
        return len(self.requests)

    def record_request(self) -> None:
        """Record a new request."""
        self.requests.append(time.time())


class RateLimiter:
    """In-memory rate limiter with sliding window."""

    def __init__(self, config: RateLimitConfig | None = None) -> None:
        self.config = config or RateLimitConfig()
        self._state: dict[str, RateLimitState] = defaultdict(RateLimitState)

    def get_client_key(self, request: Request) -> str:
        """Extract client identifier from request."""
        # Use API key if present, otherwise fall back to IP
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return f"key:{api_key[:8]}"  # Use first 8 chars as identifier

        # Use forwarded IP if behind proxy, otherwise direct IP
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"

        client = request.client
        if client:
            return f"ip:{client.host}"

        return "unknown"

    def is_allowed(self, request: Request) -> tuple[bool, dict[str, str]]:
        """Check if request is allowed. Returns (allowed, headers)."""
        if not self.config.enabled:
            return True, {}

        client_key = self.get_client_key(request)
        state = self._state[client_key]

        current_count = state.count_in_window()

        headers = {
            "X-RateLimit-Limit": str(self.config.requests_per_minute),
            "X-RateLimit-Remaining": str(max(0, self.config.requests_per_minute - current_count)),
            "X-RateLimit-Reset": str(int(time.time()) + 60),
        }

        if current_count >= self.config.requests_per_minute:
            return False, headers

        state.record_request()
        headers["X-RateLimit-Remaining"] = str(
            max(0, self.config.requests_per_minute - current_count - 1)
        )

        return True, headers


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for rate limiting."""

    def __init__(
        self,
        app: object,
        limiter: RateLimiter | None = None,
        protected_paths: set[str] | None = None,
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.limiter = limiter or RateLimiter()
        self.protected_paths = protected_paths or {"/event"}

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Only rate limit protected paths
        if request.url.path not in self.protected_paths:
            return await call_next(request)

        allowed, headers = self.limiter.is_allowed(request)

        if not allowed:
            return Response(
                content='{"error": "rate_limit_exceeded", "message": "Too many requests"}',
                status_code=429,
                media_type="application/json",
                headers=headers,
            )

        response = await call_next(request)

        # Add rate limit headers to response
        for key, value in headers.items():
            response.headers[key] = value

        return response
