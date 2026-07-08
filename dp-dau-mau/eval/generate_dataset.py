import json
import random
import datetime as dt
from pathlib import Path
import typer

app = typer.Typer()

def generate_events(n_users: int, days: int, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    base_date = dt.date(2023, 1, 1)
    user_ids = list(range(n_users))
    
    print(f"Generating {days} days of events for {n_users} users to {out_path}...")
    
    with out_path.open("w") as fp:
        for day_offset in range(days):
            day = base_date + dt.timedelta(days=day_offset)
            day_str = day.isoformat()
            
            # 20% daily activity
            active_count = int(n_users * 0.2)
            active_users = random.sample(user_ids, active_count)
            
            for uid in active_users:
                record = {
                    "user_id": str(uid),
                    "op": "+",
                    "day": day_str,
                    "metadata": {}
                }
                fp.write(json.dumps(record) + "\n")
    print("Done.")

@app.command()
def main(
    n_users: int = 10000,
    days: int = 60,
    out: Path = Path("data/streams/eval_10k.jsonl")
):
    generate_events(n_users, days, out)

if __name__ == "__main__":
    app()
