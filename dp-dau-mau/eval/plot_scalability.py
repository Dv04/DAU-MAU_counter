#!/usr/bin/env python3
"""Generate Linear Scalability Plot for Paper."""

import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

# Data from benchmarks
users = [10_000, 100_000, 1_000_000]
ingest_times = [0.42, 4.60, 51.90]

# Create figure
fig, ax = plt.subplots(figsize=(8, 5))

# Plot actual data
ax.plot(users, ingest_times, 'o-', linewidth=2.5, markersize=10, 
        color='#2ecc71', label='Vectorized Engine (Ours)')

# Add theoretical O(N) reference line
theoretical = [users[0] * t / users[0] * (u / users[0]) for u, t in zip(users, [ingest_times[0]] * 3)]
# Perfect linear would be: time proportional to N
perfect_linear = [ingest_times[0] * (u / users[0]) for u in users]
ax.plot(users, perfect_linear, '--', linewidth=1.5, color='#95a5a6', 
        alpha=0.7, label='Ideal $O(N)$ Scaling')

# Formatting
ax.set_xscale('log')
ax.set_yscale('log')
ax.set_xlabel('Number of Users', fontsize=12)
ax.set_ylabel('Ingestion Time (seconds)', fontsize=12)
ax.set_title('Ingestion Scalability: Linear Performance to 1M Users', fontsize=14)

# Custom tick labels
ax.set_xticks(users)
ax.set_xticklabels(['10K', '100K', '1M'])

ax.grid(True, alpha=0.3, linestyle='--')
ax.legend(fontsize=11, loc='upper left')

# Annotate points
for u, t in zip(users, ingest_times):
    label = f'{t:.1f}s' if t >= 1 else f'{t*1000:.0f}ms'
    ax.annotate(label, (u, t), textcoords="offset points", 
                xytext=(0, 12), ha='center', fontsize=10, fontweight='bold')

plt.tight_layout()

# Save
out_path = Path("/Users/apple/DAU-MAU_counter/paper/figs/scalability_linear.png")
out_path.parent.mkdir(exist_ok=True, parents=True)
plt.savefig(out_path, dpi=300, bbox_inches='tight')
print(f"Saved plot to {out_path}")
