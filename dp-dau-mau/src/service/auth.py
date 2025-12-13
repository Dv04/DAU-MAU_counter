"""Simple API key authentication dependency with alerting hooks."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import Header, HTTPException, Request, status

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# Alerting configuration from environment
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")
ALERT_WEBHOOK_URL = os.environ.get("ALERT_WEBHOOK_URL", "")


def _send_alert(event_type: str, details: dict[str, str]) -> None:
    """Send security alert via configured channels.

    Currently logs to stderr. Extend with email/webhook integration.
    """
    timestamp = datetime.now(UTC).isoformat()
    message = f"[SECURITY ALERT] {event_type} at {timestamp}: {details}"

    # Always log
    logger.warning(message)

    # TODO: Implement actual alerting when ADMIN_EMAIL is configured
    if ADMIN_EMAIL and not ADMIN_EMAIL.startswith("{{"):
        # Future: send email via SMTP or external service
        logger.info(f"Would send alert to {ADMIN_EMAIL}")

    # TODO: Implement webhook alerting when ALERT_WEBHOOK_URL is configured
    if ALERT_WEBHOOK_URL and not ALERT_WEBHOOK_URL.startswith("{{"):
        # Future: POST to webhook URL
        logger.info(f"Would send webhook to {ALERT_WEBHOOK_URL}")


async def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    config = request.app.state.config  # type: ignore[attr-defined]
    required_key = config.security.api_key
    if not required_key:
        return
    if x_api_key != required_key:
        # Log failed authentication attempt
        client_ip = request.client.host if request.client else "unknown"
        _send_alert(
            "UNAUTHORIZED_ACCESS_ATTEMPT",
            {
                "path": str(request.url.path),
                "client_ip": client_ip,
                "api_key_provided": "yes" if x_api_key else "no",
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "unauthorized",
                "hint": "Provide X-API-Key header with the configured SERVICE_API_KEY value.",
            },
            headers={"WWW-Authenticate": "API-Key"},
        )
