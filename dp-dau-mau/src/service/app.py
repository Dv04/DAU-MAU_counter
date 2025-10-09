"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from dp_core.config import AppConfig
from dp_core.pipeline import PipelineManager

from . import openapi_overrides
from .routes import router


def create_app() -> FastAPI:
    config = AppConfig.from_env()
    app = FastAPI(
        title="DP-accurate DAU/MAU Counter",
        description="Proof-of-concept FastAPI service for differentially private DAU/MAU metrics.",
        version=config.storage.experiment_id,
        openapi_url="/openapi.json",
        contact={"name": "DP Duty", "email": config.security.admin_email or "{{ADMIN_EMAIL}}"},
    )
    app.state.config = config
    app.state.pipeline = PipelineManager(config=config)
    openapi_overrides.apply(app)
    app.include_router(router)
    return app


app = create_app()
