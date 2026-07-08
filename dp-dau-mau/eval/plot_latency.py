#!/usr/bin/env python3
"""Generate Query Latency vs Users Plot for Paper."""

import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

# Data from benchmarks
users = [10_000, 100_000, 1_000_000]
dau_latency = [0.77, 0.97, 2.41]  # ms
mau_latency = [7.40, 171.87, 202.52]  # ms

# Create figure
fig, ax = plt.subplots(figsize=(8, 5))

# Plot
ax.plot(users, dau_latency, 'o-', linewidth=2.5, markersize=10, 
        color='#3498db', label='DAU Query')
ax.plot(users, mau_latency, 's-', linewidth=2.5, markersize=10, 
        color='#e74c3c', label='MAU Query')

# Formatting
ax.set_xscale('log')
ax.set_yscale('log')
ax.set_xlabel('Number of Users', fontsize=12)
ax.set_ylabel('Query Latency (ms)', fontsize=12)
ax.set_title('Query Latency: Sub-Second Performance at Scale', fontsize=14)

# Custom tick labels
ax.set_xticks(users)
ax.set_xticklabels(['10K', '100K', '1M'])

# Add horizontal line for "interactive" threshold (1 second = 1000ms)
ax.axhline(1000, color='gray', linestyle='--', alpha=0.5, label='1s Interactive Threshold')

ax.grid(True, alpha=0.3, linestyle='--')
ax.legend(fontsize=11, loc='upper left')

# Annotate points
for u, d, m in zip(users, dau_latency, mau_latency):
    ax.annotate(f'{d:.1f}ms', (u, d), textcoords="offset points", 
                xytext=(0, 12), ha='center', fontsize=9, fontweight='bold', color='#3498db')
    ax.annotate(f'{m:.0f}ms', (u, m), textcoords="offset points", 
                xytext=(0, -18), ha='center', fontsize=9, fontweight='bold', color='#e74c3c')

plt.tight_layout()

# Save
out_path = Path("/Users/apple/DAU-MAU_counter/paper/figs/query_latency.png")
out_path.parent.mkdir(exist_ok=True, parents=True)
plt.savefig(out_path, dpi=300, bbox_inches='tight')
print(f"Saved plot to {out_path}")
