"""Centralised configuration models leveraging Pydantic."""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
from pathlib import Path
from typing import cast

from pydantic import BaseModel, Field, field_validator

PLACEHOLDER_PATTERN = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


def _as_path(value: str | Path) -> Path:
    return value if isinstance(value, Path) else Path(value).expanduser()


def _resolve_numeric(value: object, placeholder: str, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, str) and PLACEHOLDER_PATTERN.fullmatch(value.strip()):
        return default
    if isinstance(value, (int, float, str)):
        return float(value)
    raise TypeError(f"{placeholder} must resolve to a numeric value")


def _resolve_int(value: object, placeholder: str, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, str) and PLACEHOLDER_PATTERN.fullmatch(value.strip()):
        return default
    if isinstance(value, (int, str)):
        return int(value)
    raise TypeError(f"{placeholder} must resolve to an integer value")


def _resolve_bool(value: object, placeholder: str, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip()
        if PLACEHOLDER_PATTERN.fullmatch(text):
            return default
        lowered = text.lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
        raise ValueError(f"{placeholder} must be a boolean string (true/false)")
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    raise ValueError(f"{placeholder} must resolve to a boolean value")


def _resolve_float_sequence(
    value: object,
    placeholder: str,
    default: tuple[float, ...],
) -> tuple[float, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip()
        if PLACEHOLDER_PATTERN.fullmatch(text):
            return default
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            items = [item.strip() for item in text.split(",") if item.strip()]
            try:
                return tuple(float(item) for item in items)
            except ValueError as convert_exc:  # pragma: no cover - defensive branch
                raise ValueError(
                    f"{placeholder} must be a JSON array or comma-separated list of numbers"
                ) from convert_exc
        else:
            if isinstance(parsed, list | tuple):
                try:
                    return tuple(float(cast(float | int | str, item)) for item in parsed)
                except ValueError as convert_exc:
                    raise ValueError(f"{placeholder} must contain numeric values") from convert_exc
            raise ValueError(
                f"{placeholder} must be a JSON array or comma-separated list of numbers"
            )
    if isinstance(value, list | tuple | set):
        try:
            return tuple(float(cast(float | int | str, item)) for item in value)
        except ValueError as exc:  # pragma: no cover - defensive branch
            raise ValueError(f"{placeholder} must contain numeric values") from exc
    raise TypeError(f"{placeholder} must be iterable of numeric values or a string")


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
    advanced_delta: float = Field(default=1e-7)
    w_bound: int = Field(default=2)
    dau_budget_total: float = Field(default=3.0)
    mau_budget_total: float = Field(default=3.5)
    default_seed: int = Field(default=20251009)
    rdp_orders: tuple[float, ...] = Field(default=(2.0, 4.0, 8.0, 16.0, 32.0))

    @field_validator("epsilon_dau", mode="before")
    def _v_eps_dau(cls, v: object) -> float:
        return _resolve_numeric(v, "{{EPSILON_DAU}}", 0.3)

    @field_validator("epsilon_mau", mode="before")
    def _v_eps_mau(cls, v: object) -> float:
        return _resolve_numeric(v, "{{EPSILON_MAU}}", 0.5)

    @field_validator("delta", mode="before")
    def _v_delta(cls, v: object) -> float:
        return _resolve_numeric(v, "{{DELTA}}", 1e-6)

    @field_validator("advanced_delta", mode="before")
    def _v_advanced_delta(cls, v: object) -> float:
        value = _resolve_numeric(v, "{{ADVANCED_DELTA}}", 1e-7)
        if value <= 0 or value >= 1:
            raise ValueError("{{ADVANCED_DELTA}} must satisfy 0 < delta < 1.")
        return value

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

    @field_validator("rdp_orders", mode="before")
    def _v_rdp_orders(cls, v: object) -> tuple[float, ...]:
        orders = _resolve_float_sequence(v, "{{RDP_ORDERS}}", (2.0, 4.0, 8.0, 16.0, 32.0))
        filtered = tuple(order for order in orders if order > 1.0)
        if not filtered:
            raise ValueError("{{RDP_ORDERS}} must contain at least one value greater than 1.")
        return filtered


class SketchSettings(BaseModel):
    impl: str = Field(default="kmv")
    mau_window_days: int = Field(default=30)
    hll_rebuild_days_buffer: int = Field(default=3)
    k: int = Field(default=4096)
    use_bloom_for_diff: bool = Field(default=True)
    bloom_fp_rate: float = Field(default=0.01)

    @field_validator("impl", mode="before")
    def _v_impl(cls, v: object) -> str:
        value = _resolve_string(v, "{{SKETCH_IMPL}}", "kmv")
        if value not in {"set", "theta", "kmv", "hllpp"}:
            raise ValueError("{{SKETCH_IMPL}} must be one of 'kmv', 'set', 'theta', 'hllpp'")
        return value

    @field_validator("mau_window_days", mode="before")
    def _v_window(cls, v: object) -> int:
        return _resolve_int(v, "{{MAU_WINDOW_DAYS}}", 30)

    @field_validator("hll_rebuild_days_buffer", mode="before")
    def _v_hll_buffer(cls, v: object) -> int:
        return _resolve_int(v, "{{HLL_REBUILD_DAYS_BUFFER}}", 3)

    @field_validator("k", mode="before")
    def _v_k(cls, v: object) -> int:
        value = _resolve_int(v, "{{SKETCH_K}}", 4096)
        if value <= 0:
            raise ValueError("{{SKETCH_K}} must be a positive integer")
        return value

    @field_validator("use_bloom_for_diff", mode="before")
    def _v_use_bloom(cls, v: object) -> bool:
        return _resolve_bool(v, "{{USE_BLOOM_FOR_DIFF}}", True)

    @field_validator("bloom_fp_rate", mode="before")
    def _v_bloom_rate(cls, v: object) -> float:
        rate = _resolve_numeric(v, "{{BLOOM_FP_RATE}}", 0.01)
        if not 0 < rate < 1:
            raise ValueError("{{BLOOM_FP_RATE}} must be between 0 and 1")
        return rate


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
    api_key: str | None = Field(default="{{SERVICE_API_KEY}}")
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
        env = os.environ
        dp_kwargs = {
            "epsilon_dau": env.get("EPSILON_DAU"),
            "epsilon_mau": env.get("EPSILON_MAU"),
            "delta": env.get("DELTA"),
            "advanced_delta": env.get("ADVANCED_DELTA"),
            "w_bound": env.get("W_BOUND"),
            "dau_budget_total": env.get("DAU_BUDGET_TOTAL"),
            "mau_budget_total": env.get("MAU_BUDGET_TOTAL"),
            "default_seed": env.get("DEFAULT_SEED"),
            "rdp_orders": env.get("RDP_ORDERS"),
        }
        sketch_kwargs = {
            "impl": env.get("SKETCH_IMPL"),
            "mau_window_days": env.get("MAU_WINDOW_DAYS"),
            "hll_rebuild_days_buffer": env.get("HLL_REBUILD_DAYS_BUFFER"),
            "k": env.get("SKETCH_K"),
            "use_bloom_for_diff": env.get("USE_BLOOM_FOR_DIFF"),
            "bloom_fp_rate": env.get("BLOOM_FP_RATE"),
        }
        storage_kwargs = {
            "data_dir": env.get("DATA_DIR"),
            "experiment_id": env.get("EXPERIMENT_ID"),
            "example_dataset_path": env.get("EXAMPLE_DATASET_PATH"),
        }
        security_kwargs = {
            "hash_salt_secret": env.get("HASH_SALT_SECRET"),
            "hash_salt_rotation_days": env.get("HASH_SALT_ROTATION_DAYS"),
            "api_key": env.get("SERVICE_API_KEY"),
            "admin_email": env.get("ADMIN_EMAIL"),
            "timezone": env.get("TIMEZONE"),
        }
        service_kwargs = {
            "host": env.get("SERVICE_HOST"),
            "port": env.get("SERVICE_PORT"),
            "database_url": env.get("SERVICE_DATABASE_URL"),
            "kafka_topic": env.get("KAFKA_TOPIC"),
        }
        payload: dict[str, object] = {}
        if any(value is not None for value in dp_kwargs.values()):
            payload["dp"] = {k: v for k, v in dp_kwargs.items() if v is not None}
        if any(value is not None for value in sketch_kwargs.values()):
            payload["sketch"] = {k: v for k, v in sketch_kwargs.items() if v is not None}
        if any(value is not None for value in storage_kwargs.values()):
            payload["storage"] = {k: v for k, v in storage_kwargs.items() if v is not None}
        if any(value is not None for value in security_kwargs.values()):
            payload["security"] = {k: v for k, v in security_kwargs.items() if v is not None}
        if any(value is not None for value in service_kwargs.values()):
            payload["service"] = {k: v for k, v in service_kwargs.items() if v is not None}
        return cls(**payload)
