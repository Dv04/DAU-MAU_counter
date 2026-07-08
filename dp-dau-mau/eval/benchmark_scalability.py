
import resource
import time
import json
from pathlib import Path
import sys
sys.path.append("src")
import typer
from dp_core import config as config_module
from dp_core.pipeline import PipelineManager, EventRecord
# import removed 
# Assuming generate_synthetic_data logic is available or can be invoked. 
# Attempting to import internal generation logic:
# Removed invalid import

app = typer.Typer()

def get_peak_rss_mb() -> float:
    # ru_maxrss is in kilobytes on Linux, bytes on Mac. 
    # The user is on Mac (OS: mac in user_information).
    # On Mac, getrusage returns bytes. Wait, Python documentation says:
    # "on MacOS ... expressed in bytes."
    # Let's assume bytes for Mac.
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return usage / (1024 * 1024)

# Re-implementing simple generator to avoid CLI import complexity
import random
import datetime as dt
def generate_batch(n_users: int, days: int) -> list[EventRecord]:
    events = []
    base_date = dt.date(2023, 1, 1)
    user_ids = list(range(n_users))
    
    # 20% daily activity
    for day_offset in range(days):
        day = base_date + dt.timedelta(days=day_offset)
        # Vectorized-like generation for speed
        active_count = int(n_users * 0.2)
        active_users = random.sample(user_ids, active_count)
        for uid in active_users:
            events.append(EventRecord(
                user_id=str(uid),
                op="+",
                day=day,
                metadata={}
            ))
    return events

@app.command()
def main(
    user_counts: list[int] = typer.Option([10000, 100000], help="User counts to sweep"),
    sketch: str = typer.Option("roaring", help="Sketch implementation"),
    out: Path = typer.Option(Path("benchmark_results.json"), help="Output path"),
):
    results = []
    
    for n in user_counts:
        print(f"Benchmarking N={n} sketch={sketch}...")
        
        # 1. Generate Data (Time it)
        t0 = time.time()
        events = generate_batch(n, 30)
        gen_time = time.time() - t0
        print(f"  Generation: {gen_time:.2f}s")
        
        # 2. Ingest (Time + Memory)
        cfg = config_module.AppConfig.from_env()
        cfg.sketch.impl = sketch
        
        # Cleanup previous data for clean benchmark
        import shutil
        data_dir = cfg.storage.data_dir
        if data_dir.exists():
            shutil.rmtree(data_dir)
            
        pipeline = PipelineManager(config=cfg)
        
        t0 = time.time()
        pipeline.ingest_batch(events)
        ingest_time = time.time() - t0
        peak_mem = get_peak_rss_mb()
        print(f"  Ingest: {ingest_time:.2f}s, Mem: {peak_mem:.2f} MB")
        
        # 3. Query Latency
        t0 = time.time()
        _ = pipeline.get_daily_release(dt.date(2023, 1, 30))
        dau_latency = (time.time() - t0) * 1000 # ms
        
        t0 = time.time()
        _ = pipeline.get_mau_release(dt.date(2023, 1, 30))
        mau_latency = (time.time() - t0) * 1000 # ms
        print(f"  DAU: {dau_latency:.2f}ms, MAU: {mau_latency:.2f}ms")
        
        results.append({
            "users": n,
            "ingest_time_sec": ingest_time,
            "peak_rss_mb": peak_mem,
            "dau_latency_ms": dau_latency,
            "mau_latency_ms": mau_latency
        })
        
        # Cleanup to try and free memory (Python GC depends though)
        del pipeline
        del events
        
    with out.open("w") as fp:
        json.dump(results, fp, indent=2)

if __name__ == "__main__":
    app()
