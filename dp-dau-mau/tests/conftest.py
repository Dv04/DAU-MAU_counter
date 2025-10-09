import base64
import os
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def configure_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("EXPERIMENT_ID", "test-exp")
    monkeypatch.setenv("HASH_SALT_SECRET", "b64:" + base64.b64encode(os.urandom(32)).decode())
    monkeypatch.setenv("HASH_SALT_ROTATION_DAYS", "30")
    monkeypatch.setenv("EPSILON_DAU", "0.3")
    monkeypatch.setenv("EPSILON_MAU", "0.5")
    monkeypatch.setenv("DELTA", "1e-6")
    monkeypatch.setenv("DEFAULT_SEED", "20251009")
    monkeypatch.setenv("MAU_WINDOW_DAYS", "30")
    monkeypatch.setenv("DAU_BUDGET_TOTAL", "3.0")
    monkeypatch.setenv("MAU_BUDGET_TOTAL", "3.5")
    monkeypatch.setenv("TIMEZONE", "UTC")
    yield
