"""Customize FastAPI OpenAPI metadata."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.routing import APIRoute


def apply(app: FastAPI) -> None:
    app.openapi_tags = [
        {"name": "metrics", "description": "Differentially private DAU and MAU endpoints."},
        {"name": "ingest", "description": "Stream ingestion and erasure APIs."},
    ]

    protected_routes = {
        ("/event", "POST"),
        ("/dau/{day}", "GET"),
        ("/mau", "GET"),
        ("/budget/{metric}", "GET"),
    }

    original_openapi = app.openapi

    def custom_openapi() -> dict[str, object]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = original_openapi()
        components = schema.setdefault("components", {})
        security_schemes = components.setdefault("securitySchemes", {})
        security_schemes["ApiKeyAuth"] = {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": (
                "Use value from {{SERVICE_API_KEY}} to authenticate protected endpoints."
            ),
        }
        for route in app.routes:
            if not isinstance(route, APIRoute):
                continue
            path = route.path
            for method in route.methods or []:
                verb = method.upper()
                if (path, verb) not in protected_routes:
                    continue
                operation = schema["paths"][path][method.lower()]
                operation.setdefault("security", [{"ApiKeyAuth": []}])
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[assignment]
