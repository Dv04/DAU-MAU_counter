"""Simple API key authentication dependency."""

from __future__ import annotations

from fastapi import Header, HTTPException, Request, status


async def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    config = request.app.state.config  # type: ignore[attr-defined]
    required_key = config.security.api_key
    if not required_key:
        return
    if x_api_key != required_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key. Contact {{ADMIN_EMAIL}} for access.",
        )
