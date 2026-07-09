"""Append-only binary log storage engine (fast ingest path).

Drop-in replacement for the SQLite `ledger.Ledger` as the per-day activity
event store. Ingest appends to per-day binary logs (buffered, no per-event
fsync) instead of doing one SQLite INSERT+commit per event -- which is the
change that lets ingest throughput approach the paper's claimed figure.
"""

from .log import ActivityEntry, AppendOnlyLog, ErasureEntry
from .manager import PartitionedLogManager

__all__ = [
    "ActivityEntry",
    "ErasureEntry",
    "AppendOnlyLog",
    "PartitionedLogManager",
]
