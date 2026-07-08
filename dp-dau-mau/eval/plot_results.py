
import json
import matplotlib.pyplot as plt
import csv
from pathlib import Path
import typer

app = typer.Typer()

@app.command()
def main(results: Path = typer.Option(Path("results_dense.json"), "--results", help="Results JSON file")):
    # Load Results
    p = results
    if not p.exists():
        print(f"File {p} not found.")
        return
        
    with p.open("r") as fp:
        data = json.load(fp)
        
    # Process Data
    epsilons = []
    dau_errors = []
    mau_errors = []
    
    # Aggregation: Group by epsilon, average error?
    # Our data has multiple entries per epsilon (seeds).
    # We should average or show scatter.
    # Grouping logic:
    from collections import defaultdict
    dau_map = defaultdict(list)
    mau_map = defaultdict(list)
    
    for entry in data:
        eps = entry["epsilon"]
        
        # DAU
        dau_res = entry["dau"]
        dau_est = dau_res["estimate"]
        dau_exact = dau_res["exact_value"]
        dau_err = abs(dau_est - dau_exact) / max(dau_exact, 1) * 100.0
        dau_map[eps].append(dau_err)
        
        # MAU
        mau_res = entry["mau"]
        mau_est = mau_res["estimate"]
        mau_exact = mau_res["exact_value"]
        mau_err = abs(mau_est - mau_exact) / max(mau_exact, 1) * 100.0
        mau_map[eps].append(mau_err)
        
    sorted_eps = sorted(dau_map.keys())
    
    dau_means = []
    dau_cis = [] # just simple std/2 for now or max/min?
    # User wanted "increase points".
    # Let's plot mean.
    
    import statistics
    
    mau_means = []
    
    for eps in sorted_eps:
        d_vals = dau_map[eps]
        m_vals = mau_map[eps]
        dau_means.append(statistics.mean(d_vals))
        mau_means.append(statistics.mean(m_vals))
        
    # Plot
    plt.figure(figsize=(10, 6))
    plt.grid(True, linestyle='--', alpha=0.7)
    
    plt.plot(sorted_eps, dau_means, marker='o', label='DAU Error', linewidth=2)
    plt.plot(sorted_eps, mau_means, marker='s', label='MAU Error', linewidth=2)
    
    plt.title("Relative Error vs. Privacy Budget (N=10,000)")
    plt.xlabel(r"Privacy Budget ($\epsilon$)")
    plt.ylabel("Relative Error (%)")
    plt.axhline(0.5, color='r', linestyle='--', label="Target Threshold (0.5%)")
    plt.legend()
    
    # Save to paper figs directory
    # Use absolute path to be safe
    out_path = Path("/Users/apple/DAU-MAU_counter/paper/figs/error_vs_epsilon_set.png")
    out_path.parent.mkdir(exist_ok=True, parents=True)
    plt.savefig(out_path, dpi=300)
    print(f"Saved plot to {out_path}")

if __name__ == "__main__":
    app()
