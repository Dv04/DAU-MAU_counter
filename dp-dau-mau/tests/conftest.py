import base64
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


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
    monkeypatch.setenv("SERVICE_API_KEY", "test-key")
    monkeypatch.setenv("RDP_ORDERS", "2,4")
    monkeypatch.setenv("ADVANCED_DELTA", "1e-7")
    monkeypatch.setenv("SKETCH_IMPL", "kmv")
    monkeypatch.setenv("SKETCH_K", "512")
    monkeypatch.setenv("USE_BLOOM_FOR_DIFF", "true")
    monkeypatch.setenv("BLOOM_FP_RATE", "0.01")
    yield
