"""Pydantic models shared by the HTTP API."""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class EventModel(BaseModel):
    user_id: str = Field(..., description="External user identifier.")
    op: str = Field(..., pattern=r"^[\+\-]$", description="Turnstile operation '+' or '-'.")
    day: dt.date = Field(..., description="Day in YYYY-MM-DD using {{TIMEZONE}} timeline.")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("op")
    @classmethod
    def validate_op(cls, value: str) -> str:
        if value not in {"+", "-"}:
            raise ValueError("op must be '+' or '-'.")
        return value


class EventIngestionRequest(BaseModel):
    event: EventModel | None = None
    events: list[EventModel] | None = None

    @model_validator(mode="after")
    def ensure_payload(self) -> EventIngestionRequest:
        if self.event and self.events:
            raise ValueError("Provide either 'event' or 'events', not both.")
        if not self.event and not self.events:
            raise ValueError("Provide at least one event.")
        if self.event and not self.events:
            object.__setattr__(self, "events", [self.event])
            object.__setattr__(self, "event", None)
        return self


class BudgetSummary(BaseModel):
    epsilon_cap: float
    epsilon_spent: float
    epsilon_remaining: float
    delta: float
    best_rdp_epsilon: float | None = None
    best_rdp_order: float | None = None
    rdp_curve: dict[float, float] = Field(default_factory=dict)
    advanced_epsilon: float | None = None
    advanced_delta: float | None = None
    release_count: int = 0


class MetricResponse(BaseModel):
    day: str
    estimate: float
    lower_95: float
    upper_95: float
    epsilon_used: float
    delta: float
    mechanism: str
    sketch_impl: str
    budget_remaining: float
    budget: BudgetSummary
    version: str
    exact_value: float | None = None
    window_days: int | None = None


class BudgetResponse(BudgetSummary):
    metric: str
    period: str


class HealthResponse(BaseModel):
    status: str = "ok"
