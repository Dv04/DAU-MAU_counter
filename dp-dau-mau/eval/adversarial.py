
import json
import random
import datetime as dt
from pathlib import Path
import sys
sys.path.append("src")
import typer
from dp_core import config as config_module
from dp_core.pipeline import PipelineManager, EventRecord

app = typer.Typer()

def generate_flipping_stream(n_users: int, flips_per_user: int, days: int) -> list[EventRecord]:
    """
    Generates a stream where each user flips status 'flips_per_user' times.
    """
    events = []
    base_date = dt.date(2023, 1, 1)
    
    for uid in range(n_users):
        # Distribute flips randomly across the timeline
        flip_days = sorted(random.sample(range(days), min(days, flips_per_user)))
        state = "+" # Start active
        
        # Initial add
        events.append(EventRecord(user_id=str(uid), op="+", day=base_date, metadata={}))
        
        for d_offset in flip_days:
            day = base_date + dt.timedelta(days=d_offset)
            state = "-" if state == "+" else "+"
            events.append(EventRecord(user_id=str(uid), op=state, day=day, metadata={}))
            
    # Sort by day for realistic ingestion
    events.sort(key=lambda e: e.day)
    return events

@app.command()
def main(
    flip_counts: list[int] = typer.Option([1, 10, 20, 50], help="Flip counts to sweep"),
    n_users: int = typer.Option(1000, help="Number of users"),
    epsilon: float = typer.Option(1.0, help="Privacy budget"),
    out: Path = typer.Option(Path("adversarial_results.json"), help="Output path"),
):
    results = []
    
    for f in flip_counts:
        print(f"Testing Flip Count F={f}...")
        events = generate_flipping_stream(n_users, f, 30)
        
        cfg = config_module.AppConfig.from_env()
        cfg.sketch.impl = "kmv"
        cfg.dp.epsilon_dau = epsilon
        cfg.dp.epsilon_mau = epsilon
        
        import shutil
        data_dir = cfg.storage.data_dir
        if data_dir.exists():
            shutil.rmtree(data_dir)
        
        pipeline = PipelineManager(config=cfg)
        pipeline.ingest_batch(events)
        
        # Calculate Ground Truth vs Estimate for Final Day
        last_day = dt.date(2023, 1, 30)
        
        # Ground Truth: Calculate manually
        # If F is even, user ends in initial state (Active). 
        # Actually it depends on the sequence.
        # My generator logic: Start "add". 
        # Flip 1: add -> del
        # Flip 2: del -> add
        # So if 'state' ended as 'add', user is active.
        # Actually calculating exact ground truth is tricky with random days.
        # Let's trust the 'state' variable tracking in the generator? 
        # No, generator builds a list.
        # Let's count explicitly.
        
        # Re-simulating ground truth
        user_states = {u: False for u in range(n_users)} # False=Inactive
        for e in events:
            if e.op == "+":
                user_states[int(e.user_id)] = True
            elif e.op == "-":
                 user_states[int(e.user_id)] = False
        
        true_val = sum(user_states.values())
        
        est_res = pipeline.get_mau_release(last_day)
        est = est_res["estimate"]
        error = abs(est - true_val) / max(true_val, 1)
        
        print(f"  True: {true_val}, Est: {est:.2f}, Err: {error:.4f}")
        
        results.append({
            "flips": f,
            "true_val": true_val,
            "est_val": est,
            "relative_error": error
        })
        
    with out.open("w") as fp:
        json.dump(results, fp, indent=2)

if __name__ == "__main__":
    app()
