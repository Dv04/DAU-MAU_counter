import datetime as dt
import os

import hypothesis.strategies as st
from hypothesis import given, settings

from dp_core.pipeline import EventRecord, PipelineManager


def _event_strategy() -> st.SearchStrategy[tuple[str, str, int]]:
    ops = st.sampled_from(["+", "-"])
    users = st.sampled_from(["alice", "bob", "carol", "dave"])
    offsets = st.integers(min_value=0, max_value=4)
    return st.tuples(ops, users, offsets)


def _build_pipeline() -> PipelineManager:
    previous = os.environ.get("SKETCH_IMPL")
    os.environ["SKETCH_IMPL"] = "set"
    try:
        return PipelineManager()
    finally:
        if previous is None:
            os.environ.pop("SKETCH_IMPL", None)
        else:
            os.environ["SKETCH_IMPL"] = previous


@given(events=st.lists(_event_strategy(), min_size=1, max_size=25))
@settings(max_examples=50)
def test_deletions_do_not_increase_daily_count(events: list[tuple[str, str, int]]) -> None:
    pipeline = _build_pipeline()
    base_day = dt.date(2025, 1, 1)
    for op, user, offset in events:
        day = base_day + dt.timedelta(days=offset)
        day_str = day.isoformat()
        pipeline.replay_deletions()
        _, _, before_count = pipeline.window_manager.get_dau(day_str, pipeline.events_loader)
        pipeline.ingest_event(EventRecord(user_id=user, op=op, day=day, metadata={}))
        pipeline.replay_deletions()
        _, _, after_count = pipeline.window_manager.get_dau(day_str, pipeline.events_loader)
        if op == "+":
            assert after_count >= before_count
        else:
            assert after_count <= before_count


@given(events=st.lists(_event_strategy(), min_size=1, max_size=25))
@settings(max_examples=50)
def test_mau_estimate_exceeds_daily_counts(events: list[tuple[str, str, int]]) -> None:
    pipeline = _build_pipeline()
    base_day = dt.date(2025, 1, 1)
    for op, user, offset in events:
        day = base_day + dt.timedelta(days=offset)
        pipeline.ingest_event(EventRecord(user_id=user, op=op, day=day, metadata={}))
    pipeline.replay_deletions()
    day_counts = []
    for offset in range(5):
        day = base_day + dt.timedelta(days=offset)
        _, _, exact = pipeline.window_manager.get_dau(day.isoformat(), pipeline.events_loader)
        day_counts.append(exact)
    end_day = base_day + dt.timedelta(days=4)
    mau_estimate, _ = pipeline.window_manager.get_mau(
        end_day.isoformat(), 5, pipeline.events_loader
    )
    assert mau_estimate >= max(day_counts)
