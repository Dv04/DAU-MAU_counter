"""Customize FastAPI OpenAPI metadata."""

from __future__ import annotations

from fastapi import FastAPI


def apply(app: FastAPI) -> None:
    app.openapi_tags = [
        {"name": "metrics", "description": "Differentially private DAU and MAU endpoints."},
        {"name": "ingest", "description": "Stream ingestion and erasure APIs."},
    ]
