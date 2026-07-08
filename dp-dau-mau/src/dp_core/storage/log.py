"""Append-only binary log for activity and erasure tracking."""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterator

# Binary Format Specs
# Record Type: 1 byte (0=Activity, 1=Erasure)
# Activity Record:
#   - Day Len (1B) + Day (N)
#   - Op (1B)
#   - User Key (32B)
#   - User Root (32B)
#   - Meta Len (2B) + Meta (N)
# Erasure Record:
#   - User Root (32B)
#   - Days Len (2B) + Days JSON (N)

TYPE_ACTIVITY = 0
TYPE_ERASURE = 1

@dataclass(slots=True)
class ActivityEntry:
    day: str
    user_key: bytes
    user_root: bytes
    op: str
    metadata: str

@dataclass(slots=True)
class ErasureEntry:
    erasure_id: int | None # Derived from file offset
    user_root: bytes
    days: list[str]
    pending: bool # Always true in log

class AppendOnlyLog:
    def __init__(self, log_path: Path) -> None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self.path = log_path
        self._f = open(log_path, "ab")
    
    def append_activity(self, entry: ActivityEntry) -> None:
        # Encode fields
        day_bytes = entry.day.encode("utf-8")
        op_byte = entry.op.encode("utf-8")
        meta_bytes = entry.metadata.encode("utf-8")
        
        # Struct format: 
        # B (Type=0)
        # B (Day Len)
        # s (Day)
        # s (Op)
        # 32s (Key)
        # 32s (Root)
        # H (Meta Len)
        # s (Meta)
        
        # We construct binary block manually
        header = struct.pack(
            f"!BB{len(day_bytes)}sc32s32sH",
            TYPE_ACTIVITY,
            len(day_bytes),
            day_bytes,
            op_byte,
            entry.user_key,
            entry.user_root,
            len(meta_bytes)
        )
        self._f.write(header + meta_bytes)
        # We don't flush every write for speed, OS buffers handling it.
        # But for durability we might want flush on batch.
        
    def append_erasure(self, entry: ErasureEntry) -> int:
        days_json = json.dumps(entry.days).encode("utf-8")
        
        # Struct format:
        # B (Type=1)
        # 32s (Root)
        # H (Days Len)
        # s (Days Payload)
        
        header = struct.pack(
            f"!B32sH",
            TYPE_ERASURE,
            entry.user_root,
            len(days_json)
        )
        
        # Get offset as ID
        offset = self._f.tell()
        self._f.write(header + days_json)
        self._f.flush() # Erasures are rare and critical -> flush
        return offset

    def flush(self) -> None:
        self._f.flush()
        
    def close(self) -> None:
        self._f.close()

    def buffered_writer(self, buffer_size: int = 65536) -> _BufferedWriter:
        """Returns a context manager for buffered writing."""
        return self._BufferedWriter(self, buffer_size)
        
    class _BufferedWriter:
        def __init__(self, log: AppendOnlyLog, buffer_size: int):
            self.log = log
            self.buffer_size = buffer_size
            self.buffer = bytearray()
            
        def __enter__(self):
            return self
            
        def __exit__(self, exc_type, exc_val, exc_tb):
            self.flush()
            
        def append_activity(self, entry: ActivityEntry) -> None:
             # Fast path optimization: Re-implement packing locally to avoid function call overhead?
             # Or just call log._pack_activity?
             # Let's verify if manual alignment helps.
             # We reuse exact same logic as Log.append_activity but direct to buffer
             
             day_bytes = entry.day.encode("utf-8")
             op_byte = entry.op.encode("utf-8")
             meta_bytes = entry.metadata.encode("utf-8")
             
             # Header packing
             header = struct.pack(
                f"!BB{len(day_bytes)}sc32s32sH",
                TYPE_ACTIVITY,
                len(day_bytes),
                day_bytes,
                op_byte,
                entry.user_key,
                entry.user_root,
                len(meta_bytes)
             )
             self.buffer.extend(header)
             self.buffer.extend(meta_bytes)
             
             if len(self.buffer) >= self.buffer_size:
                 self.flush()
                 
        def flush(self):
            if self.buffer:
                self.log._f.write(self.buffer)
                self.buffer.clear()
        
    def replay(self) -> Iterator[ActivityEntry | ErasureEntry]:
        """Yields entries from the log."""
        if not self.path.exists():
            return
            
        with open(self.path, "rb") as f:
            while True:
                # Read Type
                type_byte = f.read(1)
                if not type_byte:
                    break
                rec_type = ord(type_byte)
                
                if rec_type == TYPE_ACTIVITY:
                    # Day Len
                    d_len = ord(f.read(1))
                    day = f.read(d_len).decode("utf-8")
                    op = f.read(1).decode("utf-8")
                    key = f.read(32)
                    root = f.read(32)
                    m_len_bytes = f.read(2)
                    m_len = struct.unpack("!H", m_len_bytes)[0]
                    meta = f.read(m_len).decode("utf-8")
                    
                    yield ActivityEntry(day, key, root, op, meta)
                    
                elif rec_type == TYPE_ERASURE:
                    # Current impl doesn't strictly need to return ID during replay
                    # since erasures are re-processed into state.
                    offset = f.tell() - 1 # Rough approx if needed
                    
                    root = f.read(32)
                    d_len_bytes = f.read(2)
                    d_len = struct.unpack("!H", d_len_bytes)[0]
                    days_json = f.read(d_len).decode("utf-8")
                    days = json.loads(days_json)
                    
                    yield ErasureEntry(offset, root, days, True)
                else:
                     raise ValueError(f"Unknown record type: {rec_type}")
