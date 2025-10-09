import datetime as dt

from dp_core.config import AppConfig
from dp_core.pipeline import EventRecord, PipelineManager


def test_pipeline_ingest_and_release() -> None:
    config = AppConfig.from_env()
    pipeline = PipelineManager(config=config)
    day = dt.date(2025, 10, 1)
    events = [
        EventRecord(user_id="alice", op="+", day=day),
        EventRecord(user_id="bob", op="+", day=day),
        EventRecord(user_id="alice", op="-", day=day),
    ]
    pipeline.ingest_batch(events)
    dau = pipeline.get_daily_release(day)
    assert "estimate" in dau
    mau = pipeline.get_mau_release(day)
    assert mau["window_days"] >= 1
