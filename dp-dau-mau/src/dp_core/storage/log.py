"""Append-only binary log for activity and erasure records.

Binary record format (big-endian):

  Activity record:
    B    record type (0)
    B    day length (bytes)
    Ns   day (UTF-8, ISO date)
    c    op (b"+" or b"-")
    32s  user_key   (fixed 32 bytes; SHA-256 digest, right-padded if shorter)
    32s  user_root  (fixed 32 bytes)
    H    metadata length (bytes)
    Ns   metadata (UTF-8 JSON)

  Erasure record:
    B    record type (1)
    32s  user_root
    H    days-JSON length
    Ns   days JSON (UTF-8)

Writes are buffered by the underlying file object; callers that need a
subsequent read to observe recent writes must `flush()` first (the
PartitionedLogManager does this before every read).
"""

from __future__ import annotations

import json
import struct
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

TYPE_ACTIVITY = 0
TYPE_ERASURE = 1

_KEY_LEN = 32


def _fix32(b: bytes) -> bytes:
    """Coerce a key to exactly 32 bytes (SHA-256 digests already are)."""
    if len(b) == _KEY_LEN:
        return b
    if len(b) > _KEY_LEN:
        return b[:_KEY_LEN]
    return b + b"\x00" * (_KEY_LEN - len(b))


@dataclass(slots=True)
class ActivityEntry:
    day: str
    user_key: bytes
    user_root: bytes
    op: str
    metadata: str


@dataclass(slots=True)
class ErasureEntry:
    erasure_id: int | None  # derived from file offset on write
    user_root: bytes
    days: list[str]
    pending: bool


def _pack_activity(entry: ActivityEntry) -> bytes:
    day_bytes = entry.day.encode("utf-8")
    op_byte = entry.op.encode("utf-8")
    meta_bytes = entry.metadata.encode("utf-8")
    header = struct.pack(
        f"!BB{len(day_bytes)}sc32s32sH",
        TYPE_ACTIVITY,
        len(day_bytes),
        day_bytes,
        op_byte,
        _fix32(entry.user_key),
        _fix32(entry.user_root),
        len(meta_bytes),
    )
    return header + meta_bytes


class AppendOnlyLog:
    """A single append-only binary log file."""

    def __init__(self, log_path: Path) -> None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self.path = log_path
        self._f = open(log_path, "ab")

    def append_activity(self, entry: ActivityEntry) -> None:
        self._f.write(_pack_activity(entry))

    def append_erasure(self, entry: ErasureEntry) -> int:
        days_json = json.dumps(entry.days).encode("utf-8")
        offset = self._f.tell()
        header = struct.pack(
            "!B32sH",
            TYPE_ERASURE,
            _fix32(entry.user_root),
            len(days_json),
        )
        self._f.write(header + days_json)
        self._f.flush()  # erasures are rare and compliance-critical
        return offset

    def flush(self) -> None:
        self._f.flush()

    def close(self) -> None:
        if not self._f.closed:
            self._f.flush()
            self._f.close()

    def buffered_writer(self, buffer_size: int = 1 << 20) -> _BufferedWriter:
        return _BufferedWriter(self, buffer_size)

    def replay(self) -> Iterator[ActivityEntry | ErasureEntry]:
        if not self.path.exists():
            return
        with open(self.path, "rb") as f:
            while True:
                type_byte = f.read(1)
                if not type_byte:
                    break
                rec_type = type_byte[0]
                if rec_type == TYPE_ACTIVITY:
                    d_len = f.read(1)[0]
                    day = f.read(d_len).decode("utf-8")
                    op = f.read(1).decode("utf-8")
                    key = f.read(32)
                    root = f.read(32)
                    m_len = struct.unpack("!H", f.read(2))[0]
                    meta = f.read(m_len).decode("utf-8")
                    yield ActivityEntry(day=day, user_key=key, user_root=root, op=op, metadata=meta)
                elif rec_type == TYPE_ERASURE:
                    offset = f.tell() - 1
                    root = f.read(32)
                    d_len = struct.unpack("!H", f.read(2))[0]
                    days = json.loads(f.read(d_len).decode("utf-8"))
                    yield ErasureEntry(erasure_id=offset, user_root=root, days=days, pending=True)
                else:
                    raise ValueError(f"Unknown record type: {rec_type}")


class _BufferedWriter:
    """Accumulates encoded records in memory and flushes in large chunks.

    Used by batch ingest to amortize write() syscalls: at ~1MB flush
    granularity, a million-event batch does a few thousand writes instead
    of a million.
    """

    def __init__(self, log: AppendOnlyLog, buffer_size: int) -> None:
        self._log = log
        self._buffer_size = buffer_size
        self._buffer = bytearray()

    def __enter__(self) -> _BufferedWriter:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.flush()

    def append_activity(self, entry: ActivityEntry) -> None:
        self._buffer.extend(_pack_activity(entry))
        if len(self._buffer) >= self._buffer_size:
            self.flush()

    def flush(self) -> None:
        if self._buffer:
            self._log._f.write(self._buffer)
            self._buffer.clear()
        self._log._f.flush()
