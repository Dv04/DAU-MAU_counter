"""Centralised configuration models leveraging Pydantic."""

from __future__ import annotations

import base64
import re
import secrets
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

PLACEHOLDER_PATTERN = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


def _as_path(value: str | Path) -> Path:
    return value if isinstance(value, Path) else Path(value).expanduser()


def _resolve_numeric(value: object, placeholder: str, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, str) and PLACEHOLDER_PATTERN.fullmatch(value.strip()):
        return default
    return float(value)


def _resolve_int(value: object, placeholder: str, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, str) and PLACEHOLDER_PATTERN.fullmatch(value.strip()):
        return default
    return int(value)


def _resolve_string(value: object, placeholder: str, default: str | None = None) -> str:
    if value is None:
        if default is not None:
            return default
        raise ValueError(f"{placeholder} must be provided")
    if isinstance(value, str) and PLACEHOLDER_PATTERN.fullmatch(value.strip()):
        if default is not None:
            return default
        raise ValueError(f"{placeholder} must be replaced with a concrete value")
    return str(value)


def _resolve_secret(value: object, placeholder: str) -> str:
    if value is None or (isinstance(value, str) and PLACEHOLDER_PATTERN.fullmatch(value.strip())):
        random_bytes = secrets.token_bytes(32)
        return "b64:" + base64.b64encode(random_bytes).decode("utf-8")
    return str(value)


class DPSettings(BaseModel):
    epsilon_dau: float = Field(default=0.3)
    epsilon_mau: float = Field(default=0.5)
    delta: float = Field(default=1e-6)
    w_bound: int = Field(default=2)
    dau_budget_total: float = Field(default=3.0)
    mau_budget_total: float = Field(default=3.5)
    default_seed: int = Field(default=20251009)

    @field_validator("epsilon_dau", mode="before")
    def _v_eps_dau(cls, v: object) -> float:
        return _resolve_numeric(v, "{{EPSILON_DAU}}", 0.3)

    @field_validator("epsilon_mau", mode="before")
    def _v_eps_mau(cls, v: object) -> float:
        return _resolve_numeric(v, "{{EPSILON_MAU}}", 0.5)

    @field_validator("delta", mode="before")
    def _v_delta(cls, v: object) -> float:
        return _resolve_numeric(v, "{{DELTA}}", 1e-6)

    @field_validator("w_bound", mode="before")
    def _v_w_bound(cls, v: object) -> int:
        return _resolve_int(v, "{{W_BOUND}}", 2)

    @field_validator("dau_budget_total", mode="before")
    def _v_dau_budget(cls, v: object) -> float:
        return _resolve_numeric(v, "{{DAU_BUDGET_TOTAL}}", 3.0)

    @field_validator("mau_budget_total", mode="before")
    def _v_mau_budget(cls, v: object) -> float:
        return _resolve_numeric(v, "{{MAU_BUDGET_TOTAL}}", 3.5)

    @field_validator("default_seed", mode="before")
    def _v_default_seed(cls, v: object) -> int:
        return _resolve_int(v, "{{DEFAULT_SEED}}", 20251009)


class SketchSettings(BaseModel):
    impl: str = Field(default="set")
    mau_window_days: int = Field(default=30)
    hll_rebuild_days_buffer: int = Field(default=3)

    @field_validator("impl", mode="before")
    def _v_impl(cls, v: object) -> str:
        value = _resolve_string(v, "{{SKETCH_IMPL}}", "set")
        if value not in {"set", "theta", "hllpp"}:
            raise ValueError("{{SKETCH_IMPL}} must be one of 'set', 'theta', 'hllpp'")
        return value

    @field_validator("mau_window_days", mode="before")
    def _v_window(cls, v: object) -> int:
        return _resolve_int(v, "{{MAU_WINDOW_DAYS}}", 30)

    @field_validator("hll_rebuild_days_buffer", mode="before")
    def _v_hll_buffer(cls, v: object) -> int:
        return _resolve_int(v, "{{HLL_REBUILD_DAYS_BUFFER}}", 3)


class StorageSettings(BaseModel):
    data_dir: Path = Field(default=Path("./data"))
    experiment_id: str = Field(default="baseline")
    example_dataset_path: Path = Field(default=Path("{{EXAMPLE_DATASET_PATH}}"))

    @field_validator("data_dir", mode="before")
    def _v_data_dir(cls, v: object) -> Path:
        value = _resolve_string(v, "{{DATA_DIR}}", "./data")
        return _as_path(value)

    @field_validator("experiment_id", mode="before")
    def _v_experiment(cls, v: object) -> str:
        return _resolve_string(v, "{{EXPERIMENT_ID}}", "baseline")

    @field_validator("example_dataset_path", mode="before")
    def _v_dataset(cls, v: object) -> Path:
        value = _resolve_string(v, "{{EXAMPLE_DATASET_PATH}}", "data/example.jsonl")
        return _as_path(value)


class SecuritySettings(BaseModel):
    hash_salt_secret: str = Field(default="{{HASH_SALT_SECRET}}")
    hash_salt_rotation_days: int = Field(default=30)
    api_key: str | None = Field(default=None)
    admin_email: str | None = Field(default="{{ADMIN_EMAIL}}")
    timezone: str = Field(default="{{TIMEZONE}}")

    @field_validator("hash_salt_secret", mode="before")
    def _v_secret(cls, v: object) -> str:
        return _resolve_secret(v, "{{HASH_SALT_SECRET}}")

    @field_validator("hash_salt_rotation_days", mode="before")
    def _v_rotation(cls, v: object) -> int:
        return _resolve_int(v, "{{HASH_SALT_ROTATION_DAYS}}", 30)

    @field_validator("api_key", mode="before")
    def _v_api_key(cls, v: object) -> str | None:
        if v is None:
            return None
        if isinstance(v, str) and PLACEHOLDER_PATTERN.fullmatch(v.strip()):
            return None
        return str(v)

    @field_validator("admin_email", mode="before")
    def _v_admin_email(cls, v: object) -> str | None:
        if v is None:
            return None
        if isinstance(v, str) and PLACEHOLDER_PATTERN.fullmatch(v.strip()):
            return None
        return str(v)

    @field_validator("timezone", mode="before")
    def _v_timezone(cls, v: object) -> str:
        return _resolve_string(v, "{{TIMEZONE}}", "UTC")


class ServiceSettings(BaseModel):
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    database_url: str | None = Field(default="{{SERVICE_DATABASE_URL}}")
    kafka_topic: str | None = Field(default="{{KAFKA_TOPIC}}")

    @field_validator("database_url", mode="before")
    def _v_db(cls, v: object) -> str | None:
        if v is None:
            return None
        if isinstance(v, str) and PLACEHOLDER_PATTERN.fullmatch(v.strip()):
            return None
        return str(v)

    @field_validator("kafka_topic", mode="before")
    def _v_kafka(cls, v: object) -> str | None:
        if v is None:
            return None
        if isinstance(v, str) and PLACEHOLDER_PATTERN.fullmatch(v.strip()):
            return None
        return str(v)


class AppConfig(BaseModel):
    dp: DPSettings = Field(default_factory=DPSettings)
    sketch: SketchSettings = Field(default_factory=SketchSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    service: ServiceSettings = Field(default_factory=ServiceSettings)

    @classmethod
    def from_env(cls) -> AppConfig:
        return cls()
